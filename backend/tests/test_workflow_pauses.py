import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.credentials import load_master_key
from app.modules.workflows import pauses
from app.modules.workflows.checkpoints import view
from app.modules.workflows.models import WorkflowCheckpoint, WorkflowPause, WorkflowRun
from app.modules.workflows.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register
from tests.test_workflow_checkpoints import queue, reconcile
from tests.test_workflow_composition import parent, publish
from tests.test_workflow_dag import edge, node
from tests.test_workflow_data_nodes import _save


def setup(client, owner, kind="approval", config=None):
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node(
                "review",
                kind,
                config
                or (
                    {
                        "prompt": "Review this customer record",
                        "expires_seconds": 3600,
                        "allow_requester": True,
                    }
                    if kind == "approval"
                    else {"seconds": 60}
                ),
            ),
            node("result", "result"),
        ],
        "edges": [edge("input", "review"), edge("review", "result")],
    }
    path = _save(client, workspace, "Review a customer", graph)
    version = publish(client, path)
    run_id = queue(client, workspace, version, {"customer": "Ada"})
    return workspace, path, version, run_id


def detail(client, workspace, run_id):
    response = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def decision(client, workspace, run_id, pause_id, value="approve"):
    return client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}/approvals/{pause_id}/decision",
        headers=headers(client),
        json={"decision": value},
    )


def test_approval_roundtrip_deadlines_budget_checkpoint_and_idempotent_decision(client, owner, db):
    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    run = detail(client, workspace, run_id)
    assert run["state"] == "waiting" and run["finished_at"] is None
    assert run["steps"][1]["status"] == "waiting" and len(run["steps"]) == 2
    assert run["pauses"][0]["state"] == "pending"
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert usage["active_runs"] == usage["accepted_runs"] == 1
    stored = db.get(WorkflowRun, uuid.UUID(run_id))
    original_deadline = stored.deadline_at
    pause = db.get(WorkflowPause, uuid.UUID(run["pauses"][0]["id"]))
    pause.created_at -= timedelta(minutes=5)
    db.commit()
    result = decision(client, workspace, run_id, str(pause.id))
    assert result.status_code == 200 and result.json()["state"] == "queued", result.text
    db.expire_all()
    assert db.get(WorkflowRun, stored.id).deadline_at > original_deadline + timedelta(minutes=4)
    assert decision(client, workspace, run_id, str(pause.id)).status_code == 200
    assert decision(client, workspace, run_id, str(pause.id), "reject").status_code == 409
    execute(run_id, client.app.state.settings)
    complete = detail(client, workspace, run_id)
    assert complete["state"] == "completed" and complete["output"] == {"customer": "Ada"}
    assert len(complete["steps"]) == 3 and complete["steps"][1]["attempt"] == 1
    assert complete["pauses"][0]["decided_by"] == owner["user"]["id"]
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 1


@pytest.mark.parametrize(
    "action,expected,code",
    [
        ("reject", "failed", "APPROVAL_REJECTED"),
        ("cancel", "cancelled", None),
        ("expire", "failed", "APPROVAL_EXPIRED"),
    ],
)
def test_rejection_cancellation_expiry_are_terminal_and_release_capacity(
    client, owner, db, monkeypatch, action, expected, code
):
    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    run = detail(client, workspace, run_id)
    pause_id = run["pauses"][0]["id"]
    if action == "cancel":
        assert (
            client.post(
                f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}/cancel",
                headers=headers(client),
            ).status_code
            == 200
        )
    elif action == "expire":
        db.get(WorkflowPause, uuid.UUID(pause_id)).due_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        reconcile(client, monkeypatch)
    else:
        assert decision(client, workspace, run_id, pause_id, "reject").status_code == 200
    result = detail(client, workspace, run_id)
    assert result["state"] == expected and result["error_code"] == code
    assert result["steps"][1]["status"] == "failed"
    assert decision(client, workspace, run_id, pause_id).status_code == 409
    assert client.get(f"/api/v1/workspaces/{workspace}/usage").json()["active_runs"] == 0
    execute(run_id, client.app.state.settings)
    assert detail(client, workspace, run_id)["state"] == expected


