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


async def _session(url: str, key: str, action):
    await asyncio.to_thread(require_public_dns, url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx2.AsyncClient(
        headers=headers, timeout=httpx2.Timeout(8.0, connect=3.0), trust_env=False
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            return await action(client)


def _call(url: str, key: str, action):
    try:
        return asyncio.run(asyncio.wait_for(_session(url, key, action), timeout=12.0))
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        fail(502, "MCP_CONNECT_FAILED", "The MCP server did not complete the request.")


def discover(url: str, key: str) -> list[dict]:
    async def action(client):
        result = await client.list_tools()
        return [
            {
                "name": tool.name,
                "description": (tool.description or "")[:500],
                "input_schema": tool.inputSchema,
            }
            for tool in result.tools
        ]

    tools = _call(url, key, action)
    if (
        not isinstance(tools, list)
        or len(tools) > 100
        or any(
            not isinstance(tool, dict)
            or not isinstance(tool.get("name"), str)
            or len(tool["name"]) > 80
            or not isinstance(tool.get("input_schema"), dict)
            for tool in tools
        )
    ):
        fail(502, "MCP_TOOL_LIST_INVALID", "The MCP server returned an invalid tool list.")
    bounded_json(tools, max_bytes=65536)
    return tools


def call_tool(url: str, key: str, name: str, arguments: dict) -> dict:
    bounded_json(arguments, max_bytes=65536)

    async def action(client):
        result = await client.call_tool(name, arguments)
        return result.model_dump(mode="json")

    result = _call(url, key, action)
    bounded_json(result, max_bytes=65536)
    if len(json.dumps(result).encode()) > 65536:
        fail(502, "MCP_RESULT_TOO_LARGE", "The MCP tool returned too much data.")
    return result
