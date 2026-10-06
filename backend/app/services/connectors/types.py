"""
Shared types for message connectors (Gmail, WhatsApp export, ...).

A connector's only job is to turn some external source into a list of
ParsedMessage objects. It never touches the database or the LLM — that is
the ingestion service's job (app/services/ingestion_service.py). Keeping
the two apart means a new connector (Telegram export, SMS backup, ...) is
just one more parser that returns ParsedMessage, with no pipeline changes.

Only messages the USER SENT are returned by the connectors. VachanAI
tracks promises the user made and detects when the user's own later
messages fulfil them, so other people's messages are never needed — and
never stored, which is also the smaller privacy footprint.
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
    counterparty_name: str | None = None
    # email address for Gmail; None for WhatsApp (no address in an export)
    counterparty_handle: str | None = None
