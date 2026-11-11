import json

from sqlalchemy import select

from app.modules.agents.models import Agent, AgentVersion
from app.modules.executions.models import RunEvent
from app.modules.executions.runtime import execute
from tests.conftest import headers


def _connect(client, workspace, monkeypatch):
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"])
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client), json={"api_key": "sk-test-runtime-aaaaaaaaaaaaaaaa"})


def _skill(client, workspace, name="Brand voice", instructions="Write warmly.", tool_keys=None, publish=True):
    base = f"/api/v1/workspaces/{workspace}/skills"
    skill = client.post(base, headers=headers(client), json={"name": name, "description": "Use when writing for customers.", "config": {
        "instructions": instructions, "examples": [{"input": "hi", "output": "Hello there!"}], "tool_keys": tool_keys or [],
    }})
    assert skill.status_code == 201, skill.text
    if publish:
        published = client.post(f"{base}/{skill.json()['id']}/publish", headers=headers(client), json={"expected_revision": 1})
        assert published.status_code == 201, published.text
    return skill.json()


def _agent(client, workspace, skills):
    base = f"/api/v1/workspaces/{workspace}/agents"
    return client.post(base, headers=headers(client), json={"name": "Writer", "config": {
        "instructions": "Answer customers.", "model_id": "gpt-5-mini",
        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
        "output_schema": {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"], "additionalProperties": False},
        "skills": [{"skill_id": skill["id"], "name": skill["name"]} for skill in skills],
    }}).json()


def test_skill_drafts_versions_and_starters(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/skills"
    skill = _skill(client, workspace, publish=False)
    assert client.post(f"{base}/{skill['id']}/publish", headers=headers(client), json={"expected_revision": 1}).json()["number"] == 1
    again = client.post(f"{base}/{skill['id']}/publish", headers=headers(client), json={"expected_revision": 1}).json()
    assert again["number"] == 1 and again["created"] is False
    client.patch(f"{base}/{skill['id']}", headers=headers(client), json={"name": "Brand voice", "description": "", "config": {"instructions": "Write warmly and briefly."}, "expected_revision": 1})
    listed = {item["name"]: item for item in client.get(base).json()["items"]}
    assert listed["Brand voice"]["status"] == "changed" and listed["Brand voice"]["latest"]["number"] == 1
    assert client.post(f"{base}/{skill['id']}/publish", headers=headers(client), json={"expected_revision": 2}).json()["number"] == 2
    assert [item["number"] for item in client.get(f"{base}/{skill['id']}/versions").json()["items"]] == [2, 1]
    empty = client.post(base, headers=headers(client), json={"name": "Empty"}).json()
    refused = client.post(f"{base}/{empty['id']}/publish", headers=headers(client), json={"expected_revision": 1})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "SKILL_INSTRUCTIONS_REQUIRED"

    starters = client.get(f"{base}/starters").json()["items"]
    assert {item["group"] for item in starters} == {"Writing & tone", "Support", "Data & research", "Dev & GitHub"}
    added = client.post(f"{base}/starters/refund-policy", headers=headers(client))
    assert added.status_code == 201 and added.json()["status"] == "draft" and "30 days" in added.json()["config"]["instructions"]
    assert next(item for item in client.get(f"{base}/starters").json()["items"] if item["key"] == "refund-policy")["added"] is True


def test_publishing_an_agent_pins_skills_and_merges_their_tools(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect(client, workspace, monkeypatch)
    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    draft_only = _skill(client, workspace, name="Unpublished", publish=False)
    voice = _skill(client, workspace, tool_keys=["text.replace"])
    agent = _agent(client, workspace, [voice, draft_only])
    base = f"/api/v1/workspaces/{workspace}/agents/{agent['id']}"
    readiness = client.get(f"{base}/readiness").json()
    assert any(issue["section"] == "skills" and "Unpublished" in issue["message"] for issue in readiness["errors"])
    blocked = client.post(f"{base}/versions", headers=headers(client), json={"expected_revision": 1})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "SKILL_UNPUBLISHED"

    current = client.get(base).json()
    client.patch(base, headers=headers(client), json={"name": "Writer", "description": "", "expected_revision": 1,
                                                       "config": {**current["config"], "skills": [{"skill_id": voice["id"], "name": voice["name"]}]}})
    published = client.post(f"{base}/versions", headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text
    frozen = db.get(AgentVersion, published.json()["id"]).config
    assert frozen["skills"][0]["number"] == 1 and frozen["skills"][0]["instructions"] == "Write warmly."
    assert frozen["tool_keys"] == ["text.replace"] and frozen["skill_loading"] == "on_demand"
    library = client.get(f"/api/v1/workspaces/{workspace}/skills").json()["items"]
    assert next(item for item in library if item["name"] == "Brand voice")["used_by"] == ["Writer"]


def test_agents_load_skills_on_demand_and_keep_their_pinned_version(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect(client, workspace, monkeypatch)
    voice = _skill(client, workspace)
    agent = _agent(client, workspace, [voice])
    base = f"/api/v1/workspaces/{workspace}/agents/{agent['id']}"
    version = client.post(f"{base}/versions", headers=headers(client), json={"expected_revision": 1}).json()
    calls = []

    def model(_key, payload, _timeout, *_rest):
        calls.append(payload)
        if len(calls) % 2 == 1:
            return {"status": "completed", "usage": {"input_tokens": 10, "output_tokens": 2}, "output": [
                {"type": "function_call", "call_id": f"c{len(calls)}", "name": "use_skill", "arguments": json.dumps({"skill": "Brand voice"})},
            ]}
        return {"status": "completed", "usage": {"input_tokens": 12, "output_tokens": 3}, "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"reply": "Hello there!"})}]},
        ]}

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    submitted = client.post(f"/api/v1/workspaces/{workspace}/runs", headers={**headers(client), "Idempotency-Key": "skill-run-0001"},
                            json={"version_id": version["id"], "input": {"message": "hi"}})
    assert submitted.status_code == 202, submitted.text
    execute(submitted.json()["id"], client.app.state.settings)
    run = client.get(f"/api/v1/workspaces/{workspace}/runs/{submitted.json()['id']}").json()
    assert run["state"] == "completed" and run["output"] == {"reply": "Hello there!"}
    assert "Brand voice: Use when writing for customers." in calls[0]["instructions"] and "Write warmly." not in calls[0]["instructions"]
    assert any(tool["name"] == "use_skill" for tool in calls[0]["tools"])
    loaded = json.loads(calls[1]["input"][-1]["output"])
    assert loaded["instructions"] == "Write warmly." and loaded["examples"][0]["output"] == "Hello there!"
    keys = db.scalars(select(RunEvent.tool_key).where(RunEvent.run_id == submitted.json()["id"], RunEvent.kind == "tool")).all()
    assert "skill:Brand voice" in keys

    # A newer skill version reaches the live agent only after republishing; the playground uses it at once.
    skills = f"/api/v1/workspaces/{workspace}/skills/{voice['id']}"
    client.patch(skills, headers=headers(client), json={"name": "Brand voice", "description": "Use when writing for customers.", "config": {"instructions": "Write warmly, v2."}, "expected_revision": 1})
    client.post(f"{skills}/publish", headers=headers(client), json={"expected_revision": 2})
    assert db.get(AgentVersion, version["id"]).config["skills"][0]["number"] == 1
    draft = client.get(base).json()["config"]
    tried = client.post(f"{base}/try", headers={**headers(client), "Idempotency-Key": "skill-try-0001"}, json={"config": draft, "input": {"message": "hi"}})
    assert tried.status_code == 202, tried.text
    db.expire_all()
    twin_version = db.get(AgentVersion, tried.json()["run"]["version_id"])
    assert db.get(Agent, twin_version.agent_id).playground_for is not None
    assert twin_version.config["skills"][0]["instructions"] == "Write warmly, v2."


def test_llm_steps_pin_skills_when_the_workflow_is_published(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect(client, workspace, monkeypatch)
    voice = _skill(client, workspace)
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Reply"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {"id": "ask", "type": "llm", "label": "Reply", "position": {"x": 300, "y": 180}, "config": {
        "instructions": "Reply.", "provider": "openai", "model_id": "gpt-5-mini", "skills": [{"skill_id": voice["id"], "name": voice["name"]}],
    }})
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "ask", "pointer": ""}}
    graph["edges"] = [{"id": "a", "source": "input", "target": "ask"}, {"id": "b", "source": "ask", "target": "result"}]
    path = f"{base}/{workflow['id']}"
    client.patch(path, headers=headers(client), json={"name": "Reply", "expected_revision": 1, "graph": graph})
    published = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text
    managed = db.scalar(select(AgentVersion).join(Agent, Agent.id == AgentVersion.agent_id).where(Agent.node_id == "ask"))
    assert managed.config["skills"][0]["instructions"] == "Write warmly."
