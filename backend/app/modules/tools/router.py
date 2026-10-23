import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf
from app.modules.tools.catalog import CATALOG, invoke
from app.modules.tools.models import ToolInstallation
from app.modules.tools.schemas import ToolInvoke, ToolResult
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/tools", tags=["tools"])


def _catalog_entry(key: str) -> dict:
    if key not in CATALOG:
        fail(404, "TOOL_NOT_FOUND", "Tool not found.")
    return CATALOG[key]


@router.get("")
def list_tools(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    installed = set(
        db.scalars(
            select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)
        )
    )
    return {
        "items": [
            {"key": key, **definition, "installed": key in installed}
            for key, definition in CATALOG.items()
        ]
    }


@router.put("/{tool_key:path}", dependencies=[Depends(check_csrf)])
def install_tool(
    workspace_id: uuid.UUID, tool_key: str, request: Request, db: Session = Depends(get_db)
) -> dict:
    _catalog_entry(tool_key)
    _, member = authorize(request, db, workspace_id, write=True)
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", "An owner or admin must approve tools.")
    existing = db.scalar(
        select(ToolInstallation).where(
            ToolInstallation.workspace_id == workspace_id, ToolInstallation.tool_key == tool_key
        )
    )
    if not existing:
        db.add(
            ToolInstallation(
                workspace_id=workspace_id, tool_key=tool_key, installed_by=member.user_id
            )
        )
        record(
            db, workspace_id, member.user_id, "tool.installed", workspace_id, {"tool_key": tool_key}
        )
        db.commit()
    return {"key": tool_key, "installed": True}


@router.delete("/{tool_key:path}", dependencies=[Depends(check_csrf)])
def remove_tool(
    workspace_id: uuid.UUID, tool_key: str, request: Request, db: Session = Depends(get_db)
) -> dict:
    _catalog_entry(tool_key)
    _, member = authorize(request, db, workspace_id, write=True)
    if member.role not in ("owner", "admin"):
        fail(403, "FORBIDDEN", "An owner or admin must approve tools.")
    result = db.execute(
        delete(ToolInstallation).where(
            ToolInstallation.workspace_id == workspace_id, ToolInstallation.tool_key == tool_key
        )
    )
    if result.rowcount:
        record(
            db, workspace_id, member.user_id, "tool.removed", workspace_id, {"tool_key": tool_key}
        )
        db.commit()
    return {"key": tool_key, "installed": False}


@router.post("/{tool_key:path}/test", response_model=ToolResult, dependencies=[Depends(check_csrf)])
def test_tool(
    workspace_id: uuid.UUID,
    tool_key: str,
    body: ToolInvoke,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _catalog_entry(tool_key)
    authorize(request, db, workspace_id, write=True)
    installed = db.scalar(
        select(ToolInstallation.id).where(
            ToolInstallation.workspace_id == workspace_id, ToolInstallation.tool_key == tool_key
        )
    )
    if not installed:
        fail(403, "TOOL_NOT_APPROVED", "Approve this tool in the workspace first.")
    return {"output": invoke(tool_key, body.input)}
