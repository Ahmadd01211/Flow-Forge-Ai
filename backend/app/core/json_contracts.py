"""Bounded, offline-only user schema validation; never resolve user references."""

import json
import math
from itertools import islice

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from app.core.errors import fail

KEYWORDS = {
    "$schema",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "enum",
    "const",
    "minProperties",
    "maxProperties",
}
UNSAFE_NAMES = {"__proto__", "prototype", "constructor"}


def bounded_json(value: object, *, max_bytes: int = 262144, max_depth: int = 16) -> None:
    count = 0

    def walk(item: object, depth: int) -> None:
        nonlocal count
        count += 1
        if count > 12000 or depth > max_depth:
            fail(422, "JSON_TOO_COMPLEX", "JSON nesting or item count exceeds the supported limit.")
        if isinstance(item, float) and not math.isfinite(item):
            fail(422, "JSON_INVALID", "JSON numbers must be finite.")
        if isinstance(item, dict):
            for key, child in item.items():
                if key in UNSAFE_NAMES:
                    fail(422, "JSON_UNSAFE_KEY", "This property name is not supported.")
                walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)

    walk(value, 0)
    if len(json.dumps(value, allow_nan=False).encode()) > max_bytes:
        fail(422, "JSON_TOO_LARGE", "JSON exceeds the supported size limit.")


def validate_user_schema(schema: dict) -> None:
    bounded_json(schema, max_bytes=65536, max_depth=24)
    if schema.get("type") != "object":
        fail(422, "SCHEMA_OBJECT_REQUIRED", "Input and output must use object schemas.")

    def walk(part: object, depth: int = 0) -> None:
        if depth > 8:
            fail(422, "SCHEMA_TOO_DEEP", "Schemas support at most eight nested schema levels.")
        if not isinstance(part, dict):
            fail(422, "SCHEMA_INVALID", "Each nested schema must be an object.")
        if set(part) - KEYWORDS:
            fail(
                422,
                "SCHEMA_UNSUPPORTED",
                "Schema uses unsupported keywords. References, patterns and executable validators are not supported.",
            )
        if "$schema" in part and part["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            fail(422, "SCHEMA_DRAFT_UNSUPPORTED", "Use JSON Schema 2020-12.")
        if isinstance(part.get("enum"), list) and len(part["enum"]) > 128:
            fail(422, "SCHEMA_TOO_COMPLEX", "Enums support at most 128 alternatives.")
        if "properties" in part:
            properties = part["properties"]
            if not isinstance(properties, dict) or len(properties) > 128:
                fail(422, "SCHEMA_INVALID", "Properties must be a bounded object of schemas.")
            for child in properties.values():
                walk(child, depth + 1)
        if "items" in part:
            walk(part["items"], depth + 1)
        if "additionalProperties" in part and not isinstance(part["additionalProperties"], bool):
            walk(part["additionalProperties"], depth + 1)
        required = part.get("required", [])
        if isinstance(required, list):
            if not all(isinstance(key, str) for key in required):
                fail(422, "SCHEMA_INVALID", "Required fields must be property names.")
            if set(required) - set(part.get("properties", {})):
                fail(
                    422,
                    "SCHEMA_REQUIRED_UNDEFINED",
                    "Required fields must be declared in properties.",
                )
        # Literal const/enum payloads are data, not additional schemas or references.
        for low, high in [
            ("minItems", "maxItems"),
            ("minLength", "maxLength"),
            ("minProperties", "maxProperties"),
            ("minimum", "maximum"),
        ]:
            if (
                isinstance(part.get(low), (int, float))
                and isinstance(part.get(high), (int, float))
                and part[low] > part[high]
            ):
                fail(422, "SCHEMA_RANGE_INVALID", "A schema minimum cannot exceed its maximum.")

    walk(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        fail(
            422,
            "SCHEMA_INVALID",
            "Schema has invalid keyword values. Check types, required fields and limits.",
        )


def example_errors(schema: dict, value: object, field: str) -> list[dict]:
    bounded_json(value)
    return [
        {
            "path": "/"
            + "/".join(
                [
                    field,
                    *(str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path),
                ]
            ),
            "code": f"SCHEMA_{str(error.validator).upper()}",
            "message": f"Value does not satisfy the {error.validator} constraint.",
        }
        for error in islice(Draft202012Validator(schema).iter_errors(value), 20)
    ]
