import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.errors import fail
from app.core.json_contracts import validate_user_schema
from app.modules.audit.service import record
from app.modules.mcp.catalog import catalog
from app.modules.mcp.client import call_tool, discover
from app.modules.mcp.models import McpConnection
from app.modules.mcp.schemas import McpCredential
from app.modules.workspaces.models import Workspace


def schema_hash(schema: dict) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def profile(raw_catalog: str, server_id: str) -> dict:
    item = catalog(raw_catalog).get(server_id)
    if not item:
        fail(404, "MCP_SERVER_NOT_FOUND", "MCP server not found in the approved catalog.")
    return item


def connection(db: Session, workspace_id: uuid.UUID, server_id: str, lock: bool = False):
    query = select(McpConnection).where(
        McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id
    )
    return db.scalar(query.with_for_update() if lock else query)


def listing(db: Session, workspace_id: uuid.UUID, raw_catalog: str) -> dict:
    entries = catalog(raw_catalog)
    saved = {
        row.server_id: row
        for row in db.scalars(
            select(McpConnection).where(McpConnection.workspace_id == workspace_id)
        )
    }
    return {
        "items": [
            {
                "id": server_id,
                "name": item["name"],
                "allowed_tools": item["allowed_tools"],
                "state": saved[server_id].state if server_id in saved else "not_connected",
                "verified_tools": saved[server_id].verified_tools
                if server_id in saved and saved[server_id].state == "active"
                else [],
                "runnable_tools": sorted(set(item.get("read_only_tools", [])) & set(saved[server_id].verified_tools))
                if server_id in saved and saved[server_id].state == "active" else [],
                "runnable_schemas": {tool["name"]: tool["input_schema"] for tool in saved[server_id].tool_snapshots
                                     if tool["name"] in item.get("read_only_tools", [])}
                if server_id in saved and saved[server_id].state == "active" else {},
                "verified_at": saved[server_id].verified_at
                if server_id in saved and saved[server_id].state == "active"
                else None,
            }
            for server_id, item in entries.items()
        ]
    }


def connect(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    key_path: str,
    server_id: str,
    body: McpCredential,
) -> dict:
    item = profile(raw_catalog, server_id)
    token = body.bearer_token.get_secret_value()
    remote_tools = discover(item["url"], token)
    snapshots = sorted(
        (tool for tool in remote_tools if tool["name"] in item["allowed_tools"]),
        key=lambda tool: tool["name"],
    )
    for tool in snapshots:
        validate_user_schema(tool["input_schema"])
    verified = sorted({tool["name"] for tool in snapshots})
    if not verified:
        fail(422, "MCP_TOOLS_UNAVAILABLE", "No approved tools were found on this MCP server.")
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
        )
        db.add(row)
        db.flush()
    row.generation += 1
    row.state = "active"
    row.verified_tools = verified
    row.tool_snapshots = snapshots
    row.verified_at = datetime.now(UTC)
    if token:
        row.nonce, row.ciphertext = encrypt_secret(
            load_master_key(key_path), workspace_id, row.id, row.generation, token
        )
    else:
        row.nonce = row.ciphertext = None
    record(
        db,
        workspace_id,
        actor_id,
        "mcp.connected",
        row.id,
        {"server_id": server_id, "tools": verified},
    )
    db.commit()
    return listing(db, workspace_id, raw_catalog)


def revoke(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    raw_catalog: str,
    server_id: str,
) -> dict:
    profile(raw_catalog, server_id)
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


def test_tool(
    db: Session,
    workspace_id: uuid.UUID,
    raw_catalog: str,
    key_path: str,
    server_id: str,
    tool_name: str,
    arguments: dict,
) -> dict:
    item = profile(raw_catalog, server_id)
    row = connection(db, workspace_id, server_id)
    if (
        not row
        or row.state != "active"
        or tool_name not in row.verified_tools
        or tool_name not in item["allowed_tools"]
    ):
        fail(403, "MCP_TOOL_NOT_APPROVED", "This MCP tool is not approved for this workspace.")
    key = (
        decrypt_secret(
            load_master_key(key_path),
            workspace_id,
            row.id,
            row.generation,
            row.nonce,
            row.ciphertext,
        )
        if row.nonce and row.ciphertext
        else ""
    )
    return {"output": call_tool(item["url"], key, tool_name, arguments)}
