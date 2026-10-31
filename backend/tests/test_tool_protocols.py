import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.modules.executions.runtime import ProviderFailure, generate_openai_with_tools


@pytest.mark.parametrize(
    "provider,model",
    [
        ("deepseek", "deepseek-flash"),
        ("anthropic", "claude-haiku-4-5"),
        ("openrouter", "openai/gpt-4o-mini"),
        ("gemini", "gemini-2.5-flash"),
    ],
)
def test_shared_tool_loop_preserves_provider_conversations(monkeypatch, provider, model):
    seen = []
    args = {"text": "hello world", "find": "world", "replacement": "FlowForge"}

    def respond(request):
        seen.append(json.loads(request.content))
        first = len(seen) == 1
        final = '{"priority":"normal"}'
        if provider == "deepseek":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "usage": {"input_tokens": 30, "output_tokens": 10},
                    "output": [
                        {
                            "type": "function_call",
                            "name": "text_replace",
                            "call_id": "t-1",
                            "arguments": json.dumps(args),
                        }
                    ]
                    if first
                    else [{"content": [{"type": "output_text", "text": final}]}],
                },
            )
        if provider == "anthropic":
            return httpx.Response(
                200,
                json={
                    "stop_reason": "tool_use" if first else "end_turn",
                    "usage": {"input_tokens": 30, "output_tokens": 10},
                    "content": [
                        {"type": "tool_use", "name": "text_replace", "id": "t-1", "input": args}
                    ]
                    if first
                    else [{"type": "text", "text": final}],
                },
            )
        if provider == "openrouter":
            return httpx.Response(
                200,
                json={
                    "usage": {"prompt_tokens": 30, "completion_tokens": 10},
                    "choices": [
                        {
                            "finish_reason": "tool_calls" if first else "stop",
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "t-1",
                                        "type": "function",
                                        "function": {
                                            "name": "text_replace",
                                            "arguments": json.dumps(args),
                                        },
                                    }
                                ]
                            }
                            if first
                            else {"content": final},
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 10},
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"functionCall": {"name": "text_replace", "args": args}}]
                            if first
                            else [{"text": final}]
                        },
                    }
                ],
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        "app.modules.executions.runtime.httpx.Client",
        lambda **kw: original(transport=httpx.MockTransport(respond), **kw),
    )
    monkeypatch.setattr("app.modules.executions.runtime._tool_approved", lambda *_: True)
    monkeypatch.setattr("app.modules.executions.runtime._provider_approved", lambda *_: True)
    version = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        config={
            "provider": provider,
            "model_id": model,
            "instructions": "Normalize then return priority.",
            "tool_keys": ["text.replace"],
            "output_schema": {
                "type": "object",
                "properties": {"priority": {"type": "string"}},
                "required": ["priority"],
                "additionalProperties": False,
            },
            "limits": {"max_iterations": 5, "max_tool_calls": 2, "max_cost_usd": "1.00"},
        },
    )
    output, inputs, outputs = generate_openai_with_tools(
        "test-key", version, {"ticket": "hello world"}, 256, 10, SimpleNamespace()
    )
    assert output == {"priority": "normal"}
    assert inputs == len(seen) * 30 and outputs == len(seen) * 10
    assert "hello FlowForge" in json.dumps(seen[1])
    if provider == "anthropic":
        assert seen[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    elif provider == "openrouter":
        assert seen[1]["messages"][-1]["role"] == "tool"
    elif provider == "gemini":
        assert len(seen) == 3
        assert "responseJsonSchema" not in seen[0]["generationConfig"]
        assert "tools" not in seen[-1]
        assert seen[-1]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_finalization_obeys_iteration_budget(monkeypatch):
    monkeypatch.setattr("app.modules.executions.runtime._provider_approved", lambda *_: True)
    from app.modules.executions import tool_protocols

    monkeypatch.setattr(
        tool_protocols,
        "roundtrip",
        lambda *args: {
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "output": [],
            "_needs_finalization": True,
        },
    )
    config = {
        "provider": "gemini",
        "model_id": "gemini-2.5-flash",
        "instructions": "Test",
        "tool_keys": ["text.replace"],
        "output_schema": {"type": "object"},
        "limits": {"max_iterations": 1, "max_tool_calls": 1, "max_cost_usd": "1.00"},
    }
    with pytest.raises(ProviderFailure) as error:
        generate_openai_with_tools(
            "key", SimpleNamespace(config=config), {}, 256, 10, SimpleNamespace()
        )
    assert error.value.code == "RUN_ITERATION_LIMIT"
