"""
Shared pytest configuration and fixtures.

pytest_addoption MUST live in conftest.py — pytest does not pick up custom
CLI options declared inside a regular test module.

The `client` fixture also lives here (moved from test_api_routes.py) so
every test file can use it, not just the one it was originally written
in — test_contacts.py needs the exact same real-HTTP-layer, in-memory-DB
setup and there's no reason for two files to maintain separate copies of
it that could quietly drift out of sync with each other.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.database import Base, get_db


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live LLM evaluation against the labeled test set (costs API credits).",
    )


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
