import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.executions import worker
from app.modules.executions.runtime import ProviderFailure
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.runtime import execute
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent


def test_published_workflow_run_recovery_and_isolation(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Echo"}).json()
    versions = f"{base}/{workflow['id']}/versions"
    published = client.post(versions, headers=headers(client), json={"expected_revision": 1})
    assert published.status_code == 201, published.text
    version = published.json()
    assert version["number"] == 1
    assert (
        client.post(versions, headers=headers(client), json={"expected_revision": 1}).json()["id"]
        == version["id"]
    )
    with pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE workflow_version SET name='mutated' WHERE id=:id"), {"id": version["id"]}
        )
    db.rollback()


def test_published_workflow_run_lifecycle(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Echo"}).json()
    version = client.post(
        f"{base}/{workflow['id']}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    payload = {"version_id": version["id"], "input": {"ticket": "A-1"}}
    head = {**headers(client), "Idempotency-Key": "echo-run-0001"}
    submitted = client.post(runs, headers=head, json=payload)
    assert submitted.status_code == 202, submitted.text
    run_id = submitted.json()["id"]
    replay = client.post(runs, headers=head, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == run_id
    conflict = client.post(runs, headers=head, json={**payload, "input": {"ticket": "B-2"}})
    assert conflict.status_code == 409
    execute(run_id, client.app.state.settings)
    completed = client.get(f"{runs}/{run_id}")
    assert completed.status_code == 200 and completed.json()["state"] == "completed"
    assert completed.json()["output"] == {"ticket": "A-1"}
    assert len(completed.json()["steps"]) == 2
    assert client.get(runs).json()["items"][0]["id"] == run_id
    second = client.post(
        runs, headers={**headers(client), "Idempotency-Key": "echo-run-0002"}, json=payload
    ).json()
    cancelled = client.post(f"{runs}/{second['id']}/cancel", headers=headers(client))
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    execute(second["id"], client.app.state.settings)
    assert client.get(f"{runs}/{second['id']}").json()["state"] == "cancelled"
    client.cookies.clear()
    register(client, "other-workflow@example.com")
    assert client.get(f"{runs}/{run_id}").status_code == 404


def test_transform_preview_publish_and_durable_run(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Ticket summary"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "shape", "type": "transform", "label": "Shape ticket",
        "position": {"x": 300, "y": 180},
        "config": {
            "fields": {
                "ticket_id": {"kind": "input", "pointer": "/ticket/id"},
                "status": {"kind": "literal", "value": "received"},
            },
            "output_schema": {
                "type": "object", "properties": {
                    "ticket_id": {"type": "string"}, "status": {"type": "string"},
                }, "required": ["ticket_id", "status"], "additionalProperties": False,
            },
        },
    })
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "shape", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-shape", "source": "input", "target": "shape"},
        {"id": "shape-result", "source": "shape", "target": "result"},
    ]
    path = f"{base}/{workflow['id']}"
    saved = client.patch(path, headers=headers(client), json={
        "name": workflow["name"], "expected_revision": 1, "graph": graph,
    })
    assert saved.status_code == 200, saved.text
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.json()["publishable"] is True, checked.text
    input_data = {"ticket": {"id": "T-42"}}
    preview = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": input_data})
    expected = {"ticket_id": "T-42", "status": "received"}
    assert preview.status_code == 200 and preview.json()["output"] == expected, preview.text
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    submitted = client.post(runs, headers={**headers(client), "Idempotency-Key": "transform-run-001"}, json={
        "version_id": version.json()["id"], "input": input_data,
    })
    assert submitted.status_code == 202, submitted.text
    execute(submitted.json()["id"], client.app.state.settings)
    result = client.get(f"{runs}/{submitted.json()['id']}").json()
    assert result["state"] == "completed" and result["output"] == expected
    assert result["steps"][1]["type"] == "transform"
    assert result["cost_usd"] is None

    missing = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": {"ticket": {}}})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "POINTER_MISSING"


def test_transform_rejects_unsafe_or_invalid_configuration(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Unsafe transform"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "shape", "type": "transform", "label": "Shape",
        "position": {"x": 300, "y": 180},
        "config": {"fields": {"secret": {"kind": "input", "pointer": "/__proto__/value"}}},
    })
    graph["edges"] = [
        {"id": "input-shape", "source": "input", "target": "shape"},
        {"id": "shape-result", "source": "shape", "target": "result"},
    ]
    path = f"{base}/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph}).status_code == 200
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2}).json()
    assert checked["publishable"] is False
    assert any(error["code"] == "TRANSFORM_INVALID" for error in checked["errors"])
    assert client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2}).status_code == 422


