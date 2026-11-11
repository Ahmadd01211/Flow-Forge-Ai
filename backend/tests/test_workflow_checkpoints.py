import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.credentials import load_master_key
from app.core.errors import fail
from app.modules.executions import worker
from app.modules.workflows import preview
from app.modules.workflows.checkpoints import Checkpoints
from app.modules.workflows.models import WorkflowCheckpoint, WorkflowRun
from app.modules.workflows.runtime import execute
from app.modules.workflows.schemas import Node
from tests.conftest import headers, register
from tests.test_workflow_dag import edge, node, ticket_agent
from tests.test_workflow_data_nodes import _save


def queue(client, workspace, version, value, key="checkpoint-run-0001"):
    response = client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs",
        headers={**headers(client), "Idempotency-Key": key},
        json={"version_id": version["id"], "input": value},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def reconcile(client, monkeypatch):
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    monkeypatch.setattr(worker.celery, "send_task", lambda *_, **__: None)
    return worker.reconcile_workflows_once()


@pytest.mark.parametrize("temporary", [True, False])
def test_retry_policy_only_retries_safe_transient_local_failures(
    client, owner, monkeypatch, temporary
):
    workspace = owner["workspaces"][0]["id"]
    current = node("shape", "transform", {"fields": {"ok": {"kind": "literal", "value": True}}})
    current["policy"] = {"timeout_seconds": 1, "max_attempts": 3}
    graph = {
        "nodes": [node("input", "manual_input"), current, node("result", "result")],
        "edges": [edge("input", "shape"), edge("shape", "result")],
    }
    path = _save(client, workspace, "Local retry policy", graph)
    version = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 2}
    ).json()
    original = preview.run_step
    calls = []

    def intermittent(current, *args):
        if current.id == "shape":
            calls.append(True)
            if len(calls) == 1 or not temporary:
                fail(
                    503 if temporary else 422,
                    "LOCAL_TOOL_TEMPORARILY_UNAVAILABLE" if temporary else "TOOL_INPUT_INVALID",
                    "Step unavailable.",
                )
        return original(current, *args)

    monkeypatch.setattr(preview, "run_step", intermittent)
    run_id = queue(client, workspace, version, {})
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert len(calls) == (2 if temporary else 1)
    assert result["state"] == ("completed" if temporary else "failed")
    assert next(step for step in result["steps"] if step["node_id"] == "shape")["attempt"] == len(
        calls
    )
    summary = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs").json()["items"][0]
    assert summary["steps"] is None and summary["output"] is None


def test_external_retry_policy_is_rejected_and_step_timeout_is_forwarded(
    client, owner, db, monkeypatch
):
    from copy import deepcopy

    from app.modules.workflows.models import WorkflowVersion

    workspace, version = ticket_agent(client, owner, monkeypatch)
    graph = deepcopy(db.get(WorkflowVersion, uuid.UUID(version["id"])).graph)
    graph["nodes"][1]["policy"] = {"timeout_seconds": 2, "max_attempts": 3}
    path = _save(client, workspace, "Step policy", graph)
    invalid = client.post(
        path + "/validate", headers=headers(client), json={"expected_revision": 2}
    ).json()
    assert not invalid["valid"] and any(
        issue["path"] == "policy.max_attempts" for issue in invalid["errors"]
    )
    graph["nodes"][1]["policy"]["max_attempts"] = 1
    checked = client.patch(
        path,
        headers=headers(client),
        json={"name": "Step policy", "expected_revision": 2, "graph": graph},
    )
    assert checked.status_code == 200, checked.text
    published = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 3}
    ).json()
    timeouts = []

    def generate(_, __, value, ___, timeout):
        timeouts.append(timeout)
        return value, 10, 10

    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    run_id = queue(client, workspace, published, {"ticket": "Check deadline"})
    execute(run_id, client.app.state.settings)
    assert timeouts[0] <= 2 and len(timeouts) == 2


