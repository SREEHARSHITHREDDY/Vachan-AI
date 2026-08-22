"""
Proves real per-user data isolation — the actual point of the auth
refactor. Every other test file relies on conftest.py's default auth
override (a fixed demo user, for backward compatibility with tests
written before login existed). This file deliberately REMOVES that
override for each test, so real JWTs from real signed-up accounts are
actually checked end-to-end, exactly as a real user's browser would
experience it.
"""

from app.core.deps import get_current_user_id
from app.main import app


def _signup_and_get_headers(client, email, password="correcthorse123"):
    response = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": password}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_two_users_do_not_see_each_others_commitments(client):
    # Remove the default demo-user override so real tokens are actually
    # checked for this test — see module docstring.
    del app.dependency_overrides[get_current_user_id]

    headers_a = _signup_and_get_headers(client, "alice@example.com")
    headers_b = _signup_and_get_headers(client, "bob@example.com")

    client.post("/api/v1/messages", json={"body": "Alice's private note, no commitment here."}, headers=headers_a)
    client.post("/api/v1/messages", json={"body": "Bob's private note, no commitment here."}, headers=headers_b)

    # Manually insert a commitment for each user directly (extraction
    # needs a real LLM key; isolation itself doesn't depend on that —
    # bypass it here the same way other test files do for setup).
    from datetime import datetime, timezone

    from app.models.database import get_db
    from app.models.db_models import Commitment, Message

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)

    # Look up each user's real id from their own /auth/me, not by
    # guessing — proves the token->user mapping is what's actually used.
    me_a = client.get("/api/v1/auth/me", headers=headers_a).json()
    me_b = client.get("/api/v1/auth/me", headers=headers_b).json()

    msg_a = Message(user_id=me_a["user_id"], channel="message", direction="outbound",
                     body_ref="Alice msg", sent_at=datetime.now(timezone.utc))
    msg_b = Message(user_id=me_b["user_id"], channel="message", direction="outbound",
                     body_ref="Bob msg", sent_at=datetime.now(timezone.utc))
    db.add_all([msg_a, msg_b])
    db.commit()
    db.refresh(msg_a)
    db.refresh(msg_b)

    commitment_a = Commitment(user_id=me_a["user_id"], source_message_id=msg_a.message_id,
                               commitment_type="made-by-me", description="Alice's commitment", state="pending")
    commitment_b = Commitment(user_id=me_b["user_id"], source_message_id=msg_b.message_id,
                               commitment_type="made-by-me", description="Bob's commitment", state="pending")
    db.add_all([commitment_a, commitment_b])
    db.commit()

    # The actual isolation proof: each user's list only shows their own.
    list_a = client.get("/api/v1/commitments", headers=headers_a).json()["data"]
    list_b = client.get("/api/v1/commitments", headers=headers_b).json()["data"]

    descriptions_a = [c["description"] for c in list_a]
    descriptions_b = [c["description"] for c in list_b]

    assert "Alice's commitment" in descriptions_a
    assert "Bob's commitment" not in descriptions_a
    assert "Bob's commitment" in descriptions_b
    assert "Alice's commitment" not in descriptions_b


def test_user_cannot_delete_another_users_commitment(client):
    del app.dependency_overrides[get_current_user_id]

    headers_a = _signup_and_get_headers(client, "owner@example.com")
    headers_b = _signup_and_get_headers(client, "intruder@example.com")

    from datetime import datetime, timezone

    from app.models.database import get_db
    from app.models.db_models import Commitment, Message

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    me_a = client.get("/api/v1/auth/me", headers=headers_a).json()

    msg = Message(user_id=me_a["user_id"], channel="message", direction="outbound",
                  body_ref="test", sent_at=datetime.now(timezone.utc))
    db.add(msg)
    db.commit()
    db.refresh(msg)
    commitment = Commitment(user_id=me_a["user_id"], source_message_id=msg.message_id,
                             commitment_type="made-by-me", description="Owner's commitment", state="pending")
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    # User B tries to delete User A's commitment — must 404, not succeed,
    # and must NOT reveal whether the commitment exists at all for
    # someone else (same 404 as a truly nonexistent id).
    response = client.delete(f"/api/v1/commitments/{commitment.commitment_id}", headers=headers_b)
    assert response.status_code == 404

    # Confirm it's genuinely untouched — owner can still see it.
    list_a = client.get("/api/v1/commitments", headers=headers_a).json()["data"]
    assert any(c["description"] == "Owner's commitment" for c in list_a)


def test_requests_without_any_token_are_rejected(client):
    del app.dependency_overrides[get_current_user_id]

    response = client.get("/api/v1/commitments")
    assert response.status_code == 401
