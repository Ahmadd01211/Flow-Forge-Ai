import hashlib
import json
import re
import secrets
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.credentials import encrypt_secret, load_master_key
from app.core.errors import fail
from app.core.json_contracts import validate_user_schema
from app.modules.audit.service import record
from app.modules.mcp import registry
from app.modules.mcp.catalog import TOOL_NAME, check_url, workspace_servers_allowed
from app.modules.mcp.client import call_tool, discover
from app.modules.mcp.models import McpConnection
from app.modules.mcp.schemas import McpCredential, McpServerCreate
from app.modules.workspaces.models import Workspace

MAX_WORKSPACE_SERVERS = 20


def schema_hash(schema: dict) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def profile(db: Session, workspace_id: uuid.UUID, raw_catalog: str, server_id: str) -> dict:
    item = registry.server(db, workspace_id, server_id, raw_catalog)
    if not item:
        fail(404, "MCP_SERVER_NOT_FOUND", "MCP server not found for this workspace.")
    return item


def connection(db: Session, workspace_id: uuid.UUID, server_id: str, lock: bool = False):
    query = select(McpConnection).where(
        McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id
    )
    return db.scalar(query.with_for_update() if lock else query)


def _describe(item: dict, row) -> dict:
    active = bool(row and row.state == "active")
    tools = [
        {
            **{key: tool[key] for key in ("name", "description", "read_only_hint", "destructive_hint") if key in tool},
            "read_only": registry.read_only(item, row, tool["name"]),
            "policy": registry.policy(item, row, tool["name"]),
        }
        for tool in (row.tool_snapshots if active else [])
    ]
    runnable = [tool["name"] for tool in tools if registry.runnable(item, row, tool["name"])]
    return {
        "id": item["id"],
        "name": item["name"],
        "source": item["source"],
        "origin": item.get("origin"),
        "allowed_tools": item["allowed_tools"],
        "state": row.state if row else "not_connected",
        "verified_tools": row.verified_tools if active else [],
        "runnable_tools": sorted(runnable),
        "runnable_schemas": {
            tool["name"]: tool["input_schema"] for tool in row.tool_snapshots if tool["name"] in runnable
        } if active else {},
        "tools": tools,
        "policy_editable": item["source"] == "workspace" or bool(item.get("open_policy")),
        "verified_at": row.verified_at if active else None,
    }


def listing(db: Session, workspace_id: uuid.UUID, raw_catalog: str) -> dict:
    entries = registry.servers(db, workspace_id, raw_catalog)
    saved = {
        row.server_id: row
        for row in db.scalars(
            select(McpConnection).where(McpConnection.workspace_id == workspace_id)
        )
    }
    ordered = sorted(entries.values(), key=lambda item: (item["source"] != "catalog", item["name"].lower()))
    return {
        "items": [_describe(item, saved.get(item["id"])) for item in ordered],
        "workspace_servers": workspace_servers_allowed(raw_catalog),
    }


def _compatible(remote_tools: list[dict]) -> tuple[list[dict], int]:
    """Tools agents and workflows can call; others are skipped rather than failing the server."""
    usable = []
    for tool in remote_tools:
        if not TOOL_NAME.fullmatch(tool["name"]):
            continue
        try:
            validate_user_schema(tool["input_schema"])
        except HTTPException:
            continue
        usable.append(tool)
    return sorted(usable, key=lambda tool: tool["name"]), len(remote_tools) - len(usable)


def _verified(db, workspace_id, row, snapshots, actor_id, action, details):
    row.state = "active"
    row.verified_tools = sorted({tool["name"] for tool in snapshots})
    row.tool_snapshots = snapshots
    row.tool_policies = {
        name: value for name, value in (row.tool_policies or {}).items() if name in row.verified_tools
    }
    row.verified_at = datetime.now(UTC)
    record(db, workspace_id, actor_id, action, row.id, {**details, "tools": row.verified_tools})


def connect(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    key_path: str,
    server_id: str,
    body: McpCredential,
) -> dict:
    """Connect an operator server, or verify/rotate the token of a workspace server."""
    item = profile(db, workspace_id, raw_catalog, server_id)
    token = body.bearer_token.get_secret_value()
    master = load_master_key(key_path)
    if item["source"] == "workspace":
        current = connection(db, workspace_id, server_id)
        url, _ = registry.endpoint(item, current, master)
        snapshots, _ = _compatible(discover(url, token))
    else:
        url = item["url"]
        snapshots = sorted(
            (tool for tool in discover(url, token) if tool["name"] in item["allowed_tools"]),
            key=lambda tool: tool["name"],
        )
        for tool in snapshots:
            validate_user_schema(tool["input_schema"])
    if not snapshots:
        fail(422, "MCP_TOOLS_UNAVAILABLE", "No usable tools were found on this MCP server.")
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    row = connection(db, workspace_id, server_id, lock=True)
    if not row:
        row = McpConnection(
            workspace_id=workspace_id,
            server_id=server_id,
            state="active",
            generation=0,
            verified_tools=[],
            tool_snapshots=[],
            tool_policies={},
        )
        db.add(row)
        db.flush()
    row.generation += 1
    if item["source"] == "workspace":
        registry.seal(master, row, url, token)
    elif token:
        row.nonce, row.ciphertext = encrypt_secret(
            master, workspace_id, row.id, row.generation, token
        )
    else:
        row.nonce = row.ciphertext = None
    _verified(db, workspace_id, row, snapshots, actor_id, "mcp.connected", {"server_id": server_id})
    db.commit()
    return listing(db, workspace_id, raw_catalog)


