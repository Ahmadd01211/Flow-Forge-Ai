"""Run traces and feedback: a readable timeline of what an agent did, and how people rated it."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret
from app.modules.agents.models import Agent, AgentVersion
from app.modules.executions.models import AgentRun, RunEvent, RunFeedback
from app.modules.executions.service import MODEL_PRICES
from app.modules.identity.models import User

PREFIXES = ("mcp:", "http:", "workflow:")


def _label(tool_key: str | None) -> tuple[str, str]:
    key = tool_key or "tool"
    if key.startswith("skill:"):
        return "skill", key[len("skill:"):]
    for prefix in PREFIXES:
        if key.startswith(prefix):
            return "tool", key[len(prefix):].replace("__", " · ")
    return "tool", key


def steps(db: Session, master: bytes, run: AgentRun, prices: tuple[Decimal, Decimal] | None) -> list[dict]:
    """Pair started/finished events into steps with durations, tokens, cost and tool payloads."""
    events = db.scalars(select(RunEvent).where(RunEvent.workspace_id == run.workspace_id, RunEvent.run_id == run.id).order_by(RunEvent.sequence)).all()
    pending: dict[str, RunEvent] = {}
    result = []
    for event in events:
        if event.kind not in ("model", "tool"):
            continue
        if event.status == "started":
            pending[event.kind] = event
            continue
        start = pending.pop(event.kind, None)
        kind, label = ("model", "Model call") if event.kind == "model" else _label(event.tool_key)
        detail = (
            json.loads(decrypt_secret(master, run.workspace_id, event.id, 1, event.nonce, event.ciphertext))
            if event.nonce and event.ciphertext else {}
        )
        cost = None
        if event.kind == "model" and prices and event.input_tokens is not None:
            cost = str(prices[0] * event.input_tokens + prices[1] * (event.output_tokens or 0))
        result.append({
            "kind": kind, "label": label, "status": event.status, "error_code": event.error_code,
            "started_at": start.created_at if start else None, "finished_at": event.created_at,
            "duration_ms": int((event.created_at - start.created_at).total_seconds() * 1000) if start else None,
            "input_tokens": event.input_tokens, "output_tokens": event.output_tokens, "cost_usd": cost,
            "arguments": detail.get("arguments"), "output": detail.get("output"),
        })
    return result


def feedback_summary(db: Session, run: AgentRun, user_id: uuid.UUID) -> dict:
    rows = db.execute(
        select(RunFeedback, User.name).outerjoin(User, User.id == RunFeedback.created_by)
        .where(RunFeedback.workspace_id == run.workspace_id, RunFeedback.run_id == run.id)
        .order_by(RunFeedback.created_at.desc())
    ).all()
    mine = next((row for row, _ in rows if row.created_by == user_id), None)
    return {
        "up": sum(row.rating == "up" for row, _ in rows),
        "down": sum(row.rating == "down" for row, _ in rows),
        "mine": {"rating": mine.rating, "comment": mine.comment} if mine else None,
        "comments": [
            {"rating": row.rating, "comment": row.comment, "author": name or "Someone", "created_at": row.created_at}
            for row, name in rows if row.comment
        ],
    }


def build(db: Session, master: bytes, run: AgentRun, public: dict, user_id: uuid.UUID) -> dict:
    version = db.get(AgentVersion, run.version_id)
    agent = db.get(Agent, version.agent_id)
    config = version.config
    prices = MODEL_PRICES.get((config.get("provider", "openai"), config.get("model_id")))
    timeline = steps(db, master, run, prices)
    input_value = json.loads(decrypt_secret(master, run.workspace_id, run.id, 1, run.input_nonce, run.input_ciphertext))
    return {
        "run": public,
        "input": input_value,
        "agent": {
            # Playground chats run in a hidden twin; point people at the agent they were building.
            "id": agent.playground_for or agent.id,
            "workflow_id": agent.workflow_id,
            "name": version.name, "version_number": version.number,
            "provider": config.get("provider", "openai"), "model_id": config.get("model_id"),
            "playground": agent.playground_for is not None,
            "system": agent.system_role is not None,
            "skills": [{"name": item["name"], "number": item.get("number")} for item in config.get("skills", [])],
            "source": "deployment" if run.deployment_id else "test" if agent.playground_for or agent.workflow_id or agent.system_role else "manual",
        },
        "steps": timeline,
        "totals": {
            "duration_ms": int((run.finished_at - (run.started_at or run.created_at)).total_seconds() * 1000) if run.finished_at else None,
            "model_calls": sum(step["kind"] == "model" for step in timeline),
            "tool_calls": sum(step["kind"] != "model" for step in timeline),
        },
        "feedback": feedback_summary(db, run, user_id),
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))], 2)


def performance(db: Session, workspace_id: uuid.UUID, agent: Agent, days: int, include_tests: bool) -> dict:
    """Health of one agent's runs over a window: volume, success, speed, cost, tools, errors, feedback."""
    owners = [agent.id]
    if include_tests:
        owners += list(db.scalars(select(Agent.id).where(Agent.playground_for == agent.id)))
    versions = select(AgentVersion.id).where(AgentVersion.workspace_id == workspace_id, AgentVersion.agent_id.in_(owners))
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    runs = db.scalars(
        select(AgentRun).where(AgentRun.workspace_id == workspace_id, AgentRun.version_id.in_(versions), AgentRun.created_at >= since)
        .order_by(AgentRun.created_at.desc()).limit(5000)
    ).all()
    ids = [run.id for run in runs]
    finished = [run for run in runs if run.state in ("completed", "failed", "cancelled")]
    completed = [run for run in runs if run.state == "completed"]
    durations = [(run.finished_at - (run.started_at or run.created_at)).total_seconds() for run in finished if run.finished_at]
    costs = [run.cost_usd for run in runs if run.cost_usd is not None]
    daily = {(since + timedelta(days=offset)).date(): {"runs": 0, "failed": 0, "cost": Decimal(0)} for offset in range(days)}
    for run in runs:
        bucket = daily.get(run.created_at.astimezone(UTC).date())
        if bucket:
            bucket["runs"] += 1
            bucket["failed"] += run.state == "failed"
            bucket["cost"] += run.cost_usd or 0
    tools = db.execute(
        select(RunEvent.tool_key, func.count(), func.count().filter(RunEvent.status == "failed"))
        .where(RunEvent.workspace_id == workspace_id, RunEvent.run_id.in_(ids), RunEvent.kind == "tool", RunEvent.status != "started")
        .group_by(RunEvent.tool_key).order_by(func.count().desc()).limit(8)
    ).all() if ids else []
    errors: dict[str, int] = {}
    for run in runs:
        if run.state == "failed":
            errors[run.error_code or "UNKNOWN"] = errors.get(run.error_code or "UNKNOWN", 0) + 1
    ratings = db.execute(
        select(RunFeedback.rating, func.count()).where(RunFeedback.workspace_id == workspace_id, RunFeedback.run_id.in_(ids)).group_by(RunFeedback.rating)
    ).all() if ids else []
    complaints = db.execute(
        select(RunFeedback.run_id, RunFeedback.comment, RunFeedback.created_at)
        .where(RunFeedback.workspace_id == workspace_id, RunFeedback.run_id.in_(ids), RunFeedback.rating == "down")
        .order_by(RunFeedback.created_at.desc()).limit(5)
    ).all() if ids else []
    sources = {row.id: ("deployment" if row.deployment_id else "manual") for row in runs}
    twins = set(owners[1:])
    if twins:
        test_versions = set(db.scalars(select(AgentVersion.id).where(AgentVersion.agent_id.in_(twins))))
        sources.update({run.id: "test" for run in runs if run.version_id in test_versions})
    return {
        "days": days,
        "include_tests": include_tests,
        "runs": len(runs),
        "completed": len(completed),
        "failed": sum(run.state == "failed" for run in runs),
        "success_rate": round(len(completed) / len(finished), 4) if finished else None,
        "cost_total_usd": str(sum(costs, Decimal(0))),
        "cost_avg_usd": str(sum(costs, Decimal(0)) / len(costs)) if costs else None,
        "duration_p50_s": _percentile(durations, 0.5),
        "duration_p95_s": _percentile(durations, 0.95),
        "tokens_avg": round(sum((run.input_tokens or 0) + (run.output_tokens or 0) for run in completed) / len(completed)) if completed else None,
        "daily": [{"date": day.isoformat(), "runs": value["runs"], "failed": value["failed"], "cost_usd": str(value["cost"])} for day, value in daily.items()],
        "tools": [{"tool_key": key, "label": _label(key)[1], "kind": _label(key)[0], "calls": calls, "failed": failed} for key, calls, failed in tools],
        "errors": [{"code": code, "count": count} for code, count in sorted(errors.items(), key=lambda item: -item[1])[:5]],
        "feedback": {"up": dict(ratings).get("up", 0), "down": dict(ratings).get("down", 0),
                     "recent_down": [{"run_id": run_id, "comment": comment, "created_at": created} for run_id, comment, created in complaints]},
        "recent": [
            {"id": run.id, "state": run.state, "created_at": run.created_at, "source": sources[run.id], "error_code": run.error_code,
             "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
             "duration_s": round((run.finished_at - (run.started_at or run.created_at)).total_seconds(), 1) if run.finished_at else None}
            for run in runs[:8]
        ],
    }
