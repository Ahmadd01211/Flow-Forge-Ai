import asyncio
import json

import mcp.types as types
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.executions.runtime import execute
from app.modules.mcp import client as mcp_client
from app.modules.mcp.agent_grants import alias
from app.modules.mcp.models import McpConnection
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers
from tests.test_agent_mcp import queued
from tests.test_workflow_mcp import CATALOG

SECRET_URL = "https://mcp.example.com/s/path-secret-123/mcp"
ISSUE = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}
TOOLS = [
    {"name": "search", "description": "Find issues", "input_schema": {"type": "object"}, "read_only_hint": True},
    {"name": "create_issue", "description": "Open an issue", "input_schema": ISSUE},
    {"name": "delete_repo", "input_schema": {"type": "object"}, "read_only_hint": True, "destructive_hint": True},
    {"name": "bad name!", "input_schema": {"type": "object"}},
    {"name": "uses_ref", "input_schema": {"type": "object", "properties": {"a": {"$ref": "#/x"}}}},
]


def add(client, owner, monkeypatch, tools=TOOLS):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    discovered = []
    monkeypatch.setattr(
        "app.modules.mcp.service.discover",
        lambda url, key: discovered.append((url, key)) or [dict(tool) for tool in tools],
    )
    response = client.post(
        f"{base}/mcp/servers",
        headers=headers(client),
        json={"name": "Issue Tracker", "url": SECRET_URL, "bearer_token": "tracker-token"},
    )
    assert response.status_code == 201, response.text
    assert discovered == [(SECRET_URL, "tracker-token")]
    return base, response.json()


def item(listing, server_id):
    return next(entry for entry in listing["items"] if entry["id"] == server_id)


def test_added_server_hides_secret_url_and_defaults_to_read_only(client, owner, db, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    assert server_id.startswith("ws-issue-tracker-") and body["skipped_tools"] == 2
    server = item(body, server_id)
    assert server["source"] == "workspace" and server["origin"] == "https://mcp.example.com"
    policies = {tool["name"]: tool["policy"] for tool in server["tools"]}
    # Destructive hints override read-only hints; undeclared tools are writes.
    assert policies == {"create_issue": "block", "delete_repo": "block", "search": "allow"}
    assert server["runnable_tools"] == ["search"] and server["policy_editable"]
    listing = client.get(f"{base}/mcp").text
    assert "path-secret-123" not in listing and "tracker-token" not in listing
    row = db.scalar(select(McpConnection).where(McpConnection.server_id == server_id))
    assert row.url == "https://mcp.example.com"
    assert b"path-secret-123" not in row.ciphertext and b"tracker-token" not in row.ciphertext
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "mcp.server_added"))
    assert "path-secret-123" not in json.dumps(audit.details)


def test_server_url_and_role_checks(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    path = f"/api/v1/workspaces/{workspace}/mcp/servers"
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: TOOLS)
    for url in (
        "http://mcp.example.com/mcp",
        "https://10.0.0.5/mcp",
        "https://localhost/mcp",
        "https://db.internal/mcp",
        "https://mcp.example.com:8443/mcp",
    ):
        response = client.post(path, headers=headers(client), json={"name": "Bad", "url": url})
        assert response.status_code == 422 and response.json()["error"]["code"] == "MCP_URL_INVALID", url
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    denied = client.post(path, headers=headers(client), json={"name": "Docs", "url": SECRET_URL})
    assert denied.status_code == 403


