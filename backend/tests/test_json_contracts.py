import pytest
from fastapi import HTTPException

from app.core.json_contracts import bounded_json, example_errors, validate_user_schema
from app.modules.agents.schemas import AgentConfig
from app.modules.agents.service import config_hash


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "$ref": "https://example.invalid/schema"},
        {"type": "object", "properties": {"x": {"type": "imaginary"}}},
        {"type": "object", "required": ["missing"]},
        {"type": "object", "required": [{}]},
        {"type": "object", "properties": {"x": {"type": "string", "pattern": ".*"}}},
        {"type": "object", "properties": {"x": {"type": "string", "minLength": 5, "maxLength": 2}}},
    ],
)
def test_invalid_or_unsupported_schema_is_rejected(schema):
    with pytest.raises(HTTPException) as exc:
        validate_user_schema(schema)
    assert exc.value.status_code == 422


def test_property_names_and_literal_payloads_are_not_treated_as_keywords():
    schema = {
        "type": "object",
        "properties": {"pattern": {"type": "string"}, "$ref": {"const": {"$ref": "literal-data"}}},
    }
    validate_user_schema(schema)
    assert not example_errors(
        schema, {"pattern": "hello", "$ref": {"$ref": "literal-data"}}, "input"
    )


def test_nested_types_and_enums_produce_safe_field_errors():
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"state": {"enum": ["ready"]}}},
            }
        },
    }
    validate_user_schema(schema)
    assert example_errors(schema, {"items": [{"state": "secret-value"}]}, "input") == [
        {
            "path": "/input/items/0/state",
            "code": "SCHEMA_ENUM",
            "message": "Value does not satisfy the enum constraint.",
        }
    ]


def test_json_complexity_is_bounded():
    with pytest.raises(HTTPException):
        bounded_json({"text": "x" * 270000})
    with pytest.raises(HTTPException):
        bounded_json({"number": float("nan")})
    with pytest.raises(HTTPException):
        validate_user_schema(
            {"type": "object", "properties": {"state": {"enum": list(range(129))}}}
        )


def test_config_fingerprint_ignores_key_order_and_decimal_spelling():
    a = AgentConfig.model_validate(
        {"instructions": "hello", "limits": {"max_cost_usd": "0.10"}}
    ).model_dump()
    b = AgentConfig.model_validate(
        {"limits": {"max_cost_usd": "0.1"}, "instructions": "hello"}
    ).model_dump()
    assert config_hash(a) == config_hash(b)
