import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.credentials import decrypt_secret, load_master_key
from app.modules.identity.mail import deliver_pending
from app.modules.identity.models import AccountToken, EmailDelivery
from app.modules.workspaces.models import WorkspaceInvitation, WorkspaceMember
from tests.conftest import headers, register


def message(client, recipient, subject):
    with client.app.state.sessions() as db:
        rows = db.scalars(select(EmailDelivery)).all()
        messages = [
            json.loads(
                decrypt_secret(
                    load_master_key(client.app.state.settings.credential_key_path),
                    r.user_id,
                    r.id,
                    1,
                    r.nonce,
                    r.ciphertext,
                )
            )
            for r in rows
        ]
        return next(
            m for m in reversed(messages) if m["to"] == recipient and m["subject"] == subject
        )


def token(client, recipient, subject):
    return message(client, recipient, subject)["text"].split("#")[1].split()[0]


def verify(client, email):
    result = client.post(
        "/api/v1/auth/verify-email",
        headers=headers(client),
        json={"token": token(client, email, "Verify your email")},
    )
    assert result.status_code == 200, result.text


def test_registration_verification_and_encrypted_delivery(client, owner, db):
    assert not owner["user"]["email_verified"]
    raw = token(client, "owner@example.com", "Verify your email")
    saved = db.scalar(select(AccountToken))
    assert saved.token_hash != raw
    mail = db.scalar(select(EmailDelivery))
    assert raw.encode() not in mail.ciphertext
    verify(client, "owner@example.com")
    assert client.get("/api/v1/auth/session").json()["user"]["email_verified"]
    assert (
        client.post(
            "/api/v1/auth/verify-email", headers=headers(client), json={"token": raw}
        ).status_code
        == 400
    )
    delivered = []
    deliver_pending(db, client.app.state.settings, send=delivered.append)
    deliver_pending(db, client.app.state.settings, send=delivered.append)
    assert len(delivered) == 1
    assert raw in delivered[0].get_content()


def test_recovery_generic_response_and_single_use_revokes_sessions(client, owner):
    base = "/api/v1/auth"

    def forgot(email):
        return client.post(
            f"{base}/forgot-password", headers=headers(client), json={"email": email}
        )

    assert forgot("unknown@example.com").json() == forgot("owner@example.com").json()
    raw = token(client, "owner@example.com", "Reset your password")
    result = client.post(
        f"{base}/reset-password",
        headers=headers(client),
        json={"token": raw, "password": "a-new-unique-password"},
    )
    assert result.status_code == 200
    assert client.get(f"{base}/session").status_code == 401
    assert (
        client.post(
            f"{base}/reset-password",
            headers=headers(client),
            json={"token": raw, "password": "another-unique-password"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{base}/login",
            headers=headers(client),
            json={"email": "owner@example.com", "password": "a-unique-password-2026"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{base}/login",
            headers=headers(client),
            json={"email": "owner@example.com", "password": "a-new-unique-password"},
        ).status_code
        == 200
    )


def test_expired_wrong_purpose_resend_and_csrf(client, owner, db):
    raw = token(client, "owner@example.com", "Verify your email")
    assert (
        client.post(
            "/api/v1/auth/reset-password",
            headers=headers(client),
            json={"token": raw, "password": "another-long-password"},
        ).status_code
        == 400
    )
    row = db.scalar(select(AccountToken))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/v1/auth/verify-email", headers=headers(client), json={"token": raw}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/auth/verification-email", headers=headers(client)).status_code == 200
    )
    verify(client, "owner@example.com")
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"}).status_code
        == 403
    )


