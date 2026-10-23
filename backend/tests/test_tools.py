import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.executions.runtime import ProviderFailure, execute, generate_openai_with_tools
from app.modules.tools.models import ToolInstallation
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def test_tool_approval_invocation_and_revoke(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/tools/json.extract"
    catalog = client.get(f"/api/v1/workspaces/{workspace}/tools").json()["items"]
    assert {item["key"] for item in catalog} == {"json.extract", "text.replace"}
    assert not any(item["installed"] for item in catalog)
    payload = {
        "input": {
            "document": {"customer": {"email": "a@example.com"}},
            "pointer": "/customer/email",
        }
    }
    assert client.post(f"{base}/test", headers=headers(client), json=payload).status_code == 403
    assert client.put(base, headers=headers(client)).status_code == 200
    assert db.scalar(select(ToolInstallation)).tool_key == "json.extract"
    result = client.post(f"{base}/test", headers=headers(client), json=payload)
    assert result.status_code == 200 and result.json() == {"output": {"value": "a@example.com"}}
    assert (
        client.post(
            f"{base}/test",
            headers=headers(client),
            json={"input": {"document": {}, "pointer": "/missing"}},
        ).status_code
        == 422
    )
    assert client.delete(base, headers=headers(client)).status_code == 200
    assert client.post(f"{base}/test", headers=headers(client), json=payload).status_code == 403
    assert {event.action for event in db.scalars(select(AuditEvent))} >= {
        "tool.installed",
        "tool.removed",
    }


def test_tool_roles_tenant_isolation_and_bounded_output(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/tools/text.replace"
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    assert client.put(base, headers=headers(client)).status_code == 403
    member.role = "owner"
    db.commit()
    assert client.put(base, headers=headers(client)).status_code == 200
    member.role = "editor"
    db.commit()
    response = client.post(
        f"{base}/test",
        headers=headers(client),
        json={"input": {"text": "a a", "find": "a", "replacement": "b"}},
    )
    assert response.json() == {"output": {"text": "b b"}}
    oversized = client.post(
        f"{base}/test",
        headers=headers(client),
        json={"input": {"text": "a" * 40000, "find": "a", "replacement": "bbb"}},
    )
    assert oversized.status_code == 422
    member.role = "viewer"
    db.commit()
    assert (
        client.post(
            f"{base}/test",
            headers=headers(client),
            json={"input": {"text": "x", "find": "x", "replacement": "y"}},
        ).status_code
        == 403
    )
    client.cookies.clear()
    register(client, "other-tools@example.com")
    assert client.get(f"/api/v1/workspaces/{workspace}/tools").status_code == 404
    assert client.put(base, headers=headers(client)).status_code == 404


def test_published_agent_grants_require_installation(client, owner, monkeypatch):
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    workspace = owner["workspaces"][0]["id"]
    client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai",
        headers=headers(client),
        json={"api_key": "sk-test-tool-aaaaaaaaaaaaaaaa"},
    )
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        headers=headers(client),
        json={
            "name": "Cleanup",
            "config": {
                "instructions": "Normalize names.",
                "model_id": "gpt-5-mini",
                "tool_keys": ["text.replace"],
            },
        },
    ).json()
    path = f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions"
    assert (
        client.post(path, headers=headers(client), json={"expected_revision": 1}).status_code == 409
    )
    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    published = client.post(path, headers=headers(client), json={"expected_revision": 1})
    assert published.status_code == 201 and published.json()["config"]["tool_keys"] == [
        "text.replace"
    ]
    client.delete(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    run = client.post(
        f"/api/v1/workspaces/{workspace}/runs",
        headers={**headers(client), "Idempotency-Key": "tool-run-123"},
        json={"version_id": published.json()["id"], "input": {"ticket": "Hello"}},
    )
    assert run.status_code == 409 and run.json()["error"]["code"] == "TOOL_APPROVAL_REVOKED"


@pytest.mark.parametrize("model_id", ["gpt-5-mini", "gpt-5-nano", "gpt-5"])
def test_openai_tool_loop_replays_call_and_counts_usage(monkeypatch, model_id):
    seen = []
    replies = [
        {
            "status": "completed",
            "usage": {"input_tokens": 40, "output_tokens": 10},
            "output": [
                {
                    "type": "function_call",
                    "name": "text_replace",
                    "call_id": "call-1",
                    "arguments": json.dumps(
                        {"text": "Hi Alex", "find": "Alex", "replacement": "team"}
                    ),
                }
            ],
        },
        {
            "status": "completed",
            "usage": {"input_tokens": 55, "output_tokens": 12},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
                }
            ],
        },
    ]

    def reply(_key, payload, _timeout):
        seen.append(payload)
        return replies.pop(0)

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", reply)
    monkeypatch.setattr("app.modules.executions.runtime._tool_approved", lambda *_: True)
    version = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        config={
            "instructions": "Normalize input.",
            "model_id": model_id,
            "tool_keys": ["text.replace"],
            "output_schema": {
                "type": "object",
                "properties": {"priority": {"type": "string"}},
                "required": ["priority"],
                "additionalProperties": False,
            },
            "limits": {"max_iterations": 4, "max_tool_calls": 2, "max_cost_usd": "0.10"},
        },
    )
    assert generate_openai_with_tools(
        "key", version, {"ticket": "Hi Alex"}, 512, 10, SimpleNamespace()
    ) == ({"priority": "normal"}, 95, 22)
    assert seen[0]["store"] is False and seen[0]["parallel_tool_calls"] is False
    assert seen[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"text": "Hi team"}',
    }


