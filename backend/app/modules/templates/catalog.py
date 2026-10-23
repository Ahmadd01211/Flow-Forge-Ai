"""Versioned, code-reviewed starter templates copied into private workspace drafts."""

from app.modules.workflows.schemas import initial_graph


def templates() -> dict[str, dict]:
    return {
        "support-triage": {
            "key": "support-triage",
            "kind": "agent",
            "name": "Support ticket triage",
            "description": "Classify an incoming ticket and explain the priority.",
            "category": "Support",
            "template_version": 1,
            "config": {
                "instructions": "Read the support ticket. Assign urgent only when service is blocked, data is at risk, or a time-critical business process has stopped. Return a short reason grounded in the ticket. Do not invent facts.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticket": {"type": "string"}},
                    "required": ["ticket"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "priority": {"type": "string", "enum": ["urgent", "normal"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["priority", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "faq-answer": {
            "key": "faq-answer",
            "kind": "agent",
            "name": "FAQ answer assistant",
            "description": "Answer a question using only supplied reference material.",
            "category": "Knowledge",
            "template_version": 1,
            "config": {
                "instructions": "Answer the user's question using only the supplied context. If the context does not contain the answer, say that the answer is unavailable. Do not cite sources that are not present in the input.",
                "input_schema": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "context": {"type": "string"}},
                    "required": ["question", "context"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "found_in_context": {"type": "boolean"},
                    },
                    "required": ["answer", "found_in_context"],
                    "additionalProperties": False,
                },
            },
        },
        "input-output": {
            "key": "input-output",
            "kind": "workflow",
            "name": "Input to result",
            "description": "A minimal canvas with manual input and a result step.",
            "category": "Workflow basics",
            "template_version": 1,
            "graph": initial_graph(),
        },
        "text-cleanup": {
            "key": "text-cleanup",
            "kind": "workflow",
            "name": "Text cleanup",
            "description": "Pass structured input through the reviewed text replacement tool.",
            "category": "Automation",
            "template_version": 1,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {"id": "input", "type": "manual_input", "label": "Text input", "position": {"x": 80, "y": 180}},
                    {"id": "replace", "type": "tool", "label": "Replace text", "position": {"x": 390, "y": 180}, "config": {"tool_key": "text.replace"}},
                    {"id": "result", "type": "result", "label": "Clean text", "position": {"x": 720, "y": 180}, "config": {"value": {"kind": "output", "node_id": "replace", "pointer": ""}}},
                ],
                "edges": [
                    {"id": "input-replace", "source": "input", "target": "replace"},
                    {"id": "replace-result", "source": "replace", "target": "result"},
                ],
                "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "find": {"type": "string"}, "replacement": {"type": "string"}}, "required": ["text", "find", "replacement"], "additionalProperties": False},
                "output_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
            },
        },
        "decision-routing": {
            "key": "decision-routing",
            "kind": "workflow",
            "name": "Decision routing",
            "description": "A two-way branch with paths that rejoin at the result.",
            "category": "Workflow basics",
            "template_version": 1,
            "graph": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": "input",
                        "type": "manual_input",
                        "label": "Request",
                        "position": {"x": 60, "y": 250},
                    },
                    {
                        "id": "decision",
                        "type": "condition",
                        "label": "Check condition",
                        "position": {"x": 340, "y": 250},
                        "config": {
                            "left": {"kind": "input", "pointer": "/priority"},
                            "operator": "equals",
                            "right": "urgent",
                        },
                    },
                    {
                        "id": "urgent",
                        "type": "transform",
                        "label": "Urgent path",
                        "position": {"x": 640, "y": 120},
                    },
                    {
                        "id": "normal",
                        "type": "transform",
                        "label": "Normal path",
                        "position": {"x": 640, "y": 380},
                    },
                    {
                        "id": "result",
                        "type": "result",
                        "label": "Return result",
                        "position": {"x": 950, "y": 250},
                        "join": "active",
                    },
                ],
                "edges": [
                    {"id": "e-input-decision", "source": "input", "target": "decision"},
                    {
                        "id": "e-decision-urgent",
                        "source": "decision",
                        "source_port": "true",
                        "target": "urgent",
                    },
                    {
                        "id": "e-decision-normal",
                        "source": "decision",
                        "source_port": "false",
                        "target": "normal",
                    },
                    {"id": "e-urgent-result", "source": "urgent", "target": "result"},
                    {"id": "e-normal-result", "source": "normal", "target": "result"},
                ],
                "input_schema": {
                    "type": "object",
                    "properties": {"priority": {"type": "string"}},
                    "required": ["priority"],
                    "additionalProperties": False,
                },
                "output_schema": {"type": "object"},
            },
        },
    }


def public_catalog() -> dict:
    return {
        "items": [
            {
                key: item[key]
                for key in ("key", "kind", "name", "description", "category", "template_version")
            }
            for item in templates().values()
        ]
    }
