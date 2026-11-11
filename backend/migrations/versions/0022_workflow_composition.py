"""Allow bounded expanded workflow checkpoint sequences; preserve existing evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade():
    op.drop_constraint(
        op.f("ck_workflow_checkpoint_checkpoint_bounds"), "workflow_checkpoint", type_="check"
    )
    op.create_check_constraint(
        "checkpoint_bounds",
        "workflow_checkpoint",
        "attempt >= 1 AND sequence >= 0 AND sequence < 120",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workflow_checkpoint WHERE sequence >= 30)")
    ):
        raise RuntimeError(
            "Expanded workflow evidence exists; refusing a downgrade that would discard history."
        )
    op.drop_constraint(
        op.f("ck_workflow_checkpoint_checkpoint_bounds"), "workflow_checkpoint", type_="check"
    )
    op.create_check_constraint(
        "checkpoint_bounds",
        "workflow_checkpoint",
        "attempt >= 1 AND sequence >= 0 AND sequence < 30",
    )