def _server_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24].strip("-") or "server"
    return f"ws-{slug}-{secrets.token_hex(3)}"


def add_server(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    key_path: str,
    body: McpServerCreate,
) -> dict:
    if not workspace_servers_allowed(raw_catalog):
        fail(403, "MCP_WORKSPACE_SERVERS_DISABLED", "This installation only permits operator-reviewed MCP servers.")
    url = check_url(body.url.strip(), 422, "MCP_URL_INVALID")
    token = body.bearer_token.get_secret_value()
    snapshots, skipped = _compatible(discover(url, token))
    if not snapshots:
        fail(422, "MCP_TOOLS_UNAVAILABLE", "No usable tools were found on this MCP server.")
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    active = db.scalar(
        select(func.count()).select_from(McpConnection).where(
            McpConnection.workspace_id == workspace_id,
            McpConnection.url.is_not(None),
            McpConnection.state == "active",
        )
    )
    if active >= MAX_WORKSPACE_SERVERS:
        fail(422, "MCP_SERVER_LIMIT", f"A workspace can add up to {MAX_WORKSPACE_SERVERS} MCP servers.")
    parts = url.split("/")
    row = McpConnection(
        workspace_id=workspace_id,
        server_id=_server_id(body.name),
        name=body.name.strip(),
        url=f"https://{parts[2]}",
        state="active",
        generation=1,
        verified_tools=[],
        tool_snapshots=[],
        tool_policies={},
    )
    db.add(row)
    db.flush()
    registry.seal(load_master_key(key_path), row, url, token)
    _verified(db, workspace_id, row, snapshots, actor_id, "mcp.server_added", {
        "server_id": row.server_id, "origin": row.url, "skipped_tools": skipped,
    })
    db.commit()
    return {**listing(db, workspace_id, raw_catalog), "added": row.server_id, "skipped_tools": skipped}


def set_policy(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    server_id: str,
    tool_name: str,
    value: str,
) -> dict:
    item = profile(db, workspace_id, raw_catalog, server_id)
    row = connection(db, workspace_id, server_id, lock=True)
    if not registry.snapshot(row, tool_name) or tool_name not in item["allowed_tools"]:
        fail(404, "MCP_TOOL_NOT_FOUND", "Connect this server and choose one of its verified tools.")
    if value == "allow" and item["source"] == "catalog" and not item.get("open_policy"):
        fail(403, "MCP_POLICY_LOCKED", "This installation only allows operator-reviewed read-only tools.")
    row.tool_policies = {**(row.tool_policies or {}), tool_name: value}
    record(db, workspace_id, actor_id, "mcp.tool_policy_changed", row.id, {
        "server_id": server_id, "tool_name": tool_name, "policy": value,
        "read_only": registry.read_only(item, row, tool_name),
    })
    db.commit()
    return listing(db, workspace_id, raw_catalog)


def revoke(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    server_id: str,
) -> dict:
    profile(db, workspace_id, raw_catalog, server_id)
    row = connection(db, workspace_id, server_id, lock=True)
    if row and row.state == "active":
        row.state = "revoked"
        row.nonce = row.ciphertext = None
        row.verified_tools = []
        row.tool_snapshots = []
        row.verified_at = None
        record(db, workspace_id, actor_id, "mcp.revoked", row.id, {"server_id": server_id})
        db.commit()
    return listing(db, workspace_id, raw_catalog)


def check_test_rate(redis, workspace_id: uuid.UUID) -> None:
    """Interactive MCP calls (tool tests and workflow node tests) share 20 per workspace-minute."""
    bucket = f"mcp-test:{workspace_id}:{int(time.time()) // 60}"
    count = redis.incr(bucket)
    if count == 1:
        redis.expire(bucket, 70)
    if count > 20:
        fail(429, "MCP_RATE_LIMIT", "Too many MCP tool tests. Try again shortly.")


def test_tool(
    db: Session,
    workspace_id: uuid.UUID,
    raw_catalog: str,
    key_path: str,
    server_id: str,
    tool_name: str,
    arguments: dict,
    manager: bool = False,
) -> dict:
    """Direct tool test. Owners/admins may test any allowed tool; others only read-only tools."""
    item = profile(db, workspace_id, raw_catalog, server_id)
    row = connection(db, workspace_id, server_id)
    if (
        not registry.snapshot(row, tool_name)
        or tool_name not in item["allowed_tools"]
        or (row.tool_policies or {}).get(tool_name) == "block"
        or (item["source"] == "workspace" and registry.policy(item, row, tool_name) == "block")
    ):
        fail(403, "MCP_TOOL_NOT_APPROVED", "This MCP tool is not approved for this workspace.")
    if item["source"] == "workspace" and not manager and not registry.read_only(item, row, tool_name):
        # Like HTTP write actions, writes run through agents or published workflows with evidence.
        fail(422, "MCP_TEST_REQUIRES_WORKFLOW", "Only an owner or admin can test a tool that may change data. Run it from an agent or published workflow.")
    url, key = registry.endpoint(item, row, load_master_key(key_path))
    return {"output": call_tool(url, key, tool_name, arguments)}
