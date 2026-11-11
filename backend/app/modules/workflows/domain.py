import hashlib
import json
import re
from collections import deque

from fastapi import HTTPException

from app.core.json_contracts import bounded_json
from app.modules.workflows.schemas import Graph


def switch_ports(config: dict) -> set[str]:
    """Validate the Switch contract and return its current stable ports.

    Raise ValueError so graph validation can return a node-local blocking issue.
    IDs are persisted identities; labels and list order never determine routes.
    """
    try:
        bounded_json(config, max_bytes=65536)
    except (HTTPException, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Switch settings must fit within the supported JSON limits.") from exc
    reference = config.get("value")
    if not isinstance(reference, dict):
        raise ValueError("Choose a fixed value or a field from this step's input.")
    if reference.get("kind") == "literal":
        valid_reference = set(reference) == {"kind", "value"}
    else:
        pointer = reference.get("pointer")
        valid_reference = (
            reference.get("kind") == "input"
            and set(reference) == {"kind", "pointer"}
            and isinstance(pointer, str)
            and len(pointer) <= 512
            and (not pointer or pointer.startswith("/"))
            and all(
                part.replace("~1", "/").replace("~0", "~")
                not in {"__proto__", "constructor", "prototype"}
                for part in pointer.split("/")[1:]
            )
        )
    if not valid_reference:
        raise ValueError("Choose a fixed value or a safe input field path.")
    cases = config.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
        raise ValueError("Add between one and eight Switch cases.")
    ports = {"default"}
    values: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "label", "value"}:
            raise ValueError("Every case needs an ID, label and scalar value.")
        identity, label, value = case["id"], case["label"], case["value"]
        if (
            not isinstance(identity, str)
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", identity) is None
            or identity in {"out", "true", "false", "default"}
            or identity in ports
        ):
            raise ValueError("Use unique, non-reserved case IDs starting with a lowercase letter.")
        if not isinstance(label, str) or not 1 <= len(label) <= 40:
            raise ValueError("Case labels need one to forty characters.")
        if type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("Case values must be text, numbers, booleans or null.")
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical in values:
            raise ValueError("Each Switch case needs a different value.")
        values.add(canonical)
        ports.add(identity)
    return ports


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
    entry_types = {"manual_input", "webhook_trigger", "schedule_trigger", "chat_trigger"}
    entries = [n for n in graph.nodes if n.type in entry_types]
    results = [n for n in graph.nodes if n.type == "result"]
    if len(entries) != 1:
        error("ENTRY_REQUIRED", "Use exactly one input or trigger node.")
    if len(results) != 1:
        error("RESULT_REQUIRED", "Use exactly one result node.")
    outgoing: dict[str, list] = {key: [] for key in nodes}
    incoming: dict[str, list] = {key: [] for key in nodes}
    expected_ports: dict[str, set[str]] = {}
    for node in graph.nodes:
        if node.type == "switch":
            try:
                expected_ports[node.id] = switch_ports(node.config)
            except ValueError as exc:
                error("SWITCH_CONFIG_INVALID", str(exc), node.id, path="config")
                expected_ports[node.id] = {"default"}
        else:
            expected_ports[node.id] = {"true", "false"} if node.type == "condition" else {"out"}
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
        expected = expected_ports[edge.source]
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
        targets = [mapping.get("to") for mapping in edge.mappings]
        if all(isinstance(pointer, str) for pointer in targets):
            for index, pointer in enumerate(targets):
                parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]] if pointer else []
                for other in targets[index + 1:]:
                    other_parts = [part.replace("~1", "/").replace("~0", "~") for part in other.split("/")[1:]] if other else []
                    if parts[:len(other_parts)] == other_parts or other_parts[:len(parts)] == parts:
                        error("MAPPING_CONFLICT", "Mapping targets must be separate fields. A whole-output mapping cannot be combined with other targets.", edge=edge.id)
                        break
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
        if node.type == "switch" and sorted(e.source_port for e in outgoing[node.id]) != sorted(
            expected_ports[node.id]
        ):
            error("BRANCH_REQUIRED", "Connect exactly one path for each Switch case and the default path.", node.id)
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
        "validator_version": "dag-2",
        "scope": "structural",
        "publishable": False,
    }
