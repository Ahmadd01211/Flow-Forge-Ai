"""Encrypted tool arguments and results on agent run events, and per-run feedback."""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = depends_on = None


def upgrade():
    op.add_column("agent_run_event", sa.Column("nonce", sa.LargeBinary(), nullable=True))
    op.add_column("agent_run_event", sa.Column("ciphertext", sa.LargeBinary(), nullable=True))
    op.create_table(
        "agent_run_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("comment", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]),
        sa.UniqueConstraint("run_id", "created_by", name="uq_agent_run_feedback_author"),
        sa.CheckConstraint("rating IN ('up','down')", name="valid_rating"),
    )
    op.create_index("ix_agent_run_feedback_run", "agent_run_feedback", ["workspace_id", "run_id"])


def downgrade():
    op.drop_table("agent_run_feedback")
    op.drop_column("agent_run_event", "ciphertext")
    op.drop_column("agent_run_event", "nonce")