def test_password_change_and_logout_all(client, owner):
    base = "/api/v1/auth"
    assert (
        client.post(
            f"{base}/change-password",
            headers=headers(client),
            json={"current_password": "wrong", "password": "a-new-unique-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{base}/change-password",
            headers=headers(client),
            json={
                "current_password": "a-unique-password-2026",
                "password": "a-new-unique-password",
            },
        ).status_code
        == 200
    )
    assert client.get(f"{base}/session").status_code == 401
    assert (
        client.post(
            f"{base}/login",
            headers=headers(client),
            json={"email": "owner@example.com", "password": "a-new-unique-password"},
        ).status_code
        == 200
    )
    assert client.post(f"{base}/logout-all", headers=headers(client)).status_code == 200
    assert client.get(f"{base}/session").status_code == 401


def test_invite_accept_role_changes_and_immediate_revocation(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    data = {"email": "teammate@example.com", "role": "editor"}
    assert client.post(f"{base}/invitations", headers=headers(client), json=data).status_code == 403
    verify(client, "owner@example.com")
    created = client.post(f"{base}/invitations", headers=headers(client), json=data)
    assert created.status_code == 201, created.text
    raw = token(client, data["email"], "Your FlowForge workspace invitation")
    assert "token" not in created.json()
    client.cookies.clear()
    teammate = register(client, data["email"])
    accept = "/api/v1/workspaces/accept-invitation"
    assert client.post(accept, headers=headers(client), json={"token": raw}).status_code == 403
    verify(client, data["email"])
    assert client.post(accept, headers=headers(client), json={"token": raw}).status_code == 200
    assert client.post(accept, headers=headers(client), json={"token": raw}).status_code == 400
    assert client.get(base).status_code == 200
    assert client.get(f"{base}/members").status_code == 403
    teammate_cookies = dict(client.cookies)
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=headers(client),
            json={"email": "owner@example.com", "password": "a-unique-password-2026"},
        ).status_code
        == 200
    )
    rows = client.get(f"{base}/members").json()["items"]
    owner_member = next(r for r in rows if r["role"] == "owner")
    target = next(r for r in rows if r["user_id"] == teammate["user"]["id"])
    assert (
        client.patch(
            f"{base}/members/{owner_member['id']}", headers=headers(client), json={"role": "editor"}
        ).status_code
        == 409
    )
    assert (
        client.delete(f"{base}/members/{owner_member['id']}", headers=headers(client)).status_code
        == 409
    )
    assert (
        client.patch(
            f"{base}/members/{target['id']}", headers=headers(client), json={"role": "viewer"}
        ).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.update(teammate_cookies)
    assert (
        client.post(
            f"{base}/workflows", headers=headers(client), json={"name": "Denied"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "owner@example.com", "password": "a-unique-password-2026"},
    )
    assert (
        client.delete(f"{base}/members/{target['id']}", headers=headers(client)).status_code == 200
    )
    client.cookies.clear()
    client.cookies.update(teammate_cookies)
    assert client.get(base).status_code == 404


def test_invitation_revoked_expired_wrong_user_and_workspace_isolation(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    verify(client, "owner@example.com")
    created = client.post(
        f"{base}/invitations",
        headers=headers(client),
        json={"email": "someone@example.com", "role": "viewer"},
    ).json()
    raw = token(client, "someone@example.com", "Your FlowForge workspace invitation")
    assert (
        client.post(
            "/api/v1/workspaces/accept-invitation", headers=headers(client), json={"token": raw}
        ).status_code
        == 403
    )
    assert (
        client.delete(f"{base}/invitations/{created['id']}", headers=headers(client)).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/workspaces/accept-invitation", headers=headers(client), json={"token": raw}
        ).status_code
        == 400
    )
    new = client.post(
        f"{base}/invitations",
        headers=headers(client),
        json={"email": "someone@example.com", "role": "viewer"},
    ).json()
    row = db.get(WorkspaceInvitation, uuid.UUID(new["id"]))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get(f"{base}/invitations").json()["items"] == []
    other = client.post(
        "/api/v1/workspaces", headers=headers(client), json={"name": "Second workspace"}
    )
    assert other.status_code == 201
    own_member = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == uuid.UUID(workspace))
    )
    assert (
        client.patch(
            f"/api/v1/workspaces/{other.json()['id']}/members/{own_member.id}",
            headers=headers(client),
            json={"role": "editor"},
        ).status_code
        == 404
    )
    assert client.patch(base, headers=headers(client), json={"name": "Renamed"}).status_code == 200
    client.cookies.clear()
    register(client, "stranger@example.com")
    assert client.get(f"{base}/members").status_code == 404


def test_admin_permissions_ownership_transfer_and_invitation_replacement(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    verify(client, "owner@example.com")
    payload = {"email": "admin@example.com", "role": "admin"}
    assert (
        client.post(f"{base}/invitations", headers=headers(client), json=payload).status_code == 201
    )
    first = token(client, payload["email"], "Your FlowForge workspace invitation")
    assert (
        client.post(f"{base}/invitations", headers=headers(client), json=payload).status_code == 201
    )
    second = token(client, payload["email"], "Your FlowForge workspace invitation")
    client.cookies.clear()
    admin = register(client, payload["email"])
    verify(client, payload["email"])
    accept = "/api/v1/workspaces/accept-invitation"
    assert client.post(accept, headers=headers(client), json={"token": first}).status_code == 400
    assert client.post(accept, headers=headers(client), json={"token": second}).status_code == 200
    members = client.get(f"{base}/members").json()["items"]
    original_owner = next(m for m in members if m["role"] == "owner")
    admin_member = next(m for m in members if m["user_id"] == admin["user"]["id"])
    assert (
        client.patch(
            f"{base}/members/{original_owner['id']}",
            headers=headers(client),
            json={"role": "editor"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{base}/members/{admin_member['id']}", headers=headers(client), json={"role": "owner"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/invitations",
            headers=headers(client),
            json={"email": "new-admin@example.com", "role": "admin"},
        ).status_code
        == 403
    )
    assert (
        client.patch(base, headers=headers(client), json={"name": "Admin renamed"}).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/invitations",
            headers=headers(client),
            json={"email": "reader@example.com", "role": "viewer"},
        ).status_code
        == 201
    )
    client.cookies.clear()
    client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "owner@example.com", "password": "a-unique-password-2026"},
    )
    assert (
        client.patch(
            f"{base}/members/{admin_member['id']}", headers=headers(client), json={"role": "owner"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{base}/members/{original_owner['id']}",
            headers=headers(client),
            json={"role": "editor"},
        ).status_code
        == 200
    )
    assert client.get(f"{base}/members").status_code == 403


def test_mail_failure_retries_without_losing_message(client, owner, db):
    def fail_delivery(_):
        raise OSError("simulated transport outage")

    deliver_pending(db, client.app.state.settings, send=fail_delivery)
    row = db.scalar(select(EmailDelivery))
    assert row.attempts == 1 and row.sent_at is None
    assert row.next_attempt_at > datetime.now(UTC)
    sent = []
    deliver_pending(db, client.app.state.settings, send=sent.append)
    assert not sent
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    deliver_pending(db, client.app.state.settings, send=sent.append)
    assert len(sent) == 1 and row.sent_at is not None


def test_real_smtp_delivery_to_development_inbox(client, owner, db):
    deliver_pending(db, client.app.state.settings)
    row = db.scalar(select(EmailDelivery))
    assert row.sent_at is not None and row.attempts == 1
