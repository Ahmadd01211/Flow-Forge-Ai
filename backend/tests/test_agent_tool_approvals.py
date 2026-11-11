import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.credentials import load_master_key
from app.modules.executions import agent_approvals
from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import execute
from app.modules.mcp.agent_grants import alias
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register
from tests.test_agent_mcp import agent_with_mcp, queued
from tests.test_agent_runs import published_agent, submit


def start_run(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    response = submit(client, workspace, version, key="approval-run-001")
    assert response.status_code == 202, response.text
    run = db.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(response.json()["id"])))
    run.state = "running"
    run.claim_token = uuid.uuid4()
    run.model_started_at = datetime.now(UTC)
    db.commit()
    master = load_master_key(client.app.state.settings.credential_key_path)
    return workspace, run, master


def pending_write_call(client, owner, db, monkeypatch, key):
    base, path = agent_with_mcp(client, owner, monkeypatch, tool="delete_everything")
    request_headers = headers(client)
    policy = client.patch(
        f"{base}/mcp/docs/tools/delete_everything",
        headers=request_headers,
        json={"policy": "allow"},
    )
    assert policy.status_code == 200, policy.text
    version_response = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 1}
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    run_id = queued(client, base, version, key=key)
    calls = []

    def respond(*_):
        return {
            "status": "completed",
            "usage": {"input_tokens": 30, "output_tokens": 8},
            "output": [{
                "type": "function_call",
                "call_id": "write-call",
                "name": alias(version["config"]["mcp_tools"][0]),
                "arguments": '{"query":"all records"}',
            }],
        }

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", respond)
    monkeypatch.setattr(
        "app.modules.mcp.client.call_tool",
        lambda *args, **kwargs: (calls.append((args, kwargs)) or {"ok": True}),
    )
    execute(run_id, client.app.state.settings)
    db.expire_all()
    run = db.get(AgentRun, uuid.UUID(run_id))
    approval = db.scalar(
        select(agent_approvals.AgentToolApproval).where(
            agent_approvals.AgentToolApproval.run_id == run.id
        )
    )
    assert run.state == "waiting" and approval and approval.state == "pending"
    return base, version, run, approval, calls


def test_parking_encrypts_continuation_and_requester_cannot_approve(
    client, owner, db, monkeypatch
):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    arguments = {"customer_id": "cus_private_123"}
    continuation = {"transcript": [{"role": "user", "content": "private prompt"}], "call": {"call_id": "call_1"}}
    now = datetime.now(UTC)

    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments=arguments,
        continuation=continuation,
        now=now,
    )

    assert run.state == "waiting" and run.claim_token is None
    assert approval.state == "pending" and approval.expires_at == now + timedelta(hours=24)
    assert b"cus_private_123" not in approval.ciphertext
    assert b"private prompt" not in approval.ciphertext
    with pytest.raises(HTTPException) as error:
        agent_approvals.decide(
            db, workspace, run.id, approval.id, run.requested_by, "approve", master, now
        )
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "INDEPENDENT_REVIEW_REQUIRED"


def test_independent_admin_decision_is_idempotent_and_claim_decrypts_once(
    client, owner, db, monkeypatch
):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    reviewer = register(client, "reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace), user_id=reviewer_id, role="admin"))
    now = datetime.now(UTC)
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_1"},
        continuation={"transcript": [], "call": {"call_id": "call_1"}},
        now=now,
    )

    result = agent_approvals.decide(
        db, workspace, run.id, approval.id, reviewer_id, "approve", master, now
    )
    assert result.state == "approved" and run.state == "queued"
    assert agent_approvals.decide(
        db, workspace, run.id, approval.id, reviewer_id, "approve", master, now
    ).state == "approved"
    run.state, run.claim_token = "running", uuid.uuid4()
    db.flush()
    assert db.scalar(select(AgentRun.state).where(AgentRun.id == run.id)) == "running"
    assert db.scalar(select(agent_approvals.AgentToolApproval.state).where(agent_approvals.AgentToolApproval.id == approval.id)) == "approved"
    resumed = agent_approvals.claim_approved(db, run, master, now)
    assert resumed["arguments"] == {"customer_id": "cus_1"}
    assert resumed["continuation"]["call"]["call_id"] == "call_1"
    assert agent_approvals.claim_approved(db, run, master, now) is None


