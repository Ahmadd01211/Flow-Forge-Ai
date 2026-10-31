"""Encrypted agent regression suites."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade():
    op.create_table(
        "evaluation_suite",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
    )
    op.create_index("ix_evaluation_suite_workspace_id", "evaluation_suite", ["workspace_id"])
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON evaluation_suite TO ff_app;
    END IF; END $$""")


def downgrade():
    op.drop_table("evaluation_suite")
