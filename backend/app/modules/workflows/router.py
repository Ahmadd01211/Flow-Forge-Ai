import json
import uuid

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.modules.identity.service import check_csrf
from app.modules.workflows import runtime
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion
from app.modules.workflows.preview import run_preview, validation
from app.modules.workflows.schemas import (
    Graph,
    ValidateRequest,
    WorkflowCreate,
    WorkflowUpdate,
    initial_graph,
)
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/workflows", tags=["workflows"])


def find(
    db: Session, workspace_id: uuid.UUID, workflow_id: uuid.UUID, lock: bool = False
) -> Workflow:
    query = select(Workflow).where(
        Workflow.workspace_id == workspace_id, Workflow.id == workflow_id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        fail(404, "NOT_FOUND", "Workflow not found.")
    return row


def serialize(row: Workflow) -> dict:
    return {
        key: getattr(row, key)
        for key in ["id", "workspace_id", "name", "description", "graph", "revision", "updated_at"]
    }


@router.get("")
def listing(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    rows = db.scalars(
        select(Workflow)
        .where(Workflow.workspace_id == workspace_id)
        .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
        .limit(100)
    ).all()
    return {"items": [serialize(row) for row in rows], "next_cursor": None}


@router.post("", status_code=201, dependencies=[Depends(check_csrf)])
def create(
    workspace_id: uuid.UUID, body: WorkflowCreate, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id, write=True)
    row = Workflow(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        graph=initial_graph(),
    )
    db.add(row)
    db.commit()
    return serialize(row)


@router.get("/{workflow_id}")
def detail(
    workspace_id: uuid.UUID, workflow_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    return serialize(find(db, workspace_id, workflow_id))


@router.patch("/{workflow_id}", dependencies=[Depends(check_csrf)])
def update(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    authorize(request, db, workspace_id, write=True)
    row = find(db, workspace_id, workflow_id, lock=True)
    if row.revision != body.expected_revision:
        fail(409, "REVISION_CONFLICT", "This workflow changed elsewhere. Reload before saving.")
    graph = body.graph.model_dump()
    if len(json.dumps(graph).encode()) > 524288:
        fail(422, "GRAPH_TOO_LARGE", "Workflow graphs must be smaller than 512 KiB.")
    row.name, row.description, row.graph = body.name, body.description, graph
    row.revision += 1
    db.commit()
    return serialize(row)


@router.post("/{workflow_id}/validate", dependencies=[Depends(check_csrf)])
def validate(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: ValidateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    authorize(request, db, workspace_id, write=True)
    row = find(db, workspace_id, workflow_id)
    if row.revision != body.expected_revision:
        fail(409, "REVISION_CONFLICT", "Save and reload the latest draft before validating.")
    return {
        "revision": row.revision,
        **validation(db, workspace_id, Graph.model_validate(row.graph), request.app.state.settings.mcp_catalog_json),
    }


@router.post("/{workflow_id}/preview", dependencies=[Depends(check_csrf)])
def preview(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    authorize(request, db, workspace_id, write=True)
    if (
        set(body) != {"expected_revision", "input"}
        or not isinstance(body["expected_revision"], int)
        or not isinstance(body["input"], dict)
    ):
        fail(422, "PREVIEW_INPUT_INVALID", "Provide expected_revision and an input object.")
    row = find(db, workspace_id, workflow_id)
    if row.revision != body["expected_revision"]:
        fail(409, "REVISION_CONFLICT", "Save the latest workflow draft before previewing.")
    return run_preview(db, workspace_id, Graph.model_validate(row.graph), body["input"], mcp_catalog_json=request.app.state.settings.mcp_catalog_json)


@router.post("/{workflow_id}/versions", status_code=201, dependencies=[Depends(check_csrf)])
def publish_version(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: ValidateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    return runtime.public_version(
        runtime.publish(db, workspace_id, workflow_id, member.user_id, body.expected_revision, request.app.state.settings.mcp_catalog_json)
    )


@router.get("/{workflow_id}/versions")
def list_versions(
    workspace_id: uuid.UUID, workflow_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    find(db, workspace_id, workflow_id)
    rows = db.scalars(
        select(WorkflowVersion)
        .where(
            WorkflowVersion.workspace_id == workspace_id, WorkflowVersion.workflow_id == workflow_id
        )
        .order_by(WorkflowVersion.number.desc())
        .limit(50)
    ).all()
    return {"items": [runtime.public_version(row) for row in rows]}


run_router = APIRouter(prefix="/workspaces/{workspace_id}/workflow-runs", tags=["workflow-runs"])


@run_router.post("", status_code=202, dependencies=[Depends(check_csrf)])
def submit_workflow_run(
    workspace_id: uuid.UUID,
    body: dict,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    if set(body) != {"version_id", "input"} or not isinstance(body["input"], dict):
        fail(422, "RUN_INPUT_INVALID", "Provide version_id and an input object.")
    try:
        version_id = uuid.UUID(str(body["version_id"]))
    except (ValueError, TypeError):
        fail(422, "RUN_INPUT_INVALID", "Provide a valid version_id.")
    master = load_master_key(request.app.state.settings.credential_key_path)
    run, created = runtime.submit(
        db, workspace_id, member.user_id, version_id, body["input"], idempotency_key, master,
        mcp_catalog_json=request.app.state.settings.mcp_catalog_json,
    )
    if not created:
        response.status_code = 200
    return runtime.public_run(run, master)


@run_router.get("")
def list_workflow_runs(
    workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    rows = db.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.workspace_id == workspace_id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .limit(50)
    ).all()
    return {"items": [runtime.public_run(row, master) for row in rows]}


@run_router.get("/{run_id}")
def workflow_run_detail(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return runtime.public_run(runtime.get_run(db, workspace_id, run_id), master)


@run_router.post("/{run_id}/cancel", dependencies=[Depends(check_csrf)])
def cancel_workflow_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return runtime.public_run(runtime.cancel(db, workspace_id, run_id, member.user_id), master)
