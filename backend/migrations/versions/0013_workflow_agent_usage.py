"""Mark external workflow calls before sending them and record usage separately."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.add_column("workflow_run", sa.Column("external_started_at", sa.DateTime(timezone=True)))
    op.add_column("workflow_run", sa.Column("cost_usd", sa.Numeric(14, 8)))
    op.add_column("workflow_run", sa.Column("uncertain_cost_usd", sa.Numeric(14, 8)))
    op.add_column("workflow_run", sa.Column("input_tokens", sa.Integer()))
    op.add_column("workflow_run", sa.Column("output_tokens", sa.Integer()))


def downgrade() -> None:
    op.drop_column("workflow_run", "output_tokens")
    op.drop_column("workflow_run", "input_tokens")
    op.drop_column("workflow_run", "uncertain_cost_usd")
    op.drop_column("workflow_run", "cost_usd")
    op.drop_column("workflow_run", "external_started_at")
