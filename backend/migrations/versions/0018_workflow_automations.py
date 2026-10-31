"""Durable workflow webhook and interval bindings."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade():
    op.create_table(
        "workflow_automation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("key_hash", sa.String(64)),
        sa.Column("interval_seconds", sa.Integer()),
        sa.Column("input_nonce", sa.LargeBinary()),
        sa.Column("input_ciphertext", sa.LargeBinary()),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_due_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["workflow_version.workspace_id", "workflow_version.id"]
        ),
        sa.CheckConstraint("state IN ('active','paused','archived')", name="valid_automation_state"),
        sa.CheckConstraint(
            "(kind='webhook' AND key_hash IS NOT NULL AND interval_seconds IS NULL AND input_ciphertext IS NULL AND next_due_at IS NULL) OR (kind='schedule' AND key_hash IS NULL AND interval_seconds IS NOT NULL AND interval_seconds BETWEEN 60 AND 86400 AND input_nonce IS NOT NULL AND input_ciphertext IS NOT NULL AND next_due_at IS NOT NULL)",
            name="valid_automation_binding",
        ),
    )
    op.create_index("ix_automation_due", "workflow_automation", ["state", "kind", "next_due_at"])
    op.create_index(
        "ix_automation_workspace", "workflow_automation", ["workspace_id", "created_at"]
    )
    op.add_column("workflow_run", sa.Column("automation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_workflow_run_automation",
        "workflow_run",
        "workflow_automation",
        ["workspace_id", "automation_id"],
        ["workspace_id", "id"],
    )
    op.create_index("ix_workflow_run_automation", "workflow_run", ["automation_id", "created_at"])
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_automation TO ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_index("ix_workflow_run_automation", table_name="workflow_run")
    op.drop_constraint("fk_workflow_run_automation", "workflow_run", type_="foreignkey")
    op.drop_column("workflow_run", "automation_id")
    op.drop_table("workflow_automation")
