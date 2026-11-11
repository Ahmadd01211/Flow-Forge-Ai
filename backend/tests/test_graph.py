import pytest
from pydantic import ValidationError

from app.modules.workflows.domain import validate_graph
from app.modules.workflows.schemas import Edge, Graph, Node, Position, initial_graph


def test_linear_draft_valid_but_not_publishable():
    result = validate_graph(Graph.model_validate(initial_graph()))
    assert result["valid"] and not result["publishable"]


def test_cycle_and_disconnected_nodes_diagnosed():
    graph = Graph.model_validate(initial_graph())
    graph.edges.append(Edge(id="cycle", source="result", target="input"))
    graph.nodes.append(
        Node(id="orphan", type="transform", label="Orphan", position=Position(x=1, y=1))
    )
    codes = {e["code"] for e in validate_graph(graph)["errors"]}
    assert {"CYCLE_DETECTED", "NODE_DISCONNECTED", "ENTRY_HAS_INPUT", "RESULT_HAS_OUTPUT"} <= codes


def test_layout_does_not_change_execution_hash():
    graph = Graph.model_validate(initial_graph())
    original = validate_graph(graph)["execution_hash"]
    graph.nodes[0].position.x = 555
    graph.nodes[0].label = "A renamed label"
    assert validate_graph(graph)["execution_hash"] == original
    graph.limits["timeout_seconds"] = 20
    assert validate_graph(graph)["execution_hash"] != original


def test_disconnected_agent_cannot_be_published():
    graph = Graph.model_validate(initial_graph())
    graph.nodes.append(
        Node(id="agent", type="agent", label="Triage", position=Position(x=10, y=10))
    )
    result = validate_graph(graph)
    assert not result["valid"]
    assert any(e["code"] == "NODE_DISCONNECTED" and e["node_id"] == "agent" for e in result["errors"])


def test_unsafe_mapping_and_missing_endpoint_are_errors():
    graph = Graph.model_validate(initial_graph())
    graph.edges[0].mappings = [{"from": "/ticket", "to": "/__proto__/polluted"}]
    graph.edges.append(Edge(id="missing", source="missing", target="result"))
    codes = {e["code"] for e in validate_graph(graph)["errors"]}
    assert {"POINTER_INVALID", "EDGE_ENDPOINT_MISSING"} <= codes


def test_condition_requires_both_branch_ports():
    graph = Graph.model_validate(initial_graph())
    graph.nodes[0].type = "condition"
    assert any(e["code"] == "BRANCH_REQUIRED" for e in validate_graph(graph)["errors"])


def branch_graph(kind="switch", cases=None):
    graph = initial_graph()
    graph["nodes"].insert(1, {
        "id": "route", "type": kind, "label": "Route", "position": {"x": 0, "y": 0},
        "config": {"value": {"kind": "input", "pointer": "/priority"}, "cases": cases if cases is not None else [
            {"id": "urgent", "label": "Urgent", "value": "high"},
        ]},
    })
    ports = ["true", "false"] if kind == "condition" else [case["id"] for case in graph["nodes"][1]["config"]["cases"]] + ["default"]
    graph["edges"] = [{"id": "start", "source": "input", "target": "route"}] + [
        {"id": f"branch-{index}", "source": "route", "source_port": port, "target": "result"}
        for index, port in enumerate(ports)
    ]
    return graph


def test_legacy_condition_ports_round_trip_and_validate():
    graph = Graph.model_validate(branch_graph("condition"))
    assert [e.source_port for e in graph.edges] == ["out", "true", "false"]
    assert Graph.model_validate(graph.model_dump()).schema_version == 1
    assert validate_graph(graph)["valid"]


def test_switch_stable_ports_and_default_round_trip_and_validate():
    graph = Graph.model_validate(branch_graph())
    assert [e.source_port for e in graph.edges] == ["out", "urgent", "default"]
    assert Graph.model_validate(graph.model_dump()).schema_version == 1
    assert validate_graph(graph)["valid"]
    graph.nodes[1].config["cases"][0]["label"] = "High priority"
    assert validate_graph(graph)["valid"]


@pytest.mark.parametrize("port", ["", "a" * 41, 1])
def test_source_ports_are_bounded_nonempty_strings(port):
    graph = initial_graph()
    graph["edges"][0]["source_port"] = port
    with pytest.raises(ValidationError):
        Graph.model_validate(graph)


@pytest.mark.parametrize("port", ["stale", "out", "true", "false"])
def test_switch_rejects_unknown_and_legacy_ports(port):
    graph = Graph.model_validate(branch_graph())
    graph.edges[1].source_port = port
    issues = validate_graph(graph)["errors"]
    assert any(issue["code"] == "PORT_INVALID" and issue["edge_id"] == "branch-0" for issue in issues)
    assert any(issue["code"] == "BRANCH_REQUIRED" and issue["node_id"] == "route" for issue in issues)


