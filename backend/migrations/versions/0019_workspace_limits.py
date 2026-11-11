"""Workspace admission limits and workflow reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade():
    op.create_index(
        "ix_agent_run_active_workspace",
        "agent_run",
        ["workspace_id"],
        postgresql_where=sa.text("state IN ('queued','running')"),
    )
    op.create_index(
        "ix_workflow_run_active_workspace",
        "workflow_run",
        ["workspace_id"],
        postgresql_where=sa.text("state IN ('queued','running')"),
    )
    op.add_column(
        "workspace",
        sa.Column("daily_budget_usd", sa.Numeric(13, 8), nullable=False, server_default="10"),
    )
    op.add_column(
        "workspace",
        sa.Column("daily_run_limit", sa.Integer(), nullable=False, server_default="1000"),
    )
    op.add_column(
        "workspace", sa.Column("active_run_limit", sa.Integer(), nullable=False, server_default="4")
    )
    op.add_column(
        "workspace", sa.Column("quota_revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint(
        "workspace_daily_budget", "workspace", "daily_budget_usd >= 0 AND daily_budget_usd <= 10000"
    )
    op.create_check_constraint(
        "workspace_daily_run_limit", "workspace", "daily_run_limit BETWEEN 1 AND 10000"
    )
    op.create_check_constraint(
        "workspace_active_run_limit", "workspace", "active_run_limit BETWEEN 1 AND 4"
    )
    op.create_check_constraint("workspace_quota_revision", "workspace", "quota_revision >= 1")
    op.add_column(
        "workflow_run",
        sa.Column("reserved_max_usd", sa.Numeric(14, 8), nullable=False, server_default="0"),
    )
    # Existing queued/running paid workflows must participate in admission after upgrade.
    op.execute("""UPDATE workflow_run r SET reserved_max_usd = (v.graph->'limits'->>'max_cost_usd')::numeric
        FROM workflow_version v WHERE r.version_id=v.id AND r.state IN ('queued','running')
        AND EXISTS (SELECT 1 FROM jsonb_array_elements(v.graph->'nodes') n WHERE n->>'type'='agent')""")


def downgrade():
    op.drop_index("ix_agent_run_active_workspace", table_name="agent_run")
    op.drop_index("ix_workflow_run_active_workspace", table_name="workflow_run")
    op.drop_column("workflow_run", "reserved_max_usd")
    for name in (
        "workspace_daily_budget",
        "workspace_daily_run_limit",
        "workspace_active_run_limit",
        "workspace_quota_revision",
    ):
        op.drop_constraint(name, "workspace", type_="check")
    for name in ("daily_budget_usd", "daily_run_limit", "active_run_limit", "quota_revision"):
        op.drop_column("workspace", name)
