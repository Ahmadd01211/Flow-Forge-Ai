import json

from sqlalchemy import select

from app.modules.agents.models import Agent, AgentVersion
from app.modules.workflows.runtime import execute
from tests.conftest import headers


def _connect_openai(client, workspace, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"]
    )
    response = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai",
        headers=headers(client),
        json={"api_key": "sk-test-runtime-aaaaaaaaaaaaaaaa"},
    )
    assert response.status_code in (200, 201), response.text


def _llm_workflow(client, workspace, config):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Answer questions"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {
        "id": "ask", "type": "llm", "label": "Answer", "position": {"x": 300, "y": 180}, "config": config,
    })
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "ask", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-ask", "source": "input", "target": "ask"},
        {"id": "ask-result", "source": "ask", "target": "result"},
    ]
    path = f"{base}/{workflow['id']}"
    saved = client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph})
    assert saved.status_code == 200, saved.text
    return path, graph


def test_draft_llm_step_reports_readiness_against_inspector_fields(client, owner):
    workspace = owner["workspaces"][0]["id"]
    path, graph = _llm_workflow(client, workspace, {"instructions": "Answer briefly.", "provider": "openai", "model_id": "gpt-5-mini"})
    checked = client.post(f"{path}/check", headers=headers(client), json={"graph": graph}).json()
    errors = [(e["code"], e["path"]) for e in checked["errors"] if e["node_id"] == "ask"]
    assert errors == [("PROVIDER_REQUIRED", "config.model_id")]
    graph["nodes"][1]["config"] = {"provider": "openai"}
    checked = client.post(f"{path}/check", headers=headers(client), json={"graph": graph}).json()
    assert {e["path"] for e in checked["errors"] if e["node_id"] == "ask"} == {"config.instructions", "config.model_id"}


def test_llm_step_publishes_a_hidden_agent_and_runs_like_an_agent(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    path, graph = _llm_workflow(client, workspace, {"instructions": "Answer briefly.", "provider": "openai", "model_id": "gpt-5-mini"})
    checked = client.post(f"{path}/validate", headers=headers(client), json={"expected_revision": 2})
    assert checked.status_code == 200 and checked.json()["publishable"], checked.text
    published = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text

    managed = db.scalar(select(Agent).where(Agent.node_id == "ask"))
    assert managed is not None and str(managed.workflow_id) == path.rsplit("/", 1)[1]
    version = db.scalar(select(AgentVersion).where(AgentVersion.agent_id == managed.id))
    assert version.purpose == "published" and version.config["input_schema"] == {"type": "object"}
    assert version.config["output_schema"]["required"] == ["reply"]
    # The hidden agent never appears among user-built agents or as a pickable agent version.
    agents = client.get(f"/api/v1/workspaces/{workspace}/agents").json()["items"]
    assert all(item["id"] != str(managed.id) for item in agents)
    options = client.get(f"/api/v1/workspaces/{workspace}/agents/workflow-options").json()["items"]
    assert all(item["id"] != str(version.id) for item in options)
    assert client.get(f"/api/v1/workspaces/{workspace}/agents/{managed.id}").status_code == 404

    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    queued = client.post(runs, headers={**headers(client), "Idempotency-Key": "llm-flow-0001"}, json={
        "version_id": published.json()["id"], "input": {"question": "What is FlowForge?"},
    })
    assert queued.status_code == 202, queued.text
    seen = []
    monkeypatch.setattr("app.modules.workflows.runtime.generate", lambda _key, frozen, data, *_rest: seen.append((frozen.id, data)) or ({"reply": "A workflow builder."}, 40, 8))
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"{runs}/{queued.json()['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"reply": "A workflow builder."}, result
    assert seen == [(version.id, {"question": "What is FlowForge?"})]
    assert result["cost_usd"] is not None


def test_republishing_reuses_identical_settings_and_freezes_changes(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    path, graph = _llm_workflow(client, workspace, {"instructions": "Answer briefly.", "provider": "openai", "model_id": "gpt-5-mini"})
    first = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2}).json()
    graph["nodes"][0]["label"] = "Question"
    client.patch(path, headers=headers(client), json={"name": "Answer questions", "expected_revision": 2, "graph": graph})
    second = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 3}).json()
    graph["nodes"][1]["config"]["instructions"] = "Answer in one sentence."
    client.patch(path, headers=headers(client), json={"name": "Answer questions", "expected_revision": 3, "graph": graph})
    third = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 4}).json()

    def pinned(version):
        row = client.get(f"{path}/versions").json()["items"]
        assert any(item["id"] == version["id"] for item in row)
        from app.modules.workflows.models import WorkflowVersion
        db.expire_all()
        frozen = db.get(WorkflowVersion, version["id"])
        return next(node for node in frozen.graph["nodes"] if node["id"] == "ask")["config"]["version_id"]

    assert pinned(first) == pinned(second) != pinned(third)
    assert db.scalar(select(AgentVersion).where(AgentVersion.id == pinned(third))).config["instructions"] == "Answer in one sentence."


