"""Workspace skills: reusable instructions and tool needs, versioned and pinned by agents."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "skill",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("starter_key", sa.String(60), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("revision >= 1", name="positive_revision"),
    )
    op.create_index("ix_skill_workspace_updated", "skill", ["workspace_id", text("updated_at DESC")])
    op.create_table(
        "skill_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id", "skill_id"], ["skill.workspace_id", "skill.id"]),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("skill_id", "number", name="uq_skill_version_number"),
        sa.CheckConstraint("number >= 1 AND source_revision >= 1", name="positive_version"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text("SELECT EXISTS(SELECT 1 FROM skill_version)")):
        raise RuntimeError("Published skills exist; agent versions may pin them.")
    op.drop_table("skill_version")
    op.drop_table("skill")
