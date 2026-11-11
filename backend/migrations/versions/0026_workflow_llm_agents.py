"""Agents managed by workflow LLM steps: each inline LLM node is backed by one hidden agent."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0026"
down_revision = "0025"
branch_labels = depends_on = None


def upgrade():
    op.add_column("agent", sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("workflow.id"), nullable=True))
    op.add_column("agent", sa.Column("node_id", sa.String(64), nullable=True))
    op.create_check_constraint(
        "workflow_node_pair", "agent", "(workflow_id IS NULL) = (node_id IS NULL)"
    )
    op.create_index(
        "uq_agent_workflow_node",
        "agent",
        ["workflow_id", "node_id"],
        unique=True,
        postgresql_where=text("workflow_id IS NOT NULL"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text("SELECT EXISTS(SELECT 1 FROM agent WHERE workflow_id IS NOT NULL)")):
        raise RuntimeError("Workflow LLM steps exist; published workflow versions depend on their agents.")
    op.drop_index("uq_agent_workflow_node", table_name="agent")
    op.drop_constraint(op.f("ck_agent_workflow_node_pair"), "agent", type_="check")
    op.drop_column("agent", "node_id")
    op.drop_column("agent", "workflow_id")
