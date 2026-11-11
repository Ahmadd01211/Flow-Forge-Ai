"""Reviewed local starters remain discoverable and executable after copying."""

import pytest
from jsonschema import Draft202012Validator

from app.modules.templates.catalog import public_catalog, templates
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.schemas import Graph
from tests.conftest import headers
from tests.test_workflow_data_nodes import _run


@pytest.mark.parametrize("key", ["switch-routing", "remove-duplicates"])
def test_practical_starters_have_valid_graphs_and_public_run_guidance(key):
    item = templates()[key]
    listed = next(row for row in public_catalog()["items"] if row["key"] == key)
    assert item["kind"] == "workflow" and item["template_version"] == 1
    assert item["setup_steps"] and item["sample_input"] and item["expected_result"]
    for field in ("setup_steps", "sample_input", "expected_result"):
        assert listed[field] == item[field]
    graph = Graph.model_validate(item["graph"])
    assert graph.schema_version == 1
    assert validate_graph(graph)["valid"]
    Draft202012Validator.check_schema(graph.input_schema)
    Draft202012Validator.check_schema(graph.output_schema)
    Draft202012Validator(graph.input_schema).validate(item["sample_input"])


@pytest.mark.parametrize(("key", "value", "expected", "port"), [
    ("switch-routing", None, {"queue": "billing-team"}, "billing"),
    ("switch-routing", {"category": "technical"}, {"queue": "technical-support"}, "technical"),
    ("switch-routing", {"category": "other"}, {"queue": "general-support"}, "default"),
    ("remove-duplicates", None, {
        "items": [
            {"name": "Ada", "email": "ada@example.com"},
            {"name": "Lin", "email": "lin@example.com"},
        ],
        "count": 2, "removed": 1,
    }, None),
    ("decision-routing", {"priority": "urgent"}, {"queue": "on-call"}, "true"),
    ("decision-routing", {"priority": "normal"}, {"queue": "standard"}, "false"),
])
def test_copied_starters_preview_publish_and_run(client, owner, key, value, expected, port):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    detail = client.get(f"/api/v1/templates/{key}")
    assert detail.status_code == 200, detail.text
    catalog = client.get("/api/v1/templates").json()["items"]
    assert sum(item["key"] == key for item in catalog) == 1
    value = detail.json()["sample_input"] if value is None else value
    copied = client.post(f"{base}/templates/{key}/instantiate", headers=headers(client))
    assert copied.status_code == 201, copied.text
    assert copied.json()["skill_ids"] == []
    path = f"{base}/workflows/{copied.json()['id']}"
    saved = client.get(path).json()
    assert saved["graph"]["schema_version"] == 1
    checked = client.post(
        path + "/validate", headers=headers(client), json={"expected_revision": 1},
    )
    assert checked.status_code == 200 and checked.json()["publishable"], checked.text
    preview = client.post(
        path + "/preview", headers=headers(client),
        json={"expected_revision": 1, "input": value},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["output"] == expected
    published = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 1},
    )
    assert published.status_code == 201, published.text
    result = _run(client, workspace, published.json()["id"], value, f"starter-{key}-{port}")
    assert result["state"] == "completed", result
    assert result["output"] == expected
    Draft202012Validator(saved["graph"]["output_schema"]).validate(result["output"])
    if port is not None:
        for steps in (preview.json()["steps"], result["steps"]):
            selected = [step for step in steps if step.get("selected_port") == port]
            assert len(selected) == 1
        assert sum(step["status"] == "skipped" for step in result["steps"]) == (
            2 if key == "switch-routing" else 1
        )
    else:
        cleanup = next(step for step in result["steps"] if step["node_id"] == "cleanup")
        assert cleanup["output"] == expected
