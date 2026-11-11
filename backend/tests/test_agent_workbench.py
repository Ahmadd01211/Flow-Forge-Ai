from sqlalchemy import select

from app.modules.agents.models import Agent, AgentVersion
from app.modules.executions.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers
from tests.test_agent_runs import published_agent

CHAT_IO = {
    "input_schema": {
        "type": "object",
        "properties": {"conversation_id": {"type": "string"}, "message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    },
    "output_schema": {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"], "additionalProperties": False},
}


def _library(client, workspace):
    response = client.get(f"/api/v1/workspaces/{workspace}/agents/library")
    assert response.status_code == 200, response.text
    return {item["name"]: item for item in response.json()["items"]}


def _chat_agent(client, workspace, memory=True):
    base = f"/api/v1/workspaces/{workspace}/agents"
    config = {"instructions": "Chat helpfully.", "model_id": "gpt-5-mini", **CHAT_IO}
    if memory:
        config["memory"] = {"key_pointer": "/conversation_id", "max_turns": 5, "retention_days": 30}
    agent = client.post(base, headers=headers(client), json={"name": "Concierge", "config": config}).json()
    published = client.post(f"{base}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    assert published.status_code == 201, published.text
    return agent, published.json()


def test_library_shows_status_runs_and_health(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    triage = _library(client, workspace)["Triage"]
    assert triage["status"] == "published" and triage["published"]["number"] == version["number"]
    assert triage["published"]["runnable"] is True and triage["published"]["chat_ready"] is False
    assert triage["model_id"] == "gpt-5-mini" and triage["tools"]["count"] == 0 and triage["last_run"] is None

    submitted = client.post(f"/api/v1/workspaces/{workspace}/runs", headers={**headers(client), "Idempotency-Key": "library-run-001"},
                            json={"version_id": version["id"], "input": {"ticket": "Outage"}})
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda *_args: ({"priority": "urgent"}, 5, 1))
    execute(submitted.json()["id"], client.app.state.settings)
    triage = _library(client, workspace)["Triage"]
    assert triage["last_run"]["state"] == "completed" and triage["week"] == {"completed": 1, "failed": 0}

    agent_id = triage["id"]
    current = client.get(f"/api/v1/workspaces/{workspace}/agents/{agent_id}").json()
    client.patch(f"/api/v1/workspaces/{workspace}/agents/{agent_id}", headers=headers(client), json={
        "name": "Triage", "description": "", "config": {**current["config"], "instructions": "Classify tickets carefully."},
        "expected_revision": current["revision"],
    })
    assert _library(client, workspace)["Triage"]["status"] == "changed"
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client),
                json={"api_key": "sk-rotated-library-aaaaaaaaaaaaaaaa"})
    assert _library(client, workspace)["Triage"]["published"]["runnable"] is False


def test_live_chat_runs_unsaved_settings_in_a_hidden_twin(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    agent_id = _library(client, workspace)["Triage"]["id"]
    draft = client.get(f"/api/v1/workspaces/{workspace}/agents/{agent_id}").json()["config"]
    unsaved = {**draft, "instructions": "Only answer with urgent."}

    def attempt(key, config=unsaved):
        return client.post(f"/api/v1/workspaces/{workspace}/agents/{agent_id}/try",
                           headers={**headers(client), "Idempotency-Key": key}, json={"config": config, "input": {"ticket": "Down"}})

    first = attempt("try-run-0001")
    assert first.status_code == 202, first.text
    run = first.json()["run"]
    twin = db.scalar(select(Agent).where(Agent.playground_for == agent_id))
    tried = db.get(AgentVersion, run["version_id"])
    assert twin is not None and tried.agent_id == twin.id and tried.config["instructions"] == "Only answer with urgent."
    # The real agent's history is untouched and the twin never appears as an agent.
    versions = client.get(f"/api/v1/workspaces/{workspace}/agents/{agent_id}/versions").json()["items"]
    assert [item["id"] for item in versions] == [version["id"]]
    assert set(_library(client, workspace)) == {"Triage"}
    assert attempt("try-run-0002").json()["run"]["version_id"] == run["version_id"]
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda *_args: ({"priority": "urgent"}, 5, 1))
    execute(run["id"], client.app.state.settings)
    assert client.get(f"/api/v1/workspaces/{workspace}/runs/{run['id']}").json()["output"] == {"priority": "urgent"}
    broken = attempt("try-run-0003", {**unsaved, "model_id": "not-a-model"})
    assert broken.status_code == 422 and broken.json()["error"]["code"] == "MODEL_UNSUPPORTED"
    assert "Brain" in broken.json()["error"]["message"]


def test_published_chat_memory_inspector_and_forgetting(client, owner, db, monkeypatch):
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"])
    workspace = owner["workspaces"][0]["id"]
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client), json={"api_key": "sk-test-runtime-aaaaaaaaaaaaaaaa"})
    agent, _ = _chat_agent(client, workspace)
    base = f"/api/v1/workspaces/{workspace}/agents/{agent['id']}"
    seen = []
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda _key, _version, data, *_rest: seen.append(data) or ({"reply": "ok"}, 5, 1))
    first = client.post(f"{base}/chat", headers={**headers(client), "Idempotency-Key": "agent-chat-001"}, json={"message": "Hi"})
    assert first.status_code == 202, first.text
    conversation = first.json()["conversation_id"]
    execute(first.json()["run"]["id"], client.app.state.settings)
    second = client.post(f"{base}/chat", headers={**headers(client), "Idempotency-Key": "agent-chat-002"}, json={"message": "Again", "conversation_id": conversation})
    execute(second.json()["run"]["id"], client.app.state.settings)
    assert seen[1]["history"][0]["content"] == {"conversation_id": conversation, "message": "Hi"}
    assert _library(client, workspace)["Concierge"]["published"]["chat_ready"] is True

    remembered = client.get(f"{base}/memory", params={"conversation_id": conversation}).json()
    assert remembered["conversations"] == 1 and [turn["role"] for turn in remembered["turns"]] == ["user", "assistant", "user", "assistant"]
    assert client.get(f"{base}/memory", params={"conversation_id": "unknown"}).json()["turns"] == []
    forgotten = client.request("DELETE", f"{base}/memory", headers=headers(client), params={"conversation_id": conversation})
    assert forgotten.status_code == 200 and forgotten.json()["deleted_turns"] == 4
    assert client.get(f"{base}/memory").json()["conversations"] == 0

    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace))
    member.role = "editor"
    db.commit()
    assert client.get(f"{base}/memory").status_code == 403


