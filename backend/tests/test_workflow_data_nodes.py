from app.modules.workflows.runtime import execute
from tests.conftest import headers


def _save(client, workspace, name, graph):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    created = client.post(base, headers=headers(client), json={"name": name}).json()
    path = f"{base}/{created['id']}"
    response = client.patch(path, headers=headers(client), json={
        "name": name, "expected_revision": 1, "graph": graph,
    })
    assert response.status_code == 200, response.text
    return path


def _run(client, workspace, version_id, input_data, key):
    base = f"/api/v1/workspaces/{workspace}/workflow-runs"
    submitted = client.post(base, headers={**headers(client), "Idempotency-Key": key}, json={
        "version_id": version_id, "input": input_data,
    })
    assert submitted.status_code == 202, submitted.text
    execute(submitted.json()["id"], client.app.state.settings)
    return client.get(f"{base}/{submitted.json()['id']}").json()


def test_condition_routes_both_paths_in_published_runs(client, owner):
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "input", "type": "manual_input", "label": "Input", "position": {"x": 0, "y": 0}},
            {"id": "priority", "type": "condition", "label": "Urgent?", "position": {"x": 200, "y": 0},
             "config": {"operator": "eq", "left": {"kind": "input", "pointer": "/urgent"}, "right": {"kind": "literal", "value": True}}},
            {"id": "urgent", "type": "transform", "label": "Escalate", "position": {"x": 400, "y": -100},
             "config": {"fields": {"queue": {"kind": "literal", "value": "on-call"}}}},
            {"id": "normal", "type": "transform", "label": "Queue", "position": {"x": 400, "y": 100},
             "config": {"fields": {"queue": {"kind": "literal", "value": "standard"}}}},
            {"id": "result", "type": "result", "label": "Result", "position": {"x": 600, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "a", "source": "input", "target": "priority"},
            {"id": "b", "source": "priority", "source_port": "true", "target": "urgent"},
            {"id": "c", "source": "priority", "source_port": "false", "target": "normal"},
            {"id": "d", "source": "urgent", "target": "result"},
            {"id": "e", "source": "normal", "target": "result"},
        ],
    }
    path = _save(client, workspace, "Ticket routing", graph)
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.status_code == 200 and checked.json()["publishable"], checked.text
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    for urgent, expected, port in [(True, "on-call", "true"), (False, "standard", "false")]:
        result = _run(client, workspace, version.json()["id"], {"urgent": urgent}, f"branch-run-{port}")
        assert result["state"] == "completed" and result["output"] == {"queue": expected}
        assert result["steps"][1]["selected_port"] == port
        assert len(result["steps"]) == 4


def test_parse_filter_and_template_pipeline(client, owner):
    workspace = owner["workspaces"][0]["id"]
    nodes = [
        {"id": "input", "type": "manual_input", "label": "Input", "position": {"x": 0, "y": 0}},
        {"id": "parse", "type": "json_parse", "label": "Parse", "position": {"x": 100, "y": 0}, "config": {"source": "/text"}},
        {"id": "filter", "type": "list_filter", "label": "Open items", "position": {"x": 200, "y": 0},
         "config": {"source": "/value", "item_pointer": "/status", "operator": "eq", "value": "open"}},
        {"id": "message", "type": "text_template", "label": "Message", "position": {"x": 300, "y": 0},
         "config": {"template": "Open tickets: {{/count}}"}},
        {"id": "result", "type": "result", "label": "Result", "position": {"x": 400, "y": 0}, "config": {}},
    ]
    edges = [{"id": f"edge-{i}", "source": nodes[i]["id"], "target": nodes[i + 1]["id"]} for i in range(4)]
    path = _save(client, workspace, "Open ticket count", {"nodes": nodes, "edges": edges})
    input_data = {"text": '[{"status":"open"},{"status":"closed"},{"status":"open"}]'}
    preview = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": input_data})
    assert preview.status_code == 200 and preview.json()["output"] == {"text": "Open tickets: 2"}, preview.text
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    run = _run(client, workspace, version.json()["id"], input_data, "data-pipeline-001")
    assert run["state"] == "completed" and run["output"] == {"text": "Open tickets: 2"}
    bad = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": {"text": "not-json"}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "JSON_PARSE_INVALID"
