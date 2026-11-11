"""Durable approval state for write-capable agent MCP calls."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0033"
down_revision = "0032"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("valid_agent_run_state", "agent_run", type_="check")
    op.create_check_constraint(
        "valid_agent_run_state",
        "agent_run",
        "state IN ('queued','running','waiting','completed','failed','cancelled')",
    )
    op.drop_index("ix_agent_run_active_workspace", table_name="agent_run")
    op.create_index(
        "ix_agent_run_active_workspace",
        "agent_run",
        ["workspace_id"],
        postgresql_where=text("state IN ('queued','running','waiting')"),
    )
    op.create_table(
        "agent_tool_approval",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("app_user.id")),
        sa.Column("tool_key", sa.String(80), nullable=False),
        sa.Column("server_id", sa.String(40), nullable=False),
        sa.Column("server_name", sa.String(100), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("tool_description", sa.String(300), nullable=False, server_default=""),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("call_claimed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]
        ),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','expired','cancelled','claimed','ready','resuming','uncertain','completed')",
            name="valid_agent_tool_approval_state",
        ),
    )
    op.create_index(
        "ix_agent_tool_approval_pending",
        "agent_tool_approval",
        ["expires_at"],
        postgresql_where=text("state = 'pending'"),
    )
    op.create_index(
        "uq_agent_tool_approval_active_run",
        "agent_tool_approval",
        ["run_id"],
        unique=True,
        postgresql_where=text("state IN ('pending','approved','claimed','ready','resuming','uncertain')"),
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_tool_approval TO ff_app;
        REVOKE TRUNCATE ON TABLE agent_tool_approval FROM ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_table("agent_tool_approval")
    op.drop_index("ix_agent_run_active_workspace", table_name="agent_run")
    op.create_index(
        "ix_agent_run_active_workspace",
        "agent_run",
        ["workspace_id"],
        postgresql_where=text("state IN ('queued','running')"),
    )
    op.drop_constraint("valid_agent_run_state", "agent_run", type_="check")
    op.create_check_constraint(
        "valid_agent_run_state",
        "agent_run",
        "state IN ('queued','running','completed','failed','cancelled')",
    )
