from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.modules.identity.models import User, UserSession
from tests.conftest import headers


def test_registration_session_and_logout(client, owner, db):
    assert owner["workspaces"][0]["role"] == "owner"
    assert client.get("/api/v1/auth/session").status_code == 200
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    record = db.scalar(select(UserSession))
    assert record.token_hash != client.cookies.get("ff_session_dev")
    result = client.post("/api/v1/auth/logout", headers=headers(client))
    assert result.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_origin_and_csrf_are_required(client):
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    body = {"email": "alex@example.com", "password": "secret-password"}
    assert client.post("/api/v1/auth/login", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/login",
            json=body,
            headers={"Origin": "https://evil.example", "X-CSRF-Token": token},
        ).status_code
        == 403
    )


def test_validation_never_echoes_password(client):
    secret = "do-not-echo-me"
    response = client.post(
        "/api/v1/auth/register", headers=headers(client), json={"email": "bad", "password": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert response.json()["error"]["request_id"]


def test_expired_session_is_rejected(client, owner, db):
    row = db.scalar(select(UserSession))
    row.absolute_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/session").status_code == 401


def test_login_rotates_session_and_wrong_credentials_are_generic(client, owner, db):
    original = client.cookies.get("ff_session_dev")
    wrong = client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "owner@example.com", "password": "wrong"},
    )
    absent = client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "missing@example.com", "password": "wrong"},
    )
    assert wrong.status_code == absent.status_code == 401
    assert wrong.json()["error"]["message"] == absent.json()["error"]["message"]
    success = client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "owner@example.com", "password": "a-unique-password-2026"},
    )
    assert success.status_code == 200
    assert client.cookies.get("ff_session_dev") != original


def test_auth_rate_limited(client):
    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            headers=headers(client),
            json={"email": "missing@example.com", "password": "wrong"},
        )
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=headers(client),
            json={"email": "missing@example.com", "password": "wrong"},
        ).status_code
        == 429
    )
