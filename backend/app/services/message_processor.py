"""
Message Processor — the orchestration layer that ties together Extraction
Service, Lifecycle Tracker, and the database. This is the piece that was
missing before Stage 4: Stages 1-2 proved the mechanisms work in isolation
(via mocked tests); this module is where they actually run against real
persisted state for the first time.

Deliberately a plain function-based service, not a class with lots of
state — per Reconciliation Addendum Item 24 (avoid over-building solo-dev
infrastructure), a stateless orchestration function is all this needs to
be at demo scale.

Per-user isolation update: process_incoming_message and
refresh_deadline_states now REQUIRE a user_id argument rather than
resolving one internally — the real, authenticated user (from the JWT,
via app.core.deps.get_current_user_id) now flows in from the router layer
instead. _get_demo_user_id is kept below, unchanged, purely as a test
fixture helper (existing tests create setup data against it directly) —
it is no longer called anywhere in the actual request-handling path.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import Commitment, Message
from app.schemas.api import CommitmentOut, MessageProcessResult
from app.schemas.lifecycle import OpenCommitmentSummary
from app.services.extraction_service import ExtractionService
from app.services.lifecycle_service import LifecycleTracker, check_deadline_proximity


def _get_demo_user_id(db: Session) -> str:
    """
    TEST/FIXTURE HELPER ONLY as of the auth refactor — no longer called
    by the actual request-handling path (see module docstring). Kept
    because every existing test creates its setup rows (messages,
    commitments, contacts) against this fixed demo user, and rewriting
    all of them to sign up/log in a real account just to attach test
    fixtures would be pure churn with no real benefit.
    """
    from app.models.db_models import User

    user = db.query(User).filter_by(email="demo@vachanai.local").first()
    if user is None:
        user = User(email="demo@vachanai.local", persona_mode="student")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.user_id


def _already_tracked(
    db: Session,
    user_id: str,
    contact_id: str | None,
    deadline: datetime | None,
    external_id: str | None,
) -> bool:
    """
    True if this user already has an OPEN commitment with the same person at
    the same date and time. In a conversation both sides usually mention the
    same meeting ("4:30 on the 7th?" / "Sure, 4:30 then"), and it must be one
    entry, not two. Only applies to connector-ingested messages and only when
    the person and a concrete time are both known, so manual entries and
    vague promises are never silently swallowed.
    """
    if external_id is None or contact_id is None or deadline is None:
        return False
    return (
        db.query(Commitment.commitment_id)
        .filter(
            Commitment.user_id == user_id,
            Commitment.contact_id == contact_id,
            Commitment.inferred_deadline == deadline,
            Commitment.state.in_(["pending", "at-risk"]),
            Commitment.is_deleted.is_(False),
        )
        .first()
        is not None
    )


def process_incoming_message(
    db: Session,
    body: str,
    user_id: str,
    channel: str = "message",
    *,
    contact_id: str | None = None,
    sent_at: datetime | None = None,
    external_id: str | None = None,
    direction: str = "outbound",
    context: str | None = None,
    utc_offset_minutes: int = 0,
) -> MessageProcessResult:
    """
    The full closed loop, run for real against the database: save the
    message, check if it resolves any open commitment, check if it
    contains a new commitment, persist whichever apply.

    user_id is now always the real authenticated user (passed in by the
    router from the JWT), not resolved internally — see module docstring.

    channel: "message" (typed text/email), "call", or "in-person" — see
    MessageIn's docstring (schemas/api.py) for why this distinction exists
    and what it does/doesn't change about how the pipeline processes it.
    Connectors add "gmail" and "whatsapp".

    Keyword-only extras, all used by the connector ingestion path
    (app/services/ingestion_service.py) and all defaulting to the old
    behaviour so manual submissions are unchanged:
      contact_id   — links the stored message AND any new commitment to a
                     contact (the manual path leaves this to the user).
      sent_at      — the message's real timestamp. Also passed to the
                     extractor so "by Friday" resolves against when the
                     message was written, not when it was imported.
      external_id  — source-side identifier used for de-duplication. If
                     processing fails for a message that has one, the
                     stored row is removed again so a later re-sync can
                     retry it instead of treating it as already done.
      direction    — "outbound" (the user wrote it) or "inbound" (the
                     other person did). Inbound messages can only fulfil,
                     and only create, promises made TO the user.
      context      — conversation text built by the ingestion service so a
                     reply like "Sure" is read against the message it
                     answers (see extraction_service.build_conversation_context).
      utc_offset_minutes — the user's offset from UTC, so the extractor
                     can be told the message's LOCAL send time.

    For connector-ingested messages (those with an external_id) resolution
    is also scoped: only open commitments with the same contact (or no
    contact yet) are considered, and only of the matching kind — so
    Priya's "done!" can never close a promise made to Rahul, and the
    user's own "sent it" can never close something Rahul promised them.
    """
    event_time = sent_at or datetime.now(timezone.utc)
    message = Message(
        user_id=user_id,
        contact_id=contact_id,
        channel=channel,
        direction=direction,
        body_ref=body,
        sent_at=event_time,
        external_id=external_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    result = MessageProcessResult()

    try:
        open_commitments = (
            db.query(Commitment)
            .filter(
                Commitment.user_id == user_id,
                Commitment.state.in_(["pending", "at-risk"]),
                Commitment.is_deleted.is_(False),
            )
            .all()
        )

        if external_id is not None:
            if contact_id is not None:
                open_commitments = [
                    c for c in open_commitments if c.contact_id in (None, contact_id)
                ]
            if direction == "inbound":
                open_commitments = [c for c in open_commitments if c.commitment_type == "made-to-me"]
            else:
                open_commitments = [c for c in open_commitments if c.commitment_type != "made-to-me"]

        if open_commitments:
            summaries = [
                OpenCommitmentSummary(
                    commitment_id=c.commitment_id, description=c.description
                )
                for c in open_commitments
            ]
            tracker = LifecycleTracker()
            resolution = tracker.check_for_resolution(body, summaries)

            if resolution.resolved and resolution.resolved_commitment_id:
                matched = next(
                    c for c in open_commitments
                    if c.commitment_id == str(resolution.resolved_commitment_id)
                )
                matched.state = "fulfilled"
                matched.resolved_at = event_time
                db.commit()
                result.resolved_commitment_id = matched.commitment_id
                result.resolution_reasoning = resolution.reasoning

        settings = get_settings()
        if settings.groq_api_key:
            extractor = ExtractionService()
            extra = {}
            if sent_at is not None:
                local_time = (
                    sent_at.astimezone(timezone.utc) if sent_at.tzinfo else sent_at
                ).replace(tzinfo=None) + timedelta(minutes=utc_offset_minutes)
                extra["reference_time"] = local_time
            if context:
                extra["context"] = context
            extraction = extractor.extract(body, **extra)

            ctype = (
                extraction.commitment_type.value
                if hasattr(extraction.commitment_type, "value")
                else extraction.commitment_type
            )
            # Someone else's message can only create a promise made TO the
            # user; a proposal/request they haven't been answered on is
            # not a commitment yet (the user's later "Sure" creates it).
            ignore_inbound = external_id is not None and direction == "inbound" and ctype != "made-to-me"

            if extraction.is_commitment and not ignore_inbound:
                if _already_tracked(db, user_id, contact_id, extraction.inferred_deadline, external_id):
                    result.duplicate_skipped = True
                else:
                    new_commitment = Commitment(
                        user_id=user_id,
                        contact_id=contact_id,
                        source_message_id=message.message_id,
                        commitment_type=ctype,
                        description=extraction.description,
                        starts_at=extraction.inferred_start,
                        inferred_deadline=extraction.inferred_deadline,
                        state="pending",
                    )
                    db.add(new_commitment)
                    db.commit()
                    db.refresh(new_commitment)
                    result.new_commitment = CommitmentOut.model_validate(new_commitment)
                    result.new_commitment.channel = channel

    except Exception:
        # Connector-ingested message: undo the stored row so the next
        # sync retries it (otherwise its external_id would mark it as
        # already processed even though the LLM step never completed).
        # Manual submissions keep the old behaviour (row stays, error
        # propagates).
        if external_id is not None:
            db.rollback()
            db.delete(message)
            db.commit()
        raise

    return result


def refresh_deadline_states(db: Session, user_id: str) -> None:
    """
    Opportunistic deadline-proximity refresh — called before reads
    (list/digest endpoints) rather than on a background schedule, since
    there's no task queue at demo scale (Reconciliation Addendum Item 14:
    load/background infra is explicitly deferred).

    Only auto-UPGRADES pending -> at-risk based on deadline proximity.
    Deliberately never auto-downgrades at-risk -> pending: that would
    silently undo a manual "mark at-risk" override (a user can flag
    something at-risk even with >24h left — see CommitmentUpdate), and
    there's no real product reason to auto-un-flag something a human
    already decided needed attention. Moving back to pending is only
    ever an explicit user action.
    """
    open_commitments = (
        db.query(Commitment)
        .filter(
            Commitment.user_id == user_id,
            Commitment.state.in_(["pending", "at-risk"]),
            Commitment.is_deleted.is_(False),
        )
        .all()
    )
    for c in open_commitments:
        check = check_deadline_proximity(c.commitment_id, c.inferred_deadline)
        if c.state == "pending" and check.new_state.value == "at-risk":
            c.state = "at-risk"
    db.commit()
