import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from app.modules.executions import worker
from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import (
    ProviderFailure,
    execute,
    generate_anthropic,
    generate_gemini,
    generate_openrouter,
)
from tests.conftest import headers, register


def published_agent(client, owner, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda _provider, _key: ["gpt-5-mini"]
    )
    workspace = owner["workspaces"][0]["id"]
    client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai",
        headers=headers(client),
        json={"api_key": "sk-test-runtime-aaaaaaaaaaaaaaaa"},
    )
    base = f"/api/v1/workspaces/{workspace}/agents"
    agent = client.post(
        base,
        headers=headers(client),
        json={
            "name": "Triage",
            "config": {"instructions": "Classify support tickets.", "model_id": "gpt-5-mini"},
        },
    ).json()
    version = client.post(
        f"{base}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()
    return workspace, version


def submit(client, workspace, version, key="run-request-001", value="urgent"):
    return client.post(
        f"/api/v1/workspaces/{workspace}/runs",
        headers={**headers(client), "Idempotency-Key": key},
        json={"version_id": version["id"], "input": {"ticket": value}},
    )


def test_run_is_encrypted_idempotent_and_completes_from_real_worker_path(
    client, owner, db, monkeypatch
):
    workspace, version = published_agent(client, owner, monkeypatch)
    created = submit(client, workspace, version)
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    row = db.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    assert b"urgent" not in row.input_ciphertext
    assert submit(client, workspace, version).status_code == 200
    assert submit(client, workspace, version, value="normal").status_code == 409
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate",
        lambda _key, _version, _input, _max_tokens, _timeout: ({"priority": "urgent"}, 100, 20),
    )
    execute(run_id, client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{run_id}")
    assert result.status_code == 200 and result.json()["state"] == "completed"
    assert result.json()["output"] == {"priority": "urgent"}
    assert result.json()["cost_usd"] is not None
    db.expire_all()
    assert (
        b"urgent"
        not in db.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id))).output_ciphertext
    )
    execute(run_id, client.app.state.settings)
    assert client.get(f"/api/v1/workspaces/{workspace}/runs").json()["items"][0]["id"] == run_id


def test_published_deepseek_agent_uses_scoped_response_adapter(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda provider, key: ["deepseek-flash"]
    )
    connected = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/deepseek",
        headers=headers(client),
        json={"api_key": "sk-deepseek-test-aaaaaaaaaaaaaaaa"},
    )
    assert connected.status_code == 200, connected.text
    base = f"/api/v1/workspaces/{workspace}/agents"
    agent = client.post(
        base,
        headers=headers(client),
        json={
            "name": "DeepSeek triage",
            "config": {
                "provider": "deepseek",
                "model_id": "deepseek-flash",
                "instructions": "Return JSON with priority.",
            },
        },
    ).json()
    version = client.post(
        f"{base}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1}
    )
    assert version.status_code == 201, version.text
    run = submit(client, workspace, version.json(), key="deepseek-run-001")
    assert run.status_code == 202, run.text
    calls = []

    def fake_response(key, payload, timeout, url):
        calls.append((payload, url))
        assert key == "sk-deepseek-test-aaaaaaaaaaaaaaaa"
        return {
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 25},
            "output": [{"content": [{"type": "output_text", "text": '{"priority":"urgent"}'}]}],
        }

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", fake_response)
    execute(run.json()["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{run.json()['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"priority": "urgent"}
    assert result["input_tokens"] == 100 and result["output_tokens"] == 25
    assert calls[0][1] == "https://api.deepseek.com/responses"
    assert calls[0][0]["model"] == "deepseek-flash"
    assert calls[0][0]["text"]["format"]["type"] == "json_schema"


def test_claude_adapter_uses_fixed_host_and_structured_output(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 52, "output_tokens": 13},
                "content": [{"type": "text", "text": '{"priority":"urgent"}'}],
            },
        )

    original_client = httpx.Client
    monkeypatch.setattr(
        "app.modules.executions.runtime.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    version = SimpleNamespace(
        config={
            "model_id": "claude-haiku-4-5",
            "instructions": "Classify tickets.",
            "output_schema": {
                "type": "object",
                "required": ["priority"],
                "properties": {"priority": {"type": "string", "enum": ["urgent", "normal"]}},
                "additionalProperties": False,
            },
        }
    )
    output, input_tokens, output_tokens = generate_anthropic(
        "test-key", version, {"ticket": "Outage"}, 128, 10
    )
    assert (output, input_tokens, output_tokens) == ({"priority": "urgent"}, 52, 13)
    assert requests[0].url.host == "api.anthropic.com"
    assert requests[0].headers["x-api-key"] == "test-key"
    payload = json.loads(requests[0].read())
    assert payload["output_config"]["format"]["type"] == "json_schema"


