"""Single-call agent worker: DB claims and markers are authoritative, not Celery delivery."""

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import Settings
from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.db import make_sessions
from app.core.json_contracts import example_errors
from app.modules.agents.models import AgentVersion
from app.modules.executions.harness import append_event
from app.modules.executions.models import AgentRun
from app.modules.executions.service import MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection, SecretReference
from app.modules.tools.catalog import invoke
from app.modules.tools.models import ToolInstallation

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEEPSEEK_RESPONSES_URL = "https://api.deepseek.com/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
)
MAX_RESPONSE_BYTES = 1_000_000
log = logging.getLogger("flowforge.agent_run")


class ProviderFailure(Exception):
    def __init__(self, code: str, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain


def _openai_response(key: str, payload: dict, timeout: float, url: str = RESPONSES_URL) -> dict:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code in (400, 401, 403, 404, 422, 429):
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
    except httpx.HTTPError:
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    except (ValueError, TypeError):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None


def _openai_usage(result: dict) -> tuple[int, int]:
    usage = result.get("usage") or {}
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    if result.get("status") != "completed":
        raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
    return input_tokens, output_tokens


def _openai_output(result: dict, version: AgentVersion) -> dict:
    texts = [
        part.get("text")
        for item in result.get("output", [])
        if isinstance(item, dict)
        for part in item.get("content", [])
        if isinstance(part, dict) and part.get("type") == "output_text"
    ]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    try:
        output = json.loads(texts[0])
    except ValueError:
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True) from None
    if not isinstance(output, dict) or example_errors(
        version.config["output_schema"], output, "output"
    ):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    return output


def generate_openai(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    payload = {
        "model": version.config["model_id"],
        "instructions": version.config["instructions"],
        "input": json.dumps(input_data, ensure_ascii=False),
        "max_output_tokens": max_tokens,
        "store": False,
        "tools": [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "agent_output",
                "schema": version.config["output_schema"],
                "strict": True,
            }
        },
    }
    result = _openai_response(key, payload, timeout)
    input_tokens, output_tokens = _openai_usage(result)
    return _openai_output(result, version), input_tokens, output_tokens


def generate_deepseek(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    payload = {
        "model": version.config["model_id"],
        "instructions": version.config["instructions"],
        "input": json.dumps(input_data, ensure_ascii=False),
        "max_output_tokens": max_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "agent_output",
                "schema": version.config["output_schema"],
            }
        },
    }
    result = _openai_response(key, payload, timeout, DEEPSEEK_RESPONSES_URL)
    input_tokens, output_tokens = _openai_usage(result)
    return _openai_output(result, version), input_tokens, output_tokens


def generate_anthropic(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    payload = {
        "model": version.config["model_id"],
        "max_tokens": max_tokens,
        "system": version.config["instructions"],
        "messages": [
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}
        ],
        "output_config": {
            "format": {"type": "json_schema", "schema": version.config["output_schema"]}
        },
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                ANTHROPIC_MESSAGES_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code in (400, 401, 403, 404, 422, 429):
                    raise ProviderFailure("PROVIDER_REJECTED")
                if response.status_code != 200:
                    raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
        result = json.loads(chunks)
    except httpx.HTTPError:
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    except (ValueError, TypeError):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    if not isinstance(result, dict) or result.get("stop_reason") != "end_turn":
        raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
    usage = result.get("usage") or {}
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    texts = [
        part.get("text")
        for part in result.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    try:
        output = json.loads(texts[0])
    except ValueError:
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True) from None
    if not isinstance(output, dict) or example_errors(
        version.config["output_schema"], output, "output"
    ):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    return output, input_tokens, output_tokens


def generate_openrouter(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    payload = {
        "model": version.config["model_id"],
        "messages": [
            {"role": "system", "content": version.config["instructions"]},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ],
        "max_completion_tokens": max_tokens,
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_output",
                "strict": True,
                "schema": version.config["output_schema"],
            },
        },
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                OPENROUTER_CHAT_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
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
    except httpx.HTTPError:
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    except (ValueError, TypeError):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    if not isinstance(result, dict):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    usage = result.get("usage") or {}
    input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    choices = result.get("choices") or []
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    try:
        output = json.loads(content)
    except ValueError:
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True) from None
    if not isinstance(output, dict) or example_errors(
        version.config["output_schema"], output, "output"
    ):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    return output, input_tokens, output_tokens