def test_claim_clears_encrypted_continuation_when_requester_access_is_revoked(
    client, owner, db, monkeypatch
):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    reviewer = register(client, "revoked-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace), user_id=reviewer_id, role="admin"))
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_1"},
        continuation={"transcript": [], "call": {"call_id": "call_1"}},
    )
    agent_approvals.decide(
        db, workspace, run.id, approval.id, reviewer_id, "approve", master
    )
    run.state, run.claim_token = "running", uuid.uuid4()
    db.commit()

    def revoke(*_):
        raise HTTPException(status_code=403, detail={"code": "RUN_AUTHORIZATION_REVOKED"})

    monkeypatch.setattr(agent_approvals, "assert_authorized", revoke)
    assert agent_approvals.claim_approved(db, run, master) is None
    assert approval.state == "cancelled"
    assert approval.ciphertext == b""


def test_expired_approval_fails_waiting_run_without_resuming(client, owner, db, monkeypatch):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    now = datetime.now(UTC)
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_1"},
        continuation={"transcript": [], "call": {"call_id": "call_1"}},
        now=now,
    )
    approval.expires_at = now - timedelta(seconds=1)
    db.commit()

    assert agent_approvals.expire(db, run, approval, now) is True
    assert run.state == "failed" and run.error_code == "AGENT_TOOL_APPROVAL_EXPIRED"
    assert approval.state == "expired"


def test_persisted_tool_result_resumes_model_without_reclaiming_tool(
    client, owner, db, monkeypatch
):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    reviewer = register(client, "resume-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace), user_id=reviewer_id, role="admin"))
    db.commit()
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_1"},
        continuation={"transcript": [], "items": [], "input_tokens": 10, "output_tokens": 2, "calls": 0, "workflow_calls": 0, "finalizing": False},
    )
    agent_approvals.decide(
        db, workspace, run.id, approval.id, reviewer_id, "approve", master
    )
    run.state, run.claim_token = "running", uuid.uuid4()
    db.commit()
    claimed = agent_approvals.claim_approved(db, run, master)
    assert claimed and claimed["_approval"]["resume_from_ready"] is False
    updated_transcript = [{"role": "user", "content": "question"}, {
        "type": "function_call_output", "call_id": "call_1", "output": '{"ok":true}'
    }]
    agent_approvals.save_call_result(
        client.app.state.sessions,
        master,
        run.id,
        run.claim_token,
        claimed,
        {"transcript": updated_transcript, "input_tokens": 10, "output_tokens": 2, "calls": 1, "workflow_calls": 0, "finalizing": False},
    )
    db.expire_all()
    assert db.get(agent_approvals.AgentToolApproval, approval.id).state == "ready"
    run.state, run.claim_token = "queued", None
    db.commit()
    run.state, run.claim_token = "running", uuid.uuid4()
    db.commit()
    resumed = agent_approvals.claim_approved(db, run, master)
    assert resumed and resumed["_approval"]["resume_from_ready"] is True
    assert resumed["continuation"]["transcript"] == updated_transcript
    assert db.get(agent_approvals.AgentToolApproval, approval.id).state == "resuming"


