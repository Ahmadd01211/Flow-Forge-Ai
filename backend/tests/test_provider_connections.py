import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import func, select

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.modules.agents.models import AgentVersion
from app.modules.audit.models import AuditEvent
from app.modules.integrations.models import IntegrationConnection, SecretReference
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register

KEY_A = "sk-test-provider-credential-aaaaaaaa"
KEY_B = "sk-test-provider-credential-bbbbbbbb"


def connect(client, workspace_id, key=KEY_A):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/integrations/provider",
        headers=headers(client),
        json={"api_key": key},
    )


def test_key_is_encrypted_rotated_and_revoked(client, owner, db, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"]
    )
    workspace = owner["workspaces"][0]["id"]
    created = connect(client, workspace)
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["state"] == "active" and data["credential_generation"] == 1
    assert data["verified_models"] == ["gpt-5-mini"]
    assert KEY_A not in created.text and data["masked_hint"] == "••••aaaa"
    secret = db.scalar(select(SecretReference))
    assert KEY_A.encode() not in secret.ciphertext
    assert (
        decrypt_secret(
            load_master_key(client.app.state.settings.credential_key_path),
            uuid.UUID(workspace),
            secret.connection_id,
            1,
            secret.nonce,
            secret.ciphertext,
        )
        == KEY_A
    )
    rotated = connect(client, workspace, KEY_B).json()
    assert rotated["id"] == data["id"] and rotated["credential_generation"] == 2
    assert db.scalar(select(func.count()).select_from(SecretReference)) == 1
    assert (
        client.delete(
            f"/api/v1/workspaces/{workspace}/integrations/provider", headers=headers(client)
        ).json()["state"]
        == "revoked"
    )
    assert db.scalar(select(func.count()).select_from(SecretReference)) == 0
    assert {row.action for row in db.scalars(select(AuditEvent))} == {
        "provider.connected",
        "provider.rotated",
        "provider.revoked",
    }


def test_failed_verification_is_not_stored_or_echoed(client, owner, db, monkeypatch):
    from app.core.errors import fail

    def reject(_provider, _key):
        fail(422, "PROVIDER_CREDENTIAL_REJECTED", "The provider rejected this credential.")

    monkeypatch.setattr("app.modules.integrations.service.verify_key", reject)
    response = connect(client, owner["workspaces"][0]["id"])
    assert response.status_code == 422 and KEY_A not in response.text
    assert db.scalar(select(func.count()).select_from(IntegrationConnection)) == 0
    assert db.scalar(select(func.count()).select_from(SecretReference)) == 0


def test_only_admin_manages_credentials_and_tenant_boundary(client, owner, db, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"]
    )
    workspace = owner["workspaces"][0]["id"]
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    assert connect(client, workspace).status_code == 403
    assert client.get(f"/api/v1/workspaces/{workspace}/integrations").status_code == 200
    member.role = "owner"
    db.commit()
    assert connect(client, workspace).status_code == 200
    client.cookies.clear()
    other = register(client, "other-provider@example.com")
    assert client.get(f"/api/v1/workspaces/{workspace}/integrations").status_code == 404
    assert connect(client, workspace).status_code == 404
    assert (
        client.get(f"/api/v1/workspaces/{other['workspaces'][0]['id']}/integrations").json()[
            "items"
        ]
        == []
    )


