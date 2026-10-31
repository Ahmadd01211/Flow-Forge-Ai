import uuid
from copy import deepcopy

import pytest

from app.modules.templates.action_starters import action_starters
from app.modules.templates.models import UserTemplate
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.preview import run_preview
from app.modules.workflows.schemas import Graph
from tests.conftest import headers


def test_template_export_import_is_private_and_clears_bindings(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    exported = client.get("/api/v1/templates/webhook-api-action/export")
    assert exported.status_code == 200, exported.text
    package = exported.json()
    assert package["format"] == "flowforge-template" and package["format_version"] == 1
    package["definition"]["graph"]["nodes"][2]["config"] = {"tool_id": str(uuid.uuid4()), "Authorization": "not-a-real-key"}
    imported = client.post(f"{base}/templates/import", headers=headers(client), json=package)
    assert imported.status_code == 201, imported.text
    assert imported.json()["visibility"] == "private"
    row = db.get(UserTemplate, uuid.UUID(imported.json()["key"]))
    assert row.definition["graph"]["nodes"][2]["config"] == {}
    copied = client.post(f"{base}/templates/{row.id}/instantiate", headers=headers(client))
    assert copied.status_code == 201, copied.text
    invalid = deepcopy(package)
    invalid["definition"]["graph"]["edges"].append({"id": "cycle", "source": "send", "target": "payload"})
    assert client.post(f"{base}/templates/import", headers=headers(client), json=invalid).status_code == 422
    assert client.post(f"{base}/templates/import", headers=headers(client), json={**package, "format_version": 2}).status_code == 422
    assert client.post(f"{base}/templates/import", headers=headers(client), json={**package, "definition": {"graph": {}, "credential": "unexpected"}}).status_code == 422


@pytest.mark.parametrize("key", list(action_starters()))
def test_action_starter_graphs_run_both_routes_with_explicit_bindings(client, owner, db, monkeypatch, key):
    from tests.test_agent_mcp import agent_with_mcp
    from tests.test_http_tools import create_tool

    item = action_starters()[key]
    graph = Graph.model_validate(item["graph"])
    assert validate_graph(graph)["valid"]
    _, tool = create_tool(client, owner, monkeypatch)
    for node in graph.nodes:
        if node.type == "http_tool":
            node.config = {"tool_id": tool["id"]}
    if key == "agent-priority-action":
        _, path = agent_with_mcp(client, owner, monkeypatch)
        version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 1}).json()
        for node in graph.nodes:
            if node.type == "agent":
                node.config = {"version_id": version["id"]}
    def service_call(node, data):
        if key == "scheduled-api-digest":
            return {"status_code": 200, "body": {"items": [{"status": "open", "id": 1}, {"status": "closed", "id": 2}]}}
        return {"status_code": 201, "body": {"receipt": "example-receipt"}}
    workspace = uuid.UUID(owner["workspaces"][0]["id"])
    for priority in ["urgent", "normal"]:
        result = run_preview(db, workspace, graph, item["sample_input"], agent_handler=lambda *_, current=priority: ({"priority": current, "reason": "Sample"}, {}), http_handler=service_call, mcp_catalog_json=client.app.state.settings.mcp_catalog_json)
        if key == "scheduled-api-digest":
            assert result["output"] == {"items": [{"status": "open", "id": 1}], "count": 1}
        elif key == "agent-priority-action" and priority == "normal":
            assert result["output"]["queue"] == "standard"
            assert next(step for step in result["steps"] if step["node_id"] == "escalate")["status"] == "skipped"
        else:
            assert result["output"]["body"]["receipt"] == "example-receipt"
