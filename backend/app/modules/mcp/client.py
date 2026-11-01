"""MCP Streamable HTTP client using the official SDK and a bounded connection."""

import asyncio
import json

import httpx2
from fastapi import HTTPException
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.core.errors import fail
from app.core.json_contracts import bounded_json
from app.modules.mcp.catalog import require_public_dns


async def _session(url: str, key: str, action, statuses: list | None = None):
    await asyncio.to_thread(require_public_dns, url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    async def observe(response):
        # The SDK reports HTTP failures as a generic JSON-RPC error; keep the status for diagnosis.
    # Some servers (GitHub) answer malformed tokens with 400 plus an RFC 6750 invalid_token challenge.
        if statuses is not None:
            challenge = response.headers.get("www-authenticate", "").lower()
            statuses.append(401 if "invalid_token" in challenge else response.status_code)

    async with httpx2.AsyncClient(
        headers=headers,
        timeout=httpx2.Timeout(8.0, connect=3.0),
        trust_env=False,
        event_hooks={"response": [observe]},
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            return await action(client)


def _call(url: str, key: str, action, timeout_seconds: float = 12.0):
    statuses: list[int] = []
    try:
        return asyncio.run(
            asyncio.wait_for(_session(url, key, action, statuses), timeout=timeout_seconds)
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if statuses and statuses[-1] in (401, 403):
            fail(
                502,
                "MCP_AUTH_FAILED",
                "The MCP server rejected the credentials. Check the token and its permissions."
                if key
                else "This MCP server requires a token.",
            )
        fail(502, "MCP_CONNECT_FAILED", "The MCP server did not complete the request.")


MAX_TOOLS = 250


def discover(url: str, key: str) -> list[dict]:
    async def action(client):
        listed, cursor = [], None
        # Servers such as GitHub's page their tool lists; follow a bounded number of pages.
        for _ in range(10):
            result = await client.list_tools(cursor=cursor)
            listed.extend(result.tools)
            cursor = result.next_cursor
            if not cursor or len(listed) > MAX_TOOLS:
                break
        tools = []
        for tool in listed:
            item = {
                "name": tool.name,
                "description": (tool.description or "")[:500],
                "input_schema": tool.input_schema,
            }
            # Server-declared hints only seed default policies; an admin decides.
            hints = tool.annotations
            if hints and hints.read_only_hint is not None:
                item["read_only_hint"] = bool(hints.read_only_hint)
            if hints and hints.destructive_hint is not None:
                item["destructive_hint"] = bool(hints.destructive_hint)
            tools.append(item)
        return tools

    tools = _call(url, key, action)
    if (
        not isinstance(tools, list)
        or len(tools) > MAX_TOOLS
        or any(
            not isinstance(tool, dict)
            or not isinstance(tool.get("name"), str)
            or len(tool["name"]) > 80
            or not isinstance(tool.get("input_schema"), dict)
            for tool in tools
        )
    ):
        fail(502, "MCP_TOOL_LIST_INVALID", "The MCP server returned an invalid tool list.")
    bounded_json(tools, max_bytes=1_048_576)
    return tools


def call_tool(url: str, key: str, name: str, arguments: dict, timeout_seconds: float = 12.0) -> dict:
    bounded_json(arguments, max_bytes=65536)

    async def action(client):
        result = await client.call_tool(name, arguments)
        # Wire-format (camelCase) keys: callers check isError and structuredContent. Server
        # metadata (`_meta`, e.g. GitHub's base64 icons) would cost tokens on every agent call.
        return result.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"meta"}
        )

    result = _call(url, key, action, timeout_seconds)
    bounded_json(result, max_bytes=65536)
    if len(json.dumps(result).encode()) > 65536:
        fail(502, "MCP_RESULT_TOO_LARGE", "The MCP tool returned too much data.")
    return result