def test_linear_workflow_runs_pinned_agent_and_records_usage(client, owner, monkeypatch):
    workspace, agent_version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Agent triage flow"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "triage", "type": "agent", "label": "Triage agent",
        "position": {"x": 300, "y": 180}, "config": {"version_id": agent_version["id"]},
    })
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "triage", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-triage", "source": "input", "target": "triage"},
        {"id": "triage-result", "source": "triage", "target": "result"},
    ]
    saved = client.patch(f"{base}/{workflow['id']}", headers=headers(client), json={
        "name": workflow["name"], "expected_revision": 1, "graph": graph,
    })
    assert saved.status_code == 200, saved.text
    checked = client.post(f"{base}/{workflow['id']}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.status_code == 200 and checked.json()["publishable"] is True, checked.text
    version = client.post(f"{base}/{workflow['id']}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    queued = client.post(runs, headers={**headers(client), "Idempotency-Key": "agent-flow-001"}, json={
        "version_id": version.json()["id"], "input": {"ticket": "Outage"},
    })
    assert queued.status_code == 202, queued.text
    monkeypatch.setattr("app.modules.workflows.runtime.generate", lambda *_args: ({"priority": "urgent"}, 80, 15))
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"{runs}/{queued.json()['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"priority": "urgent"}
    assert result["input_tokens"] == 80 and result["output_tokens"] == 15
    assert result["cost_usd"] is not None
    assert result["steps"][1]["usage"]["agent_version_id"] == agent_version["id"]
    uncertain = client.post(runs, headers={**headers(client), "Idempotency-Key": "agent-flow-uncertain"}, json={
        "version_id": version.json()["id"], "input": {"ticket": "Another outage"},
    }).json()
    def uncertain_provider(*_args):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
    monkeypatch.setattr("app.modules.workflows.runtime.generate", uncertain_provider)
    execute(uncertain["id"], client.app.state.settings)
    failed = client.get(f"{runs}/{uncertain['id']}").json()
    assert failed["state"] == "failed" and failed["uncertain_cost_usd"] is not None
    rotated = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai",
        headers=headers(client), json={"api_key": "sk-rotated-workflow-aaaaaaaaaaaaaaaa"},
    )
    assert rotated.status_code == 200
    rejected = client.post(runs, headers={**headers(client), "Idempotency-Key": "agent-flow-002"}, json={
        "version_id": version.json()["id"], "input": {"ticket": "Outage"},
    })
    assert rejected.status_code == 422


