"""
Tests for the Contacts CRUD endpoints — mirrors the conventions in
test_api_routes.py (same client fixture, same direct-DB-setup pattern for
anything the API itself doesn't create).
"""

from app.main import app
from app.models.database import get_db


def test_list_contacts_empty_initially(client):
    response = client.get("/api/v1/contacts")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_create_contact(client):
    response = client.post(
        "/api/v1/contacts",
        json={"name": "Priya Sharma", "email_or_handle": "priya@example.com", "role_tag": "friend"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Priya Sharma"
    assert data["role_tag"] == "friend"
    assert "contact_id" in data


def test_create_contact_defaults_role_tag_to_other(client):
    response = client.post(
        "/api/v1/contacts",
        json={"name": "Someone", "email_or_handle": "someone@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["role_tag"] == "other"


def test_list_contacts_returns_created_ones_sorted_by_name(client):
    client.post("/api/v1/contacts", json={"name": "Zara", "email_or_handle": "z@example.com"})
    client.post("/api/v1/contacts", json={"name": "Amit", "email_or_handle": "a@example.com"})

    response = client.get("/api/v1/contacts")
    names = [c["name"] for c in response.json()["data"]]
    assert names.index("Amit") < names.index("Zara")


def test_update_contact_partial_fields_only(client):
    create = client.post(
        "/api/v1/contacts",
        json={"name": "Rahul", "email_or_handle": "rahul@example.com", "role_tag": "teammate"},
    )
    contact_id = create.json()["data"]["contact_id"]

    response = client.patch(f"/api/v1/contacts/{contact_id}", json={"role_tag": "recruiter"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["role_tag"] == "recruiter"
    assert data["name"] == "Rahul"  # untouched


def test_update_contact_404_for_unknown(client):
    response = client.patch("/api/v1/contacts/does-not-exist", json={"name": "X"})
    assert response.status_code == 404


def test_delete_contact_soft_deletes(client):
    create = client.post(
        "/api/v1/contacts",
        json={"name": "Temp Contact", "email_or_handle": "temp@example.com"},
    )
    contact_id = create.json()["data"]["contact_id"]

    delete_response = client.delete(f"/api/v1/contacts/{contact_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True

    list_response = client.get("/api/v1/contacts")
    ids = [c["contact_id"] for c in list_response.json()["data"]]
    assert contact_id not in ids


def test_delete_contact_404_for_unknown(client):
    response = client.delete("/api/v1/contacts/does-not-exist")
    assert response.status_code == 404


def test_assign_contact_to_commitment(client):
    """The actual end-to-end value of this feature: a commitment can be
    linked to a contact, and the link shows up in the commitment's own
    response (contact_id + contact_name), not just on the contact side."""
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    contact_resp = client.post(
        "/api/v1/contacts",
        json={"name": "Prof. Iyer", "email_or_handle": "iyer@example.com", "role_tag": "professor"},
    )
    contact_id = contact_resp.json()["data"]["contact_id"]

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id, channel="message", direction="outbound",
        body_ref="Test message for contact linking.", sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id, source_message_id=message.message_id,
        commitment_type="made-to-me", description="Get feedback on draft",
        state="pending",
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    patch_response = client.patch(
        f"/api/v1/commitments/{commitment.commitment_id}",
        json={"contact_id": contact_id},
    )
    assert patch_response.status_code == 200
    data = patch_response.json()["data"]
    assert data["contact_id"] == contact_id
    assert data["contact_name"] == "Prof. Iyer"


def test_assign_unknown_contact_to_commitment_404s(client):
    from datetime import datetime, timezone

    from app.models.db_models import Commitment, Message
    from app.services.message_processor import _get_demo_user_id

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user_id = _get_demo_user_id(db)

    message = Message(
        user_id=user_id, channel="message", direction="outbound",
        body_ref="Another test message.", sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    commitment = Commitment(
        user_id=user_id, source_message_id=message.message_id,
        commitment_type="made-to-me", description="Test",
        state="pending",
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)

    response = client.patch(
        f"/api/v1/commitments/{commitment.commitment_id}",
        json={"contact_id": "does-not-exist"},
    )
    assert response.status_code == 404
