import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.identity.service import check_csrf
from app.modules.mcp import service
from app.modules.mcp.schemas import McpCredential, McpServerCreate, McpToolInput, McpToolPolicy
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/mcp", tags=["mcp"])


@router.get("")
def list_servers(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    return service.listing(db, workspace_id, request.app.state.settings.mcp_catalog_json)


def manager(request, db, workspace_id, action):
    _, member = authorize(request, db, workspace_id, write=True)
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", f"An owner or admin must {action}.")
    return member


@router.post("/servers", status_code=201, dependencies=[Depends(check_csrf)])
def add_server(
    workspace_id: uuid.UUID,
    body: McpServerCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    member = manager(request, db, workspace_id, "add MCP servers")
    settings = request.app.state.settings
    return service.add_server(
        db, workspace_id, member.user_id, settings.mcp_catalog_json,
        settings.credential_key_path, body,
    )


@router.patch("/{server_id}/tools/{tool_name}", dependencies=[Depends(check_csrf)])
def set_tool_policy(
    workspace_id: uuid.UUID,
    server_id: str,
    tool_name: str,
    body: McpToolPolicy,
    request: Request,
    db: Session = Depends(get_db),
):
    member = manager(request, db, workspace_id, "change MCP tool policies")
    return service.set_policy(
        db, workspace_id, member.user_id, request.app.state.settings.mcp_catalog_json,
        server_id, tool_name, body.policy,
    )


@router.put("/{server_id}", dependencies=[Depends(check_csrf)])
def connect_server(
    workspace_id: uuid.UUID,
    server_id: str,
    body: McpCredential,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", "An owner or admin must connect MCP servers.")
    return service.connect(
        db,
        workspace_id,
        member.user_id,
        request.app.state.settings.mcp_catalog_json,
        request.app.state.settings.credential_key_path,
        server_id,
        body,
    )


@router.delete("/{server_id}", dependencies=[Depends(check_csrf)])
def disconnect_server(
    workspace_id: uuid.UUID,
    server_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", "An owner or admin must disconnect MCP servers.")
    return service.revoke(
        db, workspace_id, member.user_id, request.app.state.settings.mcp_catalog_json, server_id
    )


@router.post("/{server_id}/tools/{tool_name}/test", dependencies=[Depends(check_csrf)])
def test_remote_tool(
    workspace_id: uuid.UUID,
    server_id: str,
    tool_name: str,
    body: McpToolInput,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    service.check_test_rate(request.app.state.redis, workspace_id)
    return service.test_tool(
        db,
        workspace_id,
        request.app.state.settings.mcp_catalog_json,
        request.app.state.settings.credential_key_path,
        server_id,
        tool_name,
        body.arguments,
        manager=member.role in ("owner", "admin"),
    )
