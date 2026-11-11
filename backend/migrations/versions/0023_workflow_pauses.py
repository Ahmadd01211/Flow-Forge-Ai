"""Durable human decisions and timers, without sleeping workers."""

from alembic import op
from sqlalchemy import text

from app.modules.workflows.models import WorkflowPause

revision = "0023"
down_revision = "0022"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint(
        op.f("ck_workflow_run_valid_workflow_run_state"), "workflow_run", type_="check"
    )
    op.create_check_constraint(
        "valid_workflow_run_state",
        "workflow_run",
        "state IN ('queued','running','waiting','completed','failed','cancelled')",
    )
    op.drop_constraint(
        op.f("ck_workflow_checkpoint_checkpoint_state"), "workflow_checkpoint", type_="check"
    )
    op.create_check_constraint(
        "checkpoint_state",
        "workflow_checkpoint",
        "state IN ('running','waiting','completed','skipped','failed')",
    )
    WorkflowPause.__table__.create(bind=op.get_bind())
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_pause TO ff_app;
    END IF; END $$""")
    op.drop_index("ix_workflow_run_active_workspace", "workflow_run")
    op.create_index(
        "ix_workflow_run_active_workspace",
        "workflow_run",
        ["workspace_id"],
        postgresql_where=text("state IN ('queued','running','waiting')"),
    )


def downgrade():
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT 1 FROM workflow_pause)")):
        raise RuntimeError("Keep durable decision history; export it before downgrading.")
    op.drop_table("workflow_pause")
    op.drop_constraint(
        op.f("ck_workflow_checkpoint_checkpoint_state"), "workflow_checkpoint", type_="check"
    )
    op.create_check_constraint(
        "checkpoint_state",
        "workflow_checkpoint",
        "state IN ('running','completed','skipped','failed')",
    )
    op.drop_constraint(
        op.f("ck_workflow_run_valid_workflow_run_state"), "workflow_run", type_="check"
    )
    op.create_check_constraint(
        "valid_workflow_run_state",
        "workflow_run",
        "state IN ('queued','running','completed','failed','cancelled')",
    )
    op.drop_index("ix_workflow_run_active_workspace", "workflow_run")
    op.create_index(
        "ix_workflow_run_active_workspace",
        "workflow_run",
        ["workspace_id"],
        postgresql_where=text("state IN ('queued','running')"),
    )