def test_timer_maintenance_survives_duplicate_ticks_and_old_worker_delivery(
    client, owner, db, monkeypatch
):
    workspace, _, _, run_id = setup(client, owner, "wait")
    execute(run_id, client.app.state.settings)
    execute(run_id, client.app.state.settings)  # stale Celery redelivery cannot claim waiting work
    result = detail(client, workspace, run_id)
    pause = db.get(WorkflowPause, uuid.UUID(result["pauses"][0]["id"]))
    assert (
        pauses.reconcile(
            client.app.state.sessions,
            load_master_key(client.app.state.settings.credential_key_path),
        )
        == 0
    )
    pause.due_at = datetime.now(UTC) - timedelta(seconds=1)
    pause.created_at -= timedelta(minutes=2)
    db.commit()
    reconcile(client, monkeypatch)
    db.expire_all()
    deadline = db.get(WorkflowRun, uuid.UUID(run_id)).deadline_at
    reconcile(client, monkeypatch)
    db.expire_all()
    assert db.get(WorkflowRun, uuid.UUID(run_id)).deadline_at == deadline
    execute(run_id, client.app.state.settings)
    result = detail(client, workspace, run_id)
    assert result["state"] == "completed" and result["pauses"][0]["state"] == "elapsed"
    assert result["output"] == {"customer": "Ada"}


def test_preview_and_isolated_node_test_cannot_approve_or_wait(client, owner):
    workspace, path, _, run_id = setup(client, owner)
    result = client.post(
        path + "/preview", headers=headers(client), json={"expected_revision": 2, "input": {}}
    )
    assert result.status_code == 422
    graph = client.get(path).json()["graph"]
    result = client.post(
        path + "/nodes/review/test", headers=headers(client), json={"graph": graph, "input": {}}
    )
    assert result.json()["error"]["code"] == "PAUSE_REQUIRES_RUN"
    assert detail(client, workspace, run_id)["state"] == "queued"


def test_requester_separation_viewer_editor_and_other_workspace_cannot_approve(client, owner, db):
    workspace, _, _, run_id = setup(
        client,
        owner,
        config={"prompt": "Independent review", "expires_seconds": 60, "allow_requester": False},
    )
    execute(run_id, client.app.state.settings)
    pause_id = detail(client, workspace, run_id)["pauses"][0]["id"]
    assert (
        decision(client, workspace, run_id, pause_id).json()["error"]["code"]
        == "INDEPENDENT_REVIEW_REQUIRED"
    )
    other = register(client, "reviewer@example.com")
    other_id = uuid.UUID(other["user"]["id"])
    assert decision(client, workspace, run_id, pause_id).status_code == 404
    member = WorkspaceMember(workspace_id=uuid.UUID(workspace), user_id=other_id, role="viewer")
    db.add(member)
    db.commit()
    assert decision(client, workspace, run_id, pause_id).status_code == 403
    member.role = "editor"
    db.commit()
    assert (
        decision(client, workspace, run_id, pause_id).json()["error"]["code"]
        == "APPROVAL_REVIEWER_REQUIRED"
    )
    member.role = "admin"
    db.commit()
    assert decision(client, workspace, run_id, pause_id).status_code == 200
    member.role = "viewer"  # revoke approval authority before downstream work consumes it
    db.commit()
    execute(run_id, client.app.state.settings)
    assert detail(client, workspace, run_id)["error_code"] == "APPROVAL_REVIEWER_REVOKED"


def test_expiry_checked_in_api_without_maintenance(client, owner, db):
    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    pause_id = detail(client, workspace, run_id)["pauses"][0]["id"]
    db.get(WorkflowPause, uuid.UUID(pause_id)).due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert (
        decision(client, workspace, run_id, pause_id).json()["error"]["code"] == "APPROVAL_EXPIRED"
    )
    assert detail(client, workspace, run_id)["state"] == "failed"


def test_requester_revocation_before_decision_prevents_resume(client, owner, db):
    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    pause_id = detail(client, workspace, run_id)["pauses"][0]["id"]
    reviewer = register(client, "admin@example.com")
    db.add(
        WorkspaceMember(
            workspace_id=uuid.UUID(workspace),
            user_id=uuid.UUID(reviewer["user"]["id"]),
            role="admin",
        )
    )
    db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == uuid.UUID(workspace),
            WorkspaceMember.user_id == uuid.UUID(owner["user"]["id"]),
        )
    ).role = "viewer"
    db.commit()
    result = decision(client, workspace, run_id, pause_id)
    assert result.status_code == 200 and result.json()["error_code"] == "RUN_AUTHORIZATION_REVOKED"


