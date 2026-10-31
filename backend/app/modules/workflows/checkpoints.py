"""Encrypted per-step evidence with run-claim fencing. No external operation is replayed blindly."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update

from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.errors import fail
from app.modules.workflows.composition import MAX_EXPANDED_STEPS
from app.modules.workflows.models import WorkflowCheckpoint, WorkflowRun

MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024


def rows(db, workspace_id, run_id):
    return db.scalars(
        select(WorkflowCheckpoint)
        .where(
            WorkflowCheckpoint.workspace_id == workspace_id,
            WorkflowCheckpoint.run_id == run_id,
        )
        .order_by(WorkflowCheckpoint.sequence)
    ).all()


def view(row, master, include_input=False):
    payload = json.loads(
        decrypt_secret(master, row.workspace_id, row.id, 1, row.nonce, row.ciphertext)
    )
    step = {
        **payload["step"],
        "status": row.state,
        "attempt": row.attempt,
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": max(0, int((row.finished_at - row.started_at).total_seconds() * 1000))
        if row.finished_at
        else None,
    }
    if row.error_code:
        step["error_code"] = row.error_code
    if include_input:
        step["input"] = payload["input"]
    return step


def settle_unfinished(db, run, code):
    db.execute(
        update(WorkflowCheckpoint)
        .where(
            WorkflowCheckpoint.workspace_id == run.workspace_id,
            WorkflowCheckpoint.run_id == run.id,
            WorkflowCheckpoint.state.in_(["running", "waiting"]),
        )
        .values(state="failed", error_code=code, finished_at=datetime.now(UTC))
    )


class Checkpoints:
    def __init__(
        self,
        sessions,
        workspace_id,
        run_id,
        claim_token,
        master,
        *,
        path=(),
        parent_node_id=None,
        iteration_index=None,
        workflow_version_id=None,
    ):
        self.sessions, self.workspace_id, self.run_id = sessions, workspace_id, run_id
        self.claim_token, self.master = claim_token, master
        self.path, self.parent_node_id = tuple(path), parent_node_id
        self.iteration_index, self.workflow_version_id = iteration_index, workflow_version_id
        self.ceiling, self.deadline = None, None

    def identity(self, node_id):
        return (
            "n" + hashlib.sha256(json.dumps([*self.path, node_id]).encode()).hexdigest()[:62]
            if self.path
            else node_id
        )

    def child(self, node, version_id, iteration=None):
        component = node.id + (f"[{iteration}]" if iteration is not None else "")
        return Checkpoints(
            self.sessions,
            self.workspace_id,
            self.run_id,
            self.claim_token,
            self.master,
            path=(*self.path, component),
            parent_node_id=self.identity(node.id),
            iteration_index=iteration,
            workflow_version_id=str(version_id),
        )

    def bind_scope(self, ceiling, deadline, entry_id):
        with self.sessions() as db:
            row = db.scalar(
                select(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.workspace_id == self.workspace_id,
                    WorkflowCheckpoint.run_id == self.run_id,
                    WorkflowCheckpoint.node_id == self.identity(entry_id),
                )
            )
            previous = view(row, self.master) if row else {}
        self.ceiling = min(ceiling, Decimal(previous.get("_scope_ceiling", str(ceiling))))
        self.deadline = min(
            deadline, datetime.fromisoformat(previous.get("_scope_deadline", deadline.isoformat()))
        )
        return self.ceiling, self.deadline

    def node_deadline(self, node, candidate):
        with self.sessions() as db:
            row = db.scalar(
                select(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.workspace_id == self.workspace_id,
                    WorkflowCheckpoint.run_id == self.run_id,
                    WorkflowCheckpoint.node_id == self.identity(node.id),
                )
            )
            previous = view(row, self.master) if row else {}
        return min(
            candidate, datetime.fromisoformat(previous.get("_node_deadline", candidate.isoformat()))
        )

    def completed(self):
        with self.sessions() as db:
            restored = [
                view(row, self.master)
                for row in rows(db, self.workspace_id, self.run_id)
                if row.state in {"completed", "skipped"}
            ]
            return {
                step.get("definition_node_id") or step["node_id"]: step
                for step in restored
                if step.get("scope", []) == list(self.path)
            }

    def _run(self, db, starting=False):
        run = db.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.workspace_id == self.workspace_id, WorkflowRun.id == self.run_id)
            .with_for_update()
        )
        if not run or run.state != "running" or run.claim_token != self.claim_token:
            fail(409, "RUN_INTERRUPTED", "This workflow claim is no longer active.")
        if starting and (run.cancel_requested_at or datetime.now(UTC) >= run.deadline_at):
            fail(409, "RUN_INTERRUPTED", "This workflow was cancelled or reached its deadline.")
        if starting:
            from app.modules.executions.authorization import assert_authorized

            assert_authorized(db, run)
        run.heartbeat_at = datetime.now(UTC)
        return run

    def write(self, node, data, step, sequence, starting=False):
        now = datetime.now(UTC)
        with self.sessions() as db:
            run = self._run(db, starting)
            row = db.scalar(
                select(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.run_id == run.id,
                    WorkflowCheckpoint.node_id == self.identity(node.id),
                )
            )
            prior_step = (
                view(row, self.master) if row and node.type in {"subworkflow", "for_each"} else {}
            )
            if row is None:
                # Allocate once under the run lock. Recovery may skip an entire
                # completed subtree, so traversal-local sequence numbers are unsafe.
                previous_sequence = db.scalar(
                    select(func.max(WorkflowCheckpoint.sequence)).where(
                        WorkflowCheckpoint.run_id == run.id
                    )
                )
                sequence = 0 if previous_sequence is None else previous_sequence + 1
                if sequence >= MAX_EXPANDED_STEPS:
                    fail(422, "WORKFLOW_STEP_LIMIT", "This run reached its expanded step limit.")
                row = WorkflowCheckpoint(
                    id=uuid.uuid4(),
                    workspace_id=self.workspace_id,
                    run_id=self.run_id,
                    node_id=self.identity(node.id),
                    sequence=sequence,
                    attempt=1,
                    started_at=now,
                )
                db.add(row)
            elif starting and row.state != "waiting":
                row.attempt += 1
                row.started_at = now
            row.state = step["status"]
            row.error_code = step.get("error_code")
            row.finished_at = None if starting else now
            stored_step = {
                **step,
                "node_id": row.node_id,
                "definition_node_id": node.id,
                "scope": list(self.path),
                "parent_node_id": self.parent_node_id,
                "iteration_index": self.iteration_index,
                "workflow_version_id": self.workflow_version_id,
            }
            if self.ceiling is not None:
                stored_step.update(
                    _scope_ceiling=str(self.ceiling), _scope_deadline=self.deadline.isoformat()
                )
            if node.type in {"subworkflow", "for_each"}:
                candidate = min(
                    self.deadline or run.deadline_at,
                    now + timedelta(seconds=node.policy.get("timeout_seconds", 60)),
                )
                stored_step["_node_deadline"] = prior_step.get(
                    "_node_deadline", candidate.isoformat()
                )
            payload = json.dumps({"input": data, "step": stored_step})
            with db.no_autoflush:
                other_bytes = db.scalar(
                    select(
                        func.coalesce(func.sum(func.octet_length(WorkflowCheckpoint.ciphertext)), 0)
                    ).where(WorkflowCheckpoint.run_id == run.id, WorkflowCheckpoint.id != row.id)
                )
            if other_bytes + len(payload.encode()) + 16 > MAX_CHECKPOINT_BYTES:
                fail(
                    422,
                    "CHECKPOINT_STORAGE_LIMIT",
                    "This run reached its 2 MiB checkpoint budget. Reduce item count or payload size.",
                )
            row.nonce, row.ciphertext = encrypt_secret(
                self.master, self.workspace_id, row.id, 1, payload
            )
            if step["status"] == "completed" and node.type in {"agent", "mcp_tool", "http_tool"}:
                run.external_inflight = False
            db.commit()

    def start(self, node, data, sequence):
        self.write(
            node,
            data,
            {"node_id": node.id, "type": node.type, "status": "running", "output": None},
            sequence,
            starting=True,
        )

    def finish(self, node, data, step, sequence):
        self.write(node, data, step, sequence)