def test_workflow_agent_node_runs_approved_tool_and_rechecks_grant(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client), json={
        "api_key": "sk-workflow-tool-aaaaaaaaaaaaaaaa",
    })
    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    agents = f"/api/v1/workspaces/{workspace}/agents"
    agent = client.post(agents, headers=headers(client), json={
        "name": "Cleanup agent", "config": {
            "instructions": "Clean up the ticket and return JSON.",
            "model_id": "gpt-5-mini", "tool_keys": ["text.replace"],
        },
    }).json()
    published = client.post(f"{agents}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    assert published.status_code == 201, published.text
    version_id = published.json()["id"]
    options = client.get(f"{agents}/workflow-options").json()["items"]
    assert any(row["id"] == version_id and row["tool_keys"] == ["text.replace"] for row in options)

    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Agent cleanup"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "cleanup", "type": "agent", "label": "Cleanup agent",
        "position": {"x": 300, "y": 180}, "config": {"version_id": version_id},
    })
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "cleanup", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-cleanup", "source": "input", "target": "cleanup"},
        {"id": "cleanup-result", "source": "cleanup", "target": "result"},
    ]
    path = f"{base}/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph}).status_code == 200
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.status_code == 200 and checked.json()["publishable"], checked.text
    flow_version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert flow_version.status_code == 201, flow_version.text
    calls = []
    def reply(_key, payload, _timeout):
        calls.append(payload)
        if len(calls) == 1:
            return {"status": "completed", "usage": {"input_tokens": 40, "output_tokens": 10}, "output": [{
                "type": "function_call", "name": "text_replace", "call_id": "call-1",
                "arguments": '{"text":"Hi Alex","find":"Alex","replacement":"team"}',
            }]}
        assert payload["input"][-1]["output"] == '{"text": "Hi team"}'
        return {"status": "completed", "usage": {"input_tokens": 55, "output_tokens": 12}, "output": [{
            "type": "message", "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
        }]}
    monkeypatch.setattr("app.modules.executions.runtime._openai_response", reply)
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    queued = client.post(runs, headers={**headers(client), "Idempotency-Key": "workflow-agent-tool-001"}, json={
        "version_id": flow_version.json()["id"], "input": {"ticket": "Hi Alex"},
    })
    assert queued.status_code == 202, queued.text
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"{runs}/{queued.json()['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"priority": "normal"}
    assert result["input_tokens"] == 95 and result["output_tokens"] == 22
    assert result["steps"][1]["usage"]["tool_keys"] == ["text.replace"]
    assert len(calls) == 2

    client.delete(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    rejected = client.post(runs, headers={**headers(client), "Idempotency-Key": "workflow-agent-tool-002"}, json={
        "version_id": flow_version.json()["id"], "input": {"ticket": "Hi again"},
    })
    assert rejected.status_code == 422

    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    pending = client.post(runs, headers={**headers(client), "Idempotency-Key": "workflow-agent-tool-003"}, json={
        "version_id": flow_version.json()["id"], "input": {"ticket": "Hi again"},
    })
    assert pending.status_code == 202, pending.text
    def revoked_during_model(_key, _payload, _timeout):
        client.delete(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
        return {"status": "completed", "usage": {"input_tokens": 40, "output_tokens": 10}, "output": [{
            "type": "function_call", "name": "text_replace", "call_id": "call-2",
            "arguments": '{"text":"Hi Alex","find":"Alex","replacement":"team"}',
        }]}
    monkeypatch.setattr("app.modules.executions.runtime._openai_response", revoked_during_model)
    execute(pending.json()["id"], client.app.state.settings)
    failed = client.get(f"{runs}/{pending.json()['id']}").json()
    assert failed["state"] == "failed" and failed["error_code"] == "TOOL_APPROVAL_REVOKED"
    assert failed["uncertain_cost_usd"] is not None


def test_workflow_external_call_marker_prevents_automatic_replay(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Recovery guard"}).json()
    version = client.post(f"{base}/{workflow['id']}/versions", headers=headers(client), json={"expected_revision": 1}).json()
    run = client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs",
        headers={**headers(client), "Idempotency-Key": "recovery-guard-001"},
        json={"version_id": version["id"], "input": {"ticket": "A-1"}},
    ).json()
    row = db.scalar(select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(run["id"])))
    row.state = "running"
    row.started_at = datetime.now(UTC) - timedelta(seconds=8)
    row.external_started_at = row.started_at
    row.claim_token = uuid.uuid4()
    row.deadline_at = datetime.now(UTC) + timedelta(seconds=8)
    db.commit()
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    assert worker.reconcile_workflows_once() == 0
    db.refresh(row)
    assert row.state == "running" and row.claim_token is not None
    row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    worker.reconcile_workflows_once()
    db.refresh(row)
    assert row.state == "failed" and row.uncertain_cost_usd is None
