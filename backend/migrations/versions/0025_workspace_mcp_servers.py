"""Workspace-added MCP servers and per-tool allow/block policies."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025"
down_revision = "0024"
branch_labels = depends_on = None


def upgrade():
    op.add_column("mcp_connection", sa.Column("name", sa.String(100)))
    op.add_column("mcp_connection", sa.Column("url", sa.String(2048)))
    op.add_column(
        "mcp_connection",
        sa.Column("tool_policies", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_check_constraint(
        "workspace_server_identity",
        "mcp_connection",
        "(url IS NULL AND name IS NULL) OR (url LIKE 'https://%' AND name IS NOT NULL)",
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text("SELECT EXISTS(SELECT 1 FROM mcp_connection WHERE url IS NOT NULL)")):
        raise RuntimeError("Workspace MCP servers exist; agents and workflows may depend on them.")
    if bind.scalar(text("SELECT EXISTS(SELECT 1 FROM mcp_connection WHERE tool_policies <> '{}')")):
        raise RuntimeError("MCP tool policies exist; dropping them could re-enable blocked tools.")
    op.drop_constraint(
        op.f("ck_mcp_connection_workspace_server_identity"), "mcp_connection", type_="check"
    )
    op.drop_column("mcp_connection", "tool_policies")
    op.drop_column("mcp_connection", "url")
    op.drop_column("mcp_connection", "name")
