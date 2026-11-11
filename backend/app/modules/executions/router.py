import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.credentials import load_master_key
from app.core.db import get_db
from app.modules.executions import service, trace
from app.modules.executions.models import AgentRun, RunEvent, RunFeedback
from app.modules.executions.schemas import RunCreate, RunEventList, RunList, RunRead
from app.modules.identity.service import check_csrf
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/runs", tags=["executions"])


@router.post("", status_code=202, response_model=RunRead, dependencies=[Depends(check_csrf)])
def submit_run(
    workspace_id: uuid.UUID,
    body: RunCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    master = load_master_key(request.app.state.settings.credential_key_path)
    run, created = service.submit(db, workspace_id, member.user_id, body, idempotency_key, master, raw_catalog=request.app.state.settings.mcp_catalog_json)
    if not created:
        response.status_code = 200
    return service.public_run(run, master)


@router.get("", response_model=RunList)
def list_runs(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.workspace_id == workspace_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(50)
    ).all()
    return {"items": [service.public_run(run, master) for run in runs]}


@router.get("/{run_id}", response_model=RunRead)
def run_detail(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return service.public_run(service.get_run(db, workspace_id, run_id), master)


@router.post("/{run_id}/cancel", response_model=RunRead, dependencies=[Depends(check_csrf)])
def cancel_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    _, member = authorize(request, db, workspace_id, write=True)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return service.public_run(service.cancel(db, workspace_id, run_id, member.user_id), master)


@router.get("/{run_id}/events", response_model=RunEventList)
def run_events(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    authorize(request, db, workspace_id)
    service.get_run(db, workspace_id, run_id)
    events = db.scalars(
        select(RunEvent)
        .where(RunEvent.workspace_id == workspace_id, RunEvent.run_id == run_id)
        .order_by(RunEvent.sequence)
        .limit(100)
    ).all()
    return {"items": events}


class FeedbackWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=500)


@router.get("/{run_id}/trace")
def run_trace(workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    """The run as a timeline: model calls, skill loads and tool calls with their payloads."""
    _, member = authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    run = service.get_run(db, workspace_id, run_id)
    return trace.build(db, master, run, service.public_run(run, master), member.user_id)


@router.put("/{run_id}/feedback", dependencies=[Depends(check_csrf)])
def give_feedback(workspace_id: uuid.UUID, run_id: uuid.UUID, body: FeedbackWrite, request: Request, db: Session = Depends(get_db)) -> dict:
    _, member = authorize(request, db, workspace_id)
    run = service.get_run(db, workspace_id, run_id)
    row = db.scalar(select(RunFeedback).where(RunFeedback.run_id == run.id, RunFeedback.created_by == member.user_id))
    if row:
        row.rating, row.comment = body.rating, body.comment.strip()
    else:
        db.add(RunFeedback(workspace_id=workspace_id, run_id=run.id, rating=body.rating, comment=body.comment.strip(), created_by=member.user_id))
    db.commit()
    return trace.feedback_summary(db, run, member.user_id)


@router.delete("/{run_id}/feedback", dependencies=[Depends(check_csrf)])
def remove_feedback(workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    _, member = authorize(request, db, workspace_id)
    run = service.get_run(db, workspace_id, run_id)
    db.execute(delete(RunFeedback).where(RunFeedback.run_id == run.id, RunFeedback.created_by == member.user_id))
    db.commit()
    return trace.feedback_summary(db, run, member.user_id)
