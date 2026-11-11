"""Single-call agent worker: DB claims and markers are authoritative, not Celery delivery."""

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

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


def checked_usage(input_tokens, output_tokens) -> tuple[int, int]:
    if any(type(value) is not int or value < 0 for value in (input_tokens, output_tokens)):
        raise ProviderFailure("PROVIDER_USAGE_MISSING", uncertain=True)
    return input_tokens, output_tokens


def _openai_usage(result: dict) -> tuple[int, int]:
    usage = result.get("usage") or {}
    input_tokens, output_tokens = checked_usage(usage.get("input_tokens"), usage.get("output_tokens"))
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
    "demo.order_lookup": {
        "type": "function",
        "name": "lookup_order",
        "description": "Look up a Northwind Outdoor order by ID (sample demo data).",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
}


def _provider_approved(settings, version):
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            row = db.scalar(select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == version.workspace_id,
                IntegrationConnection.id == version.connection_id,
            ))
            return bool(row and row.state == "active" and row.credential_generation == version.credential_generation
                        and version.config["model_id"] in row.verified_models)
    finally:
        sessions.kw["bind"].dispose()


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
            if run:
                from app.modules.executions.authorization import assert_authorized
                try:
                    assert_authorized(db, run)
                except HTTPException:
                    return False
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
                if "detail" in details:
                    details["master"] = load_master_key(settings.credential_key_path)
                append_event(db, run, kind, status, **details)
                db.commit()
    finally:
        sessions.kw["bind"].dispose()


TRACE_VALUE_BYTES = 8000


