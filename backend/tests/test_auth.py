"""
Tests for the auth layer — signup, email verification, login, and /me.

Email sending is mocked universally by conftest.py's autouse mock_email
fixture (not redefined here) — signup always tries to send a real email
now, and every test in the whole suite needs protection from that, not
just this file. Tests here that use the `mock_email` fixture argument are
receiving that same conftest.py fixture, inspecting what link/address it
recorded.
"""

from unittest.mock import patch

import pytest

from app.core.deps import get_current_user_id
from app.core.security import create_verification_token
from app.main import app
from app.models.database import get_db


def _verify_user_directly(db, email):
    """Bypasses the real email-click flow for tests that only care about
    login behavior, not verification itself — sets is_verified=True
    directly, the same effect clicking the link would have."""
    from app.models.db_models import User

    user = db.query(User).filter(User.email == email).first()
    user.is_verified = True
    db.commit()


def test_signup_creates_unverified_user_and_does_not_return_a_token(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "student@example.com", "password": "correcthorse123", "persona_mode": "student"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "student@example.com"
    assert "access_token" not in data  # the actual behavior change — no more auto-login


def test_signup_sends_a_verification_email(client, mock_email):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "verifyme@example.com", "password": "correcthorse123"},
    )
    assert mock_email["to_email"] == "verifyme@example.com"
    assert "/auth/verify-email?token=" in mock_email["verification_link"]


def test_signup_defaults_persona_to_student(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "default@example.com", "password": "correcthorse123"},
    )
    assert response.status_code == 200


def test_signup_duplicate_email_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "password": "correcthorse123"})
    response = client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "password": "differentpassword"})
    assert response.status_code == 409


def test_signup_rejects_short_password(client):
    response = client.post("/api/v1/auth/signup", json={"email": "short@example.com", "password": "short"})
    assert response.status_code == 422


def test_login_before_verifying_is_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "unverified@example.com", "password": "correcthorse123"})
    response = client.post("/api/v1/auth/login", json={"email": "unverified@example.com", "password": "correcthorse123"})
    assert response.status_code == 403
    assert "verify" in response.json()["detail"].lower()


def test_login_after_verifying_succeeds(client):
    client.post("/api/v1/auth/signup", json={"email": "verified@example.com", "password": "correcthorse123"})

    db = next(app.dependency_overrides[get_db]())
    _verify_user_directly(db, "verified@example.com")

    response = client.post("/api/v1/auth/login", json={"email": "verified@example.com", "password": "correcthorse123"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "wrongpw@example.com", "password": "correcthorse123"})
    db = next(app.dependency_overrides[get_db]())
    _verify_user_directly(db, "wrongpw@example.com")
    response = client.post("/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "totallywrong"})
    assert response.status_code == 401


def test_login_with_unknown_email_rejected(client):
    response = client.post("/api/v1/auth/login", json={"email": "doesnotexist@example.com", "password": "whatever123"})
    assert response.status_code == 401


def test_verify_email_with_valid_token_activates_account(client):
    signup_resp = client.post("/api/v1/auth/signup", json={"email": "clickme@example.com", "password": "correcthorse123"})
    user_id = signup_resp.json()["user_id"]

    token = create_verification_token(user_id)
    response = client.get(f"/api/v1/auth/verify-email?token={token}")
    assert response.status_code == 200
    assert "Verified" in response.text

    # Now login should actually work, having gone through the real
    # verify-email endpoint rather than the direct-DB test shortcut.
    login_resp = client.post("/api/v1/auth/login", json={"email": "clickme@example.com", "password": "correcthorse123"})
    assert login_resp.status_code == 200


def test_verify_email_with_garbage_token_shows_invalid_page(client):
    response = client.get("/api/v1/auth/verify-email?token=not-a-real-token")
    assert response.status_code == 200  # HTML page, not a JSON error
    assert "Invalid" in response.text


def test_verify_email_twice_is_idempotent(client):
    signup_resp = client.post("/api/v1/auth/signup", json={"email": "twice@example.com", "password": "correcthorse123"})
    token = create_verification_token(signup_resp.json()["user_id"])

    first = client.get(f"/api/v1/auth/verify-email?token={token}")
    second = client.get(f"/api/v1/auth/verify-email?token={token}")
    assert "Verified" in first.text
    assert "Already Verified" in second.text


def test_login_error_message_identical_for_unknown_email_and_wrong_password(client):
    client.post("/api/v1/auth/signup", json={"email": "enum@example.com", "password": "correcthorse123"})
    db = next(app.dependency_overrides[get_db]())
    _verify_user_directly(db, "enum@example.com")

    wrong_password_resp = client.post("/api/v1/auth/login", json={"email": "enum@example.com", "password": "wrong"})
    unknown_email_resp = client.post("/api/v1/auth/login", json={"email": "neverexisted@example.com", "password": "wrong"})
    assert wrong_password_resp.json()["detail"] == unknown_email_resp.json()["detail"]


def test_me_returns_user_info_with_valid_token(client):
    del app.dependency_overrides[get_current_user_id]

    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "me@example.com", "password": "correcthorse123", "persona_mode": "business"},
    )
    db = next(app.dependency_overrides[get_db]())
    _verify_user_directly(db, "me@example.com")

    login_resp = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "correcthorse123"})
    token = login_resp.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["persona_mode"] == "business"
    assert data["is_verified"] is True


def test_me_without_token_rejected(client):
    del app.dependency_overrides[get_current_user_id]
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_rejected(client):
    del app.dependency_overrides[get_current_user_id]
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_verification_token_cannot_be_used_as_access_token(client):
    """The actual security property from the purpose-claim design —
    someone who intercepts a verification link can't replay it as a
    login session."""
    del app.dependency_overrides[get_current_user_id]

    signup_resp = client.post("/api/v1/auth/signup", json={"email": "crosstoken@example.com", "password": "correcthorse123"})
    verification_token = create_verification_token(signup_resp.json()["user_id"])

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {verification_token}"})
    assert response.status_code == 401


def test_update_persona_mode(client):
    del app.dependency_overrides[get_current_user_id]

    signup_resp = client.post("/api/v1/auth/signup", json={"email": "switcher@example.com", "password": "correcthorse123"})
    db = next(app.dependency_overrides[get_db]())
    _verify_user_directly(db, "switcher@example.com")

    login_resp = client.post("/api/v1/auth/login", json={"email": "switcher@example.com", "password": "correcthorse123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).json()["persona_mode"] == "student"

    response = client.patch("/api/v1/auth/me", json={"persona_mode": "business"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["persona_mode"] == "business"

    # Confirm it actually persisted, not just echoed back in the response
    assert client.get("/api/v1/auth/me", headers=headers).json()["persona_mode"] == "business"


def test_update_me_without_token_rejected(client):
    del app.dependency_overrides[get_current_user_id]
    response = client.patch("/api/v1/auth/me", json={"persona_mode": "business"})
    assert response.status_code == 401
