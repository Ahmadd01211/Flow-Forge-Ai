import json
import uuid

import pytest
from sqlalchemy import select

from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import execute
from app.modules.mcp.agent_grants import alias
from app.modules.mcp.models import McpConnection
from tests.conftest import headers
from tests.test_workflow_mcp import CATALOG


def agent_with_mcp(client, owner, monkeypatch, tool="search"):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    monkeypatch.setattr(
        "app.modules.mcp.service.discover",
        lambda *_: [
            {
                "name": "search",
                "description": "Find company docs",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {"name": "delete_everything", "input_schema": {"type": "object"}},
        ],
    )
    assert (
        client.put(
            f"{base}/mcp/docs", headers=headers(client), json={"bearer_token": "test-mcp-secret"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/integrations/providers/openai",
            headers=headers(client),
            json={"api_key": "test-provider-secret"},
        ).status_code
        == 200
    )
    draft = client.post(
        f"{base}/agents",
        headers=headers(client),
        json={
            "name": "Docs agent",
            "config": {
                "instructions": "Look up the ticket in company docs.",
                "model_id": "gpt-5-mini",
                "mcp_tools": [
                    {
                        "server_id": "docs",
                        "tool_name": tool,
                        "connection_generation": 999,
                        "input_schema": {"type": "object"},
                    }
                ],
            },
        },
    )
    assert draft.status_code == 201, draft.text
    path = f"{base}/agents/{draft.json()['id']}"
    return base, path


def queued(client, base, version, key="agent-mcp-001"):
    result = client.post(
        f"{base}/runs",
        headers={**headers(client), "Idempotency-Key": key},
        json={"version_id": version["id"], "input": {"ticket": "policy"}},
    )
    assert result.status_code == 202, result.text
    return result.json()["id"]


def test_agent_model_can_call_only_pinned_mcp_tool(client, owner, db, monkeypatch):
    base, path = agent_with_mcp(client, owner, monkeypatch)
    checked = client.get(f"{path}/readiness").json()
    assert checked["publishable"], checked
    published = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    )
    assert published.status_code == 201, published.text
    version = published.json()
    grant = version["config"]["mcp_tools"][0]
    assert grant["connection_generation"] == 1 and grant["input_schema"]["required"] == ["query"]
    run_id = queued(client, base, version)
    model_requests, remote_requests = [], []

    def model(key, payload, timeout):
        model_requests.append(payload)
        if len(model_requests) == 1:
            return {
                "status": "completed",
                "usage": {"input_tokens": 50, "output_tokens": 10},
                "output": [
                    {
                        "type": "function_call",
                        "name": alias(grant),
                        "call_id": "mcp-1",
                        "arguments": '{"query":"policy"}',
                    }
                ],
            }
        return {
            "status": "completed",
            "usage": {"input_tokens": 60, "output_tokens": 10},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
                }
            ],
        }

    def remote(url, key, name, data, timeout_seconds):
        db.expire_all()
        assert db.get(AgentRun, uuid.UUID(run_id)).model_started_at is not None
        remote_requests.append((url, key, name, data))
        assert timeout_seconds <= 12
        return {"content": [{"type": "text", "text": "policy found"}]}

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    monkeypatch.setattr("app.modules.mcp.client.call_tool", remote)
    execute(run_id, client.app.state.settings)
    result = client.get(f"{base}/runs/{run_id}").json()
    assert result["state"] == "completed", result
    assert result["input_tokens"] == 110 and result["output_tokens"] == 20
    assert remote_requests == [
        ("https://mcp.example.com/mcp", "test-mcp-secret", "search", {"query": "policy"})
    ]
    assert model_requests[0]["tools"][0]["strict"] is False
    assert "test-mcp-secret" not in json.dumps(model_requests)
    events = client.get(f"{base}/runs/{run_id}/events").json()["items"]
    assert any(e["kind"] == "tool" and e["status"] == "completed" for e in events)
    assert "policy found" not in json.dumps(events)
    execute(run_id, client.app.state.settings)
    assert len(remote_requests) == 1


