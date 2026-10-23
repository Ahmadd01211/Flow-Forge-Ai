"""Workspace approvals for reviewed built-in tools."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.create_table(
        "tool_installation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("tool_key", sa.String(80), nullable=False),
        sa.Column("installed_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "tool_key"),
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tool_installation TO ff_app;
        REVOKE TRUNCATE ON TABLE tool_installation FROM ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_table("tool_installation")
