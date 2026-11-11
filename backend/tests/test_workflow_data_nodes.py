import pytest
from fastapi import HTTPException

from app.modules.workflows.preview import run_step
from app.modules.workflows.runtime import execute
from app.modules.workflows.schemas import Node, Position
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
        assert len(result["steps"]) == 5
        assert sum(step["status"] == "skipped" for step in result["steps"]) == 1


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


def _step(kind, config, data):
    node = Node(id="step", type=kind, label="Step", position=Position(x=0, y=0), config=config)
    return run_step(node, data, {})


@pytest.mark.parametrize(("value", "port"), [(True, "yes"), (1, "one"), (None, "empty"), ("other", "default"), ({}, "default")])
def test_switch_selects_strict_case_id_or_default(value, port):
    config = {"value": {"kind": "input", "pointer": "/value"}, "cases": [
        {"id": "yes", "label": "Yes", "value": True},
        {"id": "one", "label": "One", "value": 1},
        {"id": "empty", "label": "Empty", "value": None},
    ]}
    step = _step("switch", config, {"value": value})
    assert step["selected_port"] == port
    assert step["output"] == {"value": value}


def test_switch_resolves_literal_and_fails_missing_input():
    config = {"value": {"kind": "literal", "value": None}, "cases": [{"id": "empty", "label": "Empty", "value": None}]}
    assert _step("switch", config, {})["selected_port"] == "empty"
    config["value"] = {"kind": "input", "pointer": "/missing"}
    with pytest.raises(HTTPException) as raised:
        _step("switch", config, {})
    assert raised.value.detail["code"] == "POINTER_MISSING"


@pytest.mark.parametrize(("case", "value"), [(1, 1.0), (1.0, 1), (0, -0.0), (-0.0, 0)])
def test_switch_matches_equivalent_json_numbers(case, value):
    config = {"value": {"kind": "input", "pointer": "/value"}, "cases": [{"id": "number", "label": "Number", "value": case}]}
    assert _step("switch", config, {"value": value})["selected_port"] == "number"


@pytest.mark.parametrize(("items", "expected"), [
    ([1, 1.0, 0, -0.0, True, False], {"items": [1, 0, True, False], "count": 4, "removed": 2}),
    ([{"key": [1, {"zero": 0}]}, {"key": [1.0, {"zero": -0.0}]}, {"key": [True, {"zero": False}]}],
     {"items": [{"key": [1, {"zero": 0}]}, {"key": [True, {"zero": False}]}], "count": 2, "removed": 1}),
])
def test_deduplicate_compares_json_number_values_recursively(items, expected):
    assert _step("list_deduplicate", {"source": ""}, items)["output"] == expected


def test_deduplicate_object_field_compares_json_number_values_recursively():
    items = [{"key": [1, -0.0], "label": "first"}, {"key": [1.0, 0], "label": "later"}, {"key": [True, False]}]
    assert _step("list_deduplicate", {"source": "", "item_pointer": "/key"}, items)["output"] == {
        "items": [{"key": [1, -0.0], "label": "first"}, {"key": [True, False]}], "count": 2, "removed": 1,
    }


@pytest.mark.parametrize(("items", "expected"), [
    ([], {"items": [], "count": 0, "removed": 0}),
    (["b", "a", "b", "c", "a"], {"items": ["b", "a", "c"], "count": 3, "removed": 2}),
    ([True, 1, False, 0, None, "1", True, None, 0], {"items": [True, 1, False, 0, None, "1"], "count": 6, "removed": 3}),
    ([{"a": 1, "b": [2]}, {"b": [2], "a": 1}, [1, 2], [2, 1], [1, 2]], {"items": [{"a": 1, "b": [2]}, [1, 2], [2, 1]], "count": 3, "removed": 2}),
])
def test_deduplicate_whole_values_preserves_order_and_strict_json_types(items, expected):
    assert _step("list_deduplicate", {"source": "/items"}, {"items": items})["output"] == expected


def test_deduplicate_nested_key_retains_missing_items_and_collapses_explicit_null():
    items = [
        {"user": {"id": "a"}, "name": "first"}, {"user": {"id": "a"}, "name": "second"},
        {"user": {}}, {"user": {}}, {},
        {"user": {"id": None}, "name": "null first"}, {"user": {"id": None}},
        {"user": {"id": True}}, {"user": {"id": 1}},
    ]
    step = _step("list_deduplicate", {"source": "/items", "item_pointer": "/user/id"}, {"items": items})
    assert step["output"] == {"items": [items[0], items[2], items[3], items[4], items[5], items[7], items[8]], "count": 7, "removed": 2}


