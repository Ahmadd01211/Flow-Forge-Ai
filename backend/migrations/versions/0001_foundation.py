"""Identity, owned workspaces and mutable definition drafts only."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "user_session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "workspace",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "workspace_member",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False, index=True
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id"),
        sa.CheckConstraint("role IN ('owner','admin','editor','viewer')", name="valid_role"),
    )
    for name in ["agent", "workflow"]:
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False, index=True
            ),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("config" if name == "agent" else "graph", postgresql.JSONB(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            *([sa.Column("archived_at", sa.DateTime(timezone=True))] if name == "agent" else []),
            sa.UniqueConstraint("workspace_id", "id"),
            sa.CheckConstraint("revision >= 1", name="positive_revision"),
        )
        op.create_index(
            f"ix_{name}_workspace_updated",
            name,
            ["workspace_id", sa.text("updated_at DESC"), sa.text("id DESC")],
        )


def downgrade() -> None:
    for name in ["workflow", "agent", "workspace_member", "user_session", "workspace", "app_user"]:
        op.drop_table(name)
