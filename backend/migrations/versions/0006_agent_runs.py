"""Durable single-call agent run state and dispatch intent."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("input_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("input_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("output_nonce", sa.LargeBinary()),
        sa.Column("output_ciphertext", sa.LargeBinary()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("model_started_at", sa.DateTime(timezone=True)),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_max_usd", sa.Numeric(12, 8), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 8)),
        sa.Column("uncertain_cost_usd", sa.Numeric(12, 8)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint(
            "workspace_id", "requested_by", "idempotency_key_hash", name="uq_agent_run_idempotency"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["agent_version.workspace_id", "agent_version.id"]
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')",
            name="valid_agent_run_state",
        ),
    )
    op.create_index(
        "ix_agent_run_history",
        "agent_run",
        ["workspace_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_agent_run_dispatch", "agent_run", ["state", "last_dispatched_at"])
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_run TO ff_app;
        REVOKE TRUNCATE ON TABLE agent_run FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_index("ix_agent_run_dispatch", table_name="agent_run")
    op.drop_index("ix_agent_run_history", table_name="agent_run")
    op.drop_table("agent_run")
