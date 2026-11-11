"""One resolution path for operator-catalog and workspace-added MCP servers.

A tool is runnable by agents and workflows only when its connection is active, the tool was
verified at connection time and its effective policy is "allow". Defaults never trust a
remote server with write access: operator servers allow only their reviewed read-only tools,
and workspace servers allow only tools the server itself declares read-only. An admin can
allow or block any tool explicitly; blocking takes effect on the next call.
"""

import json

from sqlalchemy import select

from app.core.credentials import decrypt_secret, encrypt_secret
from app.modules.mcp.catalog import catalog, workspace_servers_allowed
from app.modules.mcp.models import McpConnection

POLICIES = ("allow", "block")


def workspace_profile(row):
    return {
        "id": row.server_id,
        "name": row.name,
        "origin": row.url,
        "source": "workspace",
        "allowed_tools": [tool["name"] for tool in row.tool_snapshots],
    }


def servers(db, workspace_id, raw_catalog):
    """Profiles visible to a workspace, keyed by server ID."""
    open_policy = workspace_servers_allowed(raw_catalog)
    # In locked-down installs admins may still block operator tools, but not allow writes.
    result = {key: {**item, "open_policy": open_policy} for key, item in catalog(raw_catalog).items()}
    if open_policy:
        rows = db.scalars(
            select(McpConnection).where(
                McpConnection.workspace_id == workspace_id,
                McpConnection.url.is_not(None),
                McpConnection.state == "active",
            )
        )
        result.update({row.server_id: workspace_profile(row) for row in rows})
    return result


def server(db, workspace_id, server_id, raw_catalog):
    if not isinstance(server_id, str):
        return None
    return servers(db, workspace_id, raw_catalog).get(server_id)


def snapshot(row, tool_name):
    if not row or row.state != "active" or tool_name not in row.verified_tools:
        return None
    return next((tool for tool in row.tool_snapshots if tool["name"] == tool_name), None)


def read_only(profile, row, tool_name):
    if profile["source"] == "catalog":
        return tool_name in profile.get("read_only_tools", [])
    tool = snapshot(row, tool_name)
    return bool(tool and tool.get("read_only_hint") and not tool.get("destructive_hint"))


def policy(profile, row, tool_name):
    explicit = (row.tool_policies or {}).get(tool_name) if row else None
    if explicit == "block":
        return "block"
    if explicit == "allow" and (profile["source"] == "workspace" or profile.get("open_policy")):
        return "allow"
    return "allow" if read_only(profile, row, tool_name) else "block"


def runnable(profile, row, tool_name):
    return bool(
        profile
        and tool_name in profile["allowed_tools"]
        and snapshot(row, tool_name)
        and policy(profile, row, tool_name) == "allow"
    )


def seal(master, row, url, token):
    """Workspace servers keep their full URL encrypted with the token: it can embed a secret."""
    row.nonce, row.ciphertext = encrypt_secret(
        master, row.workspace_id, row.id, row.generation, json.dumps({"url": url, "token": token})
    )


def endpoint(profile, row, master):
    """The (url, token) pair for one call against the row's current generation."""
    secret = (
        decrypt_secret(
            master, row.workspace_id, row.id, row.generation, row.nonce, row.ciphertext
        )
        if row.nonce and row.ciphertext
        else ""
    )
    if profile["source"] == "catalog":
        return profile["url"], secret
    stored = json.loads(secret)
    return stored["url"], stored["token"]
