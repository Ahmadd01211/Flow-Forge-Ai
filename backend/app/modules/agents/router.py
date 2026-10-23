import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.agents import service
from app.modules.agents.models import AgentVersion
from app.modules.agents.readiness import assess
from app.modules.agents.schemas import (
    AgentConfig,
    AgentCreate,
    AgentRead,
    AgentUpdate,
    ExampleRequest,
    ExampleResult,
    ReadinessRead,
    RestoreRequest,
    SnapshotCreate,
    VersionList,
    VersionRead,
)
from app.modules.executions.service import MODEL_PRICES
from app.modules.identity.service import check_csrf
from app.modules.integrations.models import IntegrationConnection
from app.modules.integrations.service import get_connection
from app.modules.tools.models import ToolInstallation
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agents"])


@router.get("")
def list_agents(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    return service.list_drafts(db, workspace_id)


@router.get("/workflow-options")
def workflow_options(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    versions = db.scalars(
        select(AgentVersion)
        .where(AgentVersion.workspace_id == workspace_id, AgentVersion.purpose == "published")
        .order_by(AgentVersion.created_at.desc())
        .limit(100)
    ).all()
    connections = {
        row.id: row for row in db.scalars(
            select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id)
        )
    }
    installed = set(db.scalars(select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)))
    return {"items": [
        {"id": row.id, "name": row.name, "number": row.number,
         "provider": row.config.get("provider", "openai"), "model_id": row.config.get("model_id"),
         "tool_keys": row.config.get("tool_keys", [])}
        for row in versions
        if (row.config.get("provider", "openai"), row.config.get("model_id")) in MODEL_PRICES
        and set(row.config.get("tool_keys", [])) <= installed
        and (connection := connections.get(row.connection_id))
        and connection.state == "active"
        and connection.credential_generation == row.credential_generation
        and row.config["model_id"] in connection.verified_models
    ]}


@router.post("", status_code=201, response_model=AgentRead, dependencies=[Depends(check_csrf)])
def create_agent(
    workspace_id: uuid.UUID, body: AgentCreate, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id, write=True)
    return service.create_draft(db, workspace_id, body)


@router.get("/{agent_id}", response_model=AgentRead)
def detail(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    return service.serialize(service.get_agent(db, workspace_id, agent_id))


@router.patch("/{agent_id}", response_model=AgentRead, dependencies=[Depends(check_csrf)])
def update(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    authorize(request, db, workspace_id, write=True)
    return service.update_draft(db, workspace_id, agent_id, body)


@router.post("/{agent_id}/archive", dependencies=[Depends(check_csrf)])
def archive(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id, write=True)
    return service.archive_draft(db, workspace_id, agent_id)


@router.post(
    "/{agent_id}/test-snapshots",
    status_code=201,
    response_model=VersionRead,
    dependencies=[Depends(check_csrf)],
)
def snapshot(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: SnapshotCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    version, created = service.snapshot(db, workspace_id, agent_id, member.user_id, body)
    if not created:
        response.status_code = 200
    return version


@router.get("/{agent_id}/readiness", response_model=ReadinessRead)
def readiness(workspace_id: uuid.UUID, agent_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    agent = service.get_agent(db, workspace_id, agent_id)
    config = AgentConfig.model_validate(agent.config).model_dump()
    return {"revision": agent.revision, **assess(db, workspace_id, config, get_connection(db, workspace_id, config["provider"]))}


@router.get("/{agent_id}/versions", response_model=VersionList)
def versions(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    request: Request,
    cursor: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=25, ge=1, le=100),
    purpose: Literal["test", "published"] | None = None,
    db: Session = Depends(get_db),
):
    authorize(request, db, workspace_id)
    return service.list_versions(db, workspace_id, agent_id, cursor, limit, purpose)


@router.get("/{agent_id}/versions/{version_id}", response_model=VersionRead)
def version(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    authorize(request, db, workspace_id)
    return service.get_version(db, workspace_id, agent_id, version_id)


@router.post("/{agent_id}/restore", response_model=AgentRead, dependencies=[Depends(check_csrf)])
def restore(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: RestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    return service.restore_version(db, workspace_id, agent_id, member.user_id, body)


@router.post(
    "/{agent_id}/versions/{version_id}/validate-example",
    response_model=ExampleResult,
    dependencies=[Depends(check_csrf)],
)
def validate_example(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ExampleRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    authorize(request, db, workspace_id, write=True)
    return service.validate_example(
        service.get_version(db, workspace_id, agent_id, version_id), body
    )


@router.post(
    "/{agent_id}/versions",
    status_code=201,
    response_model=VersionRead,
    dependencies=[Depends(check_csrf)],
)
def publish(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: SnapshotCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    version, created = service.publish(db, workspace_id, agent_id, member.user_id, body)
    if not created:
        response.status_code = 200
    return version
