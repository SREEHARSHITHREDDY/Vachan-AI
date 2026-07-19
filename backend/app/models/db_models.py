"""
SQLAlchemy ORM models.

Scoped to what Stage 1-2 (Extraction + Lifecycle Tracker) actually need to
persist: User, Contact, Message, Commitment. RelationshipScore,
CalendarAction, and FeedbackCorrection (from the full Database Design doc,
Section 4.3) are NOT built here — they belong to later stages (Scoring,
Action Layer) that haven't been implemented yet. Adding their tables now,
before the code that uses them exists, would be exactly the kind of
premature building the Reconciliation Addendum's "deliberately not built
yet" pattern warns against.

UUIDs are stored as strings (36-char) rather than a native UUID type —
SQLite has no native UUID column type, and storing as a string keeps this
portable to Postgres later (where a String(36) still works fine, even if
a native UUID column would be more "proper" in production — that upgrade
is a Phase 2+ migration, not a demo-scope concern).

Soft-delete (is_deleted, deleted_at) is included on Contact and Commitment
per Reconciliation Addendum Item 5 — NOT on Message, per that same item's
reasoning (no business reason to soft-delete raw ingested messages
independently of their parent user).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    persona_mode: Mapped[str] = mapped_column(String(20), default="student", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="user")
    messages: Mapped[list["Message"]] = relationship(back_populates="user")
    commitments: Mapped[list["Commitment"]] = relationship(back_populates="user")


class Contact(Base):
    __tablename__ = "contacts"

    contact_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_or_handle: Mapped[str] = mapped_column(String(255), nullable=False)
    role_tag: Mapped[str] = mapped_column(String(50), default="other", nullable=False)
    importance_weight: Mapped[float] = mapped_column(default=0.50, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    # Reconciliation Addendum Item 5: soft-delete, not hard-delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="contacts")
    messages: Mapped[list["Message"]] = relationship(back_populates="contact")
    commitments: Mapped[list["Commitment"]] = relationship(back_populates="contact")


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id"), nullable=False)
    contact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contacts.contact_id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # 'gmail' | 'slack'
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # 'inbound' | 'outbound'
    body_ref: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="messages")
    contact: Mapped["Contact | None"] = relationship(back_populates="messages")


class Commitment(Base):
    __tablename__ = "commitments"

    commitment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id"), nullable=False)
    contact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contacts.contact_id"), nullable=True
    )
    source_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.message_id"), nullable=False
    )
    commitment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inferred_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reconciliation Addendum Item 5: soft-delete, not hard-delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="commitments")
    contact: Mapped["Contact | None"] = relationship(back_populates="commitments")
