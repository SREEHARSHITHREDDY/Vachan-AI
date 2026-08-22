"""
Tests for the auth layer — signup, login, and the /auth/me check.
Uses the same shared `client` fixture from conftest.py as every other
test file (real in-memory DB per test, real HTTP layer via TestClient).
"""


def test_signup_creates_user_and_returns_token(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "student@example.com", "password": "correcthorse123", "persona_mode": "student"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["persona_mode"] == "student"
    assert "access_token" in data
    assert "user_id" in data


def test_signup_defaults_persona_to_student(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "default@example.com", "password": "correcthorse123"},
    )
    assert response.status_code == 200
    assert response.json()["persona_mode"] == "student"


def test_signup_accepts_professional_and_business_personas(client):
    for persona in ["professional", "business"]:
        response = client.post(
            "/api/v1/auth/signup",
            json={"email": f"{persona}@example.com", "password": "correcthorse123", "persona_mode": persona},
        )
        assert response.status_code == 200
        assert response.json()["persona_mode"] == persona


def test_signup_duplicate_email_rejected(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "dup@example.com", "password": "correcthorse123"},
    )
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "dup@example.com", "password": "differentpassword"},
    )
    assert response.status_code == 409


def test_signup_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "short@example.com", "password": "short"},
    )
    assert response.status_code == 422  # pydantic min_length=8 validation


def test_login_with_correct_credentials(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "login@example.com", "password": "correcthorse123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "correcthorse123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "wrongpw@example.com", "password": "correcthorse123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "totallywrong"},
    )
    assert response.status_code == 401


def test_login_with_unknown_email_rejected(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "doesnotexist@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401


def test_login_error_message_identical_for_unknown_email_and_wrong_password(client):
    """Guards against user enumeration — see the router's own comment on
    why this specific behavior matters."""
    client.post(
        "/api/v1/auth/signup",
        json={"email": "enum@example.com", "password": "correcthorse123"},
    )
    wrong_password_resp = client.post(
        "/api/v1/auth/login", json={"email": "enum@example.com", "password": "wrong"}
    )
    unknown_email_resp = client.post(
        "/api/v1/auth/login", json={"email": "neverexisted@example.com", "password": "wrong"}
    )
    assert wrong_password_resp.json()["detail"] == unknown_email_resp.json()["detail"]


def test_me_returns_user_info_with_valid_token(client):
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "me@example.com", "password": "correcthorse123", "persona_mode": "business"},
    )
    token = signup_resp.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["persona_mode"] == "business"


def test_me_without_token_rejected(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_rejected(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_malformed_header_rejected(client):
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "malformed@example.com", "password": "correcthorse123"},
    )
    token = signup_resp.json()["access_token"]
    # Missing "Bearer " prefix
    response = client.get("/api/v1/auth/me", headers={"Authorization": token})
    assert response.status_code == 401