def test_published_claude_agent_can_run(client, owner, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key",
        lambda _provider, _key: ["claude-haiku-4-5"],
    )
    workspace = owner["workspaces"][0]["id"]
    connected = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/anthropic",
        headers=headers(client),
        json={"api_key": "sk-ant-test-aaaaaaaaaaaaaaaa"},
    )
    assert connected.status_code == 200, connected.text
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        headers=headers(client),
        json={
            "name": "Claude triage",
            "config": {
                "provider": "anthropic",
                "model_id": "claude-haiku-4-5",
                "instructions": "Classify tickets.",
            },
        },
    ).json()
    version = client.post(
        f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    ).json()
    queued = submit(client, workspace, version, key="run-claude-001")
    assert queued.status_code == 202, queued.text
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate_anthropic",
        lambda *_args: ({"priority": "urgent"}, 52, 13),
    )
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{queued.json()['id']}")
    assert result.json()["state"] == "completed"
    assert result.json()["output"] == {"priority": "urgent"}


def test_openrouter_adapter_requires_structured_output_provider(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"priority":"urgent"}'}}
                ],
                "usage": {"prompt_tokens": 48, "completion_tokens": 12},
            },
        )

    original_client = httpx.Client
    monkeypatch.setattr(
        "app.modules.executions.runtime.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    version = SimpleNamespace(
        config={
            "model_id": "openai/gpt-4o-mini",
            "instructions": "Classify tickets.",
            "output_schema": {
                "type": "object",
                "required": ["priority"],
                "properties": {"priority": {"type": "string", "enum": ["urgent", "normal"]}},
                "additionalProperties": False,
            },
        }
    )
    result = generate_openrouter("test-key", version, {"ticket": "Outage"}, 128, 10)
    assert result == ({"priority": "urgent"}, 48, 12)
    assert requests[0].url.host == "openrouter.ai"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].read())
    assert payload["provider"] == {"require_parameters": True}
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_published_openrouter_agent_can_run(client, owner, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key",
        lambda _provider, _key: ["openai/gpt-4o-mini"],
    )
    workspace = owner["workspaces"][0]["id"]
    connected = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openrouter",
        headers=headers(client),
        json={"api_key": "sk-or-test-aaaaaaaaaaaaaaaa"},
    )
    assert connected.status_code == 200, connected.text
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        headers=headers(client),
        json={
            "name": "OpenRouter triage",
            "config": {
                "provider": "openrouter",
                "model_id": "openai/gpt-4o-mini",
                "instructions": "Classify tickets.",
            },
        },
    ).json()
    version = client.post(
        f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    ).json()
    queued = submit(client, workspace, version, key="run-openrouter-001")
    assert queued.status_code == 202, queued.text
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate_openrouter",
        lambda *_args: ({"priority": "urgent"}, 48, 12),
    )
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{queued.json()['id']}")
    assert result.json()["state"] == "completed"
    assert result.json()["output"] == {"priority": "urgent"}