FUNCTIONS = {
    "json.extract": {
        "type": "function",
        "name": "json_extract",
        "description": "Extract a JSON value by pointer.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"document_json": {"type": "string"}, "pointer": {"type": "string"}},
            "required": ["document_json", "pointer"],
            "additionalProperties": False,
        },
    },
    "text.replace": {
        "type": "function",
        "name": "text_replace",
        "description": "Replace literal text in a string.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "find": {"type": "string"},
                "replacement": {"type": "string"},
            },
            "required": ["text", "find", "replacement"],
            "additionalProperties": False,
        },
    },
}


def _tool_approved(settings: Settings, workspace_id: uuid.UUID, tool_key: str) -> bool:
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            return (
                db.scalar(
                    select(ToolInstallation.id).where(
                        ToolInstallation.workspace_id == workspace_id,
                        ToolInstallation.tool_key == tool_key,
                    )
                )
                is not None
            )
    finally:
        sessions.kw["bind"].dispose()


def _run_active(settings: Settings, run_id: uuid.UUID, token: uuid.UUID) -> bool:
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            run = db.get(AgentRun, run_id)
            return bool(
                run
                and run.state == "running"
                and run.claim_token == token
                and not run.cancel_requested_at
                and datetime.now(UTC) < run.deadline_at
            )
    finally:
        sessions.kw["bind"].dispose()


def _trace(
    settings: Settings,
    run_id: uuid.UUID | None,
    token: uuid.UUID | None,
    kind: str,
    status: str,
    **details,
) -> None:
    if not run_id or not token:
        return
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run and run.state == "running" and run.claim_token == token:
                append_event(db, run, kind, status, **details)
                db.commit()
    finally:
        sessions.kw["bind"].dispose()


