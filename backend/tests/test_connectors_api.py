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
    assert again["already_imported"] == 2 and again["processed"] == 0

    status = client.get("/api/v1/connectors/status").json()["data"]
    assert status["whatsapp"]["messages"] == 2 and status["gmail"]["messages"] == 0


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
