import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.credentials import load_master_key
from app.modules.executions import worker
from app.modules.workflows import preview
from app.modules.workflows.checkpoints import Checkpoints
from app.modules.workflows.models import WorkflowCheckpoint, WorkflowRun, WorkflowVersion
from app.modules.workflows.runtime import execute
from tests.conftest import headers, register
from tests.test_workflow_checkpoints import queue
from tests.test_workflow_dag import edge, node, ticket_agent
from tests.test_workflow_data_nodes import _run, _save


def publish(client, path, revision=2):
    response = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": revision}
    )
    assert response.status_code == 201, response.text
    return response.json()


def child_version(client, workspace, envelope=True, timeout=60):
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node(
                "shape",
                "transform",
                {
                    "fields": {
                        "name": {"kind": "input", "pointer": "/item/name" if envelope else "/name"},
                        "index": {"kind": "input", "pointer": "/index"}
                        if envelope
                        else {"kind": "literal", "value": 0},
                    }
                },
            ),
            node("result", "result"),
        ],
        "edges": [edge("input", "shape"), edge("shape", "result")],
    }
    item_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    graph["limits"] = {"timeout_seconds": timeout, "max_cost_usd": "0.10"}
    graph["input_schema"] = (
        {
            "type": "object",
            "properties": {"item": item_schema, "index": {"type": "integer"}},
            "required": ["item", "index"],
            "additionalProperties": False,
        }
        if envelope
        else item_schema
    )
    path = _save(client, workspace, "Reusable item workflow", graph)
    return path, publish(client, path)


def parent(client, workspace, version, kind="for_each", **config):
    settings = {
        "version_id": version["id"],
        **(
            {"source": "/items", "max_items": 3, "input_mode": "envelope"}
            if kind == "for_each"
            else {}
        ),
        **config,
    }
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node("batch", kind, settings),
            node("result", "result"),
        ],
        "edges": [edge("input", "batch"), edge("batch", "result")],
    }
    path = _save(client, workspace, "Batch workflow", graph)
    return path, graph


@pytest.mark.parametrize("mode", ["item", "envelope"])
def test_bounded_loop_preview_run_and_scoped_step_evidence(client, owner, db, mode):
    workspace = owner["workspaces"][0]["id"]
    _, child = child_version(client, workspace, envelope=mode == "envelope")
    path, graph = parent(client, workspace, child, input_mode=mode)
    values = {"items": [{"name": "Ada"}, {"name": "Lin"}]}
    check = client.post(path + "/check", headers=headers(client), json={"graph": graph}).json()
    assert check["publishable"] and check["expanded_steps"] == 12 and check["agent_steps"] == 0
    sample = client.post(
        path + "/preview", headers=headers(client), json={"expected_revision": 2, "input": values}
    )
    assert sample.status_code == 200, sample.text
    version = publish(client, path)
    frozen = db.get(WorkflowVersion, uuid.UUID(version["id"]))
    assert (
        frozen.graph["nodes"][1]["config"]["graph_hash"]
        == db.get(WorkflowVersion, uuid.UUID(child["id"])).graph_hash
    )
    result = _run(client, workspace, version["id"], values, "loop-roundtrip-0001")
    assert result["state"] == "completed", result
    assert (
        result["output"]
        == sample.json()["output"]
        == {
            "items": [
                {"name": "Ada", "index": 0},
                {"name": "Lin", "index": 1 if mode == "envelope" else 0},
            ],
            "count": 2,
        }
    )
    steps = result["steps"]
    assert len(steps) == 9 and len({step["node_id"] for step in steps}) == 9
    assert {tuple(step["scope"]) for step in steps} == {(), ("batch[0]",), ("batch[1]",)}
    child_step = next(
        step
        for step in steps
        if step["scope"] == ["batch[1]"] and step["definition_node_id"] == "shape"
    )
    assert child_step["parent_node_id"] == "batch" and child_step["iteration_index"] == 1
    detail = client.get(
        f"/api/v1/workspaces/{workspace}/workflow-runs/{result['id']}/steps/{child_step['node_id']}"
    ).json()
    assert detail["input"] == (
        {"item": {"name": "Lin"}, "index": 1} if mode == "envelope" else {"name": "Lin"}
    )
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 1


