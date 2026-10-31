"""Fenced encrypted workflow checkpoints and external-call recovery markers."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade():
    op.add_column(
        "workflow_run",
        sa.Column("external_inflight", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("workflow_run", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    # Preserve the conservative no-replay rule for work accepted by the previous runtime.
    op.execute(
        "UPDATE workflow_run SET external_inflight=true WHERE state IN ('queued','running') AND external_started_at IS NOT NULL"
    )
    op.create_table(
        "workflow_checkpoint",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["workflow_run.workspace_id", "workflow_run.id"]
        ),
        sa.UniqueConstraint("run_id", "node_id", name="uq_workflow_checkpoint_node"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workflow_checkpoint_sequence"),
        sa.CheckConstraint(
            "state IN ('running','completed','skipped','failed')", name="checkpoint_state"
        ),
        sa.CheckConstraint(
            "attempt >= 1 AND sequence >= 0 AND sequence < 30", name="checkpoint_bounds"
        ),
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_checkpoint TO ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_table("workflow_checkpoint")
    op.drop_column("workflow_run", "heartbeat_at")
    op.drop_column("workflow_run", "external_inflight")
