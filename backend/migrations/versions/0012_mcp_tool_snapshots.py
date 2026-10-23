"""Store bounded MCP tool contracts for later version-pinned grants."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.add_column(
        "mcp_connection",
        sa.Column("tool_snapshots", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("mcp_connection", "tool_snapshots")