def test_publish_requires_verified_model_and_strict_output(client, owner, db, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"]
    )
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/agents"
    created = client.post(
        base,
        headers=headers(client),
        json={
            "name": "Triage",
            "config": {"instructions": "Classify a ticket."},
        },
    ).json()
    path = f"{base}/{created['id']}/versions"
    assert (
        client.post(path, headers=headers(client), json={"expected_revision": 1}).status_code == 409
    )
    connection = connect(client, workspace).json()
    assert (
        client.post(path, headers=headers(client), json={"expected_revision": 1}).status_code == 422
    )
    config = {**created["config"], "model_id": "gpt-5-mini"}
    changed = client.patch(
        f"{base}/{created['id']}",
        headers=headers(client),
        json={
            "name": "Triage",
            "description": "",
            "config": config,
            "expected_revision": 1,
        },
    ).json()
    published = client.post(path, headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text
    version = published.json()
    assert version["purpose"] == "published" and version["connection_id"] == connection["id"]
    assert version["credential_generation"] == 1
    assert (
        client.post(path, headers=headers(client), json={"expected_revision": 2}).status_code == 200
    )
    assert connect(client, workspace, KEY_B).json()["credential_generation"] == 2
    assert client.get(f"{path}/{version['id']}").json()["credential_generation"] == 1
    assert db.scalar(select(func.count()).select_from(AgentVersion)) == 1
    bad = {
        **changed["config"],
        "output_schema": {
            "type": "object",
            "properties": {"priority": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
    }
    updated = client.patch(
        f"{base}/{created['id']}",
        headers=headers(client),
        json={
            "name": "Triage",
            "description": "",
            "config": bad,
            "expected_revision": 2,
        },
    ).json()
    denied = client.post(
        path, headers=headers(client), json={"expected_revision": updated["revision"]}
    )
    assert (
        denied.status_code == 422 and denied.json()["error"]["code"] == "OUTPUT_SCHEMA_UNSUPPORTED"
    )
    client.delete(f"/api/v1/workspaces/{workspace}/integrations/provider", headers=headers(client))
    assert (
        client.post(path, headers=headers(client), json={"expected_revision": 3}).status_code == 409
    )


def test_ciphertext_cannot_move_between_workspaces():
    key = b"k" * 32
    workspace, connection = uuid.uuid4(), uuid.uuid4()
    nonce, encrypted = encrypt_secret(key, workspace, connection, 1, KEY_A)
    with pytest.raises(InvalidTag):
        decrypt_secret(key, uuid.uuid4(), connection, 1, nonce, encrypted)


def test_multiple_providers_are_isolated_and_publication_selects_one(
    client, owner, db, monkeypatch
):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key",
        lambda provider, _key: ["gpt-5-mini"] if provider == "openai" else ["deepseek-chat"],
    )
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    openai = client.post(
        f"{base}/integrations/providers/openai",
        headers=headers(client),
        json={"api_key": KEY_A},
    )
    deepseek = client.post(
        f"{base}/integrations/providers/deepseek",
        headers=headers(client),
        json={"api_key": KEY_B},
    )
    assert openai.status_code == 200 and deepseek.status_code == 200
    assert {item["provider"] for item in client.get(f"{base}/integrations").json()["items"]} == {
        "openai",
        "deepseek",
    }
    agent = client.post(
        f"{base}/agents",
        headers=headers(client),
        json={
            "name": "Triage",
            "config": {
                "instructions": "Classify.",
                "provider": "deepseek",
                "model_id": "deepseek-chat",
            },
        },
    ).json()
    version = client.post(
        f"{base}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    )
    assert version.status_code == 201, version.text
    assert version.json()["connection_id"] == deepseek.json()["id"]
    assert version.json()["config"]["provider"] == "deepseek"
    client.delete(f"{base}/integrations/providers/deepseek", headers=headers(client))
    assert client.get(f"{base}/integrations").json()["items"][0]["provider"] == "deepseek"
    assert db.scalar(select(func.count()).select_from(SecretReference)) == 1


def test_default_model_is_verified_and_scoped_to_provider(client, owner, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key",
        lambda provider, _key: (
            ["gpt-5-mini", "gpt-5"] if provider == "openai" else ["deepseek-chat"]
        ),
    )
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/integrations/providers"
    assert (
        client.patch(
            f"{base}/openai/default-model", headers=headers(client), json={"model_id": "gpt-5"}
        ).status_code
        == 409
    )
    assert (
        client.post(f"{base}/openai", headers=headers(client), json={"api_key": KEY_A}).status_code
        == 200
    )
    assert (
        client.patch(
            f"{base}/openai/default-model",
            headers=headers(client),
            json={"model_id": "deepseek-chat"},
        ).status_code
        == 422
    )
    chosen = client.patch(
        f"{base}/openai/default-model", headers=headers(client), json={"model_id": "gpt-5"}
    )
    assert chosen.status_code == 200 and chosen.json()["default_model_id"] == "gpt-5"
    assert connect(client, workspace, KEY_B).json()["default_model_id"] == "gpt-5"
    client.delete(f"{base}/openai", headers=headers(client))
    assert (
        client.get(f"/api/v1/workspaces/{workspace}/integrations").json()["items"][0][
            "default_model_id"
        ]
        is None
    )
