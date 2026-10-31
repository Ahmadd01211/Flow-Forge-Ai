import json

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.executions.models import AgentRun
from tests.conftest import headers
from tests.test_agent_runs import published_agent

CATALOG = json.dumps([{
    "id": "docs", "name": "Company docs", "url": "https://mcp.example.com/mcp",
    "allowed_tools": ["search", "delete_everything"], "read_only_tools": ["search"],
}])


def _draft(client, workspace, *nodes):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Node tests"}).json()
    graph = workflow["graph"]
    for index, node in enumerate(nodes):
        graph["nodes"].insert(1 + index, {"label": node["id"], "position": {"x": 300, "y": 100 * index}, **node})
    return f"{base}/{workflow['id']}", graph


def _test(client, path, graph, node_id, key=None, **body):
    extra = {"Idempotency-Key": key} if key else {}
    return client.post(f"{path}/nodes/{node_id}/test", headers={**headers(client), **extra}, json={"graph": graph, **body})


def test_local_steps_run_on_sample_input_without_saving(client, owner):
    workspace = owner["workspaces"][0]["id"]
    path, graph = _draft(
        client, workspace,
        {"id": "shape", "type": "transform", "config": {"fields": {
            "queue": {"kind": "literal", "value": "billing"}, "who": {"kind": "input", "pointer": "/user/name"},
        }}},
        {"id": "decide", "type": "condition", "config": {
            "operator": "gt", "left": {"kind": "input", "pointer": "/score"}, "right": {"kind": "literal", "value": 5},
        }},
    )
    # Neither node is connected yet: an unfinished graph does not block testing one step.
    shaped = _test(client, path, graph, "shape", input={"user": {"name": "Ada"}})
    assert shaped.status_code == 200, shaped.text
    assert shaped.json()["status"] == "completed" and shaped.json()["output"] == {"queue": "billing", "who": "Ada"}
    decided = _test(client, path, graph, "decide", input={"score": 9}).json()
    assert decided["selected_port"] == "true" and decided["output"] == {"score": 9}
    missing = _test(client, path, graph, "shape", input={}).json()
    assert missing["status"] == "failed" and missing["error"]["code"] == "POINTER_MISSING"
    assert client.get(path).json()["revision"] == 1


def test_invalid_configuration_and_unknown_steps_are_rejected(client, owner):
    workspace = owner["workspaces"][0]["id"]
    path, graph = _draft(client, workspace, {"id": "decide", "type": "condition", "config": {"operator": "eq"}})
    rejected = _test(client, path, graph, "decide", input={})
    assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "NODE_CONFIG_INVALID"
    assert _test(client, path, graph, "nope", input={}).status_code == 404


def test_result_fields_combine_step_outputs_and_incoming_data(client, owner):
    workspace = owner["workspaces"][0]["id"]
    path, graph = _draft(client, workspace, {"id": "shape", "type": "transform", "config": {
        "fields": {"queue": {"kind": "literal", "value": "billing"}},
    }})
    graph["edges"] = [
        {"id": "a", "source": "input", "target": "shape"},
        {"id": "b", "source": "shape", "target": "result"},
    ]
    graph["nodes"][-1]["config"] = {"fields": {
        "queue": {"kind": "output", "node_id": "shape", "pointer": "/queue"},
        "original": {"kind": "output", "node_id": "input", "pointer": "/text"},
        "version": {"kind": "literal", "value": 2},
    }}
    tested = _test(client, path, graph, "result", input={"queue": "billing"}, outputs={
        "shape": {"queue": "billing"}, "input": {"text": "hi"},
    }).json()
    assert tested["output"] == {"queue": "billing", "original": "hi", "version": 2}
    unrun = _test(client, path, graph, "result", input={}, outputs={}).json()
    assert unrun["status"] == "failed" and unrun["error"]["code"] == "RESULT_SOURCE_INVALID"
    saved = client.patch(path, headers=headers(client), json={"name": "Node tests", "expected_revision": 1, "graph": graph})
    assert saved.status_code == 200, saved.text
    preview = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": {"text": "hi"}})
    assert preview.status_code == 200, preview.text
    assert preview.json()["output"] == {"queue": "billing", "original": "hi", "version": 2}


def test_mcp_node_test_needs_confirmation_and_read_only_grant(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: [
        {"name": "search", "description": "Find docs", "input_schema": {"type": "object"}},
        {"name": "delete_everything", "description": "Danger", "input_schema": {"type": "object"}},
    ])
    calls = []
    monkeypatch.setattr("app.modules.mcp.service.call_tool", lambda url, key, name, data: calls.append(name) or {"hits": 1})
    assert client.put(f"/api/v1/workspaces/{workspace}/mcp/docs", headers=headers(client), json={"bearer_token": "test-mcp-secret"}).status_code == 200
    path, graph = _draft(
        client, workspace,
        {"id": "lookup", "type": "mcp_tool", "config": {"server_id": "docs", "tool_name": "search"}},
        {"id": "danger", "type": "mcp_tool", "config": {"server_id": "docs", "tool_name": "delete_everything"}},
    )
    unconfirmed = _test(client, path, graph, "lookup", input={"query": "policy"})
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "EXTERNAL_TEST_UNCONFIRMED"
    assert calls == []
    tested = _test(client, path, graph, "lookup", input={"query": "policy"}, confirm_external=True).json()
    assert tested["status"] == "completed" and tested["external"] and tested["output"] == {"hits": 1}
    assert calls == ["search"]
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "workflow.node_tested")) is not None
    blocked = _test(client, path, graph, "danger", input={}, confirm_external=True)
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "NODE_CONFIG_INVALID"
    assert calls == ["search"]


def test_agent_node_test_becomes_a_budgeted_agent_run(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    path, graph = _draft(client, workspace, {"id": "triage", "type": "agent", "config": {"version_id": version["id"]}})
    unconfirmed = _test(client, path, graph, "triage", key="node-test-0001", input={"ticket": "urgent"})
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "EXTERNAL_TEST_UNCONFIRMED"
    queued = _test(client, path, graph, "triage", key="node-test-0001", input={"ticket": "urgent"}, confirm_external=True)
    assert queued.status_code == 200, queued.text
    run = queued.json()["agent_run"]
    assert queued.json()["status"] == "queued" and run["state"] == "queued" and run["reserved_max_usd"]
    assert db.scalar(select(AgentRun).where(AgentRun.id == run["id"])) is not None
    again = _test(client, path, graph, "triage", key="node-test-0001", input={"ticket": "urgent"}, confirm_external=True)
    assert again.json()["agent_run"]["id"] == run["id"]


def test_node_tests_accept_larger_bodies_than_other_endpoints(client, owner):
    workspace = owner["workspaces"][0]["id"]
    path, graph = _draft(client, workspace, {"id": "shape", "type": "transform", "config": {
        "fields": {"who": {"kind": "input", "pointer": "/user"}},
    }})
    body = json.dumps({"graph": graph, "input": {"user": "Ada"}, "outputs": {"pad": "y" * 250000}}) + " " * 400000
    sent = {**headers(client), "Content-Type": "application/json"}
    accepted = client.post(f"{path}/nodes/shape/test", headers=sent, content=body)
    assert accepted.status_code == 200 and accepted.json()["output"] == {"who": "Ada"}, accepted.text
    rejected = client.post(f"{path}/check", headers=sent, content=body)
    assert rejected.status_code == 413 and rejected.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