def generate_openai_with_tools(
    key: str,
    version: AgentVersion,
    input_data: dict,
    max_tokens: int,
    timeout: float,
    settings: Settings,
    run_id: uuid.UUID | None = None,
    claim_token: uuid.UUID | None = None,
    active_check: Callable[[], bool] | None = None,
    budget_override: Decimal | None = None,
) -> tuple[dict, int, int]:
    """Stateless function-call loop; version grants and live installation both gate each call."""
    grants = version.config["tool_keys"]
    names = {FUNCTIONS[tool_key]["name"]: tool_key for tool_key in grants}
    transcript: list = [{"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}]
    total_input = total_output = calls = 0
    started = time.monotonic()
    input_price, output_price = MODEL_PRICES[("openai", version.config["model_id"])]
    budget = min(Decimal(version.config["limits"]["max_cost_usd"]), budget_override) if budget_override is not None else Decimal(version.config["limits"]["max_cost_usd"])
    for _ in range(version.config["limits"]["max_iterations"]):
        if active_check is not None and not active_check():
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=bool(total_input))
        if run_id and claim_token and not _run_active(settings, run_id, claim_token):
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=bool(total_input))
        remaining_time = timeout - (time.monotonic() - started)
        if remaining_time < 1:
            raise ProviderFailure("RUN_TIMEOUT", uncertain=True)
        spent = input_price * total_input + output_price * total_output
        estimate = input_price * len(json.dumps(transcript, ensure_ascii=False).encode())
        allowance = int((budget - spent - estimate) / output_price)
        if allowance < 16:
            raise ProviderFailure("RUN_BUDGET_EXCEEDED", uncertain=bool(total_input))
        payload = {
            "model": version.config["model_id"],
            "instructions": version.config["instructions"],
            "input": transcript,
            "max_output_tokens": min(max_tokens, allowance),
            "store": False,
            "tools": [FUNCTIONS[tool_key] for tool_key in grants],
            "parallel_tool_calls": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_output",
                    "schema": version.config["output_schema"],
                    "strict": True,
                }
            },
        }
        _trace(settings, run_id, claim_token, "model", "started")
        result = _openai_response(key, payload, min(30.0, remaining_time))
        used_input, used_output = _openai_usage(result)
        _trace(
            settings,
            run_id,
            claim_token,
            "model",
            "completed",
            input_tokens=used_input,
            output_tokens=used_output,
        )
        total_input += used_input
        total_output += used_output
        if input_price * total_input + output_price * total_output > budget:
            raise ProviderFailure("RUN_BUDGET_EXCEEDED", uncertain=True)
        items = result.get("output", [])
        if not isinstance(items, list):
            raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
        function_calls = [
            item for item in items if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if not function_calls:
            return _openai_output(result, version), total_input, total_output
        if len(function_calls) != 1 or calls >= version.config["limits"]["max_tool_calls"]:
            raise ProviderFailure("TOOL_CALL_LIMIT", uncertain=True)
        call = function_calls[0]
        tool_key = names.get(call.get("name"))
        if not tool_key or not isinstance(call.get("call_id"), str):
            raise ProviderFailure("TOOL_NOT_GRANTED", uncertain=True)
        if run_id and claim_token and not _run_active(settings, run_id, claim_token):
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=True)
        if active_check is not None and not active_check():
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=True)
        if not _tool_approved(settings, version.workspace_id, tool_key):
            raise ProviderFailure("TOOL_APPROVAL_REVOKED", uncertain=True)
        _trace(settings, run_id, claim_token, "tool", "started", tool_key=tool_key)
        try:
            arguments = json.loads(call["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError
            if tool_key == "json.extract":
                arguments = {
                    "document": json.loads(arguments["document_json"]),
                    "pointer": arguments["pointer"],
                }
            tool_output = invoke(tool_key, arguments)
        except (ValueError, KeyError, TypeError, HTTPException):
            tool_output = {"error": "TOOL_INPUT_INVALID"}
        _trace(
            settings,
            run_id,
            claim_token,
            "tool",
            "failed" if "error" in tool_output else "completed",
            tool_key=tool_key,
            error_code=tool_output.get("error"),
        )
        calls += 1
        transcript.extend(items)
        transcript.append(
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": json.dumps(tool_output, ensure_ascii=False),
            }
        )
        if len(json.dumps(transcript, ensure_ascii=False).encode()) > 120_000:
            raise ProviderFailure("TOOL_CONTEXT_TOO_LARGE", uncertain=True)
    raise ProviderFailure("RUN_ITERATION_LIMIT", uncertain=True)


def generate_gemini(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    payload = {
        "systemInstruction": {"parts": [{"text": version.config["instructions"]}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(input_data, ensure_ascii=False)}]}
        ],
        "generationConfig": {
            "candidateCount": 1,
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseJsonSchema": version.config["output_schema"],
        },
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/models/" + version.config["model_id"] + ":generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code in (400, 401, 403, 404, 422, 429):
                    raise ProviderFailure("PROVIDER_REJECTED")
                if response.status_code != 200:
                    raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
        result = json.loads(chunks)
    except httpx.HTTPError:
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    except (ValueError, TypeError):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True) from None
    usage = result.get("usageMetadata") or {}
    input_tokens = usage.get("promptTokenCount")
    candidate_tokens = usage.get("candidatesTokenCount")
    thought_tokens = usage.get("thoughtsTokenCount", 0)
    if not all(
        isinstance(value, int) for value in (input_tokens, candidate_tokens, thought_tokens)
    ):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    candidates = result.get("candidates") or []
    if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
        raise ProviderFailure("PROVIDER_INCOMPLETE", uncertain=True)
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [part.get("text") for part in parts if isinstance(part, dict) and "text" in part]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    try:
        output = json.loads(texts[0])
    except ValueError:
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True) from None
    if not isinstance(output, dict) or example_errors(
        version.config["output_schema"], output, "output"
    ):
        raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
    return output, input_tokens, candidate_tokens + thought_tokens


def generate(
    key: str, version: AgentVersion, input_data: dict, max_tokens: int, timeout: float
) -> tuple[dict, int, int]:
    if (version.config.get("provider", "openai"), version.config.get("model_id")) not in MODEL_PRICES:
        raise ProviderFailure("RUNTIME_UNSUPPORTED")
    if version.config.get("provider", "openai") == "gemini":
        return generate_gemini(key, version, input_data, max_tokens, timeout)
    if version.config.get("provider") == "deepseek":
        return generate_deepseek(key, version, input_data, max_tokens, timeout)
    if version.config.get("provider") == "anthropic":
        return generate_anthropic(key, version, input_data, max_tokens, timeout)
    if version.config.get("provider") == "openrouter":
        return generate_openrouter(key, version, input_data, max_tokens, timeout)
    return generate_openai(key, version, input_data, max_tokens, timeout)


