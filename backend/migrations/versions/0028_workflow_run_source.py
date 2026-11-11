"""Record what started each workflow run: manual, chat, webhook, schedule, deployment or replay."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = depends_on = None

SOURCES = "('manual','chat','webhook','schedule','deployment','replay')"


def upgrade():
    op.add_column("workflow_run", sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
    # Older runs: deployments and triggers are recoverable from their links; the rest were manual
    # or chat, which were indistinguishable before this column.
    op.execute("UPDATE workflow_run SET source = 'deployment' WHERE deployment_id IS NOT NULL")
    op.execute(
        "UPDATE workflow_run SET source = workflow_automation.kind FROM workflow_automation"
        " WHERE workflow_run.automation_id = workflow_automation.id"
        " AND workflow_automation.kind IN ('webhook','schedule')"
    )
    op.create_check_constraint("valid_workflow_run_source", "workflow_run", f"source IN {SOURCES}")


def downgrade():
    op.drop_constraint(op.f("ck_workflow_run_valid_workflow_run_source"), "workflow_run", type_="check")
    op.drop_column("workflow_run", "source")
