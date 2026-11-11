"""Durable independent review for write-capable MCP calls made by agent runs."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.deployments.models import Deployment
from app.modules.executions.authorization import assert_authorized
from app.modules.executions.harness import append_event
from app.modules.executions.models import AgentRun, AgentToolApproval, RunEvent
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMember

MAX_APPROVAL_SECONDS = 24 * 60 * 60
MAX_CONTINUATION_BYTES = 120_000


class Parked(Exception):
    """The run was durably moved to waiting and must leave the worker cleanly."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def context_hash(version_id: uuid.UUID | str, tool_identity: dict, arguments: dict) -> str:
    arguments_hash = hashlib.sha256(_canonical(arguments)).hexdigest()
    context = {
        "version_id": str(version_id),
        "tool_identity": tool_identity,
        "arguments_hash": arguments_hash,
    }
    return hashlib.sha256(_canonical(context)).hexdigest()


def _payload(master: bytes, run: AgentRun, approval: AgentToolApproval) -> dict:
    try:
        plain = decrypt_secret(
            master, run.workspace_id, approval.id, 1, approval.nonce, approval.ciphertext
        )
        result = json.loads(plain)
    except (InvalidTag, UnicodeDecodeError, ValueError, TypeError):
        fail(409, "APPROVAL_CONTEXT_CORRUPT", "The saved tool approval could not be verified.")
    if not isinstance(result, dict):
        fail(409, "APPROVAL_CONTEXT_CORRUPT", "The saved tool approval could not be verified.")
    return result


