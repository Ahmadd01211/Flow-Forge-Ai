import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.modules.executions.runtime import ProviderFailure, generate
from app.modules.integrations.models import SecretReference
from app.modules.workspaces.models import WorkspaceMember
from app.providers import registry
from app.providers.profiles import RATES, capability
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent, submit
from tests.test_provider_connections import KEY_A, connect


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-5-nano"),
        ("openai", "gpt-5"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("anthropic", "claude-sonnet-4-6"),
    ],
)
def test_new_profile_can_publish_submit_and_complete(client, owner, monkeypatch, provider, model):
    from app.modules.executions.runtime import execute

    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda p, k: [model])
    assert (
        client.post(
            f"{base}/integrations/providers/{provider}",
            headers=headers(client),
            json={"api_key": KEY_A},
        ).status_code
        == 200
    )
    agent = client.post(
        f"{base}/agents",
        headers=headers(client),
        json={
            "name": "Profile test",
            "config": {
                "instructions": "Classify tickets.",
                "provider": provider,
                "model_id": model,
                "limits": {"max_cost_usd": "1.00"},
            },
        },
    ).json()
    version = client.post(
        f"{base}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    )
    assert version.status_code == 201, version.text
    run = submit(client, workspace, version.json())
    assert run.status_code == 202, run.text
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate",
        lambda key, version, data, limit, timeout: ({"priority": "urgent"}, 100, 20),
    )
    execute(run.json()["id"], client.app.state.settings)
    result = client.get(f"{base}/runs/{run.json()['id']}").json()
    assert result["state"] == "completed" and result["cost_usd"] is not None


def test_refresh_preserves_generation_and_secret_and_updates_capabilities(
    client, owner, db, monkeypatch
):
    models = ["gpt-5-mini", "gpt-5-nano", "embedding-model"]
    monkeypatch.setattr(
        "app.modules.integrations.service.verify_key", lambda provider, key: models.copy()
    )
    workspace = owner["workspaces"][0]["id"]
    original = connect(client, workspace).json()
    capabilities = original["model_capabilities"]
    assert capabilities["gpt-5-nano"]["runnable"] and capabilities["gpt-5-nano"]["local_tools"]
    assert not capabilities["embedding-model"]["runnable"]
    base = f"/api/v1/workspaces/{workspace}/integrations/providers/openai"
    client.patch(f"{base}/default-model", headers=headers(client), json={"model_id": "gpt-5-mini"})
    secret = db.scalar(select(SecretReference))
    ciphertext = secret.ciphertext
    models[:] = ["gpt-5-nano"]
    result = client.post(f"{base}/refresh-models", headers=headers(client))
    assert result.status_code == 200, result.text
    assert result.json()["default_model_id"] is None
    assert result.json()["credential_generation"] == original["credential_generation"]
    db.expire_all()
    assert db.scalar(select(SecretReference)).ciphertext == ciphertext
    assert KEY_A not in result.text


def test_failed_refresh_is_atomic_and_permission_protected(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda p, k: ["gpt-5-mini"])
    connect(client, workspace)
    base = f"/api/v1/workspaces/{workspace}/integrations"
    original = client.get(base).json()

    def failure(*args):
        raise HTTPException(503, {"code": "PROVIDER_UNAVAILABLE", "message": "Unavailable"})

    monkeypatch.setattr("app.modules.integrations.service.verify_key", failure)
    assert (
        client.post(f"{base}/providers/openai/refresh-models", headers=headers(client)).status_code
        == 503
    )
    assert client.get(base).json() == original
    assert client.post(f"{base}/providers/openai/refresh-models").status_code == 403


def test_refresh_removed_model_blocks_submissions(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda p, k: ["gpt-5-nano"])
    result = client.post(
        f"/api/v1/workspaces/{workspace}/integrations/providers/openai/refresh-models",
        headers=headers(client),
    )
    assert result.status_code == 200
    assert submit(client, workspace, version).status_code == 409


def test_refresh_cannot_be_used_by_editor_or_another_workspace(client, owner, db, monkeypatch):
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda p, k: ["gpt-5-mini"])
    workspace = owner["workspaces"][0]["id"]
    assert connect(client, workspace).status_code == 200
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    path = f"/api/v1/workspaces/{workspace}/integrations/providers/openai/refresh-models"
    assert client.post(path, headers=headers(client)).status_code == 403
    client.cookies.clear()
    register(client, "other-profile@example.com")
    assert client.post(path, headers=headers(client)).status_code == 404


@pytest.mark.parametrize("provider,model", RATES)
def test_every_runnable_profile_uses_its_exact_model_and_fixed_host(monkeypatch, provider, model):
    seen = []
    output = {"answer": "ok"}

    def respond(request):
        seen.append(request)
        if provider in {"openai", "deepseek"}:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "output": [{"content": [{"type": "output_text", "text": json.dumps(output)}]}],
                },
            )
        if provider == "anthropic":
            return httpx.Response(
                200,
                json={
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": [{"type": "text", "text": json.dumps(output)}],
                },
            )
        if provider == "openrouter":
            return httpx.Response(
                200,
                json={
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(output)}}
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output)}]}}
                ],
            },
        )

    real = httpx.Client
    monkeypatch.setattr(
        "app.modules.executions.runtime.httpx.Client",
        lambda **kw: real(transport=httpx.MockTransport(respond)),
    )
    version = SimpleNamespace(
        config={
            "provider": provider,
            "model_id": model,
            "instructions": "Answer in JSON",
            "output_schema": {"type": "object"},
        }
    )
    assert generate("test-key", version, {}, 100, 3) == (output, 10, 5)
    request = seen[0]
    if provider == "gemini":
        assert request.url.path.endswith(f"/{model}:generateContent")
    else:
        assert json.loads(request.content)["model"] == model
    assert request.url.host == httpx.URL(registry.PROVIDERS[provider][1]).host


def test_unknown_profile_never_dispatches():
    with pytest.raises(ProviderFailure) as error:
        generate(
            "never-send",
            SimpleNamespace(config={"provider": "gemini", "model_id": "../../malicious"}),
            {},
            100,
            3,
        )
    assert error.value.code == "RUNTIME_UNSUPPORTED"
    assert not capability("gemini", "../../malicious").runnable


@pytest.mark.parametrize("provider", ["anthropic", "gemini"])
def test_paginated_models_keep_fixed_host_and_collect_all_pages(monkeypatch, provider):
    seen = []

    def respond(request):
        seen.append(request)
        if provider == "anthropic":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "claude-haiku-4-5" if len(seen) == 1 else "claude-sonnet-4-6"}],
                    "has_more": len(seen) == 1,
                    "last_id": "https://untrusted.example/?cursor",
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.5-flash"
                        if len(seen) == 1
                        else "models/gemini-2.5-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ],
                **(
                    {"nextPageToken": "https://untrusted.example/?cursor"} if len(seen) == 1 else {}
                ),
            },
        )

    real = httpx.Client
    monkeypatch.setattr(
        registry.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(respond))
    )
    models = registry.verify_key(provider, "key")
    assert len(models) == 2 and len(seen) == 2
    assert all(r.url.host == httpx.URL(registry.PROVIDERS[provider][1]).host for r in seen)


def test_pagination_cycle_is_rejected(monkeypatch):
    real = httpx.Client

    def respond(request):
        return httpx.Response(
            200, json={"data": [{"id": "claude-haiku-4-5"}], "has_more": True, "last_id": "repeat"}
        )

    monkeypatch.setattr(
        registry.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(respond))
    )
    with pytest.raises(HTTPException):
        registry.verify_key("anthropic", "key")
