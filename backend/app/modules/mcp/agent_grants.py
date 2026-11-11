"""Pin reviewed MCP tools in agent versions and re-check them before every remote call."""

import hashlib

from sqlalchemy import select

from app.core.credentials import load_master_key
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors, validate_user_schema
from app.modules.mcp import registry
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash


def alias(grant):
    identity = grant["server_id"] + ":" + grant["tool_name"]
    return "mcp_" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def resolve(db, workspace_id, grant, raw_catalog, pinned=False, lock=False):
    profile = registry.server(db, workspace_id, grant["server_id"], raw_catalog)
    query = select(McpConnection).where(
            McpConnection.workspace_id == workspace_id,
            McpConnection.server_id == grant["server_id"],
        )
    row = db.scalar(query.with_for_update() if lock else query)
    snapshot = registry.snapshot(row, grant["tool_name"])
    if not registry.runnable(profile, row, grant["tool_name"]):
        fail(
            409,
            "MCP_GRANT_CHANGED",
            "Connect this MCP server and allow the tool before publishing or running.",
        )
    digest = schema_hash(snapshot["input_schema"])
    if pinned and (
        row.generation != grant.get("connection_generation")
        or digest != grant.get("input_schema_hash")
        or schema_hash(grant.get("input_schema", {})) != digest
    ):
        fail(
            409,
            "MCP_GRANT_CHANGED",
            "The MCP credential or schema changed. Publish a new agent version.",
        )
    return profile, row, snapshot


def pin(db, workspace_id, grants, raw_catalog):
    result = []
    for grant in grants:
        _, row, snapshot = resolve(db, workspace_id, grant, raw_catalog)
        validate_user_schema(snapshot["input_schema"], tool=True)
        result.append(
            {
                "server_id": grant["server_id"],
                "tool_name": grant["tool_name"],
                "connection_generation": row.generation,
                "input_schema_hash": schema_hash(snapshot["input_schema"]),
                "input_schema": snapshot["input_schema"],
                "description": snapshot.get("description", "")[:500],
            }
        )
    bounded_json(result, max_bytes=65536)
    return result


def validate_grants(db, workspace_id, config, raw_catalog):
    for grant in config.get("mcp_tools", []):
        resolve(db, workspace_id, grant, raw_catalog, pinned=True)


def invoke(settings, workspace_id, grant, arguments, timeout, expected_identity=None):
    from app.core.db import make_sessions
    from app.modules.mcp.client import call_tool

    bounded_json(arguments, max_bytes=65536)
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            profile, row, snapshot = resolve(
                db,
                workspace_id,
                grant,
                settings.mcp_catalog_json,
                pinned=True,
                lock=expected_identity is not None,
            )
            if expected_identity is not None:
                current_identity = {
                    "server_id": grant["server_id"],
                    "server_name": profile.get("name", grant["server_id"]),
                    "tool_name": grant["tool_name"],
                    "description": (snapshot.get("description") or "")[:300],
                    "connection_generation": row.generation,
                    "input_schema_hash": schema_hash(snapshot["input_schema"]),
                    "policy": registry.policy(profile, row, grant["tool_name"]),
                    "read_only": registry.read_only(profile, row, grant["tool_name"]),
                }
                if current_identity != expected_identity:
                    fail(
                        409,
                        "APPROVAL_CONTEXT_CHANGED",
                        "The MCP tool permission changed after approval.",
                    )
            if example_errors(snapshot["input_schema"], arguments, "arguments"):
                fail(
                    422,
                    "MCP_INPUT_SCHEMA_INVALID",
                    "Arguments do not match the granted MCP tool schema.",
                )
            url, token = registry.endpoint(
                profile, row, load_master_key(settings.credential_key_path)
            )
            if expected_identity is not None:
                # Keep the tool-policy row locked through the outbound call so
                # an admin's policy edit cannot race the final approval check.
                result = call_tool(
                    url,
                    token,
                    grant["tool_name"],
                    arguments,
                    timeout_seconds=min(12.0, timeout),
                )
                if result.get("isError"):
                    fail(502, "MCP_TOOL_FAILED", "The MCP tool reported a failure.")
                return result
        result = call_tool(
            url, token, grant["tool_name"], arguments, timeout_seconds=min(12.0, timeout)
        )
        if result.get("isError"):
            fail(502, "MCP_TOOL_FAILED", "The MCP tool reported a failure.")
        return result
    finally:
        sessions.kw["bind"].dispose()
