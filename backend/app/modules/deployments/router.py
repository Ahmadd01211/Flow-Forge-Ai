import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.modules.deployments import service
from app.modules.deployments.models import Deployment
from app.modules.executions import service as agent_runs
from app.modules.executions.models import AgentRun
from app.modules.executions.schemas import RunCreate
from app.modules.identity.service import check_csrf
from app.modules.workflows import runtime as workflow_runs
from app.modules.workflows.models import WorkflowRun
from app.modules.workspaces.service import authorize

manage = APIRouter(prefix="/workspaces/{workspace_id}/deployments", tags=["deployments"])
invoke = APIRouter(prefix="/deployments", tags=["hosted-invocation"])


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["agent", "workflow"]
    version_id: uuid.UUID


class InvokeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict


def _admin(workspace_id: uuid.UUID, request: Request, db: Session):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "Workspace administration is required.")
    return member


@manage.get("")
def listing(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    _admin(workspace_id, request, db)
    rows = db.scalars(
        select(Deployment)
        .where(Deployment.workspace_id == workspace_id)
        .order_by(Deployment.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [service.public(row) for row in rows]}


@manage.get("/eligible")
def eligible(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    _admin(workspace_id, request, db)
    return service.eligible(db, workspace_id, request.app.state.settings.mcp_catalog_json)


@manage.post("", status_code=201, dependencies=[Depends(check_csrf)])
def create(
    workspace_id: uuid.UUID, body: DeploymentCreate, request: Request, db: Session = Depends(get_db)
) -> dict:
    member = _admin(workspace_id, request, db)
    return service.create(db, workspace_id, member.user_id, body.name, body.kind, body.version_id, request.app.state.settings.mcp_catalog_json)


@manage.post("/{deployment_id}/rotate", dependencies=[Depends(check_csrf)])
def rotate(
    workspace_id: uuid.UUID,
    deployment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    member = _admin(workspace_id, request, db)
    return service.rotate(db, workspace_id, deployment_id, member.user_id)


@manage.post("/{deployment_id}/revoke", dependencies=[Depends(check_csrf)])
def revoke(
    workspace_id: uuid.UUID,
    deployment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    member = _admin(workspace_id, request, db)
    return service.revoke(db, workspace_id, deployment_id, member.user_id)


@manage.get("/{deployment_id}/runs")
def recent_runs(
    workspace_id: uuid.UUID,
    deployment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _admin(workspace_id, request, db)
    deployment = service.find(db, workspace_id, deployment_id)
    model = AgentRun if deployment.kind == "agent" else WorkflowRun
    rows = db.scalars(
        select(model)
        .where(model.workspace_id == workspace_id, model.deployment_id == deployment_id)
        .order_by(model.created_at.desc(), model.id.desc())
        .limit(20)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "state": row.state,
                "error_code": row.error_code,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
            }
            for row in rows
        ]
    }


@invoke.post("/{deployment_id}/invoke", status_code=202)
def submit(
    deployment_id: uuid.UUID,
    body: InvokeInput,
    request: Request,
    response: Response,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    deployment = service.authenticate(db, request, deployment_id)
    service.throttle(request, deployment.id, "invoke")
    master = load_master_key(request.app.state.settings.credential_key_path)
    if deployment.kind == "agent":
        run, created = agent_runs.submit(
            db,
            deployment.workspace_id,
            deployment.created_by,
            RunCreate(version_id=deployment.agent_version_id, input=body.input),
            idempotency_key,
            master,
            deployment.id,
        )
        result = agent_runs.public_run(run, master)
    else:
        run, created = workflow_runs.submit(
            db,
            deployment.workspace_id,
            deployment.created_by,
            deployment.workflow_version_id,
            body.input,
            idempotency_key,
            master,
            deployment.id,
            request.app.state.settings.mcp_catalog_json,
        )
        result = workflow_runs.public_run(run, master)
    if not created:
        response.status_code = 200
    return result


@invoke.get("/{deployment_id}/runs/{run_id}")
def run_detail(
    deployment_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    deployment = service.authenticate(db, request, deployment_id)
    service.throttle(request, deployment.id, "poll")
    master = load_master_key(request.app.state.settings.credential_key_path)
    model = AgentRun if deployment.kind == "agent" else WorkflowRun
    run = db.scalar(
        select(model).where(
            model.id == run_id,
            model.workspace_id == deployment.workspace_id,
            model.deployment_id == deployment.id,
        )
    )
    if not run:
        fail(404, "NOT_FOUND", "Run not found for this deployment.")
    return (
        agent_runs.public_run(run, master)
        if deployment.kind == "agent"
        else workflow_runs.public_run(run, master)
    )
