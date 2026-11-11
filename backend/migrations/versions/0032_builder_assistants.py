"""Hidden system agents that power the builder's AI helpers (one per workspace and task)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0032"
down_revision = "0031"
branch_labels = depends_on = None


def upgrade():
    op.add_column("agent", sa.Column("system_role", sa.String(40), nullable=True))
    op.create_check_constraint(
        "system_role_alone", "agent", "system_role IS NULL OR (workflow_id IS NULL AND playground_for IS NULL)"
    )
    op.create_index(
        "uq_agent_system_role", "agent", ["workspace_id", "system_role"], unique=True,
        postgresql_where=text("system_role IS NOT NULL"),
    )


def downgrade():
    op.drop_index("uq_agent_system_role", table_name="agent")
    op.drop_constraint(op.f("ck_agent_system_role_alone"), "agent", type_="check")
    op.drop_column("agent", "system_role")