def test_policy_controls_tests_and_runnable_tools(client, owner, db, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    calls = []
    monkeypatch.setattr(
        "app.modules.mcp.service.call_tool",
        lambda url, key, name, args: calls.append((url, key, name)) or {"content": []},
    )
    tool_path = f"{base}/mcp/{server_id}/tools"
    tested = client.post(f"{tool_path}/search/test", headers=headers(client), json={"arguments": {}})
    assert tested.status_code == 200 and calls == [(SECRET_URL, "tracker-token", "search")]
    assert client.post(f"{tool_path}/create_issue/test", headers=headers(client), json={"arguments": {}}).status_code == 403

    allowed = client.patch(f"{tool_path}/create_issue", headers=headers(client), json={"policy": "allow"})
    assert allowed.status_code == 200
    assert item(allowed.json(), server_id)["runnable_tools"] == ["create_issue", "search"]
    # Owners/admins may test an allowed write tool deliberately; editors may not.
    assert client.post(f"{tool_path}/create_issue/test", headers=headers(client), json={"arguments": {}}).status_code == 200
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    write_test = client.post(f"{tool_path}/create_issue/test", headers=headers(client), json={"arguments": {}})
    assert write_test.status_code == 422 and write_test.json()["error"]["code"] == "MCP_TEST_REQUIRES_WORKFLOW"
    member.role = "owner"
    db.commit()

    blocked = client.patch(f"{tool_path}/search", headers=headers(client), json={"policy": "block"})
    assert item(blocked.json(), server_id)["runnable_tools"] == ["create_issue"]
    assert client.post(f"{tool_path}/search/test", headers=headers(client), json={"arguments": {}}).status_code == 403
    assert [call[2] for call in calls] == ["search", "create_issue"]
    assert client.patch(f"{tool_path}/missing", headers=headers(client), json={"policy": "allow"}).status_code == 404
    assert client.patch(f"{tool_path}/search", headers=headers(client), json={"policy": "maybe"}).status_code == 422
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "mcp.tool_policy_changed").limit(1))
    assert event.details["tool_name"] == "create_issue" and event.details["read_only"] is False


def test_agent_calls_allowed_write_tool_and_block_stops_next_run(client, owner, db, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    client.patch(f"{base}/mcp/{server_id}/tools/create_issue", headers=headers(client), json={"policy": "allow"})
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    client.post(f"{base}/integrations/providers/openai", headers=headers(client), json={"api_key": "provider-key"})
    draft = client.post(f"{base}/agents", headers=headers(client), json={
        "name": "Issue agent",
        "config": {
            "instructions": "Open an issue for each bug report.",
            "model_id": "gpt-5-mini",
            "mcp_tools": [{"server_id": server_id, "tool_name": "create_issue", "connection_generation": 1, "input_schema": ISSUE}],
        },
    })
    assert draft.status_code == 201, draft.text
    path = f"{base}/agents/{draft.json()['id']}"
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 1})
    assert version.status_code == 201, version.text
    grant = version.json()["config"]["mcp_tools"][0]
    remote = []

    def model(key, payload, timeout):
        if not any(item.get("type") == "function_call_output" for item in payload["input"] if isinstance(item, dict)):
            return {"status": "completed", "usage": {"input_tokens": 40, "output_tokens": 8}, "output": [
                {"type": "function_call", "name": alias(grant), "call_id": "c1", "arguments": '{"title":"Login fails"}'},
            ]}
        return {"status": "completed", "usage": {"input_tokens": 40, "output_tokens": 8}, "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"priority":"normal"}'}]},
        ]}

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    monkeypatch.setattr(
        "app.modules.mcp.client.call_tool",
        lambda url, key, name, data, timeout_seconds: remote.append((url, key, name, data)) or {"content": [{"type": "text", "text": "Issue #7"}]},
    )
    run_id = queued(client, base, version.json(), key="write-tool-0001")
    execute(run_id, client.app.state.settings)
    assert client.get(f"{base}/runs/{run_id}").json()["state"] == "completed"
    assert remote == [(SECRET_URL, "tracker-token", "create_issue", {"title": "Login fails"})]

    # A run queued before the block must not reach the server; new runs are refused outright.
    second = queued(client, base, version.json(), key="write-tool-0002")
    client.patch(f"{base}/mcp/{server_id}/tools/create_issue", headers=headers(client), json={"policy": "block"})
    execute(second, client.app.state.settings)
    failed = client.get(f"{base}/runs/{second}").json()
    assert failed["state"] == "failed" and len(remote) == 1, failed
    refused = client.post(
        f"{base}/runs",
        headers={**headers(client), "Idempotency-Key": "write-tool-0003"},
        json={"version_id": version.json()["id"], "input": {"ticket": "policy"}},
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "MCP_GRANT_CHANGED"


def test_workflow_can_publish_allowed_write_tool(client, owner, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    workflow = client.post(f"{base}/workflows", headers=headers(client), json={"name": "File issue"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "file", "type": "mcp_tool", "label": "File issue",
        "position": {"x": 300, "y": 180}, "config": {"server_id": server_id, "tool_name": "create_issue"},
    })
    graph["edges"] = [
        {"id": "input-file", "source": "input", "target": "file"},
        {"id": "file-result", "source": "file", "target": "result"},
    ]
    path = f"{base}/workflows/{workflow['id']}"
    client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph})
    blocked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2}).json()
    assert not blocked["publishable"] and blocked["errors"][0]["code"] == "MCP_TOOL_UNAVAILABLE"
    client.patch(f"{base}/mcp/{server_id}/tools/create_issue", headers=headers(client), json={"policy": "allow"})
    allowed = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2}).json()
    assert allowed["publishable"], allowed


