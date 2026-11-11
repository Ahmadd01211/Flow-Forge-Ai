"""Local routing and cleanup recipes with reproducible sample results."""

from app.modules.templates.action_starters import edge, node


def practical_starters():
    customer = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
        "required": ["name", "email"],
        "additionalProperties": False,
    }
    return {
        "switch-routing": {
            "key": "switch-routing",
            "kind": "workflow",
            "name": "Route requests by category",
            "description": "Use Switch to choose a billing, technical or default support queue.",
            "category": "Workflow basics",
            "template_version": 1,
            "setup_steps": [
                "Create a workspace draft and open Route by category to review its billing and technical cases and Default route.",
                "Use local draft preview with the sample input: billing selects billing-team. Try technical for technical-support and other for general-support.",
                "Edit case labels or queue names as needed, validate, then publish for a durable run. Inspect the selected route in Executions > Workflows. No provider or connection is needed.",
            ],
            "sample_input": {"category": "billing"},
            "expected_result": 'With the sample input, returns {"queue": "billing-team"}. Only the billing path runs; technical and Default are skipped.',
            "graph": {
                "schema_version": 1,
                "nodes": [
                    node("input", "manual_input", "Request category", 60, 260),
                    node("route", "switch", "Route by category", 340, 260, {
                        "value": {"kind": "input", "pointer": "/category"},
                        "cases": [
                            {"id": "billing", "label": "Billing", "value": "billing"},
                            {"id": "technical", "label": "Technical", "value": "technical"},
                        ],
                    }),
                    node("billing", "transform", "Billing queue", 640, 60, {
                        "fields": {"queue": {"kind": "literal", "value": "billing-team"}},
                    }),
                    node("technical", "transform", "Technical queue", 640, 260, {
                        "fields": {"queue": {"kind": "literal", "value": "technical-support"}},
                    }),
                    node("general", "transform", "Default queue", 640, 460, {
                        "fields": {"queue": {"kind": "literal", "value": "general-support"}},
                    }),
                    {**node("result", "result", "Selected queue", 960, 260), "join": "active"},
                ],
                "edges": [
                    edge("input", "route"),
                    edge("route", "billing", "billing"),
                    edge("route", "technical", "technical"),
                    edge("route", "general", "default"),
                    edge("billing", "result"),
                    edge("technical", "result"),
                    edge("general", "result"),
                ],
                "input_schema": {
                    "type": "object",
                    "properties": {"category": {"type": "string"}},
                    "required": ["category"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"queue": {"type": "string"}},
                    "required": ["queue"],
                    "additionalProperties": False,
                },
            },
        },
        "remove-duplicates": {
            "key": "remove-duplicates",
            "kind": "workflow",
            "name": "Remove duplicate contacts",
            "description": "Keep the first contact for each email and preserve the original list order.",
            "category": "Data cleanup",
            "template_version": 1,
            "setup_steps": [
                "Create a workspace draft and open Remove duplicates. The list comes from /items and contacts are compared by /email.",
                "Use local draft preview with the sample input. Ada's first record and then Lin remain; the later record with Ada's email is removed. Email comparison is exact and case-sensitive.",
                "Choose a different field to match your data, or clear the field selector to compare whole items. Validate, then publish for a durable run and inspect items, count and removed in Executions > Workflows. No provider or connection is needed.",
            ],
            "sample_input": {
                "items": [
                    {"name": "Ada", "email": "ada@example.com"},
                    {"name": "Lin", "email": "lin@example.com"},
                    {"name": "Ada updated", "email": "ada@example.com"},
                ],
            },
            "expected_result": 'Returns {"items": [{"name": "Ada", "email": "ada@example.com"}, {"name": "Lin", "email": "lin@example.com"}], "count": 2, "removed": 1}. The first record for each email is kept in its original order.',
            "graph": {
                "schema_version": 1,
                "nodes": [
                    node("input", "manual_input", "Contact list", 60),
                    node("cleanup", "list_deduplicate", "Remove duplicates", 360, config={
                        "source": "/items", "item_pointer": "/email",
                    }),
                    node("result", "result", "Unique contacts", 660),
                ],
                "edges": [edge("input", "cleanup"), edge("cleanup", "result")],
                "input_schema": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": customer, "maxItems": 100}},
                    "required": ["items"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": customer, "maxItems": 100},
                        "count": {"type": "integer", "minimum": 0, "maximum": 100},
                        "removed": {"type": "integer", "minimum": 0, "maximum": 100},
                    },
                    "required": ["items", "count", "removed"],
                    "additionalProperties": False,
                },
            },
        },
    }