def park(
    db: Session,
    master: bytes,
    run: AgentRun,
    *,
    tool_key: str,
    tool_identity: dict,
    arguments: dict,
    continuation: dict,
    now: datetime | None = None,
) -> AgentToolApproval:
    """Encrypt and commit an exact MCP call before the remote side effect starts."""
    now = now or datetime.now(UTC)
    if run.state != "running" or not run.claim_token:
        fail(409, "RUN_NOT_ACTIVE", "This agent run cannot be paused for approval.")
    if tool_identity.get("read_only") is not False:
        fail(409, "APPROVAL_NOT_REQUIRED", "Only write-capable tools use this approval path.")
    arguments_hash = hashlib.sha256(_canonical(arguments)).hexdigest()
    context_digest = context_hash(run.version_id, tool_identity, arguments)
    approval_id = uuid.uuid4()
    saved = {"tool_identity": tool_identity, "arguments": arguments, "continuation": continuation}
    encoded = json.dumps(saved, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > MAX_CONTINUATION_BYTES:
        fail(413, "TOOL_CONTEXT_TOO_LARGE", "The saved tool continuation exceeds the run limit.")
    nonce, ciphertext = encrypt_secret(master, run.workspace_id, approval_id, 1, encoded)
    approval = AgentToolApproval(
        id=approval_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        requester_id=run.requested_by,
        tool_key=tool_key,
        server_id=tool_identity["server_id"],
        server_name=tool_identity.get("server_name", tool_identity["server_id"])[:100],
        tool_name=tool_identity["tool_name"],
        tool_description=tool_identity.get("description", "")[:300],
        read_only=tool_identity["read_only"],
        arguments_hash=arguments_hash,
        context_hash=context_digest,
        state="pending",
        nonce=nonce,
        ciphertext=ciphertext,
        created_at=now,
        expires_at=now + timedelta(seconds=MAX_APPROVAL_SECONDS),
    )
    db.add(approval)
    if isinstance(continuation.get("input_tokens"), int):
        run.input_tokens = continuation["input_tokens"]
    if isinstance(continuation.get("output_tokens"), int):
        run.output_tokens = continuation["output_tokens"]
    if continuation.get("cost_usd") is not None:
        run.cost_usd = continuation["cost_usd"]
    run.state, run.claim_token, run.last_dispatched_at = "waiting", None, None
    append_event(
        db,
        run,
        "tool",
        "waiting",
        tool_key=tool_key,
        detail={"arguments": arguments, "output": None},
        master=master,
    )
    record(
        db,
        run.workspace_id,
        run.requested_by,
        "agent_tool_approval.created",
        approval.id,
        {"run_id": str(run.id), "tool_key": tool_key},
    )
    db.commit()
    return approval


def expire(db: Session, run: AgentRun, approval: AgentToolApproval, now: datetime) -> bool:
    if approval.state != "pending" or run.state != "waiting":
        return False
    if approval.expires_at > now:
        return False
    approval.state, approval.settled_at = "expired", now
    approval.ciphertext = b""
    run.state, run.error_code, run.finished_at, run.claim_token = (
        "failed",
        "AGENT_TOOL_APPROVAL_EXPIRED",
        now,
        None,
    )
    record(
        db,
        run.workspace_id,
        run.requested_by,
        "agent_tool_approval.expired",
        approval.id,
        {"run_id": str(run.id), "tool_key": approval.tool_key},
    )
    return True


def decide(
    db: Session,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    approval_id: uuid.UUID,
    actor_id: uuid.UUID,
    decision: str,
    master: bytes,
    now: datetime | None = None,
) -> AgentToolApproval:
    now = now or datetime.now(UTC)
    if decision not in {"approve", "reject"}:
        fail(422, "INVALID_APPROVAL_DECISION", "Choose approve or reject.")
    run = db.scalar(
        select(AgentRun)
        .where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
        .with_for_update()
    )
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == workspace_id,
            AgentToolApproval.run_id == run_id,
            AgentToolApproval.id == approval_id,
        )
        .with_for_update()
    )
    if not run or not approval:
        fail(404, "NOT_FOUND", "Tool approval not found.")
    if approval.requester_id == actor_id:
        fail(403, "INDEPENDENT_REVIEW_REQUIRED", "The run requester cannot approve this call.")
    role = db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == actor_id,
        )
    )
    if role not in {"owner", "admin"}:
        fail(403, "APPROVAL_REVIEWER_REQUIRED", "Workspace owner or admin approval is required.")
    if approval.state == ("approved" if decision == "approve" else "rejected"):
        if approval.reviewer_id == actor_id:
            return approval
        fail(409, "APPROVAL_ALREADY_SETTLED", "Another reviewer already decided this call.")
    if approval.state != "pending" or run.state != "waiting":
        fail(409, "APPROVAL_NOT_PENDING", "This tool approval is no longer pending.")
    if expire(db, run, approval, now):
        db.commit()
        fail(409, "AGENT_TOOL_APPROVAL_EXPIRED", "This tool approval has expired.")
    try:
        assert_authorized(db, run)
    except HTTPException:
        approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
        run.state, run.error_code, run.finished_at = "failed", "RUN_AUTHORIZATION_REVOKED", now
        db.commit()
        fail(403, "RUN_AUTHORIZATION_REVOKED", "The requester or deployment no longer has permission.")
    approval.reviewer_id, approval.settled_at = actor_id, now
    if decision == "reject":
        approval.state = "rejected"
        approval.ciphertext = b""
        run.state, run.error_code, run.finished_at = "failed", "AGENT_TOOL_APPROVAL_REJECTED", now
    else:
        approval.state = "approved"
        parked = min(max(timedelta(0), now - approval.created_at), timedelta(seconds=MAX_APPROVAL_SECONDS))
        run.deadline_at += parked
        run.state, run.claim_token, run.last_dispatched_at = "queued", None, None
    record(
        db,
        workspace_id,
        actor_id,
        "agent_tool_approval." + ("approved" if decision == "approve" else "rejected"),
        approval.id,
        {"run_id": str(run.id), "tool_key": approval.tool_key},
    )
    db.commit()
    return approval


def claim_approved(db: Session, run: AgentRun, master: bytes, now: datetime | None = None) -> dict | None:
    """Claim an approved call or resume a persisted successful-call continuation."""
    now = now or datetime.now(UTC)
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == run.workspace_id,
            AgentToolApproval.run_id == run.id,
            AgentToolApproval.state.in_(["approved", "ready"]),
        )
        .with_for_update()
    )
    if not approval:
        return None
    if run.state != "running":
        return None
    try:
        assert_authorized(db, run)
    except HTTPException:
        approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
        run.state, run.error_code, run.finished_at, run.claim_token = (
            "failed", "RUN_AUTHORIZATION_REVOKED", now, None
        )
        db.commit()
        return None
    if approval.reviewer_id:
        reviewer_role = db.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == run.workspace_id,
                WorkspaceMember.user_id == approval.reviewer_id,
            )
        )
        if reviewer_role not in {"owner", "admin"}:
            approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
            run.state, run.error_code, run.finished_at, run.claim_token = (
                "failed", "APPROVAL_REVIEWER_REVOKED", now, None
            )
            db.commit()
            return None
    from_ready = approval.state == "ready"
    saved = _payload(master, run, approval)
    if not from_ready and hashlib.sha256(_canonical(saved.get("arguments"))).hexdigest() != approval.arguments_hash:
        approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
        run.state, run.error_code, run.finished_at, run.claim_token = (
            "failed", "APPROVAL_CONTEXT_CHANGED", now, None
        )
        db.commit()
        return None
    approval.state, approval.call_claimed_at = ("resuming" if from_ready else "claimed"), now
    db.commit()
    saved["_approval"] = {
        "id": str(approval.id),
        "tool_key": approval.tool_key,
        "context_hash": approval.context_hash,
        "resume_from_ready": from_ready,
    }
    return saved


