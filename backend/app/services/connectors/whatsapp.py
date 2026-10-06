"""
WhatsApp connector — parses the text file produced by WhatsApp's own
"Export chat" feature (Chat → ⋮ / contact name → Export chat → Without media).

Why an export file and not a live connection: WhatsApp has no API for
reading a personal account's messages. The official Business API needs
Meta's approval and a paid provider (docs/10_Future_Roadmap), and
unofficial "WhatsApp Web" automation breaks the terms of service and can
get the number banned. The export file is the one route that is fully
supported, free, works today, and keeps the user in control of exactly
which chat they hand over.

Handles both export layouts:
  Android: 31/12/23, 9:41 pm - Ravi: I'll send the notes tomorrow
  iOS:     [31/12/23, 9:41:05 PM] Ravi: I'll send the notes tomorrow
including 12h/24h clocks, 2- or 4-digit years, multi-line messages, and the
invisible left-to-right marks iOS inserts.

Everyone's messages are parsed (direction + sender recorded) so replies can
be understood in context; in a group chat each message is attributed to the
person it concerns (see _attribute_group_message).

Date order (DD/MM vs MM/DD) is not recorded in the file, so it is inferred
from the data: any date whose first number is >12 proves day-first, any
whose second number is >12 proves month-first. If the whole file is
ambiguous it defaults to day-first (the common order outside the US) and
the caller can override it.
"""

import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.services.connectors.types import ConnectorError, ParsedMessage

# U+200E (LRM) and U+202F (narrow no-break space, used before am/pm by
# newer exports) are invisible but break naive regexes — normalized first.
_INVISIBLE = {ord("\u200e"): None, ord("\u200f"): None, ord("\u202f"): " ", ord("\u00a0"): " "}

_HEADER_RE = re.compile(
    r"^\[?(?P<a>\d{1,2})[/.\-](?P<b>\d{1,2})[/.\-](?P<y>\d{2,4}),?\s+"
    r"(?P<h>\d{1,2})[:.](?P<mi>\d{2})(?:[:.](?P<s>\d{2}))?\s*"
    r"(?P<ap>[AaPp]\.?\s?[Mm]\.?)?\]?\s*(?:-\s*)?(?P<rest>.*)$"
)

_SKIP_PHRASES = (
    "<media omitted>",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "gif omitted",
    "document omitted",
    "contact card omitted",
    "this message was deleted",
    "you deleted this message",
    "missed voice call",
    "missed video call",
    "waiting for this message",
)
_EDITED_SUFFIX = re.compile(r"\s*<This message was edited>\s*$")

MAX_TEXT_CHARS = 3_000_000


def _normalize(text: str) -> str:
    return text.translate(_INVISIBLE).replace("\r\n", "\n").replace("\r", "\n")


def _detect_date_order(lines: list[str], requested: str) -> str:
    if requested in ("dmy", "mdy"):
        return requested
    saw_first_gt12 = saw_second_gt12 = False
    for line in lines:
        m = _HEADER_RE.match(line)
        if not m:
            continue
        a, b = int(m["a"]), int(m["b"])
        saw_first_gt12 |= a > 12
        saw_second_gt12 |= b > 12
    if saw_second_gt12 and not saw_first_gt12:
        return "mdy"
    return "dmy"


def _build_datetime(m: re.Match, order: str, utc_offset_minutes: int) -> datetime | None:
    a, b, y = int(m["a"]), int(m["b"]), int(m["y"])
    day, month = (a, b) if order == "dmy" else (b, a)
    if y < 100:
        y += 2000
    hour, minute, second = int(m["h"]), int(m["mi"]), int(m["s"] or 0)
    ap = (m["ap"] or "").replace(".", "").replace(" ", "").lower()
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    try:
        local = datetime(y, month, day, hour, minute, second)
    except ValueError:
        return None
    # The export carries the phone's local time with no zone. Convert to
    # UTC using the offset the caller supplies (the browser's offset).
    return (local - timedelta(minutes=utc_offset_minutes)).replace(tzinfo=timezone.utc)


