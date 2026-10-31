"""Provider wire formats around the same bounded, permission-checked tool loop."""

import json

import httpx


def request_json(url, headers, body, timeout):
    from app.modules.executions.runtime import MAX_RESPONSE_BYTES, ProviderFailure

    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code in (400, 401, 402, 403, 404, 422, 429):
                    raise ProviderFailure("PROVIDER_REJECTED")
                if response.status_code != 200:
                    raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
        result = json.loads(chunks)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (httpx.HTTPError, ValueError, TypeError):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None


def transcript_messages(items, provider):
    messages = []
    for item in items:
        if item.get("role") == "user":
            messages.append({"role": "user", "content": item["content"]})
        elif item.get("type") == "function_call":
            if provider == "anthropic":
                messages.append(
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": item["call_id"],
                                "name": item["name"],
                                "input": json.loads(item["arguments"]),
                            }
                        ],
                    }
                )
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {"name": item["name"], "arguments": item["arguments"]},
                            }
                        ],
                    }
                )
        elif item.get("type") == "function_call_output":
            if provider == "anthropic":
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": item["call_id"],
                                "content": item["output"],
                            }
                        ],
                    }
                )
            else:
                messages.append(
                    {"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]}
                )
    return messages


def roundtrip(provider, key, payload, timeout):
    from app.modules.executions.runtime import (
        ANTHROPIC_MESSAGES_URL,
        DEEPSEEK_RESPONSES_URL,
        OPENROUTER_CHAT_URL,
        ProviderFailure,
        _openai_response,
    )

    if provider == "deepseek":
        return _openai_response(key, payload, timeout, DEEPSEEK_RESPONSES_URL)
    if provider == "gemini":
        return gemini_roundtrip(key, payload, timeout)
    tools = payload["tools"]
    schema = payload["text"]["format"]["schema"]
    messages = transcript_messages(payload["input"], provider)
    if provider == "anthropic":
        body = {
            "model": payload["model"],
            "system": payload["instructions"],
            "messages": messages,
            "max_tokens": payload["max_output_tokens"],
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"],
                }
                for t in tools
            ],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        result = request_json(
            ANTHROPIC_MESSAGES_URL,
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            body,
            timeout,
        )
        if result.get("stop_reason") not in {"end_turn", "tool_use"}:
            raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
        usage = result.get("usage", {})
        outputs = [
            {
                "type": "function_call",
                "name": t["name"],
                "call_id": t["id"],
                "arguments": json.dumps(t["input"]),
            }
            for t in result.get("content", [])
            if t.get("type") == "tool_use"
        ]
        texts = [t["text"] for t in result.get("content", []) if t.get("type") == "text"]
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    elif provider == "openrouter":
        body = {
            "model": payload["model"],
            "messages": [{"role": "system", "content": payload["instructions"]}] + messages,
            "max_completion_tokens": payload["max_output_tokens"],
            "provider": {"require_parameters": True},
            "parallel_tool_calls": False,
            "tools": [
                {"type": "function", "function": {k: v for k, v in t.items() if k != "type"}}
                for t in tools
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "agent_output", "strict": True, "schema": schema},
            },
        }
        result = request_json(
            OPENROUTER_CHAT_URL, {"Authorization": "Bearer " + key}, body, timeout
        )
        choices = result.get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") not in {"stop", "tool_calls"}:
            raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
        message = choices[0].get("message", {})
        outputs = [
            {
                "type": "function_call",
                "name": t["function"]["name"],
                "call_id": t["id"],
                "arguments": t["function"]["arguments"],
            }
            for t in message.get("tool_calls", [])
        ]
        texts = [message["content"]] if isinstance(message.get("content"), str) else []
        input_tokens, output_tokens = (
            result.get("usage", {}).get("prompt_tokens"),
            result.get("usage", {}).get("completion_tokens"),
        )
    else:
        raise ProviderFailure("TOOLS_RUNTIME_UNSUPPORTED")
    if not outputs:
        outputs = [
            {"type": "message", "content": [{"type": "output_text", "text": t} for t in texts]}
        ]
    return {
        "status": "completed",
        "output": outputs,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def gemini_roundtrip(key, payload, timeout):
    from app.modules.executions.runtime import ProviderFailure

    contents, calls = [], {}
    for item in payload["input"]:
        if item.get("role") == "user":
            contents.append({"role": "user", "parts": [{"text": item["content"]}]})
        elif item.get("type") == "function_call":
            calls[item["call_id"]] = item["name"]
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": item["name"],
                                "args": json.loads(item["arguments"]),
                            }
                        }
                    ],
                }
            )
        elif item.get("type") == "function_call_output":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": calls[item["call_id"]],
                                "response": json.loads(item["output"]),
                            }
                        }
                    ],
                }
            )
        elif item.get("type") == "message":
            contents.append(
                {"role": "model", "parts": [{"text": p["text"]} for p in item["content"]]}
            )
    tools = payload["tools"]
    config = {
        "maxOutputTokens": payload["max_output_tokens"],
        "candidateCount": 1,
        "thinkingConfig": {"thinkingBudget": 0},
    }
    body = {
        "systemInstruction": {"parts": [{"text": payload["instructions"]}]},
        "contents": contents,
        "generationConfig": config,
    }
    if tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "parametersJsonSchema": t["parameters"],
                    }
                    for t in tools
                ]
            }
        ]
    else:
        # Start a new turn for the final JSON instead of asking Gemini to
        # continue an assistant message from its tool-discovery phase.
        if contents and contents[-1]["role"] == "model":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": "Return the final answer as JSON matching the required output schema."
                        }
                    ],
                }
            )
        config.update(
            {
                "responseMimeType": "application/json",
                "responseJsonSchema": payload["text"]["format"]["schema"],
            }
        )
    result = request_json(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + payload["model"]
        + ":generateContent",
        {"x-goog-api-key": key},
        body,
        timeout,
    )
    candidates = result.get("candidates", [])
    if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
        raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
    parts = candidates[0].get("content", {}).get("parts", [])
    outputs = [
        {
            "type": "function_call",
            "call_id": "gemini_" + str(len(payload["input"])) + "_" + str(i),
            "name": p["functionCall"]["name"],
            "arguments": json.dumps(p["functionCall"].get("args", {})),
        }
        for i, p in enumerate(parts)
        if "functionCall" in p
    ]
    if not outputs:
        outputs = [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": p["text"]} for p in parts if "text" in p
                ],
            }
        ]
    usage = result.get("usageMetadata", {})
    out = usage.get("candidatesTokenCount")
    thoughts = usage.get("thoughtsTokenCount", 0)
    if not isinstance(out, int) or not isinstance(thoughts, int):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    return {
        "status": "completed",
        "output": outputs,
        "usage": {"input_tokens": usage.get("promptTokenCount"), "output_tokens": out + thoughts},
        "_needs_finalization": bool(tools)
        and not any(x["type"] == "function_call" for x in outputs),
    }
