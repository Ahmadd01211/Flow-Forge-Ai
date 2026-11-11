"""Hidden playground twins: the builder's live chat runs unsaved drafts without new real versions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0029"
down_revision = "0028"
branch_labels = depends_on = None


def upgrade():
    op.add_column("agent", sa.Column("playground_for", sa.Uuid(), sa.ForeignKey("agent.id"), nullable=True))
    op.create_check_constraint("one_owner", "agent", "workflow_id IS NULL OR playground_for IS NULL")
    op.create_index(
        "uq_agent_playground_for", "agent", ["playground_for"], unique=True,
        postgresql_where=text("playground_for IS NOT NULL"),
    )


def downgrade():
    op.drop_index("uq_agent_playground_for", table_name="agent")
    op.drop_constraint(op.f("ck_agent_one_owner"), "agent", type_="check")
    op.drop_column("agent", "playground_for")
