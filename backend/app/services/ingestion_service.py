"""
Ingestion service — takes messages read by a connector and runs each one
through the same closed loop as a manually typed message
(process_incoming_message: resolution check against open commitments, then
new-commitment extraction), plus the extra work that only matters for real
conversations:

  * conversation context — every message is analysed together with the few
    messages before it in the SAME chat, so "Sure, see you then" becomes
    "Meet Rahul at 4:30 PM on 7 Oct" instead of being a contextless "sure"
  * per-person attribution — each message is tied to the person it is with;
    that person becomes (or matches) a Contact and the commitment is linked
    to them, so everything is segregated by person
  * both directions — what the user promised AND what others promised the
    user; an inbound message can only fulfil promises made TO the user
  * "waiting for your reply" — chats whose last message is a question or
    request from the other person (deterministic, no LLM)
  * de-duplication, chronological order, per-run cap, trivial-reply filter,
    and an early abort if the LLM keeps failing

Stateless function-style service, same as message_processor.py.
"""

import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db_models import Contact, Message
from app.schemas.connectors import AwaitingReply, IngestItem, IngestSummary, PersonBreakdown
from app.services.connectors.types import ParsedMessage
from app.services.extraction_service import build_conversation_context
from app.services.message_processor import process_incoming_message

MIN_WORDS = 3  # "ok", "thanks bro", "see you" carry no trackable promise
CONSECUTIVE_ERROR_LIMIT = 3
CONTEXT_MESSAGES = 6  # earlier messages of the same chat shown to the LLM
CONTEXT_CHARS = 300  # per earlier message
MAX_AWAITING = 10
_IN_CHUNK = 500  # keeps IN (...) lists well under SQLite's variable limit

