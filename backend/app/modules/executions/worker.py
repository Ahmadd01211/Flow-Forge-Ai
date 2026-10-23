import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from celery import Celery
from sqlalchemy import or_, select

from app.core.config import Settings
from app.core.db import make_sessions
from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import execute
from app.modules.workflows.models import WorkflowRun, WorkflowVersion
from app.modules.workflows.runtime import execute as execute_workflow_runtime

settings = Settings()
celery = Celery("flowforge", broker=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=45,
    task_soft_time_limit=40,
    broker_transport_options={"visibility_timeout": 600},
)
log = logging.getLogger("flowforge.maintenance")


@celery.task(name="flowforge.execute_agent")
def execute_agent(run_id: str) -> None:
    execute(run_id)


@celery.task(name="flowforge.execute_workflow")
def execute_workflow(run_id: str) -> None:
    execute_workflow_runtime(run_id)


def reconcile_workflows_once() -> int:
    sessions = make_sessions(settings.database_url)
    now = datetime.now(UTC)
    dispatched = []
    try:
        with sessions() as db:
            rows = db.scalars(
                select(WorkflowRun)
                .where(WorkflowRun.state.in_(["queued", "running"]))
                .order_by(WorkflowRun.created_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            ).all()
            for run in rows:
                if run.cancel_requested_at or run.deadline_at <= now:
                    run.state = "cancelled" if run.cancel_requested_at else "failed"
                    run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                    if run.external_started_at and run.cost_usd is None:
                        version = db.scalar(select(WorkflowVersion).where(WorkflowVersion.id == run.version_id))
                        if version and any(node.get("type") == "agent" for node in version.graph.get("nodes", [])):
                            run.uncertain_cost_usd = Decimal(version.graph["limits"]["max_cost_usd"])
                    run.finished_at = now
                    run.claim_token = None
                elif (
                    run.state == "running"
                    and run.external_started_at is None
                    and run.started_at
                    and run.started_at < now - timedelta(seconds=6)
                ):
                    # Local tools are pure; invalidating the claim makes replay safe.
                    run.state = "queued"
                    run.claim_token = None
                    run.started_at = None
                    run.last_dispatched_at = None
                elif run.state == "queued" and (
                    run.last_dispatched_at is None
                    or run.last_dispatched_at < now - timedelta(seconds=4)
                ):
                    run.last_dispatched_at = now
                    dispatched.append(str(run.id))
            db.commit()
        for run_id in dispatched:
            try:
                celery.send_task("flowforge.execute_workflow", args=[run_id], queue="agents")
            except Exception as exc:
                log.warning("workflow_dispatch_failed %s", type(exc).__name__)
        return len(dispatched)
    finally:
        sessions.kw["bind"].dispose()


def reconcile_once() -> int:
    """Redis delivery is disposable; queued/running truth remains in PostgreSQL."""
    sessions = make_sessions(settings.database_url)
    now = datetime.now(UTC)
    dispatched = []
    try:
        with sessions() as db:
            rows = db.scalars(
                select(AgentRun)
                .where(
                    or_(
                        (AgentRun.state == "queued")
                        & (
                            (AgentRun.last_dispatched_at.is_(None))
                            | (AgentRun.last_dispatched_at < now - timedelta(seconds=10))
                            | (AgentRun.deadline_at <= now)
                        ),
                        (AgentRun.state == "running") & (AgentRun.deadline_at <= now),
                        (AgentRun.state == "running")
                        & AgentRun.model_started_at.is_(None)
                        & (AgentRun.started_at < now - timedelta(seconds=45)),
                    )
                )
                .order_by(AgentRun.created_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            ).all()
            for run in rows:
                if run.deadline_at <= now:
                    run.state = "cancelled" if run.cancel_requested_at else "failed"
                    run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                    run.uncertain_cost_usd = run.reserved_max_usd if run.model_started_at else None
                    run.finished_at = now
                elif run.state == "queued":
                    run.last_dispatched_at = now
                    dispatched.append(str(run.id))
                elif run.state == "running" and run.model_started_at is None:
                    # A crashed worker had not crossed the provider-call marker.
                    # Its claim is invalidated before a replacement can dispatch.
                    run.state = "queued"
                    run.claim_token = None
                    run.started_at = None
                    run.last_dispatched_at = None
            db.commit()
        for run_id in dispatched:
            try:
                celery.send_task("flowforge.execute_agent", args=[run_id], queue="agents")
            except Exception as exc:
                log.warning("dispatch_failed %s", type(exc).__name__)
        return len(dispatched)
    finally:
        sessions.kw["bind"].dispose()


def maintenance_loop() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            reconcile_once()
            reconcile_workflows_once()
            from app.modules.identity.mail import deliver_pending
            sessions = make_sessions(settings.database_url)
            try:
                with sessions() as db:
                    deliver_pending(db, settings)
            finally:
                sessions.kw["bind"].dispose()
        except Exception as exc:
            log.warning("reconciliation_failed %s", type(exc).__name__)
        time.sleep(2)


if __name__ == "__main__":
    maintenance_loop()
