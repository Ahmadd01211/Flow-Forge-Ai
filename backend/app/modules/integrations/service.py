import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.integrations.models import IntegrationConnection, SecretReference
from app.modules.integrations.schemas import DefaultModelUpdate, ProviderCredential
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.providers.registry import PROVIDERS, Provider, verify_key


def require_admin(member: WorkspaceMember) -> None:
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", "An owner or admin role is required for provider credentials.")


def get_connection(
    db: Session, workspace_id: uuid.UUID, provider: Provider = "openai", lock: bool = False
) -> IntegrationConnection | None:
    query = select(IntegrationConnection).where(
        IntegrationConnection.workspace_id == workspace_id,
        IntegrationConnection.provider == provider,
    )
    return db.scalar(query.with_for_update() if lock else query)


def list_connections(db: Session, workspace_id: uuid.UUID) -> dict:
    return {
        "items": list(
            db.scalars(
                select(IntegrationConnection)
                .where(IntegrationConnection.workspace_id == workspace_id)
                .order_by(IntegrationConnection.provider)
            )
        )
    }


def upsert_connection(
    request: Request,
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: ProviderCredential,
    provider: Provider = "openai",
) -> IntegrationConnection:
    key = body.api_key.get_secret_value()
    models = verify_key(provider, key)
    master = load_master_key(request.app.state.settings.credential_key_path)
    # The workspace row serializes first creation and rotation for this tenant.
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    connection = get_connection(db, workspace_id, provider, lock=True)
    if connection is None:
        connection = IntegrationConnection(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            provider=provider,
            display_name=PROVIDERS[provider][0],
            state="active",
            credential_generation=1,
            masked_hint=f"••••{key[-4:]}",
            verified_models=models,
            default_model_id=None,
            verified_at=datetime.now(UTC),
            revoked_at=None,
        )
        db.add(connection)
        action = "provider.connected"
    else:
        connection.credential_generation += 1
        connection.state = "active"
        connection.masked_hint = f"••••{key[-4:]}"
        connection.verified_models = models
        if connection.default_model_id not in models:
            connection.default_model_id = None
        connection.verified_at = datetime.now(UTC)
        connection.revoked_at = None
        db.execute(delete(SecretReference).where(SecretReference.connection_id == connection.id))
        action = "provider.rotated"
    nonce, ciphertext = encrypt_secret(
        master, workspace_id, connection.id, connection.credential_generation, key
    )
    db.add(
        SecretReference(
            workspace_id=workspace_id,
            connection_id=connection.id,
            generation=connection.credential_generation,
            key_version=1,
            nonce=nonce,
            ciphertext=ciphertext,
        )
    )
    record(
        db,
        workspace_id,
        actor_id,
        action,
        connection.id,
        {
            "provider": provider,
            "credential_generation": connection.credential_generation,
            "verified_models": models,
        },
    )
    db.commit()
    return connection


def set_default_model(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    provider: Provider,
    body: DefaultModelUpdate,
) -> IntegrationConnection:
    connection = get_connection(db, workspace_id, provider, lock=True)
    if not connection or connection.state != "active":
        fail(409, "PROVIDER_REQUIRED", "Connect this provider before selecting a model.")
    if body.model_id not in connection.verified_models:
        fail(422, "MODEL_UNSUPPORTED", "Choose a model from this provider's verified list.")
    if connection.default_model_id != body.model_id:
        connection.default_model_id = body.model_id
        record(
            db,
            workspace_id,
            actor_id,
            "provider.default_model_changed",
            connection.id,
            {"provider": provider, "model_id": body.model_id},
        )
        db.commit()
    return connection


def revoke_connection(
    db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, provider: Provider = "openai"
) -> IntegrationConnection:
    connection = get_connection(db, workspace_id, provider, lock=True)
    if not connection:
        fail(404, "NOT_FOUND", "Provider connection not found.")
    if connection.state != "revoked":
        db.execute(delete(SecretReference).where(SecretReference.connection_id == connection.id))
        connection.state = "revoked"
        connection.verified_models = []
        connection.default_model_id = None
        connection.masked_hint = ""
        connection.revoked_at = datetime.now(UTC)
        record(
            db, workspace_id, actor_id, "provider.revoked", connection.id, {"provider": provider}
        )
        db.commit()
    return connection


def refresh_models(
    request: Request, db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, provider: Provider
) -> IntegrationConnection:
    connection = get_connection(db, workspace_id, provider, lock=True)
    if not connection or connection.state != "active":
        fail(409, "PROVIDER_REQUIRED", "Connect this provider before refreshing models.")
    secret = db.scalar(
        select(SecretReference).where(
            SecretReference.connection_id == connection.id,
            SecretReference.generation == connection.credential_generation,
        )
    )
    if not secret:
        fail(409, "PROVIDER_REQUIRED", "Reconnect this provider to restore its credential.")
    key = decrypt_secret(
        load_master_key(request.app.state.settings.credential_key_path),
        workspace_id,
        connection.id,
        secret.generation,
        secret.nonce,
        secret.ciphertext,
    )
    # A failed lookup leaves the saved key, generation, catalog and defaults intact.
    models = verify_key(provider, key)
    connection.verified_models = models
    connection.verified_at = datetime.now(UTC)
    if connection.default_model_id not in models:
        connection.default_model_id = None
    record(
        db,
        workspace_id,
        actor_id,
        "provider.models_refreshed",
        connection.id,
        {"provider": provider, "model_count": len(models)},
    )
    db.commit()
    return connection
