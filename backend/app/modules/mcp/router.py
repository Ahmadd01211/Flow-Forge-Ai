import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.identity.service import check_csrf
from app.modules.mcp import service
from app.modules.mcp.schemas import McpCredential, McpToolInput
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/mcp", tags=["mcp"])


@router.get("")
def list_servers(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    return service.listing(db, workspace_id, request.app.state.settings.mcp_catalog_json)


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
    authorize(request, db, workspace_id, write=True)
    service.check_test_rate(request.app.state.redis, workspace_id)
    return service.test_tool(
        db,
        workspace_id,
        request.app.state.settings.mcp_catalog_json,
        request.app.state.settings.credential_key_path,
        server_id,
        tool_name,
        body.arguments,
    )
