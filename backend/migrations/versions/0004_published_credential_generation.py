"""Pin the verified credential generation in published agent definitions."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.add_column("agent_version", sa.Column("credential_generation", sa.Integer(), nullable=True))
    op.drop_constraint("published_connection", "agent_version", type_="check")
    op.create_check_constraint(
        "published_connection",
        "agent_version",
        "purpose != 'published' OR (connection_id IS NOT NULL AND credential_generation IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("published_connection", "agent_version", type_="check")
    op.create_check_constraint(
        "published_connection",
        "agent_version",
        "purpose != 'published' OR connection_id IS NOT NULL",
    )
    op.drop_column("agent_version", "credential_generation")
