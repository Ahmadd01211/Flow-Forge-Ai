"""Admission control derived from the durable run ledgers, under the workspace lock."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select

from app.core.errors import fail
from app.modules.executions.models import AgentRun
from app.modules.workflows.models import WorkflowRun
from app.modules.workspaces.models import Workspace


def summary(db, workspace, now=None):
    now = now or datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    totals = dict(
        runs=0,
        active=0,
        measured=Decimal(0),
        uncertain=Decimal(0),
        reserved=Decimal(0),
        input_tokens=0,
        output_tokens=0,
    )
    for model in (AgentRun, WorkflowRun):
        active = model.state.in_(["queued", "running", "waiting"])
        today = (model.created_at >= start) & (model.created_at < start + timedelta(days=1))
        # A workflow may now finish after midnight. Conservatively charge its
        # complete recorded spend on the completion day too, rather than let a
        # yesterday-created run release today's reservation without a charge.
        cost_today = today | ((model.finished_at >= start) & (model.finished_at < start + timedelta(days=1)))
        cost = func.coalesce(model.cost_usd, 0)
        reservation = func.greatest(model.reserved_max_usd - case((cost_today, cost), else_=0), 0)
        values = db.execute(
            select(
                func.count().filter(today),
                func.count().filter(active),
                func.coalesce(func.sum(case((cost_today, cost), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                cost_today & ~active,
                                func.coalesce(model.uncertain_cost_usd, 0),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(case((active, reservation), else_=0)), 0),
                func.coalesce(
                    func.sum(case((cost_today, func.coalesce(model.input_tokens, 0)), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((cost_today, func.coalesce(model.output_tokens, 0)), else_=0)), 0
                ),
            ).where(model.workspace_id == workspace.id, today | cost_today | active)
        ).one()
        for key, value in zip(totals, values, strict=True):
            totals[key] += value
    committed = totals["measured"] + totals["uncertain"] + totals["reserved"]
    return {
        "window_start": start,
        "resets_at": start + timedelta(days=1),
        "daily_budget_usd": str(workspace.daily_budget_usd),
        "daily_run_limit": workspace.daily_run_limit,
        "active_run_limit": workspace.active_run_limit,
        "revision": workspace.quota_revision,
        "accepted_runs": totals["runs"],
        "active_runs": totals["active"],
        "measured_usd": str(totals["measured"]),
        "uncertain_usd": str(totals["uncertain"]),
        "reserved_usd": str(totals["reserved"]),
        "committed_usd": str(committed),
        "remaining_usd": str(max(Decimal(0), workspace.daily_budget_usd - committed)),
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
    }


def admit(db, workspace_id, reservation):
    # Reacquiring a row lock in the same transaction is safe. The caller retains
    # it through run insertion/commit; agents, workflows and triggers share it.
    workspace = db.scalar(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    usage = summary(db, workspace)
    if usage["active_runs"] >= workspace.active_run_limit:
        fail(
            429,
            "WORKSPACE_CONCURRENCY_LIMIT",
            "This workspace has reached its shared active-run limit.",
        )
    if usage["accepted_runs"] >= workspace.daily_run_limit:
        fail(
            429,
            "WORKSPACE_DAILY_RUN_LIMIT",
            "This workspace has reached its daily accepted-run limit. Limits reset at midnight UTC.",
        )
    if (
        reservation > 0
        and Decimal(usage["committed_usd"]) + reservation > workspace.daily_budget_usd
    ):
        fail(
            429,
            "WORKSPACE_DAILY_BUDGET",
            "This run would exceed the workspace daily budget, including reservations and uncertain charges.",
        )
