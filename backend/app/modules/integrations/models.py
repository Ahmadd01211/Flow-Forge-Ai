import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IntegrationConnection(Base):
    __tablename__ = "integration_connection"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_connection_workspace_id"),
        UniqueConstraint("workspace_id", "provider", name="uq_connection_provider"),
        CheckConstraint("state IN ('active','revoked')", name="valid_connection_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"))
    provider: Mapped[str] = mapped_column(String(40))
    display_name: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20))
    credential_generation: Mapped[int] = mapped_column(Integer)
    masked_hint: Mapped[str] = mapped_column(String(20))
    verified_models: Mapped[list] = mapped_column(JSONB)
    default_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SecretReference(Base):
    __tablename__ = "secret_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["integration_connection.workspace_id", "integration_connection.id"],
        ),
        UniqueConstraint("connection_id", "generation"),
        CheckConstraint("generation >= 1 AND key_version = 1", name="valid_secret_generation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    connection_id: Mapped[uuid.UUID] = mapped_column()
    generation: Mapped[int] = mapped_column(Integer)
    key_version: Mapped[int] = mapped_column(Integer)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
