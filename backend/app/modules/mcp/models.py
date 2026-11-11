import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class McpConnection(Base):
    __tablename__ = "mcp_connection"
    __table_args__ = (
        UniqueConstraint("workspace_id", "server_id"),
        CheckConstraint("state IN ('active','revoked')", name="valid_mcp_state"),
        # url/name are set only for servers a workspace admin added; NULL means operator catalog.
        CheckConstraint(
            "(url IS NULL AND name IS NULL) OR (url LIKE 'https://%' AND name IS NOT NULL)",
            name="workspace_server_identity",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    server_id: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    verified_tools: Mapped[list] = mapped_column(JSONB, nullable=False)
    tool_snapshots: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # {tool_name: "allow" | "block"}; absent tools use the default from registry.policy().
    tool_policies: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
