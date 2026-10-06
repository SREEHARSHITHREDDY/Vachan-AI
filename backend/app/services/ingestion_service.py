"""
Ingestion service — takes messages read by a connector and runs each one
through the same closed loop as a manually typed message
(process_incoming_message: resolution check against open commitments, then
new-commitment extraction), plus the extra work that only matters for bulk
history:

  * de-duplication  — re-running a sync/import never double-processes
  * chronological order — oldest first, so "I'll send it Friday" is already
    an open commitment by the time "Sent it!" arrives and can resolve it
  * contact linking — the other party becomes (or matches) a Contact, and
    the commitment inherits it
  * cost/safety limits — a cap on messages per run, a cheap filter for
    one-or-two-word replies, and an early abort if the LLM keeps failing
    (e.g. a revoked/rate-limited key) instead of burning through the batch

Stateless function-style service, same as message_processor.py.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db_models import Contact, Message
from app.schemas.connectors import IngestItem, IngestSummary
from app.services.connectors.types import ParsedMessage
from app.services.message_processor import process_incoming_message

MIN_WORDS = 3  # "ok", "thanks bro", "see you" carry no trackable promise
CONSECUTIVE_ERROR_LIMIT = 3
_IN_CHUNK = 500  # keeps IN (...) lists well under SQLite's variable limit


def _already_ingested(db: Session, user_id: str, external_ids: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(external_ids), _IN_CHUNK):
        chunk = external_ids[i : i + _IN_CHUNK]
        rows = (
            db.query(Message.external_id)
            .filter(Message.user_id == user_id, Message.external_id.in_(chunk))
            .all()
        )
        found.update(r[0] for r in rows)
    return found


def _resolve_contact(
    db: Session, user_id: str, msg: ParsedMessage, cache: dict, summary: IngestSummary
) -> Contact | None:
    name, handle = msg.counterparty_name, (msg.counterparty_handle or None)
    if not name and not handle:
        return None
    key = (handle or name).lower()
    if key in cache:
        return cache[key]

    base = db.query(Contact).filter(Contact.user_id == user_id, Contact.is_deleted.is_(False))
    contact = None
    if handle:
        contact = base.filter(func.lower(Contact.email_or_handle) == handle.lower()).first()
    if contact is None and name:
        contact = base.filter(func.lower(Contact.name) == name.lower()).first()
    if contact is None:
        contact = Contact(
            user_id=user_id,
            name=name or handle,
            email_or_handle=handle or f"{msg.channel}:{name}",
            role_tag="other",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        summary.contacts_created += 1

    cache[key] = contact
    return contact


def ingest_messages(
    db: Session,
    user_id: str,
    messages: list[ParsedMessage],
    channel: str,
    max_messages: int | None = None,
) -> IngestSummary:
    summary = IngestSummary(channel=channel, fetched=len(messages))

    messages = sorted(messages, key=lambda m: m.sent_at)
    seen = _already_ingested(db, user_id, [m.external_id for m in messages])
    fresh = [m for m in messages if m.external_id not in seen]
    summary.already_imported = len(messages) - len(fresh)

    # Cap AFTER de-duplication and keep the most recent ones: repeated runs
    # then walk further back in time instead of re-picking the same tail.
    if max_messages is not None:
        fresh = fresh[-max_messages:]

    contact_cache: dict = {}
    consecutive_errors = 0

    for msg in fresh:
        if len(msg.body.split()) < MIN_WORDS:
            summary.skipped_trivial += 1
            continue
        try:
            contact = _resolve_contact(db, user_id, msg, contact_cache, summary)
            result = process_incoming_message(
                db,
                msg.body,
                user_id,
                msg.channel,
                contact_id=contact.contact_id if contact else None,
                sent_at=msg.sent_at,
                external_id=msg.external_id,
            )
        except Exception as exc:
            db.rollback()
            consecutive_errors += 1
            # Class name + a short slice only — never the message body.
            summary.errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            if consecutive_errors >= CONSECUTIVE_ERROR_LIMIT:
                summary.aborted = True
                break
            continue

        consecutive_errors = 0
        summary.processed += 1
        if result.new_commitment:
            summary.commitments_created += 1
        if result.resolved_commitment_id:
            summary.commitments_resolved += 1
        if result.new_commitment or result.resolved_commitment_id:
            summary.items.append(
                IngestItem(
                    sent_at=msg.sent_at.isoformat(),
                    contact_name=contact.name if contact else None,
                    preview=" ".join(msg.body.split())[:100],
                    new_commitment=result.new_commitment.description if result.new_commitment else None,
                    resolved_commitment_id=result.resolved_commitment_id,
                    resolution_reasoning=result.resolution_reasoning,
                )
            )

    return summary
