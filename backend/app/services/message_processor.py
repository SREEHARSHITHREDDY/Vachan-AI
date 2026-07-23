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
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import Commitment, Message
from app.schemas.api import CommitmentOut, MessageProcessResult
from app.schemas.lifecycle import OpenCommitmentSummary
from app.services.extraction_service import ExtractionService
from app.services.lifecycle_service import LifecycleTracker, check_deadline_proximity


def _get_demo_user_id(db: Session) -> str:
    """
    Demo scope has no auth (per the API Design doc's Stage 4 scoping —
    auth is a later-stage concern). All messages/commitments belong to a
    single fixed demo user, auto-created on first use.
    """
    from app.models.db_models import User

    user = db.query(User).filter_by(email="demo@vachanai.local").first()
    if user is None:
        user = User(email="demo@vachanai.local", persona_mode="student")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.user_id


def process_incoming_message(
    db: Session, body: str, channel: str = "message"
) -> MessageProcessResult:
    """
    The full closed loop, run for real against the database for the first
    time: save the message, check if it resolves any open commitment,
    check if it contains a new commitment, persist whichever apply.

    channel: "message" (typed text/email), "call", or "in-person" — see
    MessageIn's docstring (schemas/api.py) for why this distinction exists
    and what it does/doesn't change about how the pipeline processes it.
    """
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id,
        channel=channel,
        direction="outbound",
        body_ref=body,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    result = MessageProcessResult()

    # Step 1: does this message resolve any currently open commitment?
    open_commitments = (
        db.query(Commitment)
        .filter(
            Commitment.user_id == user_id,
            Commitment.state.in_(["pending", "at-risk"]),
            Commitment.is_deleted.is_(False),
        )
        .all()
    )

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
            matched.resolved_at = datetime.now(timezone.utc)
            db.commit()
            result.resolved_commitment_id = matched.commitment_id
            result.resolution_reasoning = resolution.reasoning

    # Step 2: does this message itself contain a new commitment?
    settings = get_settings()
    if settings.groq_api_key:  # skip gracefully if no key configured yet
        extractor = ExtractionService()
        extraction = extractor.extract(body)

        if extraction.is_commitment:
            new_commitment = Commitment(
                user_id=user_id,
                source_message_id=message.message_id,
                commitment_type=extraction.commitment_type.value
                if hasattr(extraction.commitment_type, "value")
                else extraction.commitment_type,
                description=extraction.description,
                inferred_deadline=extraction.inferred_deadline,
                state="pending",
            )
            db.add(new_commitment)
            db.commit()
            db.refresh(new_commitment)
            result.new_commitment = CommitmentOut.model_validate(new_commitment)
            # channel lives on Message, not Commitment (see CommitmentOut's
            # docstring) — set it here since we already know it, rather
            # than requiring the caller to look it up again.
            result.new_commitment.channel = channel

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
