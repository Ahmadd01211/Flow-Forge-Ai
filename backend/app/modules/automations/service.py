"""PostgreSQL owns trigger delivery. Redis remains disposable transport for accepted runs."""

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.db import make_sessions
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.audit.service import record
from app.modules.automations.models import WorkflowAutomation
from app.modules.workflows.models import WorkflowVersion
from app.modules.workflows.runtime import _executable, submit
from app.modules.workflows.schemas import Graph
from app.modules.workspaces.models import Workspace, WorkspaceMember


def public(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "name",
            "version_id",
            "kind",
            "state",
            "interval_seconds",
            "next_due_at",
            "next_attempt_at",
            "last_due_at",
            "last_error_code",
            "created_at",
        )
    }


def target(db, workspace_id, version_id, kind, catalog):
    version = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workspace_id == workspace_id,
            WorkflowVersion.id == version_id,
        )
    )
    if not version:
        fail(404, "NOT_FOUND", "Published workflow version not found.")
    graph = Graph.model_validate(version.graph)
    if not any(n.type == kind + "_trigger" for n in graph.nodes):
        fail(422, "TRIGGER_MISMATCH", "Publish a workflow with the matching trigger node first.")
    _executable(db, workspace_id, graph, catalog)
    return graph


def create(db, workspace_id, actor_id, body, settings):
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    count = db.scalar(
        select(func.count())
        .select_from(WorkflowAutomation)
        .where(
            WorkflowAutomation.workspace_id == workspace_id, WorkflowAutomation.state != "archived"
        )
    )
    if count >= 50:
        fail(422, "AUTOMATION_LIMIT", "This workspace supports up to 50 automations.")
    graph = target(db, workspace_id, body.version_id, body.kind, settings.mcp_catalog_json)
    row = WorkflowAutomation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by=actor_id,
        name=body.name.strip(),
        version_id=body.version_id,
        kind=body.kind,
    )
    raw = None
    if body.kind == "webhook":
        raw = "ff_hook_" + secrets.token_urlsafe(32)
        row.key_hash = hashlib.sha256(raw.encode()).hexdigest()
    else:
        bounded_json(body.input, max_bytes=65536)
        if example_errors(graph.input_schema, body.input, "input"):
            fail(
                422, "INPUT_SCHEMA_INVALID", "Scheduled input does not match the published version."
            )
        row.interval_seconds = body.interval_seconds
        row.input_nonce, row.input_ciphertext = encrypt_secret(
            load_master_key(settings.credential_key_path),
            workspace_id,
            row.id,
            1,
            json.dumps(body.input),
        )
        row.next_due_at = datetime.now(UTC) + timedelta(seconds=body.interval_seconds)
    db.add(row)
    record(
        db,
        workspace_id,
        actor_id,
        "automation.created",
        row.id,
        {"kind": row.kind, "version_id": str(row.version_id)},
    )
    db.commit()
    return {**public(row), "webhook_key": raw}


def actor_allowed(db, row):
    role = db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == row.workspace_id,
            WorkspaceMember.user_id == row.created_by,
        )
    )
    return role in {"owner", "admin"}


def tick(settings, now=None):
    """Coalesce downtime into one occurrence. Run insertion and cursor advance commit together.

    A crash before commit leaves the same slot due; a crash after commit leaves a durable run
    for the existing dispatcher. Never backfill a burst of paid calls after downtime.
    """
    now = now or datetime.now(UTC)
    sessions = make_sessions(settings.database_url)
    accepted = 0
    try:
        for _ in range(20):
            with sessions() as db:
                row = db.scalar(
                    select(WorkflowAutomation)
                    .where(
                        WorkflowAutomation.kind == "schedule",
                        WorkflowAutomation.state == "active",
                        WorkflowAutomation.next_due_at <= now,
                        or_(
                            WorkflowAutomation.next_attempt_at.is_(None),
                            WorkflowAutomation.next_attempt_at <= now,
                        ),
                    )
                    .order_by(WorkflowAutomation.next_due_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if row is None:
                    break
                try:
                    with db.begin_nested():
                        if not actor_allowed(db, row):
                            fail(
                                403,
                                "AUTOMATION_OWNER_ACCESS_CHANGED",
                                "Automation owner access changed.",
                            )
                        target(
                            db,
                            row.workspace_id,
                            row.version_id,
                            "schedule",
                            settings.mcp_catalog_json,
                        )
                        master = load_master_key(settings.credential_key_path)
                        value = json.loads(
                            decrypt_secret(
                                master,
                                row.workspace_id,
                                row.id,
                                1,
                                row.input_nonce,
                                row.input_ciphertext,
                            )
                        )
                        slot = row.next_due_at
                        _, created = submit(
                            db,
                            row.workspace_id,
                            row.created_by,
                            row.version_id,
                            value,
                            slot.isoformat(),
                            master,
                            mcp_catalog_json=settings.mcp_catalog_json,
                            automation_id=row.id,
                            commit=False,
                        )
                        # Keep the original interval anchor and skip missed occurrences.
                        elapsed = int((now - slot).total_seconds()) // row.interval_seconds + 1
                        row.last_due_at = slot
                        row.next_due_at = slot + timedelta(seconds=elapsed * row.interval_seconds)
                        row.next_attempt_at = None
                        row.last_error_code = None
                        accepted += int(created)
                except HTTPException as exc:
                    row.last_error_code = exc.detail["code"]
                    if exc.status_code in {429, 503}:
                        if row.last_error_code == "WORKSPACE_DAILY_RUN_LIMIT":
                            row.next_attempt_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                        else:
                            row.next_attempt_at = now + timedelta(seconds=60 if row.last_error_code == "WORKSPACE_DAILY_BUDGET" else 10)
                    else:
                        row.state = "paused"
                        row.next_attempt_at = None
                db.commit()
        return accepted
    finally:
        sessions.kw["bind"].dispose()
