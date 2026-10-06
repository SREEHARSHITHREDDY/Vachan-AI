"""
Shared types for message connectors (Gmail, WhatsApp export, ...).

A connector's only job is to turn some external source into a list of
ParsedMessage objects. It never touches the database or the LLM — that is
the ingestion service's job (app/services/ingestion_service.py). Keeping
the two apart means a new connector (Telegram export, SMS backup, ...) is
just one more parser that returns ParsedMessage, with no pipeline changes.

Connectors return BOTH directions of a conversation (outbound = the user
sent it, inbound = someone else did). Whether inbound messages are also
analysed and stored is the caller's choice (`include_incoming`); even when
they are not, they are still used as in-memory context so a reply such as
"Sure, see you then" can be understood against the message it answers.
"""

from dataclasses import dataclass
from datetime import datetime


class ConnectorError(Exception):
    """Anything that goes wrong reading a source (bad file, network...)."""


class ConnectorAuthError(ConnectorError):
    """Credentials were rejected by the source (e.g. wrong app password)."""


@dataclass(frozen=True)
class ParsedMessage:
    channel: str  # "gmail" | "whatsapp"
    external_id: str  # stable id used for de-duplication, unique per user
    body: str
    sent_at: datetime  # timezone-aware, UTC
    # The OTHER person this message is with: the recipient for an outbound
    # message, the sender for an inbound one. In a group chat it is the
    # best attributable member (named in the text, or the person being
    # replied to) and may be None when no one can be singled out.
    counterparty_name: str | None = None
    # email address for Gmail; None for WhatsApp (no address in an export)
    counterparty_handle: str | None = None
    direction: str = "outbound"  # "outbound" | "inbound"
    sender_name: str | None = None  # display name of whoever wrote it
    # Identifies the conversation, so a message's context only ever comes
    # from its own chat/thread (never from a different person's chat).
    thread_key: str | None = None
