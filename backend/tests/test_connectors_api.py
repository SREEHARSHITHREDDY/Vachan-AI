"""HTTP layer for the connector routes (LLM and IMAP both faked)."""

import pytest

from app.core.config import get_settings
from app.services.connectors.types import ConnectorAuthError, ConnectorError, ParsedMessage
from tests.test_ingestion_service import FakeExtractor, FakeTracker, PROMISE, DONE  # noqa: F401

CHAT = (
    "05/01/2026, 21:41 - Priya: Can you share the notes?\n"
    "05/01/2026, 21:42 - Harshith: Sure, I'll send the notes by tomorrow evening\n"
    "06/01/2026, 18:06 - Harshith: Sent the notes just now\n"
)


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    monkeypatch.setattr("app.services.message_processor.ExtractionService", FakeExtractor)
    monkeypatch.setattr("app.services.message_processor.LifecycleTracker", FakeTracker)
    FakeExtractor.calls, FakeExtractor.fail = [], False


def test_whatsapp_inspect_then_import_end_to_end(client, llm):
    info = client.post("/api/v1/connectors/whatsapp/inspect", json={"text": CHAT}).json()["data"]
    assert {p["name"] for p in info["participants"]} == {"Priya", "Harshith"}

    res = client.post("/api/v1/connectors/whatsapp/import",
                      json={"text": CHAT, "my_name": "Harshith", "utc_offset_minutes": 330})
    assert res.status_code == 200
    data = res.json()["data"]
    assert (data["commitments_created"], data["commitments_resolved"], data["contacts_created"]) == (1, 1, 1)

    listed = client.get("/api/v1/commitments").json()["data"]
    only = listed if isinstance(listed, list) else listed.get("items", listed)
    assert any(c["state"] == "fulfilled" and c["contact_name"] == "Priya" and c["channel"] == "whatsapp"
               for c in only)

    # idempotent from the user's point of view
    again = client.post("/api/v1/connectors/whatsapp/import",
                        json={"text": CHAT, "my_name": "Harshith"}).json()["data"]
    assert again["already_imported"] == 3 and again["processed"] == 0  # her question + my 2 messages

    status = client.get("/api/v1/connectors/status").json()["data"]
    assert status["whatsapp"]["messages"] == 3 and status["gmail"]["messages"] == 0


def test_whatsapp_wrong_name_is_a_clear_422(client, llm):
    res = client.post("/api/v1/connectors/whatsapp/import", json={"text": CHAT, "my_name": "Nobody"})
    assert res.status_code == 422 and "Harshith" in res.json()["detail"]


def test_import_without_llm_key_fails_loudly_instead_of_silently_extracting_nothing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    res = client.post("/api/v1/connectors/whatsapp/import", json={"text": CHAT, "my_name": "Harshith"})
    assert res.status_code == 503


def test_gmail_sync_uses_connector_and_feeds_pipeline(client, llm, monkeypatch):
    seen = {}

    def fake_read(address, password, since_days, max_messages):
        seen.update(address=address, password=password, days=since_days)
        return [ParsedMessage("gmail", "gmail:<1@x>", "I'll upload the report by Monday morning", PROMISE.sent_at,
                              "Dr Rao", "rao@univ.edu")]

    monkeypatch.setattr("app.routers.connectors.gmail.read_sent_messages", fake_read)
    res = client.post("/api/v1/connectors/gmail/sync",
                      json={"gmail_address": "me@gmail.com", "app_password": "abcd efgh ijkl mnop", "days": 7})
    assert res.status_code == 200 and res.json()["data"]["commitments_created"] == 1
    assert seen == {"address": "me@gmail.com", "password": "abcd efgh ijkl mnop", "days": 7}
    assert "abcd" not in res.text  # credentials never echoed back


@pytest.mark.parametrize("exc,code", [(ConnectorAuthError("bad login"), 401), (ConnectorError("down"), 502)])
def test_gmail_errors_map_to_http_codes(client, llm, monkeypatch, exc, code):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr("app.routers.connectors.gmail.read_sent_messages", boom)
    res = client.post("/api/v1/connectors/gmail/sync",
                      json={"gmail_address": "me@gmail.com", "app_password": "abcdefghijklmnop"})
    assert res.status_code == code


def test_invalid_gmail_request_does_not_echo_the_password(client, llm):
    res = client.post("/api/v1/connectors/gmail/sync",
                      json={"gmail_address": "not-an-email", "app_password": "hunter2hunter2"})
    assert res.status_code == 422
    assert "hunter2hunter2" not in res.text


def test_connector_routes_require_login():
    from fastapi.testclient import TestClient
    from app.main import app
    app.dependency_overrides.clear()
    res = TestClient(app).post("/api/v1/connectors/whatsapp/inspect", json={"text": CHAT})
    assert res.status_code == 401


def test_too_short_app_password_is_rejected_without_echoing_it(client, llm):
    res = client.post("/api/v1/connectors/gmail/sync",
                      json={"gmail_address": "me@gmail.com", "app_password": "tiny-pw"})
    assert res.status_code == 422 and "tiny-pw" not in res.text


RAHUL_CHAT = (
    "05/10/2026, 14:00 - Rahul: Can we meet at 4:30 pm on 7th Oct to go over the demo?\n"
    "05/10/2026, 14:05 - Harshith: Sure, see you then\n"
    "05/10/2026, 18:00 - Rahul: Also please send me the slides before that, let me know\n"
)


def test_meeting_shows_up_under_the_right_person_with_a_natural_description(client, llm):
    data = client.post("/api/v1/connectors/whatsapp/import",
                       json={"text": RAHUL_CHAT, "my_name": "Harshith"}).json()["data"]
    assert data["commitments_created"] == 1
    assert data["by_person"][0]["contact_name"] == "Rahul"
    assert data["items"][0]["new_commitment"] == "Meet Rahul at 4:30 PM on 7 Oct"
    assert data["items"][0]["deadline"].startswith("2026-10-07T16:30")
    # his last message is a request nobody has answered yet
    assert [a["contact_name"] for a in data["awaiting_reply"]] == ["Rahul"]

    commitments = client.get("/api/v1/commitments").json()["data"]
    meet = next(c for c in commitments if "Rahul" in c["description"])
    assert meet["contact_name"] == "Rahul" and meet["channel"] == "whatsapp"


def test_include_incoming_false_keeps_other_peoples_messages_out_of_the_database(client, llm):
    data = client.post("/api/v1/connectors/whatsapp/import",
                       json={"text": RAHUL_CHAT, "my_name": "Harshith", "include_incoming": False}).json()["data"]
    assert data["incoming_processed"] == 0 and data["commitments_created"] == 1  # still understood in context
    assert client.get("/api/v1/connectors/status").json()["data"]["whatsapp"]["messages"] == 1