def finish_claim(db: Session, run: AgentRun, approval: AgentToolApproval, state: str, now=None) -> None:
    if state not in {"completed", "uncertain", "cancelled"}:
        raise ValueError("invalid approval claim completion state")
    now = now or datetime.now(UTC)
    if approval.state in {"claimed", "resuming"}:
        approval.state, approval.settled_at = state, now
        approval.ciphertext = b""


def finish_claim_run(sessions, run_id: uuid.UUID, token: uuid.UUID, state: str) -> None:
    """Settle a claimed approval only while the worker still owns the run claim."""
    try:
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                return
            approval = db.scalar(
                select(AgentToolApproval)
                .where(
                    AgentToolApproval.workspace_id == run.workspace_id,
                    AgentToolApproval.run_id == run.id,
                    AgentToolApproval.state.in_(["claimed", "ready", "resuming"]),
                )
                .with_for_update()
            )
            if approval:
                finish_claim(db, run, approval, state)
                if state == "uncertain":
                    approval.ciphertext = b""
                    run.error_code = "EXTERNAL_OUTCOME_UNKNOWN"
                    record(
                        db,
                        run.workspace_id,
                        run.requested_by,
                        "agent_tool_approval.execution_uncertain",
                        approval.id,
                        {"run_id": str(run.id), "tool_key": approval.tool_key},
                    )
                db.commit()
    finally:
        sessions.kw["bind"].dispose()


def save_call_result(
    sessions,
    master: bytes,
    run_id: uuid.UUID,
    token: uuid.UUID,
    approved_tool: dict,
    continuation: dict,
) -> None:
    """Persist the successful tool result before asking the provider for another step."""
    try:
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                fail(409, "RUN_INTERRUPTED", "The agent run lost its worker claim.")
            approval = db.scalar(
                select(AgentToolApproval)
                .where(
                    AgentToolApproval.workspace_id == run.workspace_id,
                    AgentToolApproval.run_id == run.id,
                    AgentToolApproval.id == uuid.UUID(approved_tool["_approval"]["id"]),
                    AgentToolApproval.state == "claimed",
                )
                .with_for_update()
            )
            if not approval:
                fail(409, "APPROVAL_NOT_CLAIMED", "The approved tool call is no longer claimed.")
            saved = _payload(master, run, approval)
            saved["continuation"] = {**continuation, "resume_from_ready": True}
            encoded = json.dumps(saved, ensure_ascii=False, separators=(",", ":"))
            if len(encoded.encode()) > MAX_CONTINUATION_BYTES:
                fail(413, "TOOL_CONTEXT_TOO_LARGE", "The saved tool continuation exceeds the run limit.")
            approval.nonce, approval.ciphertext = encrypt_secret(
                master, run.workspace_id, approval.id, 1, encoded
            )
            approval.state = "ready"
            db.commit()
    finally:
        sessions.kw["bind"].dispose()


def cancel_claim(db: Session, run: AgentRun, reason: str, now=None) -> None:
    """Settle a claimed call when a worker preflight stops before runtime dispatch."""
    now = now or datetime.now(UTC)
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == run.workspace_id,
            AgentToolApproval.run_id == run.id,
            AgentToolApproval.state.in_(["claimed", "ready", "resuming"]),
        )
        .with_for_update()
    )
    if approval:
        approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
        record(
            db,
            run.workspace_id,
            run.requested_by,
            "agent_tool_approval.cancelled",
            approval.id,
            {"run_id": str(run.id), "tool_key": approval.tool_key, "reason": reason},
        )