def test_resume_reuses_completed_agent_and_fences_old_claim(client, owner, db, monkeypatch):
    workspace, version = ticket_agent(client, owner, monkeypatch)
    run_id = queue(client, workspace, version, {"ticket": "confidential checkpoint case"})
    calls = []

    def generate(_, __, value, *___):
        calls.append(value)
        return {"ticket": value["ticket"] + "!"}, 100, 20

    original = Checkpoints.start

    def crash(self, current, data, sequence):
        original(self, current, data, sequence)
        if current.id == "second":
            raise SystemExit("Simulated process loss before second agent call")

    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    monkeypatch.setattr(Checkpoints, "start", crash)
    with pytest.raises(SystemExit):
        execute(run_id, client.app.state.settings)
    row = db.get(WorkflowRun, uuid.UUID(run_id))
    old_claim = row.claim_token
    assert row.state == "running" and not row.external_inflight and len(calls) == 1
    records = db.scalars(
        select(WorkflowCheckpoint).where(WorkflowCheckpoint.run_id == row.id)
    ).all()
    assert all(b"confidential checkpoint case" not in record.ciphertext for record in records)
    row.heartbeat_at = datetime.now(UTC) - timedelta(seconds=11)
    row.deadline_at = datetime.now(UTC) + timedelta(seconds=30)
    db.commit()
    reconcile(client, monkeypatch)
    db.expire_all()
    assert row.state == "queued"
    stale = Checkpoints(
        client.app.state.sessions,
        row.workspace_id,
        row.id,
        old_claim,
        load_master_key(client.app.state.settings.credential_key_path),
    )
    with pytest.raises(HTTPException) as denied:
        stale.finish(
            Node.model_validate(node("input", "manual_input")),
            {},
            {
                "node_id": "input",
                "type": "manual_input",
                "status": "completed",
                "output": {"forged": True},
            },
            0,
        )
    assert denied.value.detail["code"] == "RUN_INTERRUPTED"
    monkeypatch.setattr(Checkpoints, "start", original)
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert result["state"] == "completed" and len(calls) == 2, result
    assert result["output"] == {"ticket": "confidential checkpoint case!!"}
    assert result["input_tokens"] == 200
    assert next(step for step in result["steps"] if step["node_id"] == "second")["attempt"] == 2
    detail = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}/steps/first").json()
    assert detail["input"] == {"ticket": "confidential checkpoint case"}
    assert detail["output"] == {"ticket": "confidential checkpoint case!"}


def test_inflight_external_call_is_not_recovered_or_replayed_automatically(
    client, owner, db, monkeypatch
):
    workspace, version = ticket_agent(client, owner, monkeypatch)
    run_id = queue(client, workspace, version, {"ticket": "Unknown provider outcome"})
    calls = []

    def crash(*_):
        calls.append(True)
        raise SystemExit("Process loss during provider request")

    monkeypatch.setattr("app.modules.workflows.runtime.generate", crash)
    with pytest.raises(SystemExit):
        execute(run_id, client.app.state.settings)
    row = db.get(WorkflowRun, uuid.UUID(run_id))
    assert row.external_inflight and row.uncertain_cost_usd > 0
    row.heartbeat_at = datetime.now(UTC) - timedelta(seconds=11)
    row.deadline_at = datetime.now(UTC) + timedelta(seconds=30)
    db.commit()
    reconcile(client, monkeypatch)
    db.expire_all()
    assert row.state == "running" and len(calls) == 1
    row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    reconcile(client, monkeypatch)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "RUN_TIMEOUT"
    assert result["steps"][-1]["status"] == "failed"
    execute(run_id, client.app.state.settings)
    assert len(calls) == 1
    path = f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}/replay"
    head = {**headers(client), "Idempotency-Key": "explicit-replay-001"}
    assert client.post(path, headers=head, json={}).status_code == 422
    replay = client.post(path, headers=head, json={"confirm_external": True})
    assert replay.status_code == 202 and replay.json()["id"] != run_id, replay.text
    assert (
        client.post(path, headers=head, json={"confirm_external": True}).json()["id"]
        == replay.json()["id"]
    )


def test_failure_keeps_prior_step_evidence_and_replay_is_a_new_guarded_run(client, owner):
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node("parse", "json_parse", {"source": "/text"}),
            node("result", "result"),
        ],
        "edges": [edge("input", "parse"), edge("parse", "result")],
    }
    path = _save(client, workspace, "Failure evidence", graph)
    version = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 2}
    ).json()
    run_id = queue(client, workspace, version, {"text": "bad-json-private-input"})
    execute(run_id, client.app.state.settings)
    base = f"/api/v1/workspaces/{workspace}/workflow-runs"
    result = client.get(f"{base}/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "JSON_PARSE_INVALID"
    assert [step["status"] for step in result["steps"]] == ["completed", "failed"]
    detail = client.get(f"{base}/{run_id}/steps/parse").json()
    assert (
        detail["input"] == {"text": "bad-json-private-input"}
        and detail["error_code"] == "JSON_PARSE_INVALID"
    )
    head = {**headers(client), "Idempotency-Key": "pure-replay-0001"}
    replay = client.post(f"{base}/{run_id}/replay", headers=head, json={})
    assert replay.status_code == 202 and replay.json()["id"] != run_id
    active = client.post(
        f"{base}/{replay.json()['id']}/replay",
        headers={**headers(client), "Idempotency-Key": "active-replay-0001"},
        json={},
    )
    assert active.status_code == 409
    client.cookies.clear()
    register(client, "checkpoint-outsider@example.com")
    assert client.get(f"{base}/{run_id}/steps/parse").status_code == 404
    assert (
        client.post(
            f"{base}/{run_id}/replay",
            headers={**headers(client), "Idempotency-Key": "outsider-replay-001"},
            json={},
        ).status_code
        == 404
    )
