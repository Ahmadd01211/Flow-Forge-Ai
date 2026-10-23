"""Retry transient mail failures with a bounded backoff."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.add_column(
        "email_delivery",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("email_delivery", "next_attempt_at")
