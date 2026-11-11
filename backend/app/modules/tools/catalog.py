"""Reviewed, deterministic handlers. No network, secrets, filesystem, or code execution."""

from copy import deepcopy
from datetime import date, timedelta

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
    "demo.order_lookup": {
        "name": "Sample order lookup (demo data)",
        "description": "Look up a made-up Northwind Outdoor order such as A-17 to try agents without a real store API.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "read_only": True,
    },
}


def _demo_orders() -> dict:
    """Sample orders dated relative to today, so the return-window examples stay true."""
    today = date.today()
    day = lambda offset: (today - timedelta(days=offset)).isoformat()  # noqa: E731
    return {
        "A-17": {"status": "delivered", "delivered_on": day(13), "items": [{"name": "Storm rain jacket", "price": 149.0, "final_sale": False}]},
        "A-18": {"status": "delivered", "delivered_on": day(45), "items": [{"name": "Trail hiking boots", "price": 189.0, "final_sale": False}]},
        "A-19": {"status": "delivered", "delivered_on": day(5), "items": [{"name": "Gift card", "price": 50.0, "final_sale": True}]},
        "A-20": {"status": "in_transit", "shipped_on": day(2), "expected_on": day(-3), "items": [{"name": "Camping stove", "price": 79.0, "final_sale": False}]},
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
    if tool_key == "demo.order_lookup":
        if set(payload) != {"order_id"} or not isinstance(payload["order_id"], str) or len(payload["order_id"]) > 40:
            fail(422, "TOOL_INPUT_INVALID", "Provide an order_id string such as A-17.")
        order_id = payload["order_id"].strip().upper()
        order = _demo_orders().get(order_id)
        return {"found": True, "order_id": order_id, **order, "sample_data": True} if order else {"found": False, "order_id": order_id, "sample_data": True}
    fail(404, "TOOL_NOT_FOUND", "Tool not found.")
