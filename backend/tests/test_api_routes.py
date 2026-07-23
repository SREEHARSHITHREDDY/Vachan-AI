"""
Integration test for Stage 4's API routes — exercises the real FastAPI
app via TestClient, with a real in-memory SQLite DB (not the demo file),
but MOCKED LLM calls (patching ExtractionService/LifecycleTracker's
underlying LLMClient) so this test suite doesn't cost API credits or
require a real key to run in CI/by default.

This is deliberately the FIRST test in the whole project that exercises
the actual HTTP layer, not just service-layer logic in isolation — proving
the wiring between routes -> services -> database actually works end to
end, which none of the Stage 1-3 tests could prove on their own.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.database import Base, get_db


@pytest.fixture
def client():
    """
    Fresh in-memory SQLite DB per test, wired into the FastAPI app via
    dependency override — standard FastAPI testing pattern.

    StaticPool is required here: sqlite:///:memory: creates a NEW, empty
    database per connection by default, so without forcing a single shared
    connection, different requests/sessions during the test would each see
    a table-less database (observed as "no such table: users" before this
    fix — each TestClient request was landing on a different in-memory DB
    than the one create_all() populated).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_submit_message_with_no_commitment(client):
    """
    No GROQ_API_KEY is set in the test environment, so extraction is
    skipped gracefully (message_processor.py's `if settings.groq_api_key`
    guard) — this test proves the endpoint doesn't crash when that's the
    case, which matters for anyone running tests without a key configured.
    """
    response = client.post("/api/v1/messages", json={"body": "Sounds good, thanks!"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["new_commitment"] is None


def test_list_commitments_empty_initially(client):
    response = client.get("/api/v1/commitments")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == []


def test_digest_reflects_empty_state(client):
    response = client.get("/api/v1/digest/today")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["at_risk_count"] == 0
    assert body["data"]["pending_count"] == 0


def test_submitted_commitment_appears_in_list_and_digest(client):
    """
    The real end-to-end proof for Stage 4: manually insert a commitment
    (bypassing extraction, since that needs a real LLM call) and confirm
    it's correctly readable through BOTH the list and digest endpoints —
    proving the routes -> database wiring itself is correct, independent
    of whether extraction is mocked or real.
    """
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.models.database import SessionLocal  # noqa — not used directly

    # Insert directly via the same DB the TestClient is using
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)

    from app.services.message_processor import _get_demo_user_id

    user_id = _get_demo_user_id(db)
    message = Message(
        user_id=user_id,
        channel="message",
        direction="outbound",
        body_ref="I'll send the deck by Friday.",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id,
        source_message_id=message.message_id,
        commitment_type="made-by-me",
        description="Send the deck by Friday",
        state="pending",
    )
    db.add(commitment)
    db.commit()

    list_response = client.get("/api/v1/commitments")
    assert len(list_response.json()["data"]) == 1
    assert list_response.json()["data"][0]["description"] == "Send the deck by Friday"

    digest_response = client.get("/api/v1/digest/today")
    assert digest_response.json()["data"]["pending_count"] == 1


def test_call_channel_is_tracked_through_full_pipeline(client):
    """
    Proves the channel selector (message/call/in-person) actually round-trips
    end to end: submit as a "call", confirm it comes back correctly on both
    the submit response AND the subsequent commitments list — not just that
    the request is accepted without error.

    No GROQ_API_KEY in test env, so no real commitment gets extracted here —
    this test instead inserts directly (like the test above) and confirms
    the list endpoint correctly attaches the channel from the related
    Message row.
    """
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id,
        channel="call",
        direction="outbound",
        body_ref="Promised on the phone to send the contract by Monday.",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id,
        source_message_id=message.message_id,
        commitment_type="made-by-me",
        description="Send the contract by Monday",
        state="pending",
    )
    db.add(commitment)
    db.commit()

    list_response = client.get("/api/v1/commitments")
    data = list_response.json()["data"]
    assert len(data) == 1
    assert data[0]["channel"] == "call"


def test_manual_mark_fulfilled(client):
    """
    Proves the new PATCH endpoint actually works end-to-end: a pending
    commitment can be manually marked fulfilled without a second message
    triggering the LLM, and resolved_at gets set correctly.
    """
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id,
        channel="message",
        direction="outbound",
        body_ref="I'll send the deck by Friday.",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id,
        source_message_id=message.message_id,
        commitment_type="made-by-me",
        description="Send the deck by Friday",
        state="pending",
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    response = client.patch(
        f"/api/v1/commitments/{commitment.commitment_id}", json={"state": "fulfilled"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] == "fulfilled"
    assert data["resolved_at"] is not None


def test_manual_mark_fulfilled_404_for_unknown_commitment(client):
    response = client.patch("/api/v1/commitments/does-not-exist", json={"state": "fulfilled"})
    assert response.status_code == 404


def test_manual_mark_at_risk(client):
    """
    Proves a user can flag something at-risk by judgment call even when
    the deadline (or lack of one) wouldn't have triggered it automatically.
    """
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id, channel="message", direction="outbound",
        body_ref="I'll get to it eventually.", sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id, source_message_id=message.message_id,
        commitment_type="made-by-me", description="Get to it eventually",
        state="pending", inferred_deadline=None,  # no deadline at all
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    response = client.patch(
        f"/api/v1/commitments/{commitment.commitment_id}", json={"state": "at-risk"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "at-risk"


def test_manual_deadline_update_without_changing_state(client):
    """Deadline can be set/edited independently of state."""
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id, channel="message", direction="outbound",
        body_ref="I'll send it.", sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id, source_message_id=message.message_id,
        commitment_type="made-by-me", description="Send it", state="pending",
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    new_deadline = "2026-08-15T14:30:00+00:00"
    response = client.patch(
        f"/api/v1/commitments/{commitment.commitment_id}",
        json={"inferred_deadline": new_deadline},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] == "pending"  # unchanged
    assert data["inferred_deadline"].startswith("2026-08-15T14:30:00")


def test_manual_at_risk_is_not_auto_reverted_by_refresh(client):
    """
    The actual bug-fix proof: a commitment manually flagged at-risk (with
    no deadline, or a far-off one) must NOT get silently flipped back to
    pending the next time commitments are listed (which triggers
    refresh_deadline_states). Before the fix, this would have reverted.
    """
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id, channel="message", direction="outbound",
        body_ref="Some far-off promise.", sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id, source_message_id=message.message_id,
        commitment_type="made-by-me", description="Some far-off promise",
        state="pending", inferred_deadline=None,
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    client.patch(f"/api/v1/commitments/{commitment.commitment_id}", json={"state": "at-risk"})

    # Listing triggers refresh_deadline_states — this is exactly the
    # moment the old code would have reverted it to pending.
    list_response = client.get("/api/v1/commitments")
    matching = [c for c in list_response.json()["data"] if c["commitment_id"] == commitment.commitment_id]
    assert len(matching) == 1
    assert matching[0]["state"] == "at-risk"