def test_openai_tool_loop_rechecks_approval(monkeypatch):
    monkeypatch.setattr(
        "app.modules.executions.runtime._openai_response",
        lambda *_: {
            "status": "completed",
            "usage": {"input_tokens": 40, "output_tokens": 10},
            "output": [
                {
                    "type": "function_call",
                    "name": "text_replace",
                    "call_id": "call-1",
                    "arguments": "{}",
                }
            ],
        },
    )
    monkeypatch.setattr("app.modules.executions.runtime._tool_approved", lambda *_: False)
    version = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        config={
            "instructions": "Normalize.",
            "model_id": "gpt-5-mini",
            "tool_keys": ["text.replace"],
            "output_schema": {"type": "object"},
            "limits": {"max_iterations": 2, "max_tool_calls": 1, "max_cost_usd": "0.10"},
        },
    )
    with pytest.raises(ProviderFailure) as error:
        generate_openai_with_tools("key", version, {}, 128, 10, SimpleNamespace())
    assert error.value.code == "TOOL_APPROVAL_REVOKED"


def test_worker_executes_published_tool_grant(client, owner, monkeypatch):
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    workspace = owner["workspaces"][0]["id"]
    client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai",
        headers=headers(client),
        json={"api_key": "sk-test-tool-bbbbbbbbbbbbbbbb"},
    )
    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        headers=headers(client),
        json={
            "name": "Cleanup",
            "config": {
                "instructions": "Normalize names.",
                "model_id": "gpt-5-mini",
                "tool_keys": ["text.replace"],
            },
        },
    ).json()
    version = client.post(
        f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    ).json()
    run = client.post(
        f"/api/v1/workspaces/{workspace}/runs",
        headers={**headers(client), "Idempotency-Key": "tool-run-456"},
        json={"version_id": version["id"], "input": {"ticket": "Hi Alex"}},
    ).json()
    replies = [
        {
            "status": "completed",
            "usage": {"input_tokens": 40, "output_tokens": 10},
            "output": [
                {
                    "type": "function_call",
                    "name": "text_replace",
                    "call_id": "call-1",
                    "arguments": json.dumps(
                        {"text": "Hi Alex", "find": "Alex", "replacement": "team"}
                    ),
                }
            ],
        },
        {
            "status": "completed",
            "usage": {"input_tokens": 55, "output_tokens": 12},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"priority":"normal"}'}],
                }
            ],
        },
    ]
    monkeypatch.setattr(
        "app.modules.executions.runtime._openai_response", lambda *_: replies.pop(0)
    )
    execute(run["id"], client.app.state.settings)
    result = client.get(f"/api/v1/workspaces/{workspace}/runs/{run['id']}").json()
    assert result["state"] == "completed" and result["output"] == {"priority": "normal"}
    assert result["input_tokens"] == 95 and result["output_tokens"] == 22
    trace = client.get(f"/api/v1/workspaces/{workspace}/runs/{run['id']}/events").json()["items"]
    assert [(item["kind"], item["status"]) for item in trace] == [
        ("run", "started"),
        ("model", "started"),
        ("model", "completed"),
        ("tool", "started"),
        ("tool", "completed"),
        ("model", "started"),
        ("model", "completed"),
        ("run", "completed"),
    ]
    assert all("Hi Alex" not in json.dumps(item) for item in trace)
    client.cookies.clear()
    register(client, "other-trace@example.com")
    assert client.get(f"/api/v1/workspaces/{workspace}/runs/{run['id']}/events").status_code == 404
