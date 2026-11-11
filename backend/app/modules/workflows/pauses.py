"""Durable suspension. PostgreSQL owns decisions/timers; no Celery task sleeps."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.executions.authorization import assert_authorized
from app.modules.workflows.checkpoints import rows, settle_unfinished
from app.modules.workflows.models import WorkflowCheckpoint, WorkflowPause, WorkflowRun
from app.modules.workspaces.models import WorkspaceMember

PAUSE_NODES = {"approval", "wait"}
MAX_PAUSE_SECONDS = 86400  # Worst-case combined parked duration, including expanded children.


class Parked(Exception):
    """Control transfer after committing suspension, never a failed/retryable step."""


def public_pause(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "node_id",
            "kind",
            "state",
            "prompt",
            "allow_requester",
            "created_at",
            "due_at",
            "decided_by",
            "settled_at",
        )
    }


def pending(db, run):
    return db.scalar(
        select(WorkflowPause).where(
            WorkflowPause.workspace_id == run.workspace_id,
            WorkflowPause.run_id == run.id,
            WorkflowPause.state == "pending",
        )
    )


def stop(db, run, pause, state, code, actor=None, now=None):
    now = now or datetime.now(UTC)
    pause.state, pause.settled_at, pause.decided_by = state, now, actor
    run.state = "cancelled" if state == "cancelled" and code is None else "failed"
    run.error_code, run.finished_at, run.claim_token = code, now, None
    settle_unfinished(db, run, code or "RUN_CANCELLED")
    record(
        db,
        run.workspace_id,
        actor or run.requested_by,
        "workflow_pause." + state,
        pause.id,
        {"run_id": str(run.id), "node_id": pause.node_id},
    )


def resume(db, run, pause, master, now, actor=None):
    """Caller locks run first. Shift active-time deadlines once in the same transaction."""
    try:
        assert_authorized(db, run)
    except HTTPException:
        stop(db, run, pause, "cancelled", "RUN_AUTHORIZATION_REVOKED", now=now)
        return
    parked = max(timedelta(0), now - pause.created_at)
    for row in rows(db, run.workspace_id, run.id):
        payload = json.loads(
            decrypt_secret(master, run.workspace_id, row.id, 1, row.nonce, row.ciphertext)
        )
        for key in ("_scope_deadline", "_node_deadline"):
            if key in payload["step"]:
                payload["step"][key] = (
                    datetime.fromisoformat(payload["step"][key]) + parked
                ).isoformat()
        row.nonce, row.ciphertext = encrypt_secret(
            master, run.workspace_id, row.id, 1, json.dumps(payload)
        )
    run.deadline_at += parked
    run.state, run.claim_token, run.last_dispatched_at = "queued", None, None
    pause.state = "approved" if pause.kind == "approval" else "elapsed"
    pause.settled_at, pause.decided_by = now, actor
    record(
        db,
        run.workspace_id,
        actor or run.requested_by,
        "workflow_pause." + pause.state,
        pause.id,
        {"run_id": str(run.id), "node_id": pause.node_id},
    )


def handler(sessions, identity, token, workspace_id, master, checkpoint):
    def call(node, data):
        now = datetime.now(UTC)
        with sessions() as db:
            run = checkpoint._run(db, starting=True)
            row = db.scalar(
                select(WorkflowPause).where(
                    WorkflowPause.workspace_id == workspace_id,
                    WorkflowPause.run_id == identity,
                    WorkflowPause.node_id == checkpoint.identity(node.id),
                )
            )
            if row:
                if row.state in {"approved", "elapsed"}:
                    if (
                        row.input_hash
                        != hashlib.sha256(
                            json.dumps(
                                data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                            ).encode()
                        ).hexdigest()
                    ):
                        fail(
                            409,
                            "APPROVAL_INPUT_CHANGED",
                            "The saved decision does not match this step's input.",
                        )
                    if row.kind == "approval":
                        role = db.scalar(
                            select(WorkspaceMember.role).where(
                                WorkspaceMember.workspace_id == workspace_id,
                                WorkspaceMember.user_id == row.decided_by,
                            )
                        )
                        if role not in {"owner", "admin"}:
                            fail(
                                403,
                                "APPROVAL_REVIEWER_REVOKED",
                                "The reviewer no longer has approval permission.",
                            )
                    # The original input is already encrypted in this checkpoint;
                    # completed upstream outputs determine it on every recovery.
                    return data
                fail(409, "PAUSE_NOT_READY", "This workflow decision has not been released.")
            if run.external_inflight:
                fail(
                    409,
                    "EXTERNAL_OUTCOME_UNKNOWN",
                    "Resolve the uncertain external outcome before pausing.",
                )
            if now >= checkpoint.deadline:
                fail(408, "RUN_TIMEOUT", "The workflow exhausted its active execution time.")
            seconds = (
                node.config["seconds"] if node.type == "wait" else node.config["expires_seconds"]
            )
            row = WorkflowPause(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                run_id=identity,
                node_id=checkpoint.identity(node.id),
                kind=node.type,
                state="pending",
                prompt=node.config.get("prompt", ""),
                allow_requester=node.config.get("allow_requester", False),
                input_hash=hashlib.sha256(
                    json.dumps(
                        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode()
                ).hexdigest(),
                created_at=now,
                due_at=now + timedelta(seconds=seconds),
            )
            db.add(row)
            evidence = db.scalar(
                select(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.workspace_id == workspace_id,
                    WorkflowCheckpoint.run_id == identity,
                    WorkflowCheckpoint.node_id == row.node_id,
                )
            )
            if not evidence:
                fail(409, "CHECKPOINT_REQUIRED", "A pause requires durable input evidence.")
            evidence.state = "waiting"
            run.state, run.claim_token = "waiting", None
            record(
                db,
                workspace_id,
                run.requested_by,
                "workflow_pause.created",
                row.id,
                {"run_id": str(identity), "node_id": row.node_id, "kind": node.type},
            )
            db.commit()
        raise Parked()

    return call


def decide(db, workspace_id, run_id, pause_id, actor_id, decision, master):
    # The same lock order as cancellation, worker claims and timer maintenance.
    run = db.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.workspace_id == workspace_id,
            WorkflowRun.id == run_id,
        )
        .with_for_update()
    )
    role = db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == actor_id,
        )
    )
    if role not in {"owner", "admin"}:
        fail(
            403,
            "APPROVAL_REVIEWER_REQUIRED",
            "A workspace owner or admin must review this request.",
        )
    row = (
        db.scalar(
            select(WorkflowPause).where(
                WorkflowPause.workspace_id == workspace_id,
                WorkflowPause.run_id == run_id,
                WorkflowPause.id == pause_id,
                WorkflowPause.kind == "approval",
            )
        )
        if run
        else None
    )
    if not row:
        fail(404, "NOT_FOUND", "Approval request not found.")
    if not row.allow_requester and actor_id == run.requested_by:
        fail(
            403,
            "INDEPENDENT_REVIEW_REQUIRED",
            "Another workspace owner or admin must review this run.",
        )
    target = "approved" if decision == "approve" else "rejected"
    if row.state == target and row.decided_by == actor_id:
        return run  # Identical retry after a lost HTTP response.
    if row.state != "pending" or run.state != "waiting":
        fail(409, "APPROVAL_ALREADY_SETTLED", "This approval request has already been settled.")
    now = datetime.now(UTC)
    if now >= row.due_at:
        stop(db, run, row, "expired", "APPROVAL_EXPIRED", now=now)
        db.commit()
        fail(409, "APPROVAL_EXPIRED", "This approval request has expired.")
    if run.cancel_requested_at:
        stop(db, run, row, "cancelled", None, now=now)
    elif decision == "reject":
        stop(db, run, row, "rejected", "APPROVAL_REJECTED", actor_id, now)
    else:
        resume(db, run, row, master, now, actor_id)
    db.commit()
    return run


def reconcile(sessions, master, now=None):
    now = now or datetime.now(UTC)
    with sessions() as db:
        due_runs = db.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.state == "waiting",
                WorkflowRun.id.in_(
                    select(WorkflowPause.run_id).where(
                        WorkflowPause.state == "pending",
                        WorkflowPause.due_at <= now,
                    )
                ),
            )
            .order_by(WorkflowRun.created_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for run in due_runs:
            row = pending(db, run)
            if run.cancel_requested_at:
                stop(db, run, row, "cancelled", None, now=now)
            elif row.kind == "approval":
                stop(db, run, row, "expired", "APPROVAL_EXPIRED", now=now)
            else:
                resume(db, run, row, master, now)
        db.commit()
        return len(due_runs)
