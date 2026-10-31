import uuid

from sqlalchemy import select

from app.modules.executions.runtime import execute as execute_agent
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.runtime import execute as execute_workflow
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers
from tests.test_agent_runs import published_agent
from tests.test_deployments import workflow_version
from tests.test_workflow_checkpoints import queue
from tests.test_workflow_dag import edge, node
from tests.test_workflow_data_nodes import _save


def test_queued_agent_stops_after_requester_role_is_removed(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    run = client.post(f"/api/v1/workspaces/{workspace}/runs", headers={**headers(client), "Idempotency-Key": "revoked-member-agent"}, json={"version_id": version["id"], "input": {"ticket": "Check this"}}).json()
    member = db.scalar(select(WorkspaceMember))
    member.role = "viewer"
    db.commit()
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda *_: (_ for _ in ()).throw(AssertionError("Must not call provider")))
    execute_agent(run["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{run['id']}").json()
    assert result["state"] == "failed" and result["error_code"] == "RUN_AUTHORIZATION_REVOKED"
    assert result["uncertain_cost_usd"] is None


def test_workflow_stops_between_steps_after_role_change_and_keeps_evidence(client, owner, db, monkeypatch):
    from app.modules.workflows import preview
    workspace = owner["workspaces"][0]["id"]
    graph = {"nodes": [node("input", "manual_input"), node("first", "transform", {"fields": {"ok": {"kind": "literal", "value": True}}}), node("second", "transform", {"fields": {"done": {"kind": "literal", "value": True}}}), node("result", "result")], "edges": [edge("input", "first"), edge("first", "second"), edge("second", "result")]}
    path = _save(client, workspace, "Access boundary", graph)
    version = client.post(path + "/versions", headers=headers(client), json={"expected_revision": 2}).json()
    run_id = queue(client, workspace, version, {})
    original = preview.run_step
    calls = []
    def step(current, *args):
        calls.append(current.id)
        output = original(current, *args)
        if current.id == "first":
            member = db.scalar(select(WorkspaceMember))
            member.role = "viewer"
            db.commit()
        return output
    monkeypatch.setattr(preview, "run_step", step)
    execute_workflow(run_id, client.app.state.settings)
    run = db.get(WorkflowRun, uuid.UUID(run_id))
    assert run.state == "failed" and run.error_code == "RUN_AUTHORIZATION_REVOKED"
    assert calls == ["input", "first"]
    detail = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
    assert next(step for step in detail["steps"] if step["node_id"] == "first")["status"] == "completed"


def test_deployment_creator_demotion_stops_queued_work(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    version = workflow_version(client, workspace)
    deployment = client.post(f"/api/v1/workspaces/{workspace}/deployments", headers=headers(client), json={"name": "App", "kind": "workflow", "version_id": version["id"]}).json()
    run = client.post(f"/api/v1/deployments/{deployment['id']}/invoke", headers={"Authorization": f"Bearer {deployment['api_key']}", "Idempotency-Key": "demoted-deployment-run"}, json={"input": {}}).json()
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    execute_workflow(run["id"], client.app.state.settings)
    detail = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run['id']}").json()
    assert detail["state"] == "failed" and detail["error_code"] == "RUN_AUTHORIZATION_REVOKED"
