"""User-created template snapshots and sharing."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"


def upgrade():
    op.create_table(
        "user_template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "visibility IN ('private','workspace','public')", name="template_visibility"
        ),
        sa.CheckConstraint("kind IN ('agent','workflow')", name="template_kind"),
    )
    for column in ("workspace_id", "created_by", "visibility"):
        op.create_index(f"ix_user_template_{column}", "user_template", [column])

    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON user_template TO ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_table("user_template")
