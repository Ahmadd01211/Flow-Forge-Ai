import pytest

from app.modules.templates.catalog import templates
from app.modules.workflows.node_config import config_issues
from app.modules.workflows.schemas import Graph, Node, Position


def _node(kind: str, config: dict) -> Node:
    return Node(id="step", type=kind, label="Step", position=Position(x=0, y=0), config=config)


def _paths(kind: str, config: dict, upstream: set[str] | None = None) -> dict[str, str]:
    errors, _ = config_issues(_node(kind, config), upstream)
    return {error["path"]: error["message"] for error in errors}


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("manual_input", {}),
        ("webhook_trigger", {}),
        ("agent", {"version_id": "8f0c7b7e-3b7b-4a59-9a43-2d43b1d7a001"}),
        ("tool", {"tool_key": "text.replace"}),
        ("mcp_tool", {"server_id": "docs", "tool_name": "search", "connection_generation": 2, "input_schema_hash": "abc"}),
        ("condition", {"operator": "eq", "left": {"kind": "input", "pointer": "/urgent"}, "right": {"kind": "literal", "value": True}}),
        ("condition", {"operator": "exists", "left": {"kind": "input", "pointer": "/a"}, "right": {"kind": "literal", "value": None}}),
        ("transform", {"fields": {"queue": {"kind": "literal", "value": "on-call"}}, "output_schema": {"type": "object"}}),
        ("text_template", {"template": "Ticket {{/ticket/id}} is ready."}),
        ("list_filter", {"source": "/items", "item_pointer": "/status", "operator": "eq", "value": "open"}),
        ("list_filter", {"source": "/items", "operator": "exists"}),
        ("json_parse", {"source": "/text"}),
        ("result", {}),
        ("result", {"value": {"kind": "output", "node_id": "input", "pointer": ""}}),
    ],
)
def test_runtime_shapes_are_accepted(kind, config):
    assert _paths(kind, config, {"input"}) == {}


def test_missing_fields_are_reported_at_their_own_path():
    assert _paths("agent", {"version_id": ""}) == {"config.version_id": "Choose a published agent version."}
    assert set(_paths("condition", {})) == {"config.left", "config.operator", "config.right"}
    assert set(_paths("list_filter", {"source": "/items", "operator": "eq"})) == {"config.value"}
    assert set(_paths("mcp_tool", {"server_id": "docs"})) == {"config.tool_name"}


def test_reference_errors_point_inside_the_selected_kind():
    paths = _paths("condition", {
        "operator": "eq",
        "left": {"kind": "input", "pointer": "/__proto__/x"},
        "right": {"kind": "literal"},
    })
    assert set(paths) == {"config.left.pointer", "config.right.value"}


def test_transform_field_rules():
    assert set(_paths("transform", {"fields": {}})) == {"config.fields"}
    assert set(_paths("transform", {"fields": {"a": {"kind": "input", "pointer": "nope"}}})) == {"config.fields.a.pointer"}
    unsafe = _paths("transform", {"fields": {"a": {"kind": "literal", "value": 1}}, "output_schema": {"type": "string"}})
    assert set(unsafe) == {"config.output_schema"}


def test_semantic_checks():
    assert "config.template" in _paths("text_template", {"template": "Hi {{name}}"})
    assert set(_paths("condition", {
        "operator": "gt", "left": {"kind": "input", "pointer": "/n"}, "right": {"kind": "literal", "value": True},
    })) == {"config.right"}
    assert set(_paths("result", {"value": {"kind": "output", "node_id": "later"}}, {"input"})) == {"config.value.node_id"}


def test_unused_keys_warn_without_blocking():
    errors, warnings = config_issues(_node("webhook_trigger", {"secret": "do-not-store"}))
    assert errors == []
    assert [(w["code"], w["path"]) for w in warnings] == [("NODE_CONFIG_UNUSED", "config.secret")]


def test_transform_keeps_its_error_code():
    errors, _ = config_issues(_node("transform", {}))
    assert errors and errors[0]["code"] == "TRANSFORM_INVALID"


def test_catalog_templates_have_valid_node_configuration():
    for template in templates().values():
        graph = template.get("graph")
        if not graph:
            continue
        for node in Graph.model_validate(graph).nodes:
            upstream = {other["id"] for other in graph["nodes"] if other["id"] != node.id}
            errors, _ = config_issues(node, upstream)
            if (node.type in {"agent", "http_tool"} and not node.config) or (node.type in {"subworkflow", "for_each"} and not node.config.get("version_id")):
                # Portable starters deliberately require workspace bindings.
                # They must explain setup and fail publication until configured.
                assert template.get("setup_steps")
                assert errors and all(error["code"] == "NODE_CONFIG_INVALID" for error in errors)
                continue
            assert errors == [], (template.get("key"), node.id, errors)


def test_result_fields_shape_and_conditional_sources():
    fields = {
        "a": {"kind": "output", "node_id": "left", "pointer": "/x"},
        "b": {"kind": "input", "pointer": "/y"},
        "c": {"kind": "literal", "value": 1},
    }
    errors, warnings = config_issues(_node("result", {"fields": fields}), {"input", "left"}, {"input"})
    assert errors == []
    assert [(w["code"], w["path"]) for w in warnings] == [("NODE_SOURCE_CONDITIONAL", "config.fields.a.node_id")]
    assert set(_paths("result", {"fields": fields}, {"input"})) == {"config.fields.a.node_id"}
    assert set(_paths("result", {"fields": {"a": {"kind": "output"}}})) == {"config.fields.a.node_id"}
    assert set(_paths("result", {"fields": {}, "value": {"kind": "output", "node_id": "input"}})) == {"config", "config.fields"}


def test_run_step_resolves_result_fields():
    from app.modules.workflows.preview import run_step

    node = _node("result", {"fields": {
        "from_step": {"kind": "output", "node_id": "left", "pointer": "/x"},
        "incoming": {"kind": "input", "pointer": "/y"},
    }})
    step = run_step(node, {"y": 2}, {"left": {"x": 1}})
    assert step["output"] == {"from_step": 1, "incoming": 2}
