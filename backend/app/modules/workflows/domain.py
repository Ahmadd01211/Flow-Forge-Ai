import hashlib
import json
from collections import deque

from app.modules.workflows.schemas import Graph


def validate_graph(graph: Graph) -> dict:
    errors: list[dict] = []

    def error(
        code: str,
        message: str,
        node: str | None = None,
        edge: str | None = None,
        path: str | None = None,
    ) -> None:
        errors.append(
            {"code": code, "message": message, "node_id": node, "edge_id": edge, "path": path}
        )

    nodes = {n.id: n for n in graph.nodes}
    if len(nodes) != len(graph.nodes):
        error("DUPLICATE_NODE", "Every node needs a unique ID.")
    if len({e.id for e in graph.edges}) != len(graph.edges):
        error("DUPLICATE_EDGE", "Every connection needs a unique ID.")
    entry_types = {"manual_input", "webhook_trigger", "schedule_trigger"}
    entries = [n for n in graph.nodes if n.type in entry_types]
    results = [n for n in graph.nodes if n.type == "result"]
    if len(entries) != 1:
        error("ENTRY_REQUIRED", "Use exactly one manual input node.")
    if len(results) != 1:
        error("RESULT_REQUIRED", "Use exactly one result node.")
    outgoing: dict[str, list] = {key: [] for key in nodes}
    incoming: dict[str, list] = {key: [] for key in nodes}
    seen_edges: set[tuple] = set()
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            error("EDGE_ENDPOINT_MISSING", "A connected node no longer exists.", edge=edge.id)
            continue
        signature = (edge.source, edge.source_port, edge.target)
        if signature in seen_edges:
            error("DUPLICATE_CONNECTION", "Remove the duplicate connection.", edge=edge.id)
        seen_edges.add(signature)
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
        expected = {"true", "false"} if nodes[edge.source].type == "condition" else {"out"}
        if edge.source_port not in expected:
            error("PORT_INVALID", "Choose a valid output port.", edge=edge.id)
        for mapping in edge.mappings:
            if set(mapping) != {"from", "to"}:
                error(
                    "MAPPING_INVALID", "Mappings require from and to JSON Pointers.", edge=edge.id
                )
                continue
            for pointer in mapping.values():
                if (
                    not isinstance(pointer, str)
                    or len(pointer) > 512
                    or (pointer and not pointer.startswith("/"))
                    or any(
                        part in {"__proto__", "constructor", "prototype"}
                        for part in pointer.replace("~1", "/").split("/")
                    )
                ):
                    error(
                        "POINTER_INVALID", "Use a safe JSON Pointer such as /ticket.", edge=edge.id
                    )
    indegree = {key: len(value) for key, value in incoming.items()}
    ready = deque(key for key, value in indegree.items() if value == 0)
    visited = 0
    while ready:
        key = ready.popleft()
        visited += 1
        for edge in outgoing[key]:
            indegree[edge.target] -= 1
            if indegree[edge.target] == 0:
                ready.append(edge.target)
    if visited != len(nodes):
        error("CYCLE_DETECTED", "Remove the loop: workflows must be directed acyclic graphs.")

    def reachable(start: str, reverse: bool = False) -> set[str]:
        found: set[str] = set()
        pending = [start]
        while pending:
            key = pending.pop()
            if key in found:
                continue
            found.add(key)
            pending.extend(
                e.source if reverse else e.target for e in (incoming if reverse else outgoing)[key]
            )
        return found

    reachable_from_entry = reachable(entries[0].id) if len(entries) == 1 else set()
    reaches_result = reachable(results[0].id, True) if len(results) == 1 else set()
    for node in graph.nodes:
        if node.id not in reachable_from_entry or node.id not in reaches_result:
            error("NODE_DISCONNECTED", "Connect this node between input and result.", node.id)
        if node.type in entry_types and incoming[node.id]:
            error("ENTRY_HAS_INPUT", "A trigger cannot have incoming connections.", node.id)
        if node.type == "result" and outgoing[node.id]:
            error("RESULT_HAS_OUTPUT", "Result must be the final node.", node.id)
        if node.type == "condition" and sorted(e.source_port for e in outgoing[node.id]) != [
            "false",
            "true",
        ]:
            error("BRANCH_REQUIRED", "Connect exactly one true path and one false path.", node.id)
    semantic = graph.model_dump()
    for node in semantic["nodes"]:
        node.pop("position")
        node.pop("label")
    digest = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "execution_hash": digest,
        "validator_version": "draft-structural-1",
        "scope": "structural",
        "publishable": False,
    }
