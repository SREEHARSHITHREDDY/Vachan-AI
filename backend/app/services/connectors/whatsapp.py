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


def parse_chat(
    text: str,
    my_name: str,
    chat_name: str | None = None,
    date_order: str = "auto",
    utc_offset_minutes: int = 0,
) -> list[ParsedMessage]:
    """
    Returns the user's OWN messages from the chat, oldest first.

    my_name must match a sender in the file (case-insensitive). The other
    side of a 1:1 chat is used as the counterparty; for a group chat pass
    chat_name (the UI derives it from the "WhatsApp Chat with X" filename).
    """
    if len(text) > MAX_TEXT_CHARS:
        raise ConnectorError("Chat file is too large (limit ~3 MB of text).")

    entries = [
        (s, b, t)
        for s, raw, t in _raw_entries(text, date_order, utc_offset_minutes)
        if (b := _clean_body(raw)) is not None
    ]
    senders = {s for s, _, _ in entries}
    me = next((s for s in senders if s.strip().lower() == my_name.strip().lower()), None)
    if me is None:
        raise ConnectorError(
            f"'{my_name}' doesn't appear in this chat. Names found: "
            + ", ".join(sorted(senders))
        )

    others = sorted(senders - {me})
    counterparty = chat_name or (others[0] if len(others) == 1 else None)
    chat_key = (chat_name or ",".join(sorted(senders))).lower()

    seen: Counter[str] = Counter()
    out: list[ParsedMessage] = []
    for sender, body, sent_at in sorted(entries, key=lambda e: e[2]):
        if sender != me:
            continue
        # Hash of chat + the timestamp exactly as written in the file + text,
        # plus an occurrence counter so two identical "ok" messages in the
        # same minute stay distinct. The timestamp is rebuilt WITHOUT the
        # UTC offset, so re-importing the same file from a browser in a
        # different timezone (travel, DST) still produces the same ids and
        # is correctly recognised as already imported.
        local_stamp = (sent_at + timedelta(minutes=utc_offset_minutes)).replace(tzinfo=None).isoformat()
        base = hashlib.sha1(f"{chat_key}|{local_stamp}|{body}".encode()).hexdigest()[:24]
        seen[base] += 1
        out.append(
            ParsedMessage(
                channel="whatsapp",
                external_id=f"wa:{base}:{seen[base]}",
                body=body,
                sent_at=sent_at,
                counterparty_name=counterparty,
            )
        )
    return out
