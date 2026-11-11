"""Versioned, code-reviewed starter templates copied into workspace drafts."""

from app.modules.templates.action_starters import action_starters
from app.modules.templates.approval_starter import approval_starter
from app.modules.templates.composition_starters import composition_starters
from app.modules.workflows.schemas import initial_graph


def templates() -> dict[str, dict]:
    return {
        **action_starters(),
        **approval_starter(),
        **composition_starters(),
        "support-triage": {
            "key": "support-triage",
            "kind": "agent",
            "name": "Support ticket triage",
            "description": "Classify an incoming ticket and explain the priority.",
            "category": "Support",
            "template_version": 1,
            "starter_skills": ["plain-language"],
            "setup_steps": [
                "Choose a model in the agent editor and connect its provider under Integrations. A real test run can incur provider charges.",
                "Review and publish the copied Plain-language replies skill before testing the agent.",
                "Use the sample ticket below in the Test panel, then adjust the instructions or input/output schemas if needed.",
                "Save, review readiness, and publish a version before using the agent in chat, a workflow, or a deployment.",
            ],
            "sample_input": {
                "ticket": "Our payment service is down and customers cannot check out."
            },
            "expected_result": "A draft urgent priority with a short explanation that checkout is blocked, for human review.",
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
            "starter_skills": ["plain-language", "summarise-sources"],
            "setup_steps": [
                "Connect a provider under Integrations and choose a model. A real test run can incur provider charges.",
                "Review and publish the copied Plain-language replies and Summarise with sources skills before testing.",
                "Supply reference material and a question, then review the sample answer before publishing the agent.",
            ],
            "sample_input": {
                "question": "When is support available?",
                "context": "Support hours: Monday to Friday, 09:00 to 17:00 UTC.",
            },
            "expected_result": "A draft answer stating the supplied support hours, with found_in_context true, for human review.",
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
        "customer-reply-draft": {
            "key": "customer-reply-draft",
            "kind": "agent",
            "name": "Customer reply draft",
            "description": "Draft a customer reply using your brand guidance for a teammate to review.",
            "category": "Support",
            "template_version": 1,
            "starter_skills": ["brand-voice", "polite-refusal"],
            "setup_steps": [
                "Connect a provider under Integrations and choose a model. A real test run can incur provider charges.",
                "Customize the copied Brand voice and Polite refusal skills, then review and publish both before testing.",
                "Add your brand guidelines and a customer message. Review the draft before sending it yourself.",
            ],
            "sample_input": {
                "customer_message": "Hello, could you let me know the shipping status of my order?",
                "brand_guidelines": "",
            },
            "expected_result": "A polite draft reply asking for the information needed to check shipping, with needs_human true, for human review. No message is sent.",
            "config": {
                "instructions": "Draft a helpful customer reply using the supplied brand guidelines. When guidelines are empty, use a neutral, clear tone. Do not invent order details, shipping status, policies or promises. If the request cannot be answered from the supplied information, ask for missing details and set needs_human to true. Flag requests needing judgement or an exception for a human. Return only a draft; do not claim to have sent a message or taken action.",
                "input_schema": {
                    "type": "object",
                    "properties": {"customer_message": {"type": "string"}, "brand_guidelines": {"type": "string"}},
                    "required": ["customer_message", "brand_guidelines"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"draft_reply": {"type": "string"}, "needs_human": {"type": "boolean"}},
                    "required": ["draft_reply", "needs_human"],
                    "additionalProperties": False,
                },
            },
        },
        "meeting-action-items": {
            "key": "meeting-action-items",
            "kind": "agent",
            "name": "Meeting action items",
            "description": "Turn meeting notes into a summary and assigned tasks for review.",
            "category": "Productivity",
            "template_version": 1,
            "starter_skills": ["extract-tables"],
            "setup_steps": [
                "Connect a provider under Integrations and choose a model. A real test run can incur provider charges.",
                "Review and publish the copied Extract tables from text skill before testing.",
                "Paste meeting notes, then check task owners and missing dates before publishing the agent.",
            ],
            "sample_input": {
                "notes": "Planning meeting: Alex will send the project brief by Friday. Sam will review the budget; no due date was agreed.",
            },
            "expected_result": "A draft summary and two action items for human review: Alex sends the project brief by Friday; Sam reviews the budget with an empty due_date because none was agreed.",
            "config": {
                "instructions": "Summarise the supplied meeting notes and extract explicit action items. Keep task owners and due dates as written. Use an empty string for a missing owner or due date; never infer or invent one. Do not convert relative dates unless the notes provide enough information. Return a draft for human review, without claiming to have created tasks or contacted anyone.",
                "input_schema": {
                    "type": "object",
                    "properties": {"notes": {"type": "string"}},
                    "required": ["notes"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "action_items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"task": {"type": "string"}, "owner": {"type": "string"}, "due_date": {"type": "string"}},
                                "required": ["task", "owner", "due_date"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["summary", "action_items"],
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
                            "operator": "eq",
                            "right": {"kind": "literal", "value": "urgent"},
                        },
                    },
                    {
                        "id": "urgent",
                        "type": "transform",
                        "label": "Urgent path",
                        "position": {"x": 640, "y": 120},
                        "config": {"fields": {"queue": {"kind": "literal", "value": "on-call"}}},
                    },
                    {
                        "id": "normal",
                        "type": "transform",
                        "label": "Normal path",
                        "position": {"x": 640, "y": 380},
                        "config": {"fields": {"queue": {"kind": "literal", "value": "standard"}}},
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
                for key in ("key", "kind", "name", "description", "category", "template_version", "starter_skills", "setup_steps", "sample_input", "expected_result")
                if key in item
            }
            for item in templates().values()
        ]
    }
