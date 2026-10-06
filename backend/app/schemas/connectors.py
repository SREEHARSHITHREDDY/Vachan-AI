"""Request/response models for the message-reading connectors."""

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, SecretStr

DateOrder = Literal["auto", "dmy", "mdy"]


class WhatsAppInspectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3_000_000)
    date_order: DateOrder = "auto"


class WhatsAppImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3_000_000)
    my_name: str = Field(min_length=1, max_length=80)
    chat_name: Optional[str] = Field(default=None, max_length=80)
    date_order: DateOrder = "auto"
    # Browser's offset from UTC in minutes (IST = 330) — export timestamps
    # are the phone's local time with no zone attached.
    utc_offset_minutes: int = Field(default=0, ge=-840, le=840)
    max_messages: int = Field(default=50, ge=1, le=200)
    # Also analyse (and store) what the OTHER people wrote, so promises they
    # made to you are tracked. Their messages are used as conversation
    # context either way; this only controls whether they are analysed/stored.
    include_incoming: bool = True


class GmailSyncRequest(BaseModel):
    gmail_address: EmailStr
    # SecretStr keeps the value out of reprs/logs. No min/max_length here on
    # purpose: FastAPI echoes the rejected value back in its 422 body, which
    # would send a (mistyped) password out in an error response. The length
    # check lives in the route instead, with a generic message.
    app_password: SecretStr
    days: int = Field(default=14, ge=1, le=90)
    max_messages: int = Field(default=25, ge=1, le=100)
    utc_offset_minutes: int = Field(default=0, ge=-840, le=840)


class IngestItem(BaseModel):
    sent_at: str
    contact_name: Optional[str] = None  # the person this is with
    from_name: Optional[str] = None  # who wrote the message ("You" for the user)
    direction: str = "outbound"
    preview: str
    new_commitment: Optional[str] = None
    deadline: Optional[str] = None
    resolved_commitment_id: Optional[str] = None
    resolution_reasoning: Optional[str] = None


class AwaitingReply(BaseModel):
    """A conversation whose last message is from the other person and looks
    like it is waiting on the user (a question or request)."""

    contact_name: str
    preview: str
    sent_at: str


class PersonBreakdown(BaseModel):
    contact_name: str
    messages: int = 0
    commitments_created: int = 0
    commitments_resolved: int = 0


class IngestSummary(BaseModel):
    channel: str
    fetched: int = 0
    already_imported: int = 0
    skipped_trivial: int = 0
    processed: int = 0
    incoming_processed: int = 0
    commitments_created: int = 0
    commitments_resolved: int = 0
    duplicates_skipped: int = 0
    contacts_created: int = 0
    errors: list[str] = []
    aborted: bool = False
    items: list[IngestItem] = []
    by_person: list[PersonBreakdown] = []
    awaiting_reply: list[AwaitingReply] = []