# A last message from the other person counts as "waiting on you" if it asks
# something or makes a request. Deliberately simple and transparent.
_REQUEST_RE = re.compile(
    r"\?|\b(please|pls|can you|could you|would you|will you|let me know|get back|"
    r"remind me|reply|respond|call me|confirm|send me|share)\b",
    re.IGNORECASE,
)


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
    db: Session, user_id: str, name: str | None, handle: str | None, channel: str,
    cache: dict, summary: IngestSummary,
) -> Contact | None:
    """
    Finds the user's Contact for this person, creating one if needed.
    Match order: email/handle → exact name → unique first-name match
    ("Rahul" finds "Rahul Sharma"). A first name shared by two contacts is
    NOT guessed — a new contact is made instead of picking the wrong one.
    """
    handle = (handle or None)
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
    if contact is None and name:
        first = name.split()[0].lower()
        same_first = [c for c in base.all() if c.name.split()[0].lower() == first]
        if len(same_first) == 1:
            contact = same_first[0]
    if contact is None:
        contact = Contact(
            user_id=user_id,
            name=name or handle,
            email_or_handle=handle or f"{channel}:{name}",
            role_tag="other",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        summary.contacts_created += 1

    cache[key] = contact
    return contact


def _local(msg: ParsedMessage, offset_minutes: int):
    """The user's local clock time as a NAIVE datetime. Naive on purpose: the
    browser reads a zone-less ISO string as local time, whereas a UTC-tagged
    one would be shifted a second time when displayed."""
    return (msg.sent_at + timedelta(minutes=offset_minutes)).replace(tzinfo=None)


def _history_lines(history: list[ParsedMessage], offset_minutes: int) -> list[str]:
    lines = []
    for m in history:
        who = "You" if m.direction == "outbound" else (m.sender_name or m.counterparty_name or "Them")
        stamp = _local(m, offset_minutes).strftime("%d %b %H:%M")
        text = " ".join(m.body.split())[:CONTEXT_CHARS]
        lines.append(f"{who} ({stamp}): {text}")
    return lines


def _awaiting_reply(all_msgs: list[ParsedMessage], offset_minutes: int) -> list[AwaitingReply]:
    threads: dict[str, list[ParsedMessage]] = defaultdict(list)
    for m in all_msgs:
        threads[m.thread_key or "_"].append(m)
    waiting = []
    for msgs in threads.values():
        last = msgs[-1]
        if (
            last.direction == "inbound"
            and len(last.body.split()) >= MIN_WORDS
            and _REQUEST_RE.search(last.body)
        ):
            waiting.append((last, last.sender_name or last.counterparty_name or "Someone"))
    waiting.sort(key=lambda w: w[0].sent_at, reverse=True)
    return [
        AwaitingReply(
            contact_name=name,
            preview=" ".join(m.body.split())[:140],
            sent_at=_local(m, offset_minutes).isoformat(),
        )
        for m, name in waiting[:MAX_AWAITING]
    ]


def ingest_messages(
    db: Session,
    user_id: str,
    messages: list[ParsedMessage],
    channel: str,
    max_messages: int | None = None,
    include_incoming: bool = False,
    utc_offset_minutes: int = 0,
) -> IngestSummary:
    summary = IngestSummary(channel=channel, fetched=len(messages))

    all_msgs = sorted(messages, key=lambda m: m.sent_at)

    # Per-chat history for context — built from EVERYTHING that was read,
    # including messages that are not themselves analysed or stored.
    histories: dict[str, list[ParsedMessage]] = defaultdict(list)
    position: dict[int, int] = {}
    for m in all_msgs:
        h = histories[m.thread_key or "_"]
        position[id(m)] = len(h)
        h.append(m)

    candidates = [m for m in all_msgs if m.direction == "outbound" or include_incoming]
    seen = _already_ingested(db, user_id, [m.external_id for m in candidates])
    fresh = [m for m in candidates if m.external_id not in seen]
    summary.already_imported = len(candidates) - len(fresh)

    # Cap AFTER de-duplication and keep the most recent ones: repeated runs
    # then walk further back in time instead of re-picking the same tail.
    if max_messages is not None:
        fresh = fresh[-max_messages:]

    contact_cache: dict = {}
    people: dict[str, PersonBreakdown] = {}
    consecutive_errors = 0

    for msg in fresh:
        if len(msg.body.split()) < MIN_WORDS:
            summary.skipped_trivial += 1
            continue
        try:
            contact = _resolve_contact(
                db, user_id, msg.counterparty_name, msg.counterparty_handle, msg.channel,
                contact_cache, summary,
            )
            thread = histories[msg.thread_key or "_"]
            idx = position[id(msg)]
            earlier = thread[max(0, idx - CONTEXT_MESSAGES) : idx]
            context = build_conversation_context(
                _history_lines(earlier, utc_offset_minutes),
                author=None if msg.direction == "outbound" else (msg.sender_name or msg.counterparty_name),
                counterparty=contact.name if contact else msg.counterparty_name,
            )
            result = process_incoming_message(
                db,
                msg.body,
                user_id,
                msg.channel,
                contact_id=contact.contact_id if contact else None,
                sent_at=msg.sent_at,
                external_id=msg.external_id,
                direction=msg.direction,
                context=context,
                utc_offset_minutes=utc_offset_minutes,
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
        if msg.direction == "inbound":
            summary.incoming_processed += 1
        if result.duplicate_skipped:
            summary.duplicates_skipped += 1

        person_name = contact.name if contact else "Unassigned"
        person = people.setdefault(person_name, PersonBreakdown(contact_name=person_name))
        person.messages += 1
        if result.new_commitment:
            summary.commitments_created += 1
            person.commitments_created += 1
        if result.resolved_commitment_id:
            summary.commitments_resolved += 1
            person.commitments_resolved += 1
        if result.new_commitment or result.resolved_commitment_id:
            nc = result.new_commitment
            summary.items.append(
                IngestItem(
                    sent_at=_local(msg, utc_offset_minutes).isoformat(),
                    contact_name=contact.name if contact else None,
                    from_name="You" if msg.direction == "outbound" else (msg.sender_name or person_name),
                    direction=msg.direction,
                    preview=" ".join(msg.body.split())[:100],
                    new_commitment=nc.description if nc else None,
                    deadline=nc.inferred_deadline.isoformat() if nc and nc.inferred_deadline else None,
                    resolved_commitment_id=result.resolved_commitment_id,
                    resolution_reasoning=result.resolution_reasoning,
                )
            )

    summary.by_person = sorted(people.values(), key=lambda p: (-p.commitments_created, p.contact_name))
    summary.awaiting_reply = _awaiting_reply(all_msgs, utc_offset_minutes)
    return summary
