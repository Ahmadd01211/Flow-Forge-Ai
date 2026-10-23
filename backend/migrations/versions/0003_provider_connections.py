"""Workspace provider credentials and published agent connection pin."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "integration_connection",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("credential_generation", sa.Integer(), nullable=False),
        sa.Column("masked_hint", sa.String(20), nullable=False),
        sa.Column("verified_models", postgresql.JSONB(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_connection_workspace_id"),
        sa.UniqueConstraint("workspace_id", "provider", name="uq_connection_provider"),
        sa.CheckConstraint("state IN ('active','revoked')", name="valid_connection_state"),
    )
    op.create_table(
        "secret_reference",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["integration_connection.workspace_id", "integration_connection.id"],
        ),
        sa.UniqueConstraint("connection_id", "generation"),
        sa.CheckConstraint("generation >= 1 AND key_version = 1", name="valid_secret_generation"),
    )
    op.add_column("agent_version", sa.Column("connection_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agent_version_connection_workspace",
        "agent_version",
        "integration_connection",
        ["workspace_id", "connection_id"],
        ["workspace_id", "id"],
    )
    op.create_check_constraint(
        "published_connection",
        "agent_version",
        "purpose != 'published' OR connection_id IS NOT NULL",
    )
    for table in ["integration_connection", "secret_reference"]:
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO ff_app;
            REVOKE TRUNCATE ON TABLE {table} FROM ff_app;
        END IF; END $$""")


def downgrade() -> None:
    op.drop_constraint("published_connection", "agent_version", type_="check")
    op.drop_constraint("fk_agent_version_connection_workspace", "agent_version", type_="foreignkey")
    op.drop_column("agent_version", "connection_id")
    op.drop_table("secret_reference")
    op.drop_table("integration_connection")
