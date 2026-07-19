"""
Integration test: proves the SQLite wiring actually persists data, not just
that the ORM models import cleanly.

Uses a temporary in-memory SQLite database (not the demo file) so tests
never touch or depend on real demo data, and each test run starts clean.

This deliberately tests the FULL flow — create a commitment, then apply a
lifecycle resolution to it, then read it back — because that's the
actual thing Stage 3 needs to prove: Stage 1+2's logic can persist and
be queried, not just run in memory during a single test.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.models.db_models import Commitment, Message, User


@pytest.fixture
def db_session():
    """Fresh in-memory SQLite DB per test — no shared state between tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()
    yield session
    session.close()


def test_create_and_read_user(db_session):
    user = User(email="student@example.com", persona_mode="student")
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter_by(email="student@example.com").first()
    assert fetched is not None
    assert fetched.persona_mode == "student"
    assert fetched.user_id is not None  # UUID default was actually applied


def test_full_commitment_lifecycle_persists_correctly(db_session):
    """
    The real end-to-end proof: a message creates a commitment, the
    commitment gets resolved (mirroring what ExtractionService +
    LifecycleTracker do in memory), and both states are correctly
    readable back from the database afterward.
    """
    user = User(email="student@example.com")
    db_session.add(user)
    db_session.commit()

    original_message = Message(
        user_id=user.user_id,
        channel="gmail",
        direction="outbound",
        body_ref="I'll send the deck by Friday.",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(original_message)
    db_session.commit()

    commitment = Commitment(
        user_id=user.user_id,
        source_message_id=original_message.message_id,
        commitment_type="made-by-me",
        description="Send the deck by Friday",
        state="pending",
    )
    db_session.add(commitment)
    db_session.commit()

    # Simulate what LifecycleTracker.check_for_resolution would trigger:
    # a later, unrelated message resolves this commitment.
    commitment.state = "fulfilled"
    commitment.resolved_at = datetime.now(timezone.utc)
    db_session.commit()

    fetched = db_session.query(Commitment).filter_by(
        commitment_id=commitment.commitment_id
    ).first()
    assert fetched.state == "fulfilled"
    assert fetched.resolved_at is not None
    assert fetched.source_message_id == original_message.message_id


def test_soft_delete_does_not_remove_row(db_session):
    """
    Reconciliation Addendum Item 5: soft-delete on Commitment means the row
    stays queryable (e.g. for relationship-score history) even after a user
    'deletes' it — this test proves that behavior actually works, not just
    that the column exists.
    """
    user = User(email="student@example.com")
    db_session.add(user)
    db_session.commit()

    message = Message(
        user_id=user.user_id,
        channel="slack",
        direction="inbound",
        body_ref="Sure, I'll get that to you.",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(message)
    db_session.commit()

    commitment = Commitment(
        user_id=user.user_id,
        source_message_id=message.message_id,
        commitment_type="made-to-me",
        description="Something promised to the user",
    )
    db_session.add(commitment)
    db_session.commit()

    # Soft-delete, not session.delete()
    commitment.is_deleted = True
    commitment.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    still_there = db_session.query(Commitment).filter_by(
        commitment_id=commitment.commitment_id
    ).first()
    assert still_there is not None
    assert still_there.is_deleted is True
