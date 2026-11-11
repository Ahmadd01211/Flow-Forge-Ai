from sqlalchemy import select

from app.modules.agents.models import Agent, AgentVersion
from app.modules.executions.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers
from tests.test_skills import _connect


def _assist(client, workspace, task, context, key):
    return client.post(f"/api/v1/workspaces/{workspace}/agents/assist", headers={**headers(client), "Idempotency-Key": key},
                       json={"task": task, "provider": "openai", "model_id": "gpt-5-mini", "context": context})


def test_improve_runs_as_a_budgeted_hidden_assistant(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect(client, workspace, monkeypatch)
    seen = []
    improved = {"instructions": "You are the Northwind returns assistant.\n- Look up the order first.", "changes": ["Added a clear role", "Made order lookup explicit"]}
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda _key, version, data, *_rest: seen.append((version.config, data)) or (improved, 120, 60))
    started = _assist(client, workspace, "improve", {"current_instructions": "help with returns", "tools": ["Sample order lookup"]}, "assist-run-0001")
    assert started.status_code == 202, started.text
    run_id = started.json()["run"]["id"]
    execute(run_id, client.app.state.settings)
    run = client.get(f"/api/v1/workspaces/{workspace}/runs/{run_id}").json()
    assert run["state"] == "completed" and run["output"] == improved and run["cost_usd"] is not None
    config, data = seen[0]
    assert "prompt engineer" in config["instructions"] and data["current_instructions"] == "help with returns"
    assert config["output_schema"]["required"] == ["instructions", "changes"]

    helper = db.scalar(select(Agent).where(Agent.system_role == "assist:improve"))
    assert helper is not None and helper.workspace_id is not None
    assert client.get(f"/api/v1/workspaces/{workspace}/agents/library").json()["items"] == []
    assert client.get(f"/api/v1/workspaces/{workspace}/runs/{run_id}/trace").json()["agent"]["system"] is True
    again = _assist(client, workspace, "improve", {"current_instructions": "other"}, "assist-run-0002").json()["run"]
    assert again["version_id"] == run["version_id"]
    assert db.scalar(select(AgentVersion).where(AgentVersion.id == run["version_id"])).config["limits"]["max_cost_usd"] == "0.05"


def test_each_task_has_its_own_assistant_and_viewers_cannot_start_one(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect(client, workspace, monkeypatch)
    draft = _assist(client, workspace, "draft", {"request": "Answer questions about our refund policy", "available_tools": [], "available_skills": []}, "assist-run-0003")
    examples = _assist(client, workspace, "examples", {"input_schema": {"type": "object"}, "instructions": "Chat."}, "assist-run-0004")
    assert draft.status_code == 202 and examples.status_code == 202
    assert draft.json()["run"]["version_id"] != examples.json()["run"]["version_id"]
    roles = set(db.scalars(select(Agent.system_role).where(Agent.system_role.is_not(None))))
    assert roles == {"assist:draft", "assist:examples"}
    bad_model = client.post(f"/api/v1/workspaces/{workspace}/agents/assist", headers={**headers(client), "Idempotency-Key": "assist-run-0005"},
                            json={"task": "improve", "provider": "openai", "model_id": "nope", "context": {}})
    assert bad_model.status_code == 422 and "Brain" in bad_model.json()["error"]["message"]
    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace))
    member.role = "viewer"
    db.commit()
    assert _assist(client, workspace, "improve", {}, "assist-run-0006").status_code == 403