@pytest.mark.parametrize(
    "values,code",
    [
        ({"items": []}, None),
        ({"items": [{"name": "A"}] * 4}, "LOOP_ITEM_LIMIT"),
        ({"items": "wrong"}, "LOOP_ITEM_LIMIT"),
        ({"items": [{"name": "A"}, {"wrong": "B"}]}, "SUBWORKFLOW_INPUT_INVALID"),
    ],
)
def test_loop_checks_all_input_before_first_child_and_never_truncates(
    client, owner, monkeypatch, values, code
):
    workspace = owner["workspaces"][0]["id"]
    _, child = child_version(client, workspace)
    path, _ = parent(client, workspace, child)
    version = publish(client, path)
    calls = []
    original = preview.run_step

    def tracked(current, *args, **kwargs):
        if current.id == "shape":
            calls.append(current.id)
        return original(current, *args, **kwargs)

    monkeypatch.setattr(preview, "run_step", tracked)
    result = _run(client, workspace, version["id"], values, "loop-preflight-0001")
    assert not calls
    if code:
        assert result["state"] == "failed" and result["error_code"] == code, result
    else:
        assert result["state"] == "completed" and result["output"] == {"items": [], "count": 0}


def test_subworkflow_versions_stay_pinned_and_cross_workspace_targets_are_hidden(client, owner):
    workspace = owner["workspaces"][0]["id"]
    child_path, child = child_version(client, workspace, envelope=False)
    path, _ = parent(client, workspace, child, "subworkflow")
    version = publish(client, path)
    draft = client.get(child_path).json()
    draft["graph"]["nodes"][1]["config"]["fields"]["name"] = {
        "kind": "literal",
        "value": "New version",
    }
    assert (
        client.patch(
            child_path,
            headers=headers(client),
            json={"name": draft["name"], "expected_revision": 2, "graph": draft["graph"]},
        ).status_code
        == 200
    )
    publish(client, child_path, 3)
    result = _run(client, workspace, version["id"], {"name": "Original"}, "pinned-child-0001")
    assert result["state"] == "completed" and result["output"]["name"] == "Original", result
    options = client.get(
        f"/api/v1/workspaces/{workspace}/workflows/call-options?exclude_workflow_id={child_path.rsplit('/', 1)[1]}"
    ).json()["items"]
    assert not any(option["workflow_id"] == child_path.rsplit("/", 1)[1] for option in options)
    client.cookies.clear()
    other = register(client, "workflow-caller@example.com")["workspaces"][0]["id"]
    other_path, graph = parent(client, other, child, "subworkflow")
    checked = client.post(
        other_path + "/check", headers=headers(client), json={"graph": graph}
    ).json()
    assert not checked["publishable"] and checked["errors"][0]["code"] == "SUBWORKFLOW_UNAVAILABLE"


def test_composition_rejects_recursion_depth_and_expansion(client, owner):
    workspace = owner["workspaces"][0]["id"]
    child_path, child = child_version(client, workspace)
    recursive = {
        "nodes": [
            node("input", "manual_input"),
            node("self", "subworkflow", {"version_id": child["id"]}),
            node("result", "result"),
        ],
        "edges": [edge("input", "self"), edge("self", "result")],
    }
    checked = client.post(
        child_path + "/check", headers=headers(client), json={"graph": recursive}
    ).json()
    assert checked["errors"][0]["code"] == "SUBWORKFLOW_RECURSION"
    middle_path, _ = parent(client, workspace, child, "subworkflow")
    middle = publish(client, middle_path)
    top_path, _ = parent(client, workspace, middle, "subworkflow")
    top = publish(client, top_path)
    overflow_path, overflow = parent(client, workspace, top, "subworkflow")
    checked = client.post(
        overflow_path + "/check", headers=headers(client), json={"graph": overflow}
    ).json()
    assert not checked["publishable"] and "three workflow levels" in checked["errors"][0]["message"]
    huge_path, huge = parent(client, workspace, middle, max_items=20)
    # 3 + 20 * (3 + 3) = 123 worst-case steps.
    checked = client.post(
        huge_path + "/check", headers=headers(client), json={"graph": huge}
    ).json()
    assert checked["errors"][0]["code"] == "WORKFLOW_EXPANSION_LIMIT"
    tested = client.post(
        huge_path + "/nodes/batch/test",
        headers=headers(client),
        json={"graph": huge, "input": {"items": []}},
    )
    assert (
        tested.status_code == 200 and tested.json()["error"]["code"] == "WORKFLOW_EXPANSION_LIMIT"
    )