@pytest.mark.parametrize("port", ["urgent", "default"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_switch_requires_exactly_one_edge_for_each_current_port(port, duplicate):
    graph = Graph.model_validate(branch_graph())
    existing = next(edge for edge in graph.edges if edge.source_port == port)
    if duplicate:
        graph.edges.append(existing.model_copy(update={"id": "extra"}))
    else:
        graph.edges.remove(existing)
    assert any(issue["code"] == "BRANCH_REQUIRED" for issue in validate_graph(graph)["errors"])


@pytest.mark.parametrize("case_id", ["", "Upper", "1first", "a" * 33, "a.b", "a\n", "default", "out", "true", "false"])
def test_switch_rejects_malformed_and_reserved_case_ids(case_id):
    graph = branch_graph()
    graph["nodes"][1]["config"]["cases"][0]["id"] = case_id
    checked = validate_graph(Graph.model_validate(graph))
    assert any(issue["code"] == "SWITCH_CONFIG_INVALID" and issue["node_id"] == "route" for issue in checked["errors"])


@pytest.mark.parametrize("cases", [
    [],
    [{"id": f"case{i}", "label": "Case", "value": i} for i in range(9)],
    [{"id": "same", "label": "One", "value": 1}, {"id": "same", "label": "Two", "value": 2}],
    [{"id": "first", "label": "One", "value": "same"}, {"id": "second", "label": "Two", "value": "same"}],
    [{"id": "case", "label": "", "value": 1}],
    [{"id": "case", "label": "x" * 41, "value": 1}],
    [{"id": "case", "label": "Case", "value": []}],
    [{"id": "case", "label": "Case", "value": {}}],
    [{"id": "case", "label": "Case", "value": float("inf")}],
    [{"id": "case", "label": "Case", "value": "x" * 65536}],
])
def test_switch_rejects_invalid_case_configuration(cases):
    graph = branch_graph()
    graph["nodes"][1]["config"]["cases"] = cases
    assert any(issue["code"] == "SWITCH_CONFIG_INVALID" for issue in validate_graph(Graph.model_validate(graph))["errors"])


@pytest.mark.parametrize("reference", [
    None,
    {},
    {"kind": "input", "pointer": "unsafe"},
    {"kind": "input", "pointer": "/" + "x" * 512},
    {"kind": "input", "pointer": "/constructor/value"},
    {"kind": "input", "pointer": 1},
    {"kind": "input", "pointer": "", "value": 1},
    {"kind": "literal"},
    {"kind": "literal", "value": 1, "pointer": ""},
])
def test_switch_requires_a_valid_value_reference(reference):
    graph = branch_graph()
    graph["nodes"][1]["config"]["value"] = reference
    assert any(issue["code"] == "SWITCH_CONFIG_INVALID" for issue in validate_graph(Graph.model_validate(graph))["errors"])


def test_switch_keeps_json_scalar_types_distinct_and_allows_eight_cases():
    values = [True, 1, 1.0, "1", None, False, 0, ""]
    cases = [{"id": f"case{i}", "label": "Case", "value": value} for i, value in enumerate(values)]
    assert validate_graph(Graph.model_validate(branch_graph(cases=cases)))["valid"]


@pytest.mark.parametrize("reference", [
    {"kind": "input", "pointer": ""},
    {"kind": "input", "pointer": "/ticket~1priority/~0key"},
    {"kind": "literal", "value": None},
    {"kind": "literal", "value": False},
    {"kind": "literal", "value": 1},
    {"kind": "literal", "value": "high"},
])
def test_switch_accepts_value_references(reference):
    graph = branch_graph()
    graph["nodes"][1]["config"]["value"] = reference
    assert validate_graph(Graph.model_validate(graph))["valid"]


def test_switch_case_reordering_keeps_routes_and_deleted_cases_block_stale_edges():
    cases = [
        {"id": "urgent", "label": "Urgent", "value": "high"},
        {"id": "routine", "label": "Routine", "value": "low"},
    ]
    graph = Graph.model_validate(branch_graph(cases=cases))
    ports = [edge.source_port for edge in graph.edges]
    graph.nodes[1].config["cases"].reverse()
    assert validate_graph(graph)["valid"]
    assert [edge.source_port for edge in graph.edges] == ports
    graph.nodes[1].config["cases"].pop()
    issues = validate_graph(graph)["errors"]
    assert any(issue["code"] == "PORT_INVALID" and issue["edge_id"] == "branch-0" for issue in issues)


def test_nonbranch_ports_validate_by_node_type_and_keep_fanout():
    graph = Graph.model_validate(initial_graph())
    graph.nodes.insert(1, Node(id="extra", type="transform", label="Extra", position=Position(x=0, y=0)))
    graph.edges.extend([Edge(id="fanout", source="input", target="extra"), Edge(id="extra-result", source="extra", target="result")])
    assert validate_graph(graph)["valid"]
    graph.edges[0].source_port = "urgent"
    assert any(issue["code"] == "PORT_INVALID" for issue in validate_graph(graph)["errors"])
