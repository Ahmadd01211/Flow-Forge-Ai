"""A local pair that teaches published-version reuse and bounded list processing."""

from app.modules.templates.action_starters import edge, node


def composition_starters():
    customer = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
        "required": ["name", "email"],
        "additionalProperties": False,
    }
    result = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "index": {"type": "integer"},
        },
        "required": ["name", "email", "index"],
        "additionalProperties": False,
    }
    return {
        "customer-profile-step": {
            "key": "customer-profile-step",
            "kind": "workflow",
            "name": "Prepare a customer profile",
            "category": "Reusable workflows",
            "template_version": 1,
            "description": "A local child workflow that turns an item/index envelope into a customer profile. Publish it for reuse in a batch.",
            "setup_steps": [
                "Create this draft and publish it; it uses only local field mappings.",
                "Create Batch customer profiles next, then select this published version in its For each item node.",
            ],
            "sample_input": {"item": {"name": "Ada", "email": "ada@example.com"}, "index": 0},
            "graph": {
                "nodes": [
                    node("input", "manual_input", "Customer and index", 60),
                    node(
                        "profile",
                        "transform",
                        "Prepare profile",
                        360,
                        config={
                            "fields": {
                                "name": {"kind": "input", "pointer": "/item/name"},
                                "email": {"kind": "input", "pointer": "/item/email"},
                                "index": {"kind": "input", "pointer": "/index"},
                            }
                        },
                    ),
                    node("result", "result", "Customer profile", 660),
                ],
                "edges": [edge("input", "profile"), edge("profile", "result")],
                "input_schema": {
                    "type": "object",
                    "properties": {"item": customer, "index": {"type": "integer", "minimum": 0}},
                    "required": ["item", "index"],
                    "additionalProperties": False,
                },
                "output_schema": result,
            },
        },
        "batch-customer-profiles": {
            "key": "batch-customer-profiles",
            "kind": "workflow",
            "name": "Batch customer profiles",
            "category": "Reusable workflows",
            "template_version": 1,
            "description": "Process up to five customers in order through a published child workflow, with per-item execution evidence.",
            "setup_steps": [
                "First publish Prepare a customer profile from the paired template.",
                "Choose that version in Process customers. Keep Item and index input and a five-item limit.",
                "Preview this local workflow, then publish and run. Inspect each item's steps in Executions → Workflows.",
            ],
            "sample_input": {
                "items": [
                    {"name": "Ada", "email": "ada@example.com"},
                    {"name": "Lin", "email": "lin@example.com"},
                ]
            },
            "graph": {
                "nodes": [
                    node("input", "manual_input", "Customer list", 60),
                    node(
                        "batch",
                        "for_each",
                        "Process customers",
                        360,
                        config={
                            "version_id": "",
                            "source": "/items",
                            "input_mode": "envelope",
                            "max_items": 5,
                        },
                    ),
                    node("result", "result", "Prepared profiles", 660),
                ],
                "edges": [edge("input", "batch"), edge("batch", "result")],
                "input_schema": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": customer, "maxItems": 5}},
                    "required": ["items"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": result, "maxItems": 5},
                        "count": {"type": "integer", "minimum": 0, "maximum": 5},
                    },
                    "required": ["items", "count"],
                    "additionalProperties": False,
                },
            },
        },
    }