def test_chat_requires_a_chat_shaped_published_agent(client, owner, monkeypatch):
    workspace, _version = published_agent(client, owner, monkeypatch)
    agent_id = _library(client, workspace)["Triage"]["id"]
    refused = client.post(f"/api/v1/workspaces/{workspace}/agents/{agent_id}/chat", headers={**headers(client), "Idempotency-Key": "agent-chat-009"}, json={"message": "Hi"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "AGENT_NOT_CHAT"


def test_duplicate_and_save_examples(client, owner, monkeypatch):
    workspace, _version = published_agent(client, owner, monkeypatch)
    agent_id = _library(client, workspace)["Triage"]["id"]
    base = f"/api/v1/workspaces/{workspace}/agents/{agent_id}"
    copy = client.post(f"{base}/duplicate", headers=headers(client))
    assert copy.status_code == 201 and copy.json()["name"] == "Triage (copy)"
    assert set(_library(client, workspace)) == {"Triage", "Triage (copy)"}
    for index in range(2):
        saved = client.post(f"{base}/examples", headers=headers(client), json={"input": {"ticket": f"t{index}"}, "expected_output": {"priority": "urgent"}})
        assert saved.status_code == 201 and saved.json()["count"] == index + 1
    suites = client.get(f"{base}/evaluations").json()["items"]
    assert [suite["name"] for suite in suites] == ["Saved from chat"]