def test_llm_node_test_becomes_a_budgeted_agent_run(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    path, graph = _llm_workflow(client, workspace, {"instructions": "Answer briefly.", "provider": "openai", "model_id": "gpt-5-mini"})
    body = {"graph": graph, "input": {"question": "Hi"}}
    unconfirmed = client.post(f"{path}/nodes/ask/test", headers={**headers(client), "Idempotency-Key": "llm-test-0001"}, json=body)
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "EXTERNAL_TEST_UNCONFIRMED"
    queued = client.post(f"{path}/nodes/ask/test", headers={**headers(client), "Idempotency-Key": "llm-test-0001"}, json={**body, "confirm_external": True})
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued" and queued.json()["agent_run"]["state"] == "queued"


def test_llm_memory_carries_a_bounded_encrypted_conversation(client, owner, db, monkeypatch):
    from app.modules.agents.models import ConversationTurn

    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    path, _ = _llm_workflow(client, workspace, {
        "instructions": "Chat helpfully.", "provider": "openai", "model_id": "gpt-5-mini",
        "memory": {"key_pointer": "/conversation_id", "max_turns": 2, "retention_days": 7},
    })
    published = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2}).json()
    seen = []
    monkeypatch.setattr(
        "app.modules.workflows.runtime.generate",
        lambda _key, _version, data, *_rest: seen.append(data) or ({"reply": f"answer {len(seen)}"}, 10, 2),
    )
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"

    def run(conversation, message, key):
        queued = client.post(runs, headers={**headers(client), "Idempotency-Key": key}, json={
            "version_id": published["id"], "input": {"conversation_id": conversation, "message": message},
        }).json()
        execute(queued["id"], client.app.state.settings)
        return client.get(f"{runs}/{queued['id']}").json()

    assert run("c-1", "hi", "memory-run-001")["state"] == "completed"
    assert seen[-1] == {"history": [], "input": {"conversation_id": "c-1", "message": "hi"}}
    run("c-1", "and then?", "memory-run-002")
    assert [turn["role"] for turn in seen[-1]["history"]] == ["user", "assistant"]
    assert seen[-1]["history"][1]["content"] == {"reply": "answer 1"}
    run("c-1", "third", "memory-run-003")
    run("c-1", "fourth", "memory-run-004")
    # A two-exchange window: the oldest exchange has been dropped.
    assert [turn["content"] for turn in seen[-1]["history"][::2]] == [
        {"conversation_id": "c-1", "message": "and then?"}, {"conversation_id": "c-1", "message": "third"},
    ]
    run("c-2", "separate", "memory-run-005")
    assert seen[-1]["history"] == []
    missing = run(None, "no id", "memory-run-006")
    assert missing["state"] == "failed" and missing["error_code"] == "MEMORY_KEY_MISSING"

    db.expire_all()
    stored = db.scalars(select(ConversationTurn)).all()
    assert len(stored) == 6  # c-1 window of 4 turns plus c-2's 2.
    assert all(b"and then?" not in row.ciphertext and b"c-1" not in row.conversation_hash.encode() for row in stored)


