import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.modules.executions import worker
from app.modules.workflows.models import WorkflowRun, WorkflowVersion
from app.modules.workflows.runtime import execute
from tests.conftest import headers

CATALOG = json.dumps([{
    "id": "docs", "name": "Company docs", "url": "https://mcp.example.com/mcp",
    "allowed_tools": ["search", "delete_everything"], "read_only_tools": ["search"],
}])


def test_published_mcp_workflow_pins_grant_and_runs(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: [
        {"name": "search", "description": "Find docs", "input_schema": {
            "type": "object", "properties": {"query": {"type": "string"}},
            "required": ["query"], "additionalProperties": False,
        }},
        {"name": "delete_everything", "description": "Danger", "input_schema": {"type": "object"}},
    ])
    base = f"/api/v1/workspaces/{workspace}"
    connected = client.put(f"{base}/mcp/docs", headers=headers(client), json={"bearer_token": "test-mcp-secret"})
    assert connected.status_code == 200, connected.text
    assert connected.json()["items"][0]["runnable_tools"] == ["search"]

    workflow = client.post(f"{base}/workflows", headers=headers(client), json={"name": "Search docs"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "lookup", "type": "mcp_tool", "label": "Search company docs",
        "position": {"x": 300, "y": 180}, "config": {"server_id": "docs", "tool_name": "search"},
    })
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "lookup", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-lookup", "source": "input", "target": "lookup"},
        {"id": "lookup-result", "source": "lookup", "target": "result"},
    ]
    path = f"{base}/workflows/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph}).status_code == 200
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.status_code == 200 and checked.json()["publishable"], checked.text
    preview = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": {"query": "policy"}})
    assert preview.status_code == 422 and preview.json()["error"]["code"] == "PREVIEW_UNSUPPORTED"
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    db.expire_all()
    frozen = db.scalar(select(WorkflowVersion).where(WorkflowVersion.id == uuid.UUID(version.json()["id"])))
    config = frozen.graph["nodes"][1]["config"]
    assert config["connection_generation"] == 1 and len(config["input_schema_hash"]) == 64

    calls = []
    run_id = None
    def remote_call(url, key, name, data):
        db.expire_all()
        active = db.scalar(select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(run_id)))
        assert active.external_started_at is not None
        calls.append((url, key, name, data))
        return {"content": [{"type": "text", "text": "Found policy"}]}
    monkeypatch.setattr("app.modules.workflows.runtime.call_tool", remote_call)
    runs = f"{base}/workflow-runs"
    queued = client.post(runs, headers={**headers(client), "Idempotency-Key": "mcp-search-001"}, json={
        "version_id": version.json()["id"], "input": {"query": "policy"},
    })
    assert queued.status_code == 202, queued.text
    run_id = queued.json()["id"]
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"{runs}/{queued.json()['id']}").json()
    assert result["state"] == "completed" and result["output"]["content"][0]["text"] == "Found policy"
    assert calls == [("https://mcp.example.com/mcp", "test-mcp-secret", "search", {"query": "policy"})]

    invalid = client.post(runs, headers={**headers(client), "Idempotency-Key": "mcp-search-002"}, json={
        "version_id": version.json()["id"], "input": {"unexpected": "value"},
    })
    assert invalid.status_code == 202
    execute(invalid.json()["id"], client.app.state.settings)
    failed = client.get(f"{runs}/{invalid.json()['id']}").json()
    assert failed["state"] == "failed" and failed["error_code"] == "MCP_INPUT_SCHEMA_INVALID"
    assert len(calls) == 1

    pending = client.post(runs, headers={**headers(client), "Idempotency-Key": "mcp-search-recovery"}, json={
        "version_id": version.json()["id"], "input": {"query": "policy"},
    })
    assert pending.status_code == 202
    row = db.scalar(select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(pending.json()["id"])))
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
    assert len(calls) == 1

    assert client.delete(f"{base}/mcp/docs", headers=headers(client)).status_code == 200
    revoked = client.post(runs, headers={**headers(client), "Idempotency-Key": "mcp-search-003"}, json={
        "version_id": version.json()["id"], "input": {"query": "policy"},
    })
    assert revoked.status_code == 422
    reconnected = client.put(f"{base}/mcp/docs", headers=headers(client), json={"bearer_token": "new-mcp-secret"})
    assert reconnected.status_code == 200
    rotated = client.post(runs, headers={**headers(client), "Idempotency-Key": "mcp-search-004"}, json={
        "version_id": version.json()["id"], "input": {"query": "policy"},
    })
    assert rotated.status_code == 422


def test_mcp_catalog_never_treats_unreviewed_tool_as_runnable(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: [
        {"name": "delete_everything", "description": "Danger", "input_schema": {"type": "object"}},
    ])
    base = f"/api/v1/workspaces/{workspace}"
    connected = client.put(f"{base}/mcp/docs", headers=headers(client), json={})
    assert connected.status_code == 200
    assert connected.json()["items"][0]["runnable_tools"] == []
    workflow = client.post(f"{base}/workflows", headers=headers(client), json={"name": "Unsafe"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "wipe", "type": "mcp_tool", "label": "Wipe",
        "position": {"x": 300, "y": 180}, "config": {"server_id": "docs", "tool_name": "delete_everything"},
    })
    graph["edges"] = [
        {"id": "input-wipe", "source": "input", "target": "wipe"},
        {"id": "wipe-result", "source": "wipe", "target": "result"},
    ]
    path = f"{base}/workflows/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph}).status_code == 200
    validation = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2}).json()
    assert not validation["publishable"] and validation["errors"][0]["code"] == "MCP_TOOL_UNAVAILABLE"
