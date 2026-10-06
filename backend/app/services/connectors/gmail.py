"""
Gmail connector — reads the user's SENT mail over IMAP using a Google
"app password".

Why IMAP + app password instead of the Gmail API + OAuth: OAuth needs a
Google Cloud project, a consent screen and (for anything beyond a handful
of test users) Google's app-verification review for the sensitive
`gmail.readonly` scope — a process outside the developer's control, the
same kind of external blocker WhatsApp's Business API has. IMAP with an app
password needs only 2-step verification on the account (already how this
project sends its verification emails), works immediately, and is
read-only in practice because we select the folder with readonly=True and
fetch with BODY.PEEK.

Credential handling: the app password is used for this one sync and then
dropped. It is never written to the database, logged, or kept in a
session. Anyone using the real connector at scale should move to OAuth
(documented as the Phase 2 upgrade in ADR-018) so no password is handled
at all.

Only the Sent folder is read — see types.py for why other people's mail is
neither needed nor stored.
"""

import email
import hashlib
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

from app.services.connectors.types import (
    ConnectorAuthError,
    ConnectorError,
    ParsedMessage,
)

IMAP_HOST = "imap.gmail.com"
FALLBACK_SENT_FOLDER = "[Gmail]/Sent Mail"
MAX_BODY_CHARS = 4000
_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\)\s+"(?P<sep>[^"]*)"\s+(?P<name>.+)$')


class _TextFromHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _TextFromHtml()
    parser.feed(html)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def _decode(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value)))).strip()
    except Exception:
        return str(value).strip()


def _find_sent_folder(conn: imaplib.IMAP4) -> str:
    """
    Gmail localizes folder names ("[Gmail]/Sent Mail", "[Gmail]/Gesendet",
    ...), but flags the real one with the \\Sent attribute — look that up
    instead of hardcoding an English name.
    """
    status, lines = conn.list()
    if status == "OK":
        for raw in lines or []:
            if not isinstance(raw, bytes):
                continue
            m = _LIST_RE.match(raw)
            if m and b"\\Sent" in m["flags"]:
                return m["name"].decode("utf-8", "replace").strip().strip('"')
    return FALLBACK_SENT_FOLDER


def _extract_body(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except Exception:
        return ""
    if part.get_content_type() == "text/html":
        content = _html_to_text(content)
    return content.strip()


def _parse_one(raw: bytes) -> ParsedMessage | None:
    msg = email.message_from_bytes(raw, policy=policy.default)

    body = _extract_body(msg)
    if not body:
        return None
    subject = _decode(msg["Subject"])
    text = f"Subject: {subject}\n\n{body}" if subject else body

    try:
        sent_at = parsedate_to_datetime(msg["Date"])
        sent_at = (
            sent_at.replace(tzinfo=timezone.utc)
            if sent_at.tzinfo is None
            else sent_at.astimezone(timezone.utc)
        )
    except Exception:
        return None  # no usable date → can't order or de-duplicate it reliably

    recipients = getaddresses([str(msg["To"] or "")])
    name, address = (recipients[0] if recipients else ("", ""))
    name = _decode(name) or (address.split("@")[0] if address else "")

    message_id = (msg["Message-ID"] or "").strip()
    external = message_id or hashlib.sha1(f"{sent_at.isoformat()}|{text}".encode()).hexdigest()

    return ParsedMessage(
        channel="gmail",
        external_id=f"gmail:{external}"[:255],
        body=text[:MAX_BODY_CHARS],
        sent_at=sent_at,
        counterparty_name=name or None,
        counterparty_handle=address.lower() or None,
        direction="outbound",
        thread_key=(address.lower() or None),
    )


def read_sent_messages(
    address: str,
    app_password: str,
    since_days: int = 14,
    max_messages: int = 25,
    imap_factory=imaplib.IMAP4_SSL,
) -> list[ParsedMessage]:
    """
    Returns up to `max_messages` of the user's most recent sent emails from
    the last `since_days` days, oldest first. imap_factory is injectable so
    tests never touch the network.
    """
    password = app_password.replace(" ", "").strip()  # Google shows it in 4-char groups
    try:
        conn = imap_factory(IMAP_HOST, timeout=20)
    except Exception as exc:
        raise ConnectorError(f"Couldn't reach Gmail ({type(exc).__name__}). Check the connection.") from exc

    try:
        try:
            conn.login(address.strip(), password)
        except imaplib.IMAP4.error as exc:
            raise ConnectorAuthError(
                "Gmail rejected the login. Use a Google *app password* (needs "
                "2-step verification), not your normal password. Some school/"
                "work accounts disable app passwords — use a personal Gmail."
            ) from exc

        folder = _find_sent_folder(conn)
        status, _ = conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            raise ConnectorError("Couldn't open the Sent Mail folder.")

        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, data = conn.search(None, "SINCE", since)
        if status != "OK":
            raise ConnectorError("Gmail search failed.")

        ids = (data[0] or b"").split()[-max_messages:]
        messages: list[ParsedMessage] = []
        for msg_id in ids:
            status, fetched = conn.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            parsed = _parse_one(fetched[0][1])
            if parsed:
                messages.append(parsed)
        return sorted(messages, key=lambda m: m.sent_at)
    finally:
        try:
            conn.logout()
        except Exception:
            pass
