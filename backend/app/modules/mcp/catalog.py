"""Operator-owned MCP allowlist; tenants never submit network destinations."""

import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit

from app.core.errors import fail

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
TOOL_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")


def catalog(raw: str) -> dict[str, dict]:
    try:
        entries = json.loads(raw)
    except ValueError:
        fail(503, "MCP_CATALOG_INVALID", "MCP catalog configuration is invalid.")
    if not isinstance(entries, list) or len(entries) > 10 or len(raw.encode()) > 8192:
        fail(503, "MCP_CATALOG_INVALID", "MCP catalog configuration is invalid.")
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in ({"id", "name", "url", "allowed_tools"}, {"id", "name", "url", "allowed_tools", "read_only_tools"}):
            fail(503, "MCP_CATALOG_INVALID", "MCP catalog configuration is invalid.")
        server_id, name, url, allowed = (
            entry[key] for key in ("id", "name", "url", "allowed_tools")
        )
        if (
            not isinstance(server_id, str)
            or not IDENTIFIER.fullmatch(server_id)
            or server_id in result
        ):
            fail(503, "MCP_CATALOG_INVALID", "MCP server IDs must be unique slugs.")
        if not isinstance(name, str) or not 1 <= len(name) <= 100 or not isinstance(url, str):
            fail(503, "MCP_CATALOG_INVALID", "MCP catalog configuration is invalid.")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            fail(503, "MCP_CATALOG_INVALID", "MCP endpoint URL is invalid.")
        hostname = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not hostname
            or hostname.lower() in {"localhost", "localhost.localdomain"}
            or hostname.lower().endswith((".local", ".internal", ".localhost"))
        ):
            fail(503, "MCP_CATALOG_INVALID", "MCP endpoints must use public HTTPS hosts.")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            fail(503, "MCP_CATALOG_INVALID", "MCP endpoints cannot use IP literals.")
        if (
            not isinstance(allowed, list)
            or not 1 <= len(allowed) <= 20
            or not all(isinstance(item, str) and TOOL_NAME.fullmatch(item) for item in allowed)
            or len(set(allowed)) != len(allowed)
        ):
            fail(503, "MCP_CATALOG_INVALID", "MCP tool allowlist is invalid.")
        read_only = entry.get("read_only_tools", [])
        if not isinstance(read_only, list) or any(not isinstance(tool, str) or tool not in allowed for tool in read_only) or len(set(read_only)) != len(read_only):
            fail(503, "MCP_CATALOG_INVALID", "MCP read-only allowlist is invalid.")
        result[server_id] = entry
    return result


def require_public_dns(url: str) -> None:
    """Defense in depth for curated endpoints; production also needs egress policy."""
    hostname = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        fail(502, "MCP_CONNECT_FAILED", "The MCP server could not be reached.")
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        fail(502, "MCP_ENDPOINT_BLOCKED", "The MCP server resolved to a blocked network.")