def test_write_capable_mcp_call_waits_before_remote_invocation(client, owner, db, monkeypatch):
    base, path = agent_with_mcp(client, owner, monkeypatch, tool="delete_everything")
    policy = client.patch(
        f"{base}/mcp/docs/tools/delete_everything",
        headers={"Origin": "http://testserver", "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]},
        json={"policy": "allow"},
    )
    assert policy.status_code == 200, policy.text
    version_response = client.post(
        f"{path}/versions",
        headers={"Origin": "http://testserver", "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]},
        json={"expected_revision": 1},
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    run_id = queued(client, base, version, key="approval-write-001")
    remote_calls = []
    model_requests = []

    def respond(_key, payload, _timeout):
        model_requests.append(payload)
        if len(model_requests) == 1:
            return {
            "status": "completed",
            "usage": {"input_tokens": 30, "output_tokens": 8},
            "output": [{
                "type": "function_call",
                "call_id": "delete-1",
                "name": alias(version["config"]["mcp_tools"][0]),
                "arguments": '{"query":"all records"}',
            }],
            }
        return {
            "status": "completed",
            "usage": {"input_tokens": 20, "output_tokens": 4},
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
            }],
        }

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", respond)
    monkeypatch.setattr(
        "app.modules.mcp.client.call_tool",
        lambda *args, **kwargs: (remote_calls.append((args, kwargs)) or {"ok": True}),
    )

    execute(run_id, client.app.state.settings)

    db.expire_all()
    result = db.get(AgentRun, uuid.UUID(run_id))
    approval = db.scalar(select(agent_approvals.AgentToolApproval).where(
        agent_approvals.AgentToolApproval.run_id == uuid.UUID(run_id)
    ))
    assert result.state == "waiting"
    assert approval and approval.state == "pending"
    assert remote_calls == []

    reviewer = register(client, "write-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=result.workspace_id, user_id=reviewer_id, role="admin"))
    now = datetime.now(UTC)
    agent_approvals.decide(
        db, result.workspace_id, result.id, approval.id, reviewer_id, "approve",
        load_master_key(client.app.state.settings.credential_key_path), now,
    )
    execute(run_id, client.app.state.settings)

    db.expire_all()
    assert db.get(AgentRun, uuid.UUID(run_id)).state == "completed"
    assert len(remote_calls) == 1
    assert len(model_requests) == 2
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "delete-1"
        for item in model_requests[1]["input"]
    )


def test_trace_shows_pending_call_and_api_requires_independent_admin(client, owner, db, monkeypatch):
    workspace, run, master = start_run(client, owner, db, monkeypatch)
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "server_name": "Billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_private"},
        continuation={"transcript": [], "call": {"call_id": "call_1"}},
    )
    trace_url = f"/api/v1/workspaces/{workspace}/runs/{run.id}/trace"
    requester_view = client.get(trace_url)
    assert requester_view.status_code == 200, requester_view.text
    pending = requester_view.json()["tool_approval"]
    assert pending["arguments"] == {"customer_id": "cus_private"}
    assert pending["requester"]["id"] == str(run.requested_by)
    assert pending["may_decide"] is False

    decision_url = f"/api/v1/workspaces/{workspace}/runs/{run.id}/tool-approvals/{approval.id}"
    denied = client.post(decision_url, headers=headers(client), json={"decision": "approve"})
    assert denied.status_code == 403
    reviewer = register(client, "trace-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=run.workspace_id, user_id=reviewer_id, role="admin"))
    db.commit()
    assert client.get(trace_url).json()["tool_approval"]["may_decide"] is True
    approved = client.post(
        decision_url, headers=headers(client), json={"decision": "approve"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["run"]["state"] == "queued"


def test_waiting_run_cancellation_settles_its_approval(client, owner, db, monkeypatch):
    base, _, run, approval, calls = pending_write_call(
        client, owner, db, monkeypatch, "approval-cancel-001"
    )
    cancelled = client.post(
        f"{base}/runs/{run.id}/cancel", headers=headers(client)
    )
    assert cancelled.status_code == 200, cancelled.text
    db.expire_all()
    assert db.get(AgentRun, run.id).state == "cancelled"
    assert db.get(agent_approvals.AgentToolApproval, approval.id).state == "cancelled"
    assert calls == []


def test_policy_classification_change_after_approval_fails_without_call(
    client, owner, db, monkeypatch
):
    base, version, run, approval, calls = pending_write_call(
        client, owner, db, monkeypatch, "approval-policy-change-001"
    )
    reviewer = register(client, "policy-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=run.workspace_id, user_id=reviewer_id, role="admin"))
    db.commit()
    agent_approvals.decide(
        db,
        run.workspace_id,
        run.id,
        approval.id,
        reviewer_id,
        "approve",
        load_master_key(client.app.state.settings.credential_key_path),
    )
    catalog = json.loads(client.app.state.settings.mcp_catalog_json)
    catalog[0]["read_only_tools"].append("delete_everything")
    client.app.state.settings.mcp_catalog_json = json.dumps(catalog)

    execute(str(run.id), client.app.state.settings)

    db.expire_all()
    assert db.get(AgentRun, run.id).state == "failed"
    assert db.get(AgentRun, run.id).error_code == "APPROVAL_CONTEXT_CHANGED"
    assert db.get(agent_approvals.AgentToolApproval, approval.id).state == "cancelled"
    assert calls == []


def test_uncertain_remote_outcome_is_never_replayed(client, owner, db, monkeypatch):
    base, _, run, approval, calls = pending_write_call(
        client, owner, db, monkeypatch, "approval-uncertain-001"
    )
    reviewer = register(client, "uncertain-reviewer@example.com")
    reviewer_id = uuid.UUID(reviewer["user"]["id"])
    db.add(WorkspaceMember(workspace_id=run.workspace_id, user_id=reviewer_id, role="admin"))
    db.commit()
    agent_approvals.decide(
        db,
        run.workspace_id,
        run.id,
        approval.id,
        reviewer_id,
        "approve",
        load_master_key(client.app.state.settings.credential_key_path),
    )

    def uncertain(*args, **kwargs):
        calls.append((args, kwargs))
        raise HTTPException(status_code=502, detail={"code": "MCP_TOOL_FAILED"})

    monkeypatch.setattr("app.modules.mcp.client.call_tool", uncertain)
    execute(str(run.id), client.app.state.settings)
    execute(str(run.id), client.app.state.settings)

    db.expire_all()
    assert len(calls) == 1
    assert db.get(AgentRun, run.id).state == "failed"
    assert db.get(AgentRun, run.id).error_code == "EXTERNAL_OUTCOME_UNKNOWN"
    assert db.get(AgentRun, run.id).uncertain_cost_usd is not None
    assert db.get(agent_approvals.AgentToolApproval, approval.id).state == "uncertain"


def test_deployment_approval_trace_names_deployment_and_creator(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    deployment = client.post(
        f"/api/v1/workspaces/{workspace}/deployments",
        headers=headers(client),
        json={"name": "Support production", "kind": "agent", "version_id": version["id"]},
    )
    assert deployment.status_code == 201, deployment.text
    invocation = client.post(
        f"/api/v1/deployments/{deployment.json()['id']}/invoke",
        headers={"Authorization": f"Bearer {deployment.json()['api_key']}", "Idempotency-Key": "deployment-approval-001"},
        json={"input": {"ticket": "example"}},
    )
    assert invocation.status_code == 202, invocation.text
    run = db.get(AgentRun, uuid.UUID(invocation.json()["id"]))
    run.state, run.claim_token = "running", uuid.uuid4()
    run.model_started_at = datetime.now(UTC)
    db.commit()
    master = load_master_key(client.app.state.settings.credential_key_path)
    approval = agent_approvals.park(
        db,
        master,
        run,
        tool_key="mcp:billing/create_customer",
        tool_identity={"server_id": "billing", "tool_name": "create_customer", "read_only": False},
        arguments={"customer_id": "cus_deployment"},
        continuation={"transcript": [], "call": {"call_id": "deployment-call"}},
    )

    trace = client.get(
        f"/api/v1/workspaces/{workspace}/runs/{run.id}/trace"
    ).json()["tool_approval"]
    assert trace["requester"]["id"] == owner["user"]["id"]
    assert trace["deployment"] == {
        "id": deployment.json()["id"], "name": "Support production"
    }
    assert trace["id"] == str(approval.id)