@pytest.mark.parametrize(("config", "data", "code"), [
    ({"source": "/items"}, {"items": {}}, "LIST_DEDUPLICATE_INPUT_INVALID"),
    ({"source": "/items"}, {}, "POINTER_MISSING"),
    ({"source": "", "item_pointer": "/id"}, [{"id": 1}, None], "LIST_DEDUPLICATE_INPUT_INVALID"),
    ({"source": "", "item_pointer": ""}, [1], "LIST_DEDUPLICATE_INPUT_INVALID"),
    ({"source": "/items"}, {"items": ["x" * 65536]}, "JSON_TOO_LARGE"),
    ({"source": "/items"}, {"items": [0] * 12000}, "JSON_TOO_COMPLEX"),
    ({"source": "/items"}, {"items": [float("nan")]}, "JSON_INVALID"),
    ({"source": "/items"}, {"items": [1], "oversized": "x" * 65536}, "JSON_TOO_LARGE"),
])
def test_deduplicate_rejects_invalid_or_unbounded_input(config, data, code):
    with pytest.raises(HTTPException) as raised:
        _step("list_deduplicate", config, data)
    assert raised.value.detail["code"] == code


def test_deduplicate_checks_output_size_as_well_as_input():
    # Root input fits 64 KiB; the output envelope pushes it over that same bound.
    with pytest.raises(HTTPException) as raised:
        _step("list_deduplicate", {"source": ""}, ["x" * 65520])
    assert raised.value.detail["code"] == "JSON_TOO_LARGE"


@pytest.mark.parametrize(("value", "port", "output"), [
    (True, "yes", {"items": ["b", "a"], "count": 2, "removed": 1}),
    (None, "empty", {"route": "empty"}),
    (1, "default", {"route": "default"}),
])
def test_switch_and_deduplicate_agree_in_preview_and_durable_trace(client, owner, value, port, output):
    workspace = owner["workspaces"][0]["id"]
    nodes = [
        {"id": "input", "type": "manual_input", "label": "Input", "position": {"x": 0, "y": 0}},
        {"id": "choose", "type": "switch", "label": "Choose", "position": {"x": 200, "y": 0}, "config": {
            "value": {"kind": "input", "pointer": "/value"}, "cases": [
                {"id": "yes", "label": "Boolean", "value": True}, {"id": "empty", "label": "Empty", "value": None},
            ],
        }},
        {"id": "unique", "type": "list_deduplicate", "label": "Unique", "position": {"x": 400, "y": 0}, "config": {"source": "/items"}},
        {"id": "empty", "type": "transform", "label": "Empty", "position": {"x": 400, "y": 100}, "config": {"fields": {"route": {"kind": "literal", "value": "empty"}}}},
        {"id": "default", "type": "transform", "label": "Default", "position": {"x": 400, "y": 200}, "config": {"fields": {"route": {"kind": "literal", "value": "default"}}}},
        {"id": "result", "type": "result", "label": "Result", "position": {"x": 600, "y": 0}},
    ]
    edges = [
        {"id": "input-choose", "source": "input", "target": "choose"},
        {"id": "choose-yes", "source": "choose", "source_port": "yes", "target": "unique"},
        {"id": "choose-empty", "source": "choose", "source_port": "empty", "target": "empty"},
        {"id": "choose-default", "source": "choose", "source_port": "default", "target": "default"},
        *[{"id": f"{source}-result", "source": source, "target": "result"} for source in ("unique", "empty", "default")],
    ]
    path = _save(client, workspace, "Practical nodes", {"nodes": nodes, "edges": edges})
    data = {"value": value, "items": ["b", "a", "b"]}
    preview = client.post(f"{path}/preview", headers=headers(client), json={"expected_revision": 2, "input": data})
    assert preview.status_code == 200, preview.text
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    durable = _run(client, workspace, version.json()["id"], data, f"practical-node-{port}")
    assert durable["state"] == "completed", durable
    for result in (preview.json(), durable):
        assert result["output"] == output
        steps = {step["node_id"]: step for step in result["steps"]}
        assert steps["choose"]["selected_port"] == port
        assert sum(step["status"] == "skipped" for step in result["steps"]) == 2
        if port == "yes":
            assert steps["unique"]["output"] == output
