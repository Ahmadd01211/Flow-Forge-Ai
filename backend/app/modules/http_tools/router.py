import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.credentials import encrypt_secret, load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.http_tools import service
from app.modules.http_tools.models import HttpTool
from app.modules.http_tools.schemas import (
    HttpCredentialUpdate,
    HttpGeneration,
    HttpToolCreate,
    HttpToolList,
    HttpToolRead,
    HttpToolTest,
)
from app.modules.identity.service import check_csrf
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/http-tools", tags=["http-tools"])


def admin(request, db, workspace_id):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "An owner or admin approves HTTP destinations and credentials.")
    return member


@router.get("", response_model=HttpToolList)
def listing(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    rows = db.scalars(
        select(HttpTool)
        .where(HttpTool.workspace_id == workspace_id)
        .order_by(
            case((HttpTool.state == "active", 0), else_=1),
            HttpTool.created_at.desc(),
            HttpTool.id.desc(),
        )
        .limit(100)
    ).all()
    return {"items": [service.public(row) for row in rows]}


@router.post("", status_code=201, response_model=HttpToolRead, dependencies=[Depends(check_csrf)])
def create(
    workspace_id: uuid.UUID, body: HttpToolCreate, request: Request, db: Session = Depends(get_db)
):
    member = admin(request, db, workspace_id)
    return service.create(db, workspace_id, member.user_id, body, request.app.state.settings)


@router.post("/{tool_id}/rotate", response_model=HttpToolRead, dependencies=[Depends(check_csrf)])
def rotate(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: HttpCredentialUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    member = admin(request, db, workspace_id)
    row = service.find(db, workspace_id, tool_id, lock=True)
    if row.generation != body.expected_generation:
        fail(
            409,
            "HTTP_TOOL_CHANGED",
            "This credential changed elsewhere. Refresh before replacing it.",
        )
    secret = service.credential(body.credential, row.spec["auth_mode"])
    service.no_embedded_credential(row.spec, secret)
    row.generation += 1
    row.state = "active"
    if secret:
        row.nonce, row.ciphertext = encrypt_secret(
            load_master_key(request.app.state.settings.credential_key_path),
            workspace_id,
            row.id,
            row.generation,
            secret,
        )
    else:
        row.nonce = row.ciphertext = None
    record(
        db,
        workspace_id,
        member.user_id,
        "http_tool.credential_rotated",
        row.id,
        {"generation": row.generation},
    )
    db.commit()
    return service.public(row)


@router.post("/{tool_id}/revoke", response_model=HttpToolRead, dependencies=[Depends(check_csrf)])
def revoke(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: HttpGeneration,
    request: Request,
    db: Session = Depends(get_db),
):
    member = admin(request, db, workspace_id)
    row = service.find(db, workspace_id, tool_id, lock=True)
    if row.generation != body.expected_generation:
        fail(409, "HTTP_TOOL_CHANGED", "This tool changed elsewhere. Refresh before revoking it.")
    row.state = "revoked"
    row.generation += 1
    row.nonce = row.ciphertext = None
    record(
        db,
        workspace_id,
        member.user_id,
        "http_tool.revoked",
        row.id,
        {"generation": row.generation},
    )
    db.commit()
    return service.public(row)


@router.post("/{tool_id}/test", dependencies=[Depends(check_csrf)])
def test(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: HttpToolTest,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    if not body.confirm_external:
        fail(
            422,
            "EXTERNAL_TEST_UNCONFIRMED",
            "Confirm that this test sends data to the approved external endpoint.",
        )
    row = service.find(db, workspace_id, tool_id)
    if row.spec["method"] != "GET" or not row.spec["read_only"]:
        fail(
            422,
            "HTTP_TEST_REQUIRES_WORKFLOW",
            "Test write actions through a published workflow so receipts and failure evidence are retained.",
        )
    service.check_test_rate(request.app.state.redis, workspace_id)
    record(
        db, workspace_id, member.user_id, "http_tool.tested", row.id, {"generation": row.generation}
    )
    db.commit()
    return {
        "output": service.invoke(
            db,
            workspace_id,
            {
                "tool_id": str(row.id),
                "connection_generation": row.generation,
                "spec_hash": row.spec_hash,
            },
            body.input,
            request.app.state.settings,
        )
    }
