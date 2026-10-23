from app.core.errors import fail


def validate_output_schema(schema: dict) -> None:
    """Reject output contracts outside our small verified Structured Outputs subset."""
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "description",
    }

    def visit(node: dict) -> None:
        kind = node.get("type")
        if not isinstance(kind, str) or kind not in {
            "object",
            "array",
            "string",
            "integer",
            "number",
            "boolean",
            "null",
        }:
            fail(
                422,
                "OUTPUT_SCHEMA_UNSUPPORTED",
                "Published output schemas need a supported explicit type.",
            )
        if set(node) - allowed:
            fail(
                422,
                "OUTPUT_SCHEMA_UNSUPPORTED",
                "The output schema uses a constraint unsupported by this provider profile.",
            )
        if kind == "object":
            properties = node.get("properties", {})
            if (
                not isinstance(properties, dict)
                or node.get("additionalProperties") is not False
                or set(node.get("required", [])) != set(properties)
            ):
                fail(
                    422,
                    "OUTPUT_SCHEMA_UNSUPPORTED",
                    "Every output object must require all fields and reject extra fields.",
                )
            for child in properties.values():
                visit(child)
        elif kind == "array":
            if not isinstance(node.get("items"), dict):
                fail(422, "OUTPUT_SCHEMA_UNSUPPORTED", "Output arrays need an item schema.")
            visit(node["items"])
        elif any(
            key in node for key in ("properties", "required", "additionalProperties", "items")
        ):
            fail(
                422,
                "OUTPUT_SCHEMA_UNSUPPORTED",
                "The output schema mixes incompatible type constraints.",
            )

    if schema.get("type") != "object":
        fail(422, "OUTPUT_SCHEMA_UNSUPPORTED", "Published output schemas must have an object root.")
    visit(schema)
