"""One-key hosted deployments pinned to immutable versions."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.create_table(
        "deployment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("agent_version_id", sa.Uuid()),
        sa.Column("workflow_version_id", sa.Uuid()),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "agent_version_id"], ["agent_version.workspace_id", "agent_version.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "workflow_version_id"],
            ["workflow_version.workspace_id", "workflow_version.id"],
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint(
            "(kind = 'agent' AND agent_version_id IS NOT NULL AND workflow_version_id IS NULL) OR (kind = 'workflow' AND workflow_version_id IS NOT NULL AND agent_version_id IS NULL)",
            name="valid_deployment_target",
        ),
        sa.CheckConstraint("state IN ('active','revoked')", name="valid_deployment_state"),
    )
    op.create_index("ix_deployment_workspace", "deployment", ["workspace_id", "created_at"])
    op.add_column("agent_run", sa.Column("deployment_id", sa.Uuid(), nullable=True))
    op.add_column("workflow_run", sa.Column("deployment_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agent_run_deployment",
        "agent_run",
        "deployment",
        ["workspace_id", "deployment_id"],
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_workflow_run_deployment",
        "workflow_run",
        "deployment",
        ["workspace_id", "deployment_id"],
        ["workspace_id", "id"],
    )
    op.create_index("ix_agent_run_deployment", "agent_run", ["deployment_id", "created_at"])
    op.create_index("ix_workflow_run_deployment", "workflow_run", ["deployment_id", "created_at"])
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE deployment TO ff_app;
        REVOKE TRUNCATE ON TABLE deployment FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_index("ix_workflow_run_deployment", table_name="workflow_run")
    op.drop_index("ix_agent_run_deployment", table_name="agent_run")
    op.drop_constraint("fk_workflow_run_deployment", "workflow_run", type_="foreignkey")
    op.drop_constraint("fk_agent_run_deployment", "agent_run", type_="foreignkey")
    op.drop_column("workflow_run", "deployment_id")
    op.drop_column("agent_run", "deployment_id")
    op.drop_index("ix_deployment_workspace", table_name="deployment")
    op.drop_table("deployment")