def cancel_waiting(db: Session, run: AgentRun, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == run.workspace_id,
            AgentToolApproval.run_id == run.id,
            AgentToolApproval.state.in_(["pending", "approved", "ready"]),
        )
        .with_for_update()
    )
    if approval:
        approval.state, approval.settled_at = "cancelled", now
        approval.ciphertext = b""
        record(
            db,
            run.workspace_id,
            run.requested_by,
            "agent_tool_approval.cancelled",
            approval.id,
            {"run_id": str(run.id), "tool_key": approval.tool_key},
        )


def invalidate_for_run(db: Session, run: AgentRun, reason: str, now=None) -> None:
    """Settle an approved continuation when a worker's preflight check fails."""
    now = now or datetime.now(UTC)
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == run.workspace_id,
            AgentToolApproval.run_id == run.id,
            AgentToolApproval.state.in_(["pending", "approved", "ready", "resuming"]),
        )
        .with_for_update()
    )
    if approval:
        approval.state, approval.settled_at, approval.ciphertext = "cancelled", now, b""
        record(
            db,
            run.workspace_id,
            run.requested_by,
            "agent_tool_approval.cancelled",
            approval.id,
            {"run_id": str(run.id), "tool_key": approval.tool_key, "reason": reason},
        )


def reconcile(sessions, master: bytes, now: datetime | None = None) -> int:
    """Expire approvals and stop waiting runs even if no UI polls them."""
    del master  # Expiry settles metadata only and does not decrypt continuations.
    now = now or datetime.now(UTC)
    settled = 0
    with sessions() as db:
        rows = db.scalars(
            select(AgentToolApproval)
            .where(AgentToolApproval.state == "pending", AgentToolApproval.expires_at <= now)
            .order_by(AgentToolApproval.expires_at)
            .limit(100)
        ).all()
        for item in rows:
            run = db.scalar(
                select(AgentRun)
                .where(AgentRun.workspace_id == item.workspace_id, AgentRun.id == item.run_id)
                .with_for_update(skip_locked=True)
            )
            if not run:
                continue
            approval = db.scalar(
                select(AgentToolApproval).where(AgentToolApproval.id == item.id).with_for_update()
            )
            if approval and expire(db, run, approval, now):
                settled += 1
        db.commit()
    return settled


def public_summary(db: Session, master: bytes, run: AgentRun, viewer_id: uuid.UUID) -> dict | None:
    """Authenticated trace payload; the only view that decrypts pending call arguments."""
    approval = db.scalar(
        select(AgentToolApproval)
        .where(
            AgentToolApproval.workspace_id == run.workspace_id,
            AgentToolApproval.run_id == run.id,
        )
        .order_by(AgentToolApproval.created_at.desc())
    )
    if not approval:
        return None
    saved = _payload(master, run, approval) if approval.ciphertext else {}
    arguments = saved.get("arguments")
    if arguments is None:
        event = db.scalar(
            select(RunEvent)
            .where(
                RunEvent.workspace_id == run.workspace_id,
                RunEvent.run_id == run.id,
                RunEvent.kind == "tool",
                RunEvent.tool_key == approval.tool_key,
                RunEvent.nonce.is_not(None),
            )
            .order_by(RunEvent.sequence.desc())
        )
        if event:
            try:
                arguments = json.loads(
                    decrypt_secret(master, run.workspace_id, event.id, 1, event.nonce, event.ciphertext)
                ).get("arguments")
            except (InvalidTag, UnicodeDecodeError, ValueError, TypeError):
                arguments = None
    requester = db.get(User, approval.requester_id)
    role = db.scalar(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == run.workspace_id,
            WorkspaceMember.user_id == viewer_id,
        )
    )
    deployment = db.get(Deployment, run.deployment_id) if run.deployment_id else None
    return {
        "id": approval.id,
        "state": approval.state,
        "tool_key": approval.tool_key,
        "tool": saved.get("tool_identity") or {
            "server_id": approval.server_id,
            "server_name": approval.server_name,
            "tool_name": approval.tool_name,
            "description": approval.tool_description,
            "read_only": approval.read_only,
        },
        "arguments": arguments,
        "requester": {"id": approval.requester_id, "name": requester.name if requester else "Former member"},
        "deployment": {"id": deployment.id, "name": deployment.name} if deployment else None,
        "expires_at": approval.expires_at,
        "decided_at": approval.settled_at,
        "decided_by": approval.reviewer_id,
        "may_decide": bool(
            role in {"owner", "admin"}
            and viewer_id != approval.requester_id
            and approval.state == "pending"
            and run.state == "waiting"
            and approval.expires_at > datetime.now(UTC)
        ),
    }