def _split_sender(rest: str) -> tuple[str, str] | None:
    # "Name: text". System lines ("Messages and calls are end-to-end
    # encrypted...", "Ravi added Priya") have no ": " and are dropped.
    if ": " not in rest:
        return None
    sender, text = rest.split(": ", 1)
    sender = sender.strip()
    if not sender or len(sender) > 80:
        return None
    return sender, text


def _raw_entries(text: str, date_order: str, utc_offset_minutes: int):
    """Yields (sender, body, sent_at) for every real chat message."""
    lines = _normalize(text).split("\n")
    order = _detect_date_order(lines, date_order)

    current: dict | None = None
    for line in lines:
        m = _HEADER_RE.match(line)
        parsed = _split_sender(m["rest"]) if m else None
        sent_at = _build_datetime(m, order, utc_offset_minutes) if m else None

        if m and parsed and sent_at:
            if current:
                yield current["sender"], current["body"], current["sent_at"]
            current = {"sender": parsed[0], "body": parsed[1], "sent_at": sent_at}
        elif m and not parsed:
            # A system line starts a new entry, so it must close the
            # previous message instead of being glued onto it.
            if current:
                yield current["sender"], current["body"], current["sent_at"]
            current = None
        elif current is not None:
            current["body"] += "\n" + line  # continuation of a multi-line message
    if current:
        yield current["sender"], current["body"], current["sent_at"]


def _clean_body(body: str) -> str | None:
    body = _EDITED_SUFFIX.sub("", body).strip()
    if not body:
        return None
    lowered = body.lower()
    if any(phrase in lowered for phrase in _SKIP_PHRASES):
        return None
    return body


def inspect_chat(text: str, date_order: str = "auto") -> dict:
    """
    Cheap first pass so the UI can ask "which of these people are you?"
    instead of making the user type their exact WhatsApp display name.
    """
    if len(text) > MAX_TEXT_CHARS:
        raise ConnectorError("Chat file is too large (limit ~3 MB of text).")
    counts: Counter[str] = Counter()
    first = last = None
    for sender, body, sent_at in _raw_entries(text, date_order, 0):
        if _clean_body(body) is None:
            continue
        counts[sender] += 1
        first = sent_at if first is None or sent_at < first else first
        last = sent_at if last is None or sent_at > last else last
    if not counts:
        raise ConnectorError(
            "No WhatsApp messages found. Use WhatsApp's 'Export chat' (without "
            "media) and upload the .txt file it produces."
        )
    return {
        "participants": [{"name": n, "message_count": c} for n, c in counts.most_common()],
        "total_messages": sum(counts.values()),
        "first_message_at": first.isoformat() if first else None,
        "last_message_at": last.isoformat() if last else None,
    }


_WORD_CACHE: dict[str, re.Pattern] = {}


def _name_pattern(token: str) -> re.Pattern:
    if token not in _WORD_CACHE:
        _WORD_CACHE[token] = re.compile(rf"(?<![\w]){re.escape(token)}(?![\w])", re.IGNORECASE)
    return _WORD_CACHE[token]


def _mentioned_people(body: str, others: list[str]) -> list[str]:
    """Participants whose full name or first name appears in the text."""
    found = []
    for name in others:
        tokens = {name, name.split()[0]}
        if any(len(t) >= 3 and _name_pattern(t).search(body) for t in tokens):
            found.append(name)
    return found


def _attribute_group_message(index: int, entries: list, me: str, others: list[str]) -> str | None:
    """
    Which group member does the user's message at `index` concern?
      1. exactly one member is named in the text ("Sure Rahul, ...") → them
      2. else the person who spoke last within 20 minutes before it, i.e.
         the one being replied to
      3. else nobody (the caller falls back to the chat name)
    Heuristics, not mind-reading — deterministic so they are testable, and
    wrong guesses only mis-label the contact, never lose the commitment.
    """
    sender, body, sent_at = entries[index]
    named = _mentioned_people(body, others)
    if len(named) == 1:
        return named[0]
    for j in range(index - 1, -1, -1):
        prev_sender, _, prev_at = entries[j]
        if (sent_at - prev_at).total_seconds() > 20 * 60:
            break
        if prev_sender != me:
            return prev_sender
    return None


