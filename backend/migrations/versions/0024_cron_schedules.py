"""Cron schedules evaluated in an IANA timezone, alongside interval schedules."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0024"
down_revision = "0023"
branch_labels = depends_on = None

INTERVAL_ONLY = (
    "(kind='webhook' AND key_hash IS NOT NULL AND interval_seconds IS NULL"
    " AND input_ciphertext IS NULL AND next_due_at IS NULL)"
    " OR (kind='schedule' AND key_hash IS NULL AND interval_seconds IS NOT NULL"
    " AND interval_seconds BETWEEN 60 AND 86400 AND input_nonce IS NOT NULL"
    " AND input_ciphertext IS NOT NULL AND next_due_at IS NOT NULL)"
)
WITH_CRON = (
    "(kind='webhook' AND key_hash IS NOT NULL AND interval_seconds IS NULL"
    " AND cron_expression IS NULL AND timezone IS NULL AND input_ciphertext IS NULL"
    " AND next_due_at IS NULL)"
    " OR (kind='schedule' AND key_hash IS NULL AND input_nonce IS NOT NULL"
    " AND input_ciphertext IS NOT NULL AND next_due_at IS NOT NULL AND ("
    "(interval_seconds IS NOT NULL AND interval_seconds BETWEEN 60 AND 86400"
    " AND cron_expression IS NULL AND timezone IS NULL)"
    " OR (interval_seconds IS NULL AND cron_expression IS NOT NULL AND timezone IS NOT NULL)))"
)
NAME = "ck_workflow_automation_valid_automation_binding"


def upgrade():
    op.add_column("workflow_automation", sa.Column("cron_expression", sa.String(100)))
    op.add_column("workflow_automation", sa.Column("timezone", sa.String(64)))
    op.drop_constraint(op.f(NAME), "workflow_automation", type_="check")
    op.create_check_constraint("valid_automation_binding", "workflow_automation", WITH_CRON)


def downgrade():
    if op.get_bind().scalar(
        text("SELECT EXISTS(SELECT 1 FROM workflow_automation WHERE cron_expression IS NOT NULL)")
    ):
        raise RuntimeError("Cron schedules exist; their run history would lose its cadence.")
    op.drop_constraint(op.f(NAME), "workflow_automation", type_="check")
    op.create_check_constraint("valid_automation_binding", "workflow_automation", INTERVAL_ONLY)
    op.drop_column("workflow_automation", "timezone")
    op.drop_column("workflow_automation", "cron_expression")
