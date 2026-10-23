"""Immutable workflow versions and durable local-tool runs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.create_table(
        "workflow_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("graph", JSONB(), nullable=False),
        sa.Column("graph_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "workflow_id"], ["workflow.workspace_id", "workflow.id"]
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workflow_id", "number", name="uq_workflow_version_number"),
        sa.UniqueConstraint("workflow_id", "source_revision", name="uq_workflow_version_revision"),
    )
    op.execute(
        "CREATE TRIGGER workflow_version_immutable BEFORE UPDATE OR DELETE ON workflow_version FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()"
    )
    op.create_table(
        "workflow_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
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
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("last_dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["workflow_version.workspace_id", "workflow_version.id"]
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint(
            "workspace_id",
            "requested_by",
            "idempotency_key_hash",
            name="uq_workflow_run_idempotency",
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')",
            name="valid_workflow_run_state",
        ),
    )
    op.create_index("ix_workflow_run_dispatch", "workflow_run", ["state", "last_dispatched_at"])
    op.create_index(
        "ix_workflow_run_history", "workflow_run", ["workspace_id", sa.text("created_at DESC")]
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT ON TABLE workflow_version TO ff_app;
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE workflow_version FROM ff_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE workflow_run TO ff_app;
        REVOKE TRUNCATE ON TABLE workflow_run FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_index("ix_workflow_run_history", table_name="workflow_run")
    op.drop_index("ix_workflow_run_dispatch", table_name="workflow_run")
    op.drop_table("workflow_run")
    op.drop_table("workflow_version")
