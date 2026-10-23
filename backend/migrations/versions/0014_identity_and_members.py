"""Account recovery, verification, invitations and transactional mail."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.add_column("app_user", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.create_table(
        "account_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_account_token_user_id", "account_token", ["user_id"])
    op.create_table(
        "email_delivery",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_email_delivery_pending", "email_delivery", ["sent_at", "attempts"])
    op.create_table(
        "workspace_invitation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('admin','editor','viewer')", name="invitation_role"),
    )
    op.create_index(
        "ix_workspace_invitation_workspace_id", "workspace_invitation", ["workspace_id"]
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ff_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON account_token, email_delivery, workspace_invitation TO ff_app;
    END IF; END $$""")


def downgrade() -> None:
    op.drop_table("workspace_invitation")
    op.drop_table("email_delivery")
    op.drop_table("account_token")
    op.drop_column("app_user", "email_verified_at")