def execute(run_id: str, settings: Settings | None = None) -> None:
    settings = settings or Settings()
    sessions = make_sessions(settings.database_url)
    master = load_master_key(settings.credential_key_path)
    identity = uuid.UUID(run_id)
    token = uuid.uuid4()
    try:
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == identity).with_for_update())
            if not run or run.state != "queued":
                return
            now = datetime.now(UTC)
            if run.cancel_requested_at or now >= run.deadline_at:
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                db.commit()
                return
            version = db.scalar(
                select(AgentVersion).where(
                    AgentVersion.id == run.version_id, AgentVersion.workspace_id == run.workspace_id
                )
            )
            connection = (
                db.scalar(
                    select(IntegrationConnection).where(
                        IntegrationConnection.id == version.connection_id,
                        IntegrationConnection.workspace_id == run.workspace_id,
                    )
                )
                if version
                else None
            )
            secret = (
                db.scalar(
                    select(SecretReference).where(
                        SecretReference.connection_id == version.connection_id,
                        SecretReference.generation == version.credential_generation,
                    )
                )
                if version
                else None
            )
            if (
                not connection
                or connection.state != "active"
                or connection.credential_generation != version.credential_generation
                or version.config["model_id"] not in connection.verified_models
                or not secret
            ):
                run.state = "failed"
                run.error_code = "CREDENTIAL_CHANGED"
                run.finished_at = now
                db.commit()
                return
            key = decrypt_secret(
                master,
                run.workspace_id,
                connection.id,
                secret.generation,
                secret.nonce,
                secret.ciphertext,
            )
            input_data = json.loads(
                decrypt_secret(
                    master, run.workspace_id, run.id, 1, run.input_nonce, run.input_ciphertext
                )
            )
            run.state = "running"
            run.started_at = now
            run.claim_token = token
            append_event(db, run, "run", "started")
            db.commit()
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                return
            now = datetime.now(UTC)
            if run.cancel_requested_at or now >= run.deadline_at:
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                db.commit()
                return
            timeout = min(30.0, max(1.0, (run.deadline_at - now).total_seconds()))
            run.model_started_at = now
            if not version.config.get("tool_keys"):
                append_event(db, run, "model", "started")
            db.commit()
        try:
            if version.config.get("tool_keys"):
                output, input_tokens, output_tokens = generate_openai_with_tools(
                    key,
                    version,
                    input_data,
                    run.max_output_tokens,
                    timeout,
                    settings,
                    identity,
                    token,
                )
            else:
                output, input_tokens, output_tokens = generate(
                    key, version, input_data, run.max_output_tokens, timeout
                )
                _trace(
                    settings,
                    identity,
                    token,
                    "model",
                    "completed",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            failure = None
        except ProviderFailure as exc:
            output = None
            input_tokens = output_tokens = None
            failure = exc
        except Exception as exc:
            log.error("provider_result_unhandled %s", type(exc).__name__)
            output = None
            input_tokens = output_tokens = None
            failure = ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                return
            now = datetime.now(UTC)
            run.finished_at = now
            if failure:
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = failure.code
                run.uncertain_cost_usd = run.reserved_max_usd if failure.uncertain else None
            else:
                run.input_tokens = input_tokens
                run.output_tokens = output_tokens
                input_price, output_price = MODEL_PRICES[
                    (version.config.get("provider", "openai"), version.config["model_id"])
                ]
                run.cost_usd = input_price * input_tokens + output_price * output_tokens
                nonce, encrypted = encrypt_secret(
                    master, run.workspace_id, run.id, 2, json.dumps(output, ensure_ascii=False)
                )
                run.output_nonce, run.output_ciphertext = nonce, encrypted
                run.state = (
                    "cancelled"
                    if run.cancel_requested_at
                    else "failed"
                    if now >= run.deadline_at
                    else "completed"
                )
                run.error_code = (
                    "RUN_TIMEOUT"
                    if now >= run.deadline_at and not run.cancel_requested_at
                    else None
                )
            append_event(db, run, "run", run.state, error_code=run.error_code)
            db.commit()
    finally:
        sessions.kw["bind"].dispose()
