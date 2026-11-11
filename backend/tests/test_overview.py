from decimal import Decimal

from sqlalchemy import select

from app.modules.workflows.runtime import execute
from app.modules.workspaces.models import Workspace, WorkspaceMember
from tests.conftest import headers
from tests.test_workflow_llm import _connect_openai
from tests.test_workflow_pauses import setup


def _overview(client, workspace):
    response = client.get(f"/api/v1/workspaces/{workspace}/overview")
    assert response.status_code == 200, response.text
    return response.json()


def test_new_workspace_shows_setup_and_an_empty_dashboard(client, owner):
    workspace = owner["workspaces"][0]["id"]
    data = _overview(client, workspace)
    assert data["setup"] == {
        "provider_connected": False, "published": False, "succeeded": False,
        "trigger": False, "teammates": False, "complete": False,
    }
    assert data["can_decide"] is True and data["counts"] == {"agents": 0, "workflows": 0}
    assert [day["runs"] for day in data["trend"]] == [0] * 7 and len({day["date"] for day in data["trend"]}) == 7
    attention = data["attention"]
    assert attention["approvals"] == [] and attention["failed_runs_24h"] == 0 and attention["stale_agents"] == []
    assert data["recent_runs"] == [] and data["triggers"]["chat"] == []
    assert isinstance(data["activity"], list)


def test_pending_approvals_runs_and_activity_respect_roles(client, owner, db):
    workspace, path, _version, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    data = _overview(client, workspace)
    approval = data["attention"]["approvals"][0]
    assert data["attention"]["approvals_total"] == 1
    assert approval["run_id"] == run_id and approval["prompt"] == "Review this customer record"
    assert approval["step_label"] == "review" and approval["requested_by_you"] is True
    assert data["recent_runs"][0]["state"] == "waiting" and data["recent_runs"][0]["source"] == "manual"
    edits = {item["name"]: item["status"] for item in data["recent_edits"]}
    assert edits["Review a customer"] == "published"
    assert data["setup"]["published"] is True
    assert data["activity"] and data["activity"][0]["actor_name"]

    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace))
    member.role = "viewer"
    db.commit()
    viewer = _overview(client, workspace)
    assert viewer["can_decide"] is False and viewer["activity"] is None
    assert viewer["attention"]["approvals_total"] == 1


def test_llm_steps_are_not_counted_as_agents_and_chat_runs_are_labelled(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Support chat"}).json()
    graph = workflow["graph"]
    graph["nodes"][0].update(type="chat_trigger")
    graph["nodes"].insert(1, {"id": "ask", "type": "llm", "label": "Reply", "position": {"x": 300, "y": 180},
                              "config": {"instructions": "Help.", "provider": "openai", "model_id": "gpt-5-mini"}})
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "ask", "pointer": ""}}
    graph["edges"] = [{"id": "a", "source": "input", "target": "ask"}, {"id": "b", "source": "ask", "target": "result"}]
    path = f"{base}/{workflow['id']}"
    client.patch(path, headers=headers(client), json={"name": "Support chat", "expected_revision": 1, "graph": graph})
    assert client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2}).status_code == 201
    monkeypatch.setattr("app.modules.workflows.runtime.generate", lambda *_args: ({"reply": "Hi"}, 5, 1))
    sent = client.post(f"{path}/chat", headers={**headers(client), "Idempotency-Key": "overview-chat-1"}, json={"message": "Hello"}).json()
    execute(sent["run"]["id"], client.app.state.settings)

    data = _overview(client, workspace)
    assert data["counts"]["agents"] == 0
    assert data["recent_runs"][0]["source"] == "chat" and data["recent_runs"][0]["state"] == "completed"
    assert data["triggers"]["chat"][0]["name"] == "Support chat"
    assert data["setup"] | {"teammates": False} == {
        "provider_connected": True, "published": True, "succeeded": True,
        "trigger": True, "teammates": False, "complete": True,
    }
    assert data["usage"]["completed_today"] == 1 and data["trend"][-1]["runs"] == 1

    graph["nodes"][1]["label"] = "Answer"
    client.patch(path, headers=headers(client), json={"name": "Support chat", "expected_revision": 2, "graph": graph})
    assert {item["name"]: item["status"] for item in _overview(client, workspace)["recent_edits"]}["Support chat"] == "changed"


def test_attention_flags_stale_agents_trigger_errors_and_limits(client, owner, db, monkeypatch):
    from tests.test_agent_runs import published_agent

    workspace, _version = published_agent(client, owner, monkeypatch)
    assert _overview(client, workspace)["attention"]["stale_agents"] == []
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client),
                json={"api_key": "sk-rotated-overview-aaaaaaaaaaaaaaaa"})
    stale = _overview(client, workspace)["attention"]["stale_agents"]
    assert [(item["name"], item["reason"]) for item in stale] == [("Triage", "credential_changed")]

    row = db.get(Workspace, workspace)
    row.daily_run_limit = 1
    db.commit()
    _, path, _version, run_id = setup(client, owner)
    near = _overview(client, workspace)["attention"]["near_limits"]
    assert near["runs"] is True and near["run_ratio"] >= 1
    assert Decimal(str(near["spend_ratio"])) >= 0