def test_loop_recovery_reuses_completed_items_after_safe_worker_failure(
    client, owner, db, monkeypatch
):
    workspace = owner["workspaces"][0]["id"]
    _, child = child_version(client, workspace)
    path, _ = parent(client, workspace, child)
    version = publish(client, path)
    run_id = queue(client, workspace, version, {"items": [{"name": "A"}, {"name": "B"}]})
    original = preview.run_step
    calls = []

    def crash(current, data, *args):
        if current.id == "shape":
            calls.append(data["index"])
            if data["index"] == 1:
                raise SystemExit("Simulated process death")
        return original(current, data, *args)

    monkeypatch.setattr(preview, "run_step", crash)
    with pytest.raises(SystemExit):
        execute(run_id, client.app.state.settings)
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    assert run.state == "running" and not run.external_inflight
    run.heartbeat_at = datetime.now(UTC) - timedelta(seconds=11)
    db.commit()
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    monkeypatch.setattr(worker.celery, "send_task", lambda *_, **__: None)
    worker.reconcile_workflows_once()
    monkeypatch.setattr(preview, "run_step", original)
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert result["state"] == "completed", result
    assert calls == [0, 1]
    first = [step for step in result["steps"] if step["scope"] == ["batch[0]"]]
    assert first and all(step["attempt"] == 1 for step in first)
    evidence = db.scalars(
        select(WorkflowCheckpoint)
        .where(WorkflowCheckpoint.run_id == run.id)
        .order_by(WorkflowCheckpoint.sequence)
    ).all()
    assert [row.sequence for row in evidence] == list(range(9))
    assert len({row.node_id for row in evidence}) == 9


def test_scope_budget_and_deadline_are_not_reset_on_recovery(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    _, child = child_version(client, workspace)
    path, _ = parent(client, workspace, child)
    version = publish(client, path)
    run_id = queue(client, workspace, version, {"items": []})
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    run.state, run.claim_token = "running", uuid.uuid4()
    db.commit()
    master = load_master_key(client.app.state.settings.credential_key_path)
    evidence = Checkpoints(
        client.app.state.sessions, run.workspace_id, run.id, run.claim_token, master
    )
    from app.modules.workflows.schemas import Node

    loop = Node.model_validate(
        node(
            "batch",
            "for_each",
            {
                "version_id": child["id"],
                "source": "/items",
                "max_items": 3,
                "input_mode": "envelope",
            },
        )
    )
    child_evidence = evidence.child(loop, child["id"], 0)
    original_deadline = datetime.now(UTC) + timedelta(seconds=2)
    child_evidence.bind_scope(Decimal("0.02"), original_deadline, "input")
    child_evidence.start(
        Node.model_validate(node("input", "manual_input")), {"item": {"name": "A"}, "index": 0}, 0
    )
    recovered = evidence.child(loop, child["id"], 0)
    ceiling, deadline = recovered.bind_scope(
        Decimal("0.09"), datetime.now(UTC) + timedelta(seconds=20), "input"
    )
    assert ceiling == Decimal("0.02") and deadline == original_deadline


def test_finished_child_can_be_reused_after_its_own_deadline_while_parent_is_active(
    client, owner, db, monkeypatch
):
    from app.modules.workflows import runner

    workspace = owner["workspaces"][0]["id"]
    _, child = child_version(client, workspace, timeout=1)
    path, _ = parent(client, workspace, child)
    version = publish(client, path)
    run_id = queue(client, workspace, version, {"items": [{"name": "A"}, {"name": "B"}]})
    original_run = runner.DurableRunner.run
    original_step = preview.run_step
    calls = []

    def step(current, data, *args):
        if current.id == "shape":
            calls.append(data["index"])
        return original_step(current, data, *args)

    def crash(self, graph, data, evidence, *args):
        if evidence.path and data.get("index") == 1:
            raise SystemExit("Process ended before starting the second child")
        return original_run(self, graph, data, evidence, *args)

    monkeypatch.setattr(preview, "run_step", step)
    monkeypatch.setattr(runner.DurableRunner, "run", crash)
    with pytest.raises(SystemExit):
        execute(run_id, client.app.state.settings)
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    run.heartbeat_at = datetime.now(UTC) - timedelta(seconds=11)
    db.commit()
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    monkeypatch.setattr(worker.celery, "send_task", lambda *_, **__: None)
    worker.reconcile_workflows_once()
    original_clock = runner.datetime

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return original_clock.now(tz) + timedelta(seconds=2)

    monkeypatch.setattr(runner, "datetime", Later)
    monkeypatch.setattr(runner.DurableRunner, "run", original_run)
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert result["state"] == "completed" and calls == [0, 1], result


def http_child(client, owner, monkeypatch):
    from tests.test_http_tools import create_tool

    base, tool = create_tool(client, owner, monkeypatch, method="POST", read_only=False)
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node("send", "http_tool", {"tool_id": tool["id"]}),
            node("result", "result"),
        ],
        "edges": [edge("input", "send"), edge("send", "result")],
        "input_schema": tool["input_schema"],
    }
    path = _save(client, workspace, "Reusable service action", graph)
    return base, tool, publish(client, path)