def test_locked_install_rejects_workspace_servers_and_catalog_writes(client, owner, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    servers = json.loads(CATALOG)
    client.app.state.settings.mcp_catalog_json = json.dumps({"servers": servers, "workspace_servers": False})
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: [
        {"name": "search", "description": "Find docs", "input_schema": {"type": "object"}},
        {"name": "delete_everything", "input_schema": {"type": "object"}},
    ])
    listing = client.get(f"{base}/mcp").json()
    assert listing["workspace_servers"] is False and server_id not in json.dumps(listing)
    refused = client.post(f"{base}/mcp/servers", headers=headers(client), json={"name": "x", "url": SECRET_URL})
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "MCP_WORKSPACE_SERVERS_DISABLED"
    assert client.patch(f"{base}/mcp/{server_id}/tools/search", headers=headers(client), json={"policy": "block"}).status_code == 404
    connected = client.put(f"{base}/mcp/docs", headers=headers(client), json={})
    assert connected.status_code == 200 and item(connected.json(), "docs")["runnable_tools"] == ["search"]
    locked = client.patch(f"{base}/mcp/docs/tools/delete_everything", headers=headers(client), json={"policy": "allow"})
    assert locked.status_code == 403 and locked.json()["error"]["code"] == "MCP_POLICY_LOCKED"
    tightened = client.patch(f"{base}/mcp/docs/tools/search", headers=headers(client), json={"policy": "block"})
    assert item(tightened.json(), "docs")["runnable_tools"] == []


def test_revoked_workspace_server_disappears_and_rotation_keeps_url(client, owner, db, monkeypatch):
    base, body = add(client, owner, monkeypatch)
    server_id = body["added"]
    calls = []
    monkeypatch.setattr(
        "app.modules.mcp.service.discover", lambda url, key: calls.append((url, key)) or [dict(TOOLS[0])]
    )
    rotated = client.put(f"{base}/mcp/{server_id}", headers=headers(client), json={"bearer_token": "new-token"})
    assert rotated.status_code == 200 and calls == [(SECRET_URL, "new-token")]
    row = db.scalar(select(McpConnection).where(McpConnection.server_id == server_id))
    assert row.generation == 2 and row.verified_tools == ["search"]
    assert client.delete(f"{base}/mcp/{server_id}", headers=headers(client)).status_code == 200
    db.refresh(row)
    assert row.state == "revoked" and row.ciphertext is None
    assert server_id not in client.get(f"{base}/mcp").text


def test_client_reads_real_sdk_types(monkeypatch):
    """Regression: SDK 2.x exposes snake_case attributes; results must keep wire-format keys."""

    class FakeClient:
        async def list_tools(self):
            return types.ListToolsResult(tools=[
                types.Tool(name="search", input_schema={"type": "object"},
                           annotations=types.ToolAnnotations(read_only_hint=True, destructive_hint=False)),
                types.Tool(name="post", description="Send", input_schema={"type": "object"}),
            ])

        async def call_tool(self, name, arguments):
            return types.CallToolResult(content=[types.TextContent(type="text", text="no")], is_error=True)

    monkeypatch.setattr(mcp_client, "_call", lambda url, key, action, timeout_seconds=12.0: asyncio.run(action(FakeClient())))
    assert mcp_client.discover("https://mcp.example.com/mcp", "") == [
        {"name": "search", "description": "", "input_schema": {"type": "object"}, "read_only_hint": True, "destructive_hint": False},
        {"name": "post", "description": "Send", "input_schema": {"type": "object"}},
    ]
    result = mcp_client.call_tool("https://mcp.example.com/mcp", "", "post", {})
    assert result["isError"] is True and result["content"][0]["text"] == "no"
