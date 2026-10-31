"""Approved fixed HTTP tools with encrypted header credentials."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"


def upgrade():
    op.create_table(
        "http_tool",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary()),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("state IN ('active','revoked')", name="http_tool_state"),
        sa.CheckConstraint("generation >= 1", name="http_tool_generation"),
    )
    op.create_index("ix_http_tool_workspace_id", "http_tool", ["workspace_id"])
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON http_tool TO ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_table("http_tool")
