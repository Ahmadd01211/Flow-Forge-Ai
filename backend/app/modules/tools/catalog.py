"""Reviewed, deterministic handlers. No network, secrets, filesystem, or code execution."""

from copy import deepcopy

from app.core.errors import fail
from app.core.json_contracts import bounded_json

CATALOG = {
    "json.extract": {
        "name": "Extract JSON value",
        "description": "Read a value from JSON using a pointer such as /customer/email.",
        "input_schema": {
            "type": "object",
            "properties": {"document": {}, "pointer": {"type": "string"}},
            "required": ["document", "pointer"],
            "additionalProperties": False,
        },
        "read_only": True,
    },
    "text.replace": {
        "name": "Replace text",
        "description": "Replace literal text in a bounded string; useful for workflow cleanup.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "find": {"type": "string"},
                "replacement": {"type": "string"},
            },
            "required": ["text", "find", "replacement"],
            "additionalProperties": False,
        },
        "read_only": True,
    },
}


def invoke(tool_key: str, payload: dict) -> dict:
    bounded_json(payload, max_bytes=65536)
    if tool_key == "json.extract":
        if set(payload) != {"document", "pointer"} or not isinstance(payload["pointer"], str):
            fail(422, "TOOL_INPUT_INVALID", "Provide document and a JSON pointer.")
        pointer = payload["pointer"]
        if len(pointer) > 1024 or (pointer and not pointer.startswith("/")):
            fail(422, "TOOL_INPUT_INVALID", "Use an empty pointer or a /-prefixed JSON pointer.")
        value = payload["document"]
        for raw in pointer.split("/")[1:] if pointer else []:
            segment = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and segment in value:
                value = value[segment]
            elif (
                isinstance(value, list)
                and segment.isascii()
                and segment.isdecimal()
                and int(segment) < len(value)
            ):
                value = value[int(segment)]
            else:
                fail(422, "TOOL_PATH_MISSING", "The JSON pointer does not exist in this document.")
        return {"value": deepcopy(value)}
    if tool_key == "text.replace":
        if set(payload) != {"text", "find", "replacement"} or not all(
            isinstance(payload[key], str) for key in payload
        ):
            fail(422, "TOOL_INPUT_INVALID", "Provide text, find, and replacement strings.")
        if not payload["find"]:
            fail(422, "TOOL_INPUT_INVALID", "Find text cannot be empty.")
        result = payload["text"].replace(payload["find"], payload["replacement"])
        bounded_json({"text": result}, max_bytes=65536)
        return {"text": result}
    fail(404, "TOOL_NOT_FOUND", "Tool not found.")