def parse_chat_all(
    text: str,
    my_name: str,
    chat_name: str | None = None,
    date_order: str = "auto",
    utc_offset_minutes: int = 0,
) -> list[ParsedMessage]:
    """
    Every message in the chat (both directions), oldest first, each tagged
    with direction, sender and the person it is with. Use parse_chat() if
    only the user's own messages are wanted.
    """
    if len(text) > MAX_TEXT_CHARS:
        raise ConnectorError("Chat file is too large (limit ~3 MB of text).")

    entries = sorted(
        (
            (s, b, t)
            for s, raw, t in _raw_entries(text, date_order, utc_offset_minutes)
            if (b := _clean_body(raw)) is not None
        ),
        key=lambda e: e[2],
    )
    senders = {s for s, _, _ in entries}
    me = next((s for s in senders if s.strip().lower() == my_name.strip().lower()), None)
    if me is None and len(senders) > 1:
        raise ConnectorError(
            f"'{my_name}' doesn't appear in this chat. Names found: "
            + ", ".join(sorted(senders))
        )
    # me is None with a single speaker: the user never replied in this chat.
    # That is a normal, valuable case ("someone is waiting to hear back"),
    # so every message is treated as incoming rather than rejecting the file.
    # (With 2+ speakers an unknown name is far more likely a wrong pick.)

    others = sorted(senders - {me})
    is_group = len(others) > 1
    chat_key = (chat_name or ",".join(sorted(senders))).lower()
    one_to_one_name = others[0] if len(others) == 1 else None

    seen: Counter[str] = Counter()
    out: list[ParsedMessage] = []
    for i, (sender, body, sent_at) in enumerate(entries):
        outbound = sender == me
        local_stamp = (sent_at + timedelta(minutes=utc_offset_minutes)).replace(tzinfo=None).isoformat()

        if outbound:
            # Hash of chat + the timestamp exactly as written in the file +
            # text, plus an occurrence counter so two identical "ok"
            # messages in the same minute stay distinct. The timestamp is
            # rebuilt WITHOUT the UTC offset, so re-importing the same file
            # from a browser in a different timezone (travel, DST) still
            # produces the same ids and is recognised as already imported.
            # (Formula unchanged from the first version so messages
            # imported earlier still de-duplicate.)
            base = hashlib.sha1(f"{chat_key}|{local_stamp}|{body}".encode()).hexdigest()[:24]
            prefix = "wa"
            counterparty = (
                one_to_one_name
                or (_attribute_group_message(i, entries, me, others) if is_group else None)
                or chat_name
            )
        else:
            base = hashlib.sha1(f"{chat_key}|{local_stamp}|{sender}|{body}".encode()).hexdigest()[:24]
            prefix = "wa-in"
            counterparty = sender
        seen[base] += 1
        out.append(
            ParsedMessage(
                channel="whatsapp",
                external_id=f"{prefix}:{base}:{seen[base]}",
                body=body,
                sent_at=sent_at,
                counterparty_name=counterparty,
                direction="outbound" if outbound else "inbound",
                sender_name=sender,
                thread_key=chat_key,
            )
        )
    return out


def parse_chat(
    text: str,
    my_name: str,
    chat_name: str | None = None,
    date_order: str = "auto",
    utc_offset_minutes: int = 0,
) -> list[ParsedMessage]:
    """The user's OWN messages only, oldest first (see parse_chat_all)."""
    return [
        m
        for m in parse_chat_all(text, my_name, chat_name, date_order, utc_offset_minutes)
        if m.direction == "outbound"
    ]