def _clip(value: object) -> object:
    """Keep trace payloads small: oversized values are replaced by a truncated preview."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text.encode()) <= TRACE_VALUE_BYTES else {"truncated": True, "preview": text[:TRACE_VALUE_BYTES]}


def uses_tools(config: dict) -> bool:
    """Whether a run needs the tool loop: any tool grant, or skills the model loads on demand."""
    return bool(
        config.get("tool_keys") or config.get("mcp_tools") or config.get("http_tools") or config.get("workflow_tools")
        or (config.get("skills") and config.get("skill_loading", "on_demand") == "on_demand")
    )


def prepared(version):
    """The version as the model should see it: instructions plus its skills.

    On-demand skills add a short catalog the model loads from with use_skill; inline skills (for
    models without tool calls) add their full text. Versions without skills pass through.
    """
    config = version.config
    skills = config.get("skills") or []
    if not skills:
        return version
    if config.get("skill_loading") == "inline":
        sections = []
        for skill in skills:
            examples = "".join(
                f"\nExample input: {item['input']}\nExample output: {item['output']}" for item in skill.get("examples", [])
            )
            sections.append(f"### {skill['name']}\n{skill['instructions']}{examples}")
        extra = "\n\n## Skills\n" + "\n\n".join(sections)
    else:
        catalog = "\n".join(f"- {skill['name']}: {skill['description']}" for skill in skills)
        extra = f"\n\n## Skills\nBefore handling a request a skill covers, load it with the use_skill tool:\n{catalog}"
    return SimpleNamespace(
        id=version.id, workspace_id=version.workspace_id, agent_id=version.agent_id, connection_id=version.connection_id,
        credential_generation=version.credential_generation, name=version.name, number=version.number,
        config={**config, "instructions": config["instructions"] + extra},
    )


def _local_workflow(settings: Settings, workspace_id: uuid.UUID) -> Callable[[dict, dict, float], object]:
    """Run tool workflows outside a workflow run: only children without external steps."""

    def call(grant: dict, arguments: dict, remaining: float) -> object:
        from app.modules.workflows.preview import run_preview
        from app.modules.workflows.tools import inspect

        sessions = make_sessions(settings.database_url)
        try:
            with sessions() as db:
                version, graph, checked = inspect(db, workspace_id, grant, settings.mcp_catalog_json)
                if checked["has_external"]:
                    raise ProviderFailure("WORKFLOW_TOOL_REQUIRES_RUN", uncertain=True)
                return run_preview(
                    db, workspace_id, graph, arguments, mcp_catalog_json=settings.mcp_catalog_json,
                    max_seconds=min(remaining, 5), root_workflow_id=version.workflow_id,
                )["output"]
        finally:
            sessions.kw["bind"].dispose()

    return call


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
    run_workflow: Callable[[dict, dict, float], object] | None = None,
    approved_tool: dict | None = None,
) -> tuple[dict, int, int]:
    """Stateless function-call loop; version grants and live installation both gate each call.

    `run_workflow(grant, arguments, remaining_seconds)` starts a tool workflow; workflow runs pass
    a durable runner, and other runs fall back to local-only execution.
    """
    from app.modules.http_tools.service import alias as http_alias
    from app.modules.http_tools.service import invoke_agent as invoke_http
    from app.modules.mcp import registry as mcp_registry
    from app.modules.mcp.agent_grants import alias
    from app.modules.mcp.agent_grants import invoke as invoke_mcp
    from app.modules.mcp.agent_grants import resolve as resolve_mcp
    from app.modules.mcp.service import schema_hash
    from app.modules.workflows.tools import MAX_WORKFLOW_TOOL_CALLS
    from app.modules.workflows.tools import alias as workflow_alias
    grants = version.config["tool_keys"]
    names = {FUNCTIONS[tool_key]["name"]: tool_key for tool_key in grants}
    remote = {"mcp:" + alias(g): g for g in version.config.get("mcp_tools", [])}
    names.update({alias(g): key for key, g in remote.items()})
    http_remote = {"http:" + http_alias(g): g for g in version.config.get("http_tools", [])}
    names.update({http_alias(g): key for key, g in http_remote.items()})
    workflow_remote = {"workflow:" + workflow_alias(g): g for g in version.config.get("workflow_tools", [])}
    names.update({workflow_alias(g): key for key, g in workflow_remote.items()})
    workflow_calls = 0
    loading = version.config.get("skill_loading", "on_demand")
    skills = {skill["name"]: skill for skill in version.config.get("skills", [])} if loading == "on_demand" else {}
    if skills:
        names["use_skill"] = "skill:use"
    functions = [FUNCTIONS[tool_key] for tool_key in grants] + [
        {"type": "function", "name": alias(g), "description": (g["server_id"] + "/" + g["tool_name"] + ": " + g.get("description", ""))[:500],
         "parameters": g["input_schema"], "strict": False} for g in remote.values()] + [
        {"type": "function", "name": http_alias(g), "description": (g["name"] + ": " + g.get("description", ""))[:500],
         "parameters": g["input_schema"], "strict": False} for g in http_remote.values()] + [
        {"type": "function", "name": workflow_alias(g), "description": ("Run the workflow " + g["name"] + ". " + g.get("description", ""))[:500],
         "parameters": g["input_schema"], "strict": False} for g in workflow_remote.values()] + ([
        {"type": "function", "name": "use_skill", "description": "Load the full instructions and examples for one of your skills.",
         "parameters": {"type": "object", "properties": {"skill": {"type": "string", "enum": sorted(skills)}}, "required": ["skill"], "additionalProperties": False},
         "strict": False}] if skills else [])
    transcript: list = [{"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}]
    total_input = total_output = calls = 0
    finalizing = False
    started = time.monotonic()
    provider = version.config.get("provider", "openai")
    input_price, output_price = MODEL_PRICES[(provider, version.config["model_id"])]
    budget = min(Decimal(version.config["limits"]["max_cost_usd"]), budget_override) if budget_override is not None else Decimal(version.config["limits"]["max_cost_usd"])
    resume = approved_tool.get("continuation") if approved_tool else None
    if resume:
        transcript = resume["transcript"]
        total_input = resume["input_tokens"]
        total_output = resume["output_tokens"]
        calls = resume["calls"]
        workflow_calls = resume["workflow_calls"]
        finalizing = resume["finalizing"]
        resume_result = None if resume.get("resume_from_ready") else {
            "output": resume["items"],
            "_needs_finalization": resume["needs_finalization"],
        }
    else:
        resume_result = None
    for _ in range(version.config["limits"]["max_iterations"]):
        if active_check is not None and not active_check():
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=bool(total_input))
        if run_id and claim_token and not _run_active(settings, run_id, claim_token):
            raise ProviderFailure("RUN_INTERRUPTED", uncertain=bool(total_input))
        if not _provider_approved(settings, version):
            raise ProviderFailure("CREDENTIAL_CHANGED", uncertain=bool(total_input))
        remaining_time = timeout - (time.monotonic() - started)
        if remaining_time < 1:
            raise ProviderFailure("RUN_TIMEOUT", uncertain=True)
        spent = input_price * total_input + output_price * total_output
        estimate = input_price * len(json.dumps([transcript, functions, version.config["instructions"], version.config["output_schema"]], ensure_ascii=False).encode())
        allowance = int((budget - spent - estimate) / output_price)
        if allowance < 16:
            raise ProviderFailure("RUN_BUDGET_EXCEEDED", uncertain=bool(total_input))
        payload = {
            "model": version.config["model_id"],
            "instructions": version.config["instructions"],
            "input": transcript,
            "max_output_tokens": min(max_tokens, allowance),
            "store": False,
            "tools": [] if finalizing else functions,
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
        if resume_result is not None:
            result, resume_result = resume_result, None
        else:
            _trace(settings, run_id, claim_token, "model", "started")
            if provider == "openai":
                result = _openai_response(key, payload, min(30.0, remaining_time))
            else:
                from app.modules.executions.tool_protocols import roundtrip
                result = roundtrip(provider, key, payload, min(30.0, remaining_time))
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
            if approved_tool and approved_tool.get("_approval", {}).get("resume_from_ready"):
                from app.modules.executions.agent_approvals import finish_claim_run

                finish_claim_run(
                    make_sessions(settings.database_url), run_id, claim_token, "completed"
                )
                approved_tool = None
        items = result.get("output", [])
        if not isinstance(items, list):
            raise ProviderFailure("PROVIDER_OUTPUT_INVALID", uncertain=True)
        function_calls = [
            item for item in items if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if result.get("_needs_finalization"):
            # Gemini 2.5 separates tool use from the native structured-output call.
            transcript.extend(items)
            finalizing = True
            continue
        if finalizing and function_calls:
            raise ProviderFailure("TOOL_NOT_GRANTED", uncertain=True)
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
        if tool_key not in remote and tool_key not in http_remote and tool_key not in workflow_remote and tool_key != "skill:use" and not _tool_approved(settings, version.workspace_id, tool_key):
            raise ProviderFailure("TOOL_APPROVAL_REVOKED", uncertain=True)
        _trace(settings, run_id, claim_token, "tool", "started", tool_key=tool_key)
        arguments = None
        try:
            arguments = json.loads(call["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError
            if tool_key == "skill:use":
                skill = skills.get(arguments.get("skill"))
                if not skill:
                    raise ValueError
                # Trace which skill loaded, so the timeline reads "skill:Brand voice".
                tool_key = f"skill:{skill['name']}"[:80]
                tool_output = {"skill": skill["name"], "instructions": skill["instructions"], "examples": skill.get("examples", [])}
            elif tool_key in remote:
                remaining_time = timeout - (time.monotonic() - started)
                if remaining_time < 1:
                    raise ProviderFailure("RUN_TIMEOUT", uncertain=True)
                grant = remote[tool_key]
                sessions = make_sessions(settings.database_url)
                try:
                    with sessions() as db:
                        profile, row, snapshot = resolve_mcp(
                            db, version.workspace_id, grant, settings.mcp_catalog_json, pinned=True
                        )
                        tool_identity = {
                            "server_id": grant["server_id"],
                            "server_name": profile.get("name", grant["server_id"]),
                            "tool_name": grant["tool_name"],
                            "description": (snapshot.get("description") or "")[:300],
                            "connection_generation": row.generation,
                            "input_schema_hash": schema_hash(snapshot["input_schema"]),
                            "policy": mcp_registry.policy(profile, row, grant["tool_name"]),
                            "read_only": mcp_registry.read_only(profile, row, grant["tool_name"]),
                        }
                finally:
                    sessions.kw["bind"].dispose()
                approval_module = None
                if approved_tool:
                    from app.modules.executions import agent_approvals as approval_module
                    if (
                        approved_tool.get("_approval", {}).get("tool_key") != tool_key
                        or approval_module.context_hash(version.id, tool_identity, arguments)
                        != approved_tool.get("_approval", {}).get("context_hash")
                    ):
                        approval_module.finish_claim_run(
                            make_sessions(settings.database_url), run_id, claim_token, "cancelled"
                        )
                        raise ProviderFailure("APPROVAL_CONTEXT_CHANGED")
                elif not tool_identity["read_only"]:
                    from app.modules.executions import agent_approvals as approval_module
                    continuation = {
                        "transcript": transcript,
                        "items": items,
                        "needs_finalization": bool(result.get("_needs_finalization")),
                        "finalizing": finalizing,
                        "input_tokens": total_input,
                        "output_tokens": total_output,
                        "calls": calls,
                        "workflow_calls": workflow_calls,
                        "cost_usd": str(input_price * total_input + output_price * total_output),
                    }
                    with make_sessions(settings.database_url)() as db:
                        run = db.scalar(
                            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
                        )
                        if not run or run.state != "running" or run.claim_token != claim_token:
                            raise ProviderFailure("RUN_INTERRUPTED", uncertain=True)
                        approval_module.park(
                            db,
                            load_master_key(settings.credential_key_path),
                            run,
                            tool_key=tool_key,
                            tool_identity=tool_identity,
                            arguments=arguments,
                            continuation=continuation,
                        )
                    raise approval_module.Parked()
                tool_output = invoke_mcp(
                    settings,
                    version.workspace_id,
                    remote[tool_key],
                    arguments,
                    remaining_time,
                    expected_identity=tool_identity,
                )
            elif tool_key in http_remote:
                remaining_time = timeout - (time.monotonic() - started)
                if remaining_time < 1:
                    raise ProviderFailure("RUN_TIMEOUT", uncertain=True)
                tool_output = invoke_http(settings, version.workspace_id, http_remote[tool_key], arguments, remaining_time)
            elif tool_key in workflow_remote:
                remaining_time = timeout - (time.monotonic() - started)
                if remaining_time < 1:
                    raise ProviderFailure("RUN_TIMEOUT", uncertain=True)
                if workflow_calls >= MAX_WORKFLOW_TOOL_CALLS:
                    raise ProviderFailure("WORKFLOW_TOOL_CALL_LIMIT", uncertain=True)
                workflow_calls += 1
                runner = run_workflow or _local_workflow(settings, version.workspace_id)
                tool_output = {"output": runner(workflow_remote[tool_key], arguments, remaining_time)}
            elif tool_key == "json.extract":
                arguments = {
                    "document": json.loads(arguments["document_json"]),
                    "pointer": arguments["pointer"],
                }
                tool_output = invoke(tool_key, arguments)
            else:
                tool_output = invoke(tool_key, arguments)
        except HTTPException as exc:
            code = exc.detail.get("code", "TOOL_INPUT_INVALID") if isinstance(exc.detail, dict) else "TOOL_INPUT_INVALID"
            if (tool_key in remote or tool_key in http_remote or tool_key in workflow_remote) and code in {"MCP_GRANT_CHANGED", "APPROVAL_CONTEXT_CHANGED", "CREDENTIAL_CHANGED"}:
                _trace(settings, run_id, claim_token, "tool", "failed", tool_key=tool_key, error_code=code,
                       detail={"arguments": _clip(arguments), "output": None})
                raise ProviderFailure(code, uncertain=False) from None
            if (tool_key in remote or tool_key in http_remote or tool_key in workflow_remote) and code not in {"MCP_INPUT_SCHEMA_INVALID", "HTTP_INPUT_SCHEMA_INVALID", "HTTP_QUERY_INVALID", "HTTP_QUERY_TOO_LARGE", "PAYLOAD_TOO_LARGE", "SUBWORKFLOW_INPUT_INVALID", "INPUT_SCHEMA_INVALID"}:
                _trace(settings, run_id, claim_token, "tool", "failed", tool_key=tool_key, error_code=code,
                       detail={"arguments": _clip(arguments), "output": None})
                if approved_tool:
                    raise ProviderFailure("EXTERNAL_OUTCOME_UNKNOWN", uncertain=True) from None
                raise ProviderFailure(code, uncertain=True) from None
            tool_output = {"error": "TOOL_INPUT_INVALID"}
        except (ValueError, KeyError, TypeError):
            tool_output = {"error": "TOOL_INPUT_INVALID"}
        _trace(
            settings,
            run_id,
            claim_token,
            "tool",
            "failed" if "error" in tool_output else "completed",
            tool_key=tool_key,
            error_code=tool_output.get("error"),
            detail={"arguments": _clip(arguments), "output": _clip(tool_output)},
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
        if approved_tool and not approved_tool.get("_approval", {}).get("resume_from_ready"):
            from app.modules.executions.agent_approvals import save_call_result

            continuation = {
                "transcript": transcript,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "calls": calls,
                "workflow_calls": workflow_calls,
                "finalizing": finalizing,
                "cost_usd": str(input_price * total_input + output_price * total_output),
            }
            save_call_result(
                make_sessions(settings.database_url),
                load_master_key(settings.credential_key_path),
                run_id,
                claim_token,
                approved_tool,
                continuation,
            )
            approved_tool["_approval"]["resume_from_ready"] = True
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
    approved_tool = None
    try:
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == identity).with_for_update())
            if not run or run.state != "queued":
                return
            now = datetime.now(UTC)
            if run.cancel_requested_at or now >= run.deadline_at:
                from app.modules.executions.agent_approvals import invalidate_for_run

                invalidate_for_run(db, run, "RUN_CANCELLED" if run.cancel_requested_at else "RUN_TIMEOUT", now)
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                db.commit()
                return
            from app.modules.executions.authorization import assert_authorized
            try:
                assert_authorized(db, run)
            except HTTPException:
                from app.modules.executions.agent_approvals import invalidate_for_run

                invalidate_for_run(db, run, "RUN_AUTHORIZATION_REVOKED", now)
                run.state, run.error_code, run.finished_at = "failed", "RUN_AUTHORIZATION_REVOKED", now
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
                from app.modules.executions.agent_approvals import invalidate_for_run

                invalidate_for_run(db, run, "CREDENTIAL_CHANGED", now)
                run.state = "failed"
                run.error_code = "CREDENTIAL_CHANGED"
                run.finished_at = now
                db.commit()
                return
            from app.modules.agents.tool_grants import validate_grants
            try:
                validate_grants(db, run.workspace_id, version.config, settings.mcp_catalog_json)
            except HTTPException as exc:
                from app.modules.executions.agent_approvals import invalidate_for_run

                invalidate_for_run(db, run, exc.detail.get("code", "MCP_GRANT_CHANGED"), now)
                run.state = "failed"
                run.error_code = exc.detail.get("code", "MCP_GRANT_CHANGED")
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
            from app.modules.agents import memory
            try:
                memory_key = memory.conversation_key(version.config, input_data)
            except HTTPException as exc:
                run.state, run.error_code, run.finished_at = "failed", exc.detail.get("code", "MEMORY_KEY_MISSING"), now
                db.commit()
                return
            model_data = memory.model_input(input_data, memory.history(
                db, master, run.workspace_id, version.agent_id, memory_key, version.config["memory"]["max_turns"],
            )) if memory_key else input_data
            run.state = "running"
            run.started_at = now
            run.claim_token = token
            append_event(db, run, "run", "started")
            from app.modules.executions.agent_approvals import claim_approved

            approved_tool = claim_approved(db, run, master, now)
            if run.state != "running":
                return
            db.commit()
        with sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                return
            now = datetime.now(UTC)
            if run.cancel_requested_at or now >= run.deadline_at:
                from app.modules.executions.agent_approvals import cancel_claim

                cancel_claim(
                    db,
                    run,
                    "RUN_CANCELLED" if run.cancel_requested_at else "RUN_TIMEOUT",
                    now,
                )
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                db.commit()
                return
            try:
                assert_authorized(db, run)
            except HTTPException:
                from app.modules.executions.agent_approvals import cancel_claim

                cancel_claim(db, run, "RUN_AUTHORIZATION_REVOKED", now)
                run.state, run.error_code, run.finished_at = "failed", "RUN_AUTHORIZATION_REVOKED", now
                db.commit()
                return
            timeout = min(30.0, max(1.0, (run.deadline_at - now).total_seconds()))
            run.model_started_at = now
            if not uses_tools(version.config):
                append_event(db, run, "model", "started")
            db.commit()
        try:
            if uses_tools(version.config):
                output, input_tokens, output_tokens = generate_openai_with_tools(
                    key,
                    prepared(version),
                    model_data,
                    run.max_output_tokens,
                    timeout,
                    settings,
                    identity,
                    token,
                    approved_tool=approved_tool,
                )
            else:
                output, input_tokens, output_tokens = generate(
                    key, prepared(version), model_data, run.max_output_tokens, timeout
                )
                input_tokens, output_tokens = checked_usage(input_tokens, output_tokens)
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
        except Exception as exc:
            from app.modules.executions.agent_approvals import Parked

            if isinstance(exc, Parked):
                return
            if isinstance(exc, ProviderFailure):
                if approved_tool:
                    from app.modules.executions.agent_approvals import finish_claim_run

                    finish_claim_run(
                        sessions,
                        identity,
                        token,
                        "completed"
                        if approved_tool.get("_approval", {}).get("resume_from_ready")
                        else "uncertain"
                        if exc.uncertain
                        else "cancelled",
                    )
                output = None
                input_tokens = output_tokens = None
                failure = exc
            else:
                log.error("provider_result_unhandled %s", type(exc).__name__)
                if approved_tool:
                    from app.modules.executions.agent_approvals import finish_claim_run

                    finish_claim_run(
                        sessions,
                        identity,
                        token,
                        "completed"
                        if approved_tool.get("_approval", {}).get("resume_from_ready")
                        else "uncertain",
                    )
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
                if memory_key and run.state == "completed":
                    memory.remember(db, master, run.workspace_id, version.agent_id, memory_key, input_data, output, version.config["memory"])
            append_event(db, run, "run", run.state, error_code=run.error_code)
            db.commit()
    finally:
        sessions.kw["bind"].dispose()
