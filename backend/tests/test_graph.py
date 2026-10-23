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
