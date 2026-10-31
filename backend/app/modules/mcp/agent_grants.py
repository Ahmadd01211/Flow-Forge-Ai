"""Pin reviewed MCP tools in agent versions and re-check them before every remote call."""

import hashlib

from sqlalchemy import select

from app.core.credentials import decrypt_secret, load_master_key
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors, validate_user_schema
from app.modules.mcp.catalog import catalog
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash


def alias(grant):
    identity = grant["server_id"] + ":" + grant["tool_name"]
    return "mcp_" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def resolve(db, workspace_id, grant, raw_catalog, pinned=False):
    profile = catalog(raw_catalog).get(grant["server_id"])
    row = db.scalar(
        select(McpConnection).where(
            McpConnection.workspace_id == workspace_id,
            McpConnection.server_id == grant["server_id"],
        )
    )
    snapshot = (
        next((t for t in row.tool_snapshots if t["name"] == grant["tool_name"]), None)
        if row and row.state == "active"
        else None
    )
    if (
        not profile
        or grant["tool_name"] not in profile.get("read_only_tools", [])
        or not row
        or row.state != "active"
        or grant["tool_name"] not in row.verified_tools
        or not snapshot
    ):
        fail(
            409,
            "MCP_GRANT_CHANGED",
            "Connect and approve this read-only MCP tool before publishing or running.",
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
        validate_user_schema(snapshot["input_schema"])
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


def invoke(settings, workspace_id, grant, arguments, timeout):
    from app.core.db import make_sessions
    from app.modules.mcp.client import call_tool

    bounded_json(arguments, max_bytes=65536)
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            profile, row, snapshot = resolve(
                db, workspace_id, grant, settings.mcp_catalog_json, pinned=True
            )
            if example_errors(snapshot["input_schema"], arguments, "arguments"):
                fail(
                    422,
                    "MCP_INPUT_SCHEMA_INVALID",
                    "Arguments do not match the granted MCP tool schema.",
                )
            token = (
                decrypt_secret(
                    load_master_key(settings.credential_key_path),
                    workspace_id,
                    row.id,
                    row.generation,
                    row.nonce,
                    row.ciphertext,
                )
                if row.nonce and row.ciphertext
                else ""
            )
        result = call_tool(
            profile["url"], token, grant["tool_name"], arguments, timeout_seconds=min(12.0, timeout)
        )
        if result.get("isError"):
            fail(502, "MCP_TOOL_FAILED", "The MCP tool reported a failure.")
        return result
    finally:
        sessions.kw["bind"].dispose()