@pytest.mark.parametrize("behavior", ["recover", "cancel", "ambiguous"])
def test_nested_writes_preserve_receipts_and_never_resend_unknown_outcomes(
    client, owner, db, monkeypatch, behavior
):
    base, _, child = http_child(client, owner, monkeypatch)
    workspace = owner["workspaces"][0]["id"]
    path, graph = parent(client, workspace, child, input_mode="item", max_items=2)
    version = publish(client, path)
    value = {"items": [{"ticket": "A"}, {"ticket": "B"}]}
    sample = client.post(
        path + "/preview", headers=headers(client), json={"expected_revision": 2, "input": value}
    )
    assert sample.status_code == 422 and sample.json()["error"]["code"] == "PREVIEW_UNSUPPORTED"
    sample_node = client.post(
        path + "/nodes/batch/test", headers=headers(client), json={"graph": graph, "input": value}
    )
    assert (
        sample_node.status_code == 200
        and sample_node.json()["error"]["code"] == "SUBWORKFLOW_TEST_REQUIRES_RUN"
    )
    run_id = queue(client, workspace, version, value)
    calls = []

    def request(_spec, _secret, data, timeout):
        assert 0 < timeout <= 12
        current = db.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id == uuid.UUID(run_id))
            .execution_options(populate_existing=True)
        )
        assert current.external_inflight
        calls.append(data["ticket"])
        if behavior == "ambiguous":
            raise SystemExit("Simulated loss of external receipt")
        if behavior == "cancel":
            current.cancel_requested_at = datetime.now(UTC)
            db.commit()
        return {"status_code": 201, "body": {"receipt": data["ticket"]}}

    monkeypatch.setattr("app.modules.http_tools.service.request", request)
    original = preview.run_step

    def crash(current, data, *args):
        if behavior == "recover" and current.id == "send" and data["ticket"] == "B":
            raise SystemExit("Simulated safe worker loss")
        return original(current, data, *args)

    monkeypatch.setattr(preview, "run_step", crash)
    if behavior == "cancel":
        execute(run_id, client.app.state.settings)
        result = client.get(f"{base}/workflow-runs/{run_id}").json()
        assert result["state"] == "cancelled" and calls == ["A"]
        assert any(
            step["scope"] == ["batch[0]"]
            and step["definition_node_id"] == "send"
            and step["status"] == "completed"
            for step in result["steps"]
        )
        return
    with pytest.raises(SystemExit):
        execute(run_id, client.app.state.settings)
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    db.refresh(run)
    assert calls == ["A"]
    run.heartbeat_at = datetime.now(UTC) - timedelta(seconds=11)
    db.commit()
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    monkeypatch.setattr(worker.celery, "send_task", lambda *_, **__: None)
    worker.reconcile_workflows_once()
    db.refresh(run)
    if behavior == "ambiguous":
        assert run.state == "running" and run.external_inflight
        run.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        worker.reconcile_workflows_once()
        db.refresh(run)
        assert run.state == "failed" and calls == ["A"]
        replay = client.post(
            f"{base}/workflow-runs/{run_id}/replay",
            headers={**headers(client), "Idempotency-Key": "nested-external-replay"},
            json={"confirm_external": False},
        )
        assert (
            replay.status_code == 422
            and replay.json()["error"]["code"] == "EXTERNAL_REPLAY_UNCONFIRMED"
        )
    else:
        assert run.state == "queued" and not run.external_inflight
        monkeypatch.setattr(preview, "run_step", original)
        execute(run_id, client.app.state.settings)
        result = client.get(f"{base}/workflow-runs/{run_id}").json()
        assert result["state"] == "completed" and calls == ["A", "B"], result
        assert result["output"] == {
            "items": [
                {"status_code": 201, "body": {"receipt": "A"}},
                {"status_code": 201, "body": {"receipt": "B"}},
            ],
            "count": 2,
        }
        assert (
            next(
                step
                for step in result["steps"]
                if step["scope"] == ["batch[0]"] and step["definition_node_id"] == "send"
            )["attempt"]
            == 1
        )