def test_agent_cannot_publish_write_mcp_grant(client, owner, monkeypatch):
    _, path = agent_with_mcp(client, owner, monkeypatch, tool="delete_everything")
    checked = client.get(f"{path}/readiness").json()
    assert not checked["publishable"]
    result = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 1})
    assert result.status_code == 422 and result.json()["error"]["code"] == "MCP_GRANT_CHANGED"


def test_workflow_agent_node_test_keeps_workspace_mcp_catalog(client, owner, monkeypatch):
    from tests.test_node_test import _draft, _test

    _, path = agent_with_mcp(client, owner, monkeypatch)
    version = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    workspace = owner["workspaces"][0]["id"]
    workflow, graph = _draft(
        client, workspace, {"id": "docs", "type": "agent", "config": {"version_id": version["id"]}}
    )
    queued = _test(
        client,
        workflow,
        graph,
        "docs",
        key="mcp-node-test-001",
        input={"ticket": "policy"},
        confirm_external=True,
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["agent_run"]["state"] == "queued"


def test_revocation_after_model_response_blocks_remote_call(client, owner, db, monkeypatch):
    base, path = agent_with_mcp(client, owner, monkeypatch)
    version = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    run_id = queued(client, base, version)

    def model(*_):
        row = db.scalar(select(McpConnection))
        row.state = "revoked"
        db.commit()
        return {
            "status": "completed",
            "usage": {"input_tokens": 50, "output_tokens": 10},
            "output": [
                {
                    "type": "function_call",
                    "call_id": "revoked-call",
                    "name": alias(version["config"]["mcp_tools"][0]),
                    "arguments": '{"query":"policy"}',
                }
            ],
        }

    def forbidden(*_, **__):
        raise AssertionError("A revoked credential must never reach the remote service")

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    monkeypatch.setattr("app.modules.mcp.client.call_tool", forbidden)
    execute(run_id, client.app.state.settings)
    result = client.get(f"{base}/runs/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "MCP_GRANT_CHANGED"
    assert result["model_started"]


def test_invalid_mcp_arguments_are_returned_to_model_without_remote_call(
    client, owner, monkeypatch
):
    base, path = agent_with_mcp(client, owner, monkeypatch)
    version = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    run_id = queued(client, base, version)
    attempts = []

    def model(_, payload, __):
        attempts.append(payload)
        if len(attempts) == 1:
            output = [
                {
                    "type": "function_call",
                    "call_id": "bad-args",
                    "name": alias(version["config"]["mcp_tools"][0]),
                    "arguments": "{}",
                }
            ]
        else:
            assert "TOOL_INPUT_INVALID" in payload["input"][-1]["output"]
            output = [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
                }
            ]
        return {
            "status": "completed",
            "usage": {"input_tokens": 20, "output_tokens": 5},
            "output": output,
        }

    def forbidden(*_, **__):
        raise AssertionError("Invalid arguments must never be sent to MCP")

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    monkeypatch.setattr("app.modules.mcp.client.call_tool", forbidden)
    execute(run_id, client.app.state.settings)
    assert client.get(f"{base}/runs/{run_id}").json()["state"] == "completed"


@pytest.mark.parametrize("change", ["revoke", "rotate", "schema", "operator"])
def test_mcp_change_blocks_queued_agent_before_model_call(client, owner, db, monkeypatch, change):
    base, path = agent_with_mcp(client, owner, monkeypatch)
    published = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    run_id = queued(client, base, published)
    row = db.scalar(select(McpConnection))
    if change == "revoke":
        row.state = "revoked"
    elif change == "rotate":
        row.generation += 1
    elif change == "schema":
        row.tool_snapshots = [{"name": "search", "input_schema": {"type": "object"}}]
    else:
        client.app.state.settings.mcp_catalog_json = "[]"
    db.commit()

    def forbidden(*args):
        raise AssertionError("Model must not be called after its MCP grant is invalid")

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", forbidden)
    execute(run_id, client.app.state.settings)
    result = client.get(f"{base}/runs/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "MCP_GRANT_CHANGED"
    assert not result["model_started"]