def test_nested_loop_pauses_resume_without_repeating_completed_items(client, owner, db):
    workspace, _, version, unused = setup(client, owner, "wait", {"seconds": 1})
    client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs/{unused}/cancel", headers=headers(client)
    )
    path, graph = parent(client, workspace, version)
    version = publish(client, path)
    run_id = queue(
        client,
        workspace,
        version,
        {"items": [{"customer": "Ada"}, {"customer": "Lin"}]},
        "two-item-timers",
    )
    master = load_master_key(client.app.state.settings.credential_key_path)
    for expected_scope in (["batch[0]"], ["batch[1]"]):
        execute(run_id, client.app.state.settings)
        result = detail(client, workspace, run_id)
        assert result["state"] == "waiting", result
        current = next(row for row in result["pauses"] if row["state"] == "pending")
        step = next(step for step in result["steps"] if step["node_id"] == current["node_id"])
        assert step["scope"] == expected_scope
        db.expire_all()
        row = db.get(WorkflowPause, uuid.UUID(current["id"]))
        row.due_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert pauses.reconcile(client.app.state.sessions, master) == 1
    execute(run_id, client.app.state.settings)
    result = detail(client, workspace, run_id)
    assert result["state"] == "completed" and result["output"]["count"] == 2, result
    assert len(result["steps"]) == 9
    assert all(step["attempt"] == 1 for step in result["steps"] if step["type"] not in {"for_each"})


def test_combined_pause_expansion_limit_and_nested_preview_safety(client, owner):
    workspace, _, version, _ = setup(client, owner, "wait", {"seconds": 43201})
    path, graph = parent(client, workspace, version, max_items=2)
    check = client.post(path + "/check", headers=headers(client), json={"graph": graph}).json()
    assert not check["valid"] and any(e["code"] == "WORKFLOW_PAUSE_LIMIT" for e in check["errors"])
    assert check["has_pause"] and not check["has_external"]
    result = client.post(
        path + "/nodes/batch/test",
        headers=headers(client),
        json={"graph": graph, "input": {"items": []}},
    )
    assert result.json()["error"]["code"] == "SUBWORKFLOW_TEST_REQUIRES_RUN"


def test_waiting_reservation_and_midnight_completion_remain_budgeted(client, owner, db):
    workspace, _, _, run_id = setup(client, owner, "wait")
    execute(run_id, client.app.state.settings)
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    run.reserved_max_usd, run.cost_usd = Decimal("0.5"), Decimal("0.1")
    run.created_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert Decimal(usage["committed_usd"]) == Decimal("0.5")
    run.state, run.finished_at = "completed", datetime.now(UTC)
    db.commit()
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert usage["active_runs"] == 0 and Decimal(usage["committed_usd"]) == Decimal("0.1")


def test_approved_input_is_bound_and_replay_of_waiting_run_is_rejected(client, owner, db):
    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    result = detail(client, workspace, run_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}/replay",
        headers={**headers(client), "Idempotency-Key": "replay-waiting-key"},
        json={},
    )
    assert response.status_code == 409
    pause_id = result["pauses"][0]["id"]
    assert decision(client, workspace, run_id, pause_id).status_code == 200
    db.expire_all()
    db.get(WorkflowPause, uuid.UUID(pause_id)).input_hash = "0" * 64
    db.commit()
    execute(run_id, client.app.state.settings)
    assert detail(client, workspace, run_id)["error_code"] == "APPROVAL_INPUT_CHANGED"
    master = load_master_key(client.app.state.settings.credential_key_path)
    row = db.scalar(
        select(WorkflowCheckpoint).where(
            WorkflowCheckpoint.run_id == uuid.UUID(run_id), WorkflowCheckpoint.node_id == "review"
        )
    )
    assert view(row, master, include_input=True)["input"] == {"customer": "Ada"}


def test_external_receipt_before_approval_is_not_repeated_on_resume(client, owner, db, monkeypatch):
    from app.modules.http_tools import service
    from tests.test_http_tools import create_tool

    workspace = owner["workspaces"][0]["id"]
    _, tool = create_tool(client, owner, monkeypatch)
    graph = {"nodes": [node("input", "manual_input"), node("fetch", "http_tool", {"tool_id": tool["id"]}), node("review", "approval", {"prompt": "Review the fetched record", "expires_seconds": 60, "allow_requester": True}), node("result", "result")], "edges": [edge("input", "fetch"), edge("fetch", "review"), edge("review", "result")]}
    path = _save(client, workspace, "Fetch then review", graph)
    version = publish(client, path)
    calls = []
    monkeypatch.setattr(service, "request", lambda *_a, **_k: calls.append(True) or {"status_code": 200, "body": {"name": "Ada"}})
    run_id = queue(client, workspace, version, {"ticket": "T1"})
    execute(run_id, client.app.state.settings)
    result = detail(client, workspace, run_id)
    assert result["state"] == "waiting" and len(calls) == 1
    assert not db.get(WorkflowRun, uuid.UUID(run_id)).external_inflight
    assert decision(client, workspace, run_id, result["pauses"][0]["id"]).status_code == 200
    execute(run_id, client.app.state.settings)
    result = detail(client, workspace, run_id)
    assert result["state"] == "completed" and len(calls) == 1
    assert result["output"] == {"status_code": 200, "body": {"name": "Ada"}}