def test_standalone_agent_runs_use_memory_too(client, owner, monkeypatch):
    from app.modules.executions.runtime import execute as execute_agent

    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"])
    workspace = owner["workspaces"][0]["id"]
    client.post(f"/api/v1/workspaces/{workspace}/integrations/providers/openai", headers=headers(client), json={"api_key": "sk-test-runtime-aaaaaaaaaaaaaaaa"})
    base = f"/api/v1/workspaces/{workspace}/agents"
    agent = client.post(base, headers=headers(client), json={"name": "Concierge", "config": {
        "instructions": "Chat.", "model_id": "gpt-5-mini",
        "input_schema": {"type": "object", "properties": {"chat": {"type": "string"}, "text": {"type": "string"}}, "required": ["chat", "text"], "additionalProperties": False},
        "output_schema": {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"], "additionalProperties": False},
        "memory": {"key_pointer": "/chat", "max_turns": 5, "retention_days": 30},
    }}).json()
    version = client.post(f"{base}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    assert version.status_code == 201, version.text
    seen = []
    monkeypatch.setattr("app.modules.executions.runtime.generate", lambda _key, _version, data, *_rest: seen.append(data) or ({"reply": "ok"}, 5, 1))
    for index, text in enumerate(["first", "second"]):
        submitted = client.post(f"/api/v1/workspaces/{workspace}/runs", headers={**headers(client), "Idempotency-Key": f"agent-memory-{index:04d}"}, json={
            "version_id": version.json()["id"], "input": {"chat": "abc", "text": text},
        })
        assert submitted.status_code == 202, submitted.text
        execute_agent(submitted.json()["id"], client.app.state.settings)
    assert seen[0]["history"] == [] and seen[1]["history"][0]["content"] == {"chat": "abc", "text": "first"}


def _publish_child(client, workspace, name, nodes, edges, input_schema=None):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": name}).json()
    graph = workflow["graph"]
    graph["nodes"] = [graph["nodes"][0], *nodes, {**graph["nodes"][-1], "config": {}}]
    graph["edges"] = edges
    if input_schema:
        graph["input_schema"] = input_schema
    path = f"{base}/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": name, "expected_revision": 1, "graph": graph}).status_code == 200
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    return version.json()


def _model_calling(tool_name, arguments, final):
    calls = []

    def model(_key, payload, _timeout, *_rest):
        calls.append(payload)
        if len(calls) == 1:
            return {"status": "completed", "usage": {"input_tokens": 20, "output_tokens": 5}, "output": [
                {"type": "function_call", "call_id": "call-1", "name": tool_name, "arguments": json.dumps(arguments)},
            ]}
        return {"status": "completed", "usage": {"input_tokens": 30, "output_tokens": 6}, "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(final)}]},
        ]}

    return model, calls


