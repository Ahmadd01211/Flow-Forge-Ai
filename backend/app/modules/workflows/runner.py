"""Recursive execution inside one run ledger, budget reservation and fenced checkpoint tree."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.executions.authorization import assert_authorized
from app.modules.workflows.composition import (
    COMPOSITE_NODES,
    MAX_CALL_DEPTH,
    inputs_for,
    resolve_version,
)
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.preview import run_preview


class DurableRunner:
    def __init__(self, sessions, identity, token, workspace_id, master, settings):
        self.sessions, self.identity, self.token = sessions, identity, token
        self.workspace_id, self.master, self.settings = workspace_id, master, settings

    def active_run(self, db):
        run = db.scalar(
            select(WorkflowRun).where(
                WorkflowRun.workspace_id == self.workspace_id, WorkflowRun.id == self.identity
            )
        )
        if (
            not run
            or run.state != "running"
            or run.claim_token != self.token
            or run.cancel_requested_at
        ):
            fail(409, "RUN_INTERRUPTED", "This workflow run was interrupted.")
        if datetime.now(UTC) >= run.deadline_at:
            fail(408, "RUN_TIMEOUT", "This workflow run exceeded its deadline.")
        assert_authorized(db, run)
        return run

    def run(self, graph, data, checkpoint, deadline, ceiling, ancestry):
        from app.modules.workflows.runtime import _agent_handler, _http_handler, _mcp_handler

        entry_id = next(
            node.id
            for node in graph.nodes
            if node.type in {"manual_input", "webhook_trigger", "schedule_trigger"}
        )
        ceiling, deadline = checkpoint.bind_scope(ceiling, deadline, entry_id)
        restored = checkpoint.completed()
        result_id = next(node.id for node in graph.nodes if node.type == "result")
        finished = restored.get(result_id)
        if finished and finished["status"] == "completed":
            # Completed work does not expire while a later item is recovering.
            # Validate its contract again: a crash may have occurred between
            # checkpointing the result and the graph-output validation.
            if example_errors(graph.output_schema, finished["output"], "output"):
                fail(
                    422,
                    "OUTPUT_SCHEMA_INVALID",
                    "Saved child output does not match its published contract.",
                )
            return {
                "output": finished["output"],
                "steps": list(restored.values()),
                "scope": "durable",
                "durable": True,
            }
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            fail(408, "RUN_TIMEOUT", "This workflow scope exceeded its deadline.")
        capped_graph = graph.model_copy(
            update={"limits": {**graph.limits, "max_cost_usd": str(ceiling)}}
        )

        def bounded(handler):
            def call(node, value):
                with self.sessions() as db:
                    self.active_run(db)
                available = (deadline - datetime.now(UTC)).total_seconds()
                if available <= 0:
                    fail(408, "RUN_TIMEOUT", "This workflow scope exceeded its deadline.")
                node = node.model_copy(
                    update={
                        "policy": {
                            **node.policy,
                            "timeout_seconds": min(
                                node.policy.get("timeout_seconds", 60), available
                            ),
                        }
                    }
                )
                return handler(node, value)

            return call

        def compose(node, value):
            with self.sessions() as db:
                run = self.active_run(db)
                version, child = resolve_version(db, self.workspace_id, node.config)
                if version.workflow_id in ancestry or len(ancestry) >= MAX_CALL_DEPTH:
                    fail(
                        422,
                        "SUBWORKFLOW_RECURSION",
                        "This workflow call exceeds the supported nesting rules.",
                    )
                values = inputs_for(node, value, child)
                node_deadline = min(
                    deadline,
                    datetime.now(UTC) + timedelta(seconds=node.policy.get("timeout_seconds", 60)),
                )
                node_deadline = checkpoint.node_deadline(node, node_deadline)
            outputs = []
            for index, child_input in enumerate(values):
                with self.sessions() as db:
                    run = self.active_run(db)
                    child_ceiling = min(
                        ceiling,
                        (run.cost_usd or Decimal(0)) + Decimal(child.limits["max_cost_usd"]),
                    )
                child_deadline = min(
                    node_deadline,
                    datetime.now(UTC) + timedelta(seconds=child.limits.get("timeout_seconds", 60)),
                )
                evidence = checkpoint.child(
                    node, version.id, index if node.type == "for_each" else None
                )
                result = self.run(
                    child,
                    child_input,
                    evidence,
                    child_deadline,
                    child_ceiling,
                    (*ancestry, version.workflow_id),
                )
                outputs.append(result["output"])
                bounded_json(outputs, max_bytes=65000)
            return (
                {"items": outputs, "count": len(outputs)} if node.type == "for_each" else outputs[0]
            )

        with self.sessions() as db:
            from app.modules.workflows.pauses import handler as pause_handler
            return run_preview(
                db,
                self.workspace_id,
                graph,
                data,
                agent_handler=bounded(
                    _agent_handler(
                        self.sessions,
                        self.identity,
                        self.token,
                        self.workspace_id,
                        self.master,
                        capped_graph,
                        self.settings,
                    )
                )
                if any(node.type == "agent" for node in graph.nodes)
                else None,
                mcp_handler=bounded(
                    _mcp_handler(
                        self.sessions,
                        self.identity,
                        self.token,
                        self.workspace_id,
                        self.master,
                        self.settings,
                    )
                )
                if any(node.type == "mcp_tool" for node in graph.nodes)
                else None,
                http_handler=bounded(
                    _http_handler(
                        self.sessions, self.identity, self.token, self.workspace_id, self.settings
                    )
                )
                if any(node.type == "http_tool" for node in graph.nodes)
                else None,
                composition_handler=compose
                if any(node.type in COMPOSITE_NODES for node in graph.nodes)
                else None,
                checkpoint=checkpoint,
                pause_handler=pause_handler(self.sessions, self.identity, self.token, self.workspace_id, self.master, checkpoint),
                mcp_catalog_json=self.settings.mcp_catalog_json,
                max_seconds=remaining,
                root_workflow_id=ancestry[-1],
            )
