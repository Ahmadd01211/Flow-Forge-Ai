"""Immutable agent snapshots and append-only definition audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "agent_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("change_summary", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("agent_id", "number", name="uq_agent_version_number"),
        sa.UniqueConstraint(
            "agent_id", "source_revision", "purpose", name="uq_agent_version_source_purpose"
        ),
        sa.CheckConstraint("number >= 1 AND source_revision >= 1", name="positive_version"),
        sa.CheckConstraint("purpose IN ('test','published')", name="valid_purpose"),
    )
    op.create_index(
        "ix_agent_version_history",
        "agent_version",
        ["workspace_id", "agent_id", sa.text("number DESC")],
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_audit_event_workspace_time", "audit_event", ["workspace_id", sa.text("created_at DESC")]
    )
    op.execute("""CREATE OR REPLACE FUNCTION reject_immutable_change() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Immutable records cannot be changed' USING ERRCODE = '55000'; END $$""")
    for table in ["agent_version", "audit_event"]:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()"
        )
        # The Docker development application role exists before migrations. Keep
        # standalone/test installations usable when that role is intentionally absent.
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
            GRANT SELECT, INSERT ON TABLE {table} TO ff_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {table} FROM ff_app;
        END IF; END $$""")


def downgrade() -> None:
    for table in ["audit_event", "agent_version"]:
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_immutable_change()")
