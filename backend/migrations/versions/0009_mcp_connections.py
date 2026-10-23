"""Encrypted workspace credentials for operator-curated MCP servers."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.create_table(
        "mcp_connection",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("server_id", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary()),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("verified_tools", JSONB(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "server_id"),
        sa.CheckConstraint("state IN ('active','revoked')", name="valid_mcp_state"),
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mcp_connection TO ff_app;
        REVOKE TRUNCATE ON TABLE mcp_connection FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_table("mcp_connection")
