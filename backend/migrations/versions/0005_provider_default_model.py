"""Store a workspace's preferred model for each connected provider."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.add_column(
        "integration_connection", sa.Column("default_model_id", sa.String(200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("integration_connection", "default_model_id")
