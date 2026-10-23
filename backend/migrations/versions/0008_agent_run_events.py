"""Metadata-only agent harness trace."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.create_table(
        "agent_run_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tool_key", sa.String(80)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]
        ),
        sa.UniqueConstraint("run_id", "sequence"),
    )
    op.create_index(
        "ix_agent_run_event_run", "agent_run_event", ["workspace_id", "run_id", "sequence"]
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT ON TABLE agent_run_event TO ff_app;
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE agent_run_event FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_index("ix_agent_run_event_run", table_name="agent_run_event")
    op.drop_table("agent_run_event")