def test_queued_cancel_and_uncertain_provider_outcome(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    first = submit(client, workspace, version, key="run-cancel-001").json()
    cancelled = client.post(
        f"/api/v1/workspaces/{workspace}/runs/{first['id']}/cancel", headers=headers(client)
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    execute(first["id"], client.app.state.settings)
    assert (
        client.get(f"/api/v1/workspaces/{workspace}/runs/{first['id']}").json()["state"]
        == "cancelled"
    )
    second = submit(client, workspace, version, key="run-unknown-001").json()

    def unknown(*_args):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)

    monkeypatch.setattr("app.modules.executions.runtime.generate", unknown)
    execute(second["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{second['id']}").json()
    assert result["state"] == "failed" and result["error_code"] == "PROVIDER_OUTCOME_UNKNOWN"
    assert result["uncertain_cost_usd"] == result["reserved_max_usd"]


def test_tenant_cannot_see_or_cancel_run(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    run = submit(client, workspace, version).json()
    client.cookies.clear()
    register(client, "other-runs@example.com")
    path = f"/api/v1/workspaces/{workspace}/runs/{run['id']}"
    assert client.get(path).status_code == 404
    assert client.post(f"{path}/cancel", headers=headers(client)).status_code == 404


def test_crashed_worker_before_provider_call_is_requeued(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    run_id = uuid.UUID(submit(client, workspace, version, key="run-recover-001").json()["id"])
    row = db.scalar(select(AgentRun).where(AgentRun.id == run_id))
    row.state = "running"
    row.started_at = datetime.now(UTC) - timedelta(seconds=46)
    row.claim_token = uuid.uuid4()
    db.commit()
    monkeypatch.setattr(worker, "settings", client.app.state.settings)
    dispatched = []
    monkeypatch.setattr(worker.celery, "send_task", lambda *args, **kwargs: dispatched.append(args))
    worker.reconcile_once()
    db.refresh(row)
    assert row.state == "queued" and row.claim_token is None
    worker.reconcile_once()
    assert dispatched == [("flowforge.execute_agent",)]


def test_gemini_adapter_uses_fixed_host_and_validates_structured_output(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"priority":"urgent"}'}]},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 50,
                    "candidatesTokenCount": 12,
                    "thoughtsTokenCount": 3,
                },
            },
        )

    original_client = httpx.Client
    monkeypatch.setattr(
        "app.modules.executions.runtime.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    version = SimpleNamespace(
        config={
            "instructions": "Classify tickets.",
            "model_id": "gemini-2.5-flash",
            "output_schema": {
                "type": "object",
                "required": ["priority"],
                "properties": {"priority": {"type": "string", "enum": ["urgent", "normal"]}},
                "additionalProperties": False,
            },
        }
    )
    output, input_tokens, output_tokens = generate_gemini(
        "test-key", version, {"ticket": "Outage"}, 128, 10
    )
    assert (output, input_tokens, output_tokens) == ({"priority": "urgent"}, 50, 15)
    assert requests[0].url.host == "generativelanguage.googleapis.com"
    assert requests[0].headers["x-goog-api-key"] == "test-key"
    assert requests[0].read().decode().find('"thinkingBudget":0') > 0


def test_published_gemini_agent_can_run(client, owner, monkeypatch):
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key",
        lambda _provider, _key: ["gemini-2.5-flash"],
    )
    workspace = owner["workspaces"][0]["id"]
    connected = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/gemini",
        headers=headers(client),
        json={"api_key": "gemini-test-key-aaaaaaaaaaaaaaaa"},
    )
    assert connected.status_code in (200, 201)
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        headers=headers(client),
        json={
            "name": "Triage",
            "config": {
                "provider": "gemini",
                "model_id": "gemini-2.5-flash",
                "instructions": "Classify tickets.",
            },
        },
    ).json()
    version = client.post(
        f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    ).json()
    queued = submit(client, workspace, version, key="run-gemini-001")
    assert queued.status_code == 202, queued.text
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate_gemini",
        lambda *_args: ({"priority": "urgent"}, 50, 15),
    )
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{queued.json()['id']}")
    assert result.json()["state"] == "completed"
    assert result.json()["output"] == {"priority": "urgent"}