def test_nested_agents_reserve_once_and_share_parent_budget_across_loop_items(
    client, owner, db, monkeypatch
):
    workspace, child = ticket_agent(client, owner, monkeypatch)
    path, graph = parent(client, workspace, child, input_mode="item", max_items=2)
    graph["limits"] = {"max_cost_usd": "0.008"}
    current = client.get(path).json()
    assert (
        client.patch(
            path,
            headers=headers(client),
            json={"name": current["name"], "expected_revision": 2, "graph": graph},
        ).status_code
        == 200
    )
    version = publish(client, path, 3)
    run_id = queue(client, workspace, version, {"items": [{"ticket": "A"}, {"ticket": "B"}]})
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    assert (
        run.reserved_max_usd == Decimal("0.008")
        and (run.deadline_at - run.created_at).total_seconds() > 20
    )
    caps = []

    def generate(_, __, data, maximum, timeout):
        caps.append(maximum)
        return data, 10000, 20

    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "BUDGET_TOO_SMALL", result
    assert len(caps) == 3 and caps[0] > caps[1] > caps[2]
    assert Decimal(result["cost_usd"]) < Decimal("0.008") and result["uncertain_cost_usd"] is None
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 1
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert usage["accepted_runs"] == 1 and Decimal(usage["measured_usd"]) == Decimal(
        result["cost_usd"]
    )
    overflow = client.post(
        path + "/check",
        headers=headers(client),
        json={
            "graph": {
                **graph,
                "nodes": [
                    graph["nodes"][0],
                    {
                        **graph["nodes"][1],
                        "config": {**graph["nodes"][1]["config"], "max_items": 5},
                    },
                    graph["nodes"][2],
                ],
            }
        },
    ).json()
    assert any(error["code"] == "WORKFLOW_EXPANSION_LIMIT" for error in overflow["errors"])


def test_nested_service_revocation_blocks_before_any_network_call(client, owner, monkeypatch):
    base, tool, child = http_child(client, owner, monkeypatch)
    workspace = owner["workspaces"][0]["id"]
    path, _ = parent(client, workspace, child, input_mode="item")
    version = publish(client, path)
    run_id = queue(client, workspace, version, {"items": [{"ticket": "A"}]})
    assert (
        client.post(
            f"{base}/http-tools/{tool['id']}/revoke",
            headers=headers(client),
            json={"expected_generation": 1},
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        "app.modules.http_tools.service.request",
        lambda *_: (_ for _ in ()).throw(AssertionError("Revoked tool must not run")),
    )
    execute(run_id, client.app.state.settings)
    result = client.get(f"{base}/workflow-runs/{run_id}").json()
    assert result["state"] == "failed" and result["error_code"] == "WORKFLOW_INVALID", result
    replay = client.post(
        f"{base}/workflow-runs/{run_id}/replay",
        headers={**headers(client), "Idempotency-Key": "revoked-child-replay"},
        json={"confirm_external": False},
    )
    assert (
        replay.status_code == 422
        and replay.json()["error"]["code"] == "EXTERNAL_REPLAY_UNCONFIRMED"
    )


def test_paired_customer_templates_can_be_bound_published_and_run(client, owner):
    from app.modules.templates.composition_starters import composition_starters

    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    child_copy = client.post(
        f"{base}/templates/customer-profile-step/instantiate", headers=headers(client)
    )
    assert child_copy.status_code == 201, child_copy.text
    child = publish(client, f"{base}/workflows/{child_copy.json()['id']}", 1)
    parent_copy = client.post(
        f"{base}/templates/batch-customer-profiles/instantiate", headers=headers(client)
    )
    assert parent_copy.status_code == 201, parent_copy.text
    path = f"{base}/workflows/{parent_copy.json()['id']}"
    draft = client.get(path).json()
    draft["graph"]["nodes"][1]["config"]["version_id"] = child["id"]
    assert (
        client.patch(
            path,
            headers=headers(client),
            json={"name": draft["name"], "expected_revision": 1, "graph": draft["graph"]},
        ).status_code
        == 200
    )
    version = publish(client, path)
    value = composition_starters()["batch-customer-profiles"]["sample_input"]
    result = _run(client, workspace, version["id"], value, "paired-starter-0001")
    assert result["state"] == "completed" and result["output"]["count"] == 2
    assert result["output"]["items"][1] == {"name": "Lin", "email": "lin@example.com", "index": 1}


def test_portable_loop_keeps_settings_but_never_copies_the_private_binding():
    from app.modules.templates.router import portable_definition

    graph = {
        "nodes": [
            node("input", "manual_input"),
            node(
                "batch",
                "for_each",
                {
                    "version_id": str(uuid.uuid4()),
                    "graph_hash": "a" * 64,
                    "source": "/items",
                    "max_items": 5,
                    "input_mode": "item",
                },
            ),
            node("result", "result"),
        ],
        "edges": [edge("input", "batch"), edge("batch", "result")],
    }
    copied = portable_definition("workflow", graph)["graph"]["nodes"][1]["config"]
    assert copied == {"source": "/items", "max_items": 5, "input_mode": "item"}
    assert "version_id" in graph["nodes"][1]["config"]
