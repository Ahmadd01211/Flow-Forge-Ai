"""A fully local approval/timer walkthrough; independent review is the safe default."""

from app.modules.templates.action_starters import edge, node


def approval_starter():
    return {
        "review-and-release": {
            "key": "review-and-release",
            "kind": "workflow",
            "name": "Review and release",
            "category": "Human review",
            "template_version": 1,
            "description": "Review a saved record, wait five seconds and return it. No external calls or provider key needed.",
            "setup_steps": [
                "Open Review record. For a single-person local test, explicitly allow the run requester to approve; otherwise another owner/admin must review.",
                "Publish and run with the sample input, then open Executions → Workflow runs.",
                "Inspect the saved input and approve or reject. Approval continues through a five-second durable timer. Inspect Activity log in Settings for its audit trail.",
            ],
            "sample_input": {"customer": "Ada", "request": "Release the prepared customer profile"},
            "graph": {
                "nodes": [
                    node("input", "manual_input", "Record to review", 60),
                    node(
                        "review",
                        "approval",
                        "Review record",
                        360,
                        config={
                            "prompt": "Check the customer record before releasing it.",
                            "expires_seconds": 3600,
                            "allow_requester": False,
                        },
                    ),
                    node("cooldown", "wait", "Five-second cooldown", 660, config={"seconds": 5}),
                    node("result", "result", "Released record", 960),
                ],
                "edges": [
                    edge("input", "review"),
                    edge("review", "cooldown"),
                    edge("cooldown", "result"),
                ],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            },
        }
    }