def test_llm_runs_a_published_workflow_as_a_tool(client, owner, db, monkeypatch):
    from app.modules.workflows.models import WorkflowCheckpoint
    from app.modules.workflows.tools import alias

    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    child = _publish_child(
        client, workspace, "Look up order",
        [{"id": "shape", "type": "transform", "label": "Shape", "position": {"x": 200, "y": 0},
          "config": {"fields": {"status": {"kind": "literal", "value": "shipped"}, "order": {"kind": "input", "pointer": "/order_id"}}}}],
        [{"id": "a", "source": "input", "target": "shape"}, {"id": "b", "source": "shape", "target": "result"}],
        {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"], "additionalProperties": False},
    )
    path, _ = _llm_workflow(client, workspace, {
        "instructions": "Look up orders when asked.", "provider": "openai", "model_id": "gpt-5-mini",
        "workflow_tools": [{"version_id": child["id"], "name": "Look up order", "description": "Find an order's status."}],
    })
    published = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text
    managed = db.scalar(select(AgentVersion).join(Agent, Agent.id == AgentVersion.agent_id).where(Agent.node_id == "ask"))
    grant = managed.config["workflow_tools"][0]
    assert grant["graph_hash"] and grant["input_schema"]["required"] == ["order_id"] and grant["has_external"] is False

    model, calls = _model_calling(alias(grant), {"order_id": "A-17"}, {"reply": "Order A-17 has shipped."})
    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    queued = client.post(runs, headers={**headers(client), "Idempotency-Key": "llm-tool-run-01"}, json={
        "version_id": published.json()["id"], "input": {"question": "Where is A-17?"},
    }).json()
    execute(queued["id"], client.app.state.settings)
    result = client.get(f"{runs}/{queued['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"reply": "Order A-17 has shipped."}, result
    assert any(tool["name"] == alias(grant) for tool in calls[0]["tools"])
    returned = json.loads(calls[1]["input"][-1]["output"])
    assert returned == {"output": {"status": "shipped", "order": "A-17"}}
    # The child ran inside the parent run, leaving checkpoint evidence under the LLM step.
    db.expire_all()
    assert db.query(WorkflowCheckpoint).filter(WorkflowCheckpoint.run_id == queued["id"]).count() >= 5


def test_workflow_tools_must_be_model_free_and_pause_free(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    model_child = _publish_child(
        client, workspace, "Has a model",
        [{"id": "think", "type": "llm", "label": "Think", "position": {"x": 200, "y": 0},
          "config": {"instructions": "Think.", "provider": "openai", "model_id": "gpt-5-mini"}}],
        [{"id": "a", "source": "input", "target": "think"}, {"id": "b", "source": "think", "target": "result"}],
    )
    path, graph = _llm_workflow(client, workspace, {
        "instructions": "Use tools.", "provider": "openai", "model_id": "gpt-5-mini",
        "workflow_tools": [{"version_id": model_child["id"], "name": "Think"}],
    })
    checked = client.post(f"{path}/check", headers=headers(client), json={"graph": graph}).json()
    assert ("WORKFLOW_TOOL_UNSUPPORTED", "config.model_id") in {(e["code"], e["path"]) for e in checked["errors"]}


def test_chat_trigger_continues_a_conversation_through_llm_memory(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _connect_openai(client, workspace, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Support chat"}).json()
    path = f"{base}/{workflow['id']}"
    send = lambda message, key, conversation=None: client.post(  # noqa: E731
        f"{path}/chat", headers={**headers(client), "Idempotency-Key": key},
        json={"message": message, **({"conversation_id": conversation} if conversation else {})},
    )
    assert send("hi", "chat-msg-0000").json()["error"]["code"] == "CHAT_NOT_PUBLISHED"

    graph = workflow["graph"]
    graph["nodes"][0].update(type="chat_trigger", label="Chat message")
    graph["nodes"].insert(1, {"id": "ask", "type": "llm", "label": "Reply", "position": {"x": 300, "y": 180}, "config": {
        "instructions": "Help the customer.", "provider": "openai", "model_id": "gpt-5-mini", "memory": {"key_pointer": "/conversation_id"},
    }})
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "ask", "pointer": ""}}
    graph["edges"] = [{"id": "a", "source": "input", "target": "ask"}, {"id": "b", "source": "ask", "target": "result"}]
    graph["input_schema"] = {"type": "object", "properties": {"ticket": {"type": "string"}}, "required": ["ticket"]}
    checked = client.post(f"{path}/check", headers=headers(client), json={"graph": graph}).json()
    assert ("CHAT_INPUT_INCOMPATIBLE", "input_schema") in {(e["code"], e["path"]) for e in checked["errors"]}
    graph["input_schema"] = {"type": "object"}
    assert client.patch(path, headers=headers(client), json={"name": "Support chat", "expected_revision": 1, "graph": graph}).status_code == 200
    assert client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2}).status_code == 201

    seen = []
    monkeypatch.setattr("app.modules.workflows.runtime.generate", lambda _key, _version, data, *_rest: seen.append(data) or ({"reply": f"reply {len(seen)}"}, 10, 2))
    first = send("Where is my order?", "chat-msg-0001")
    assert first.status_code == 202, first.text
    conversation = first.json()["conversation_id"]
    execute(first.json()["run"]["id"], client.app.state.settings)
    second = send("It was A-17", "chat-msg-0002", conversation)
    execute(second.json()["run"]["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{second.json()['run']['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"reply": "reply 2"}
    assert seen[1]["input"] == {"conversation_id": conversation, "message": "It was A-17"}
    assert [turn["content"] for turn in seen[1]["history"]] == [
        {"conversation_id": conversation, "message": "Where is my order?"}, {"reply": "reply 1"},
    ]
    other = client.post(base, headers=headers(client), json={"name": "Not chat"}).json()
    client.post(f"{base}/{other['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    refused = client.post(f"{base}/{other['id']}/chat", headers={**headers(client), "Idempotency-Key": "chat-msg-0003"}, json={"message": "hi"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "CHAT_TRIGGER_REQUIRED"
