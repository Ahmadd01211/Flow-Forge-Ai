"""Encrypted conversation memory for agents and workflow LLM steps."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0027"
down_revision = "0026"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "conversation_turn",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_hash", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
        sa.UniqueConstraint("conversation_hash", "sequence", name="uq_conversation_turn_sequence"),
        sa.CheckConstraint("role IN ('user','assistant')", name="valid_role"),
        sa.CheckConstraint("sequence >= 1", name="positive_sequence"),
    )
    op.create_index("ix_conversation_turn_recent", "conversation_turn", ["conversation_hash", text("sequence DESC")])
    op.create_index("ix_conversation_turn_expiry", "conversation_turn", ["expires_at"])


def downgrade():
    op.drop_table("conversation_turn")
