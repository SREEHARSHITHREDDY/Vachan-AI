"""
Shared pytest configuration and fixtures.

pytest_addoption MUST live in conftest.py — pytest does not pick up custom
CLI options declared inside a regular test module.

The `client` fixture also overrides the real auth dependency
(get_current_user_id) to always resolve to a fixed demo user — this is
what lets every test written BEFORE the auth layer existed keep passing
completely unchanged: they never needed to know a login system was
coming. Any test that calls signup makes a REAL email-send attempt unless
mocked — mock_email below is autouse=True, so it protects every test
file automatically (not just ones that remember to opt in), which
matters a lot now that real SMTP credentials exist in .env: without
this, running the suite would actually send real emails to fake
addresses like alice@example.com on every test run.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_user_id
from app.main import app
from app.models.database import Base, get_db
from app.services.message_processor import _get_demo_user_id


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live LLM evaluation against the labeled test set (costs API credits).",
    )


@pytest.fixture(autouse=True)
def mock_email(monkeypatch):
    """Replaces the real SMTP call with a no-op for every single test in
    the whole suite — see module docstring for why this must be
    universal, not opt-in per file."""
    sent = {}

    def fake_send(to_email, verification_link):
        sent["to_email"] = to_email
        sent["verification_link"] = verification_link

    monkeypatch.setattr("app.routers.auth.send_verification_email", fake_send)
    return sent


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

    # Default auth override — see module docstring for why this exists.
    db_gen = override_get_db()
    db = next(db_gen)
    demo_user_id = _get_demo_user_id(db)
    app.dependency_overrides[get_current_user_id] = lambda: demo_user_id

    yield TestClient(app)
    app.dependency_overrides.clear()
