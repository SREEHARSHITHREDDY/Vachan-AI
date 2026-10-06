"""Contacts page data: per-person counts and per-person commitment lists."""

import pytest

from app.main import app
from app.models.database import get_db
from app.models.db_models import Contact, User
from tests.test_connectors_api import RAHUL_CHAT, llm  # noqa: F401


def _import_rahul(client):
    client.post("/api/v1/connectors/whatsapp/import", json={"text": RAHUL_CHAT, "my_name": "Harshith"})
    return next(c for c in client.get("/api/v1/contacts").json()["data"] if c["name"] == "Rahul")


def test_contact_list_shows_open_count_and_next_deadline(client, llm):
    rahul = _import_rahul(client)
    assert (rahul["open_commitments"], rahul["fulfilled_commitments"]) == (1, 0)
    assert rahul["next_deadline"].startswith("2026-10-07T16:30")


def test_contact_with_no_commitments_has_zero_counts(client):
    client.post("/api/v1/contacts", json={"name": "Nobody", "email_or_handle": "n@x.com", "role_tag": "other"})
    c = client.get("/api/v1/contacts").json()["data"][0]
    assert (c["open_commitments"], c["fulfilled_commitments"], c["next_deadline"]) == (0, 0, None)


def test_commitments_for_one_contact_open_first(client, llm):
    rahul = _import_rahul(client)
    items = client.get(f"/api/v1/contacts/{rahul['contact_id']}/commitments").json()["data"]
    assert [i["description"] for i in items] == ["Meet Rahul at 4:30 PM on 7 Oct"]
    assert items[0]["contact_name"] == "Rahul"


def test_another_users_contact_is_a_404(client):
    db = next(app.dependency_overrides[get_db]())
    stranger = User(email="stranger@example.com", persona_mode="student")
    db.add(stranger)
    db.commit()
    theirs = Contact(user_id=stranger.user_id, name="Theirs", email_or_handle="t@x.com", role_tag="other")
    db.add(theirs)
    db.commit()
    assert client.get(f"/api/v1/contacts/{theirs.contact_id}/commitments").status_code == 404
