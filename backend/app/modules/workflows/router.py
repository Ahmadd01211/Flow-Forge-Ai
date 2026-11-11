import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf
from app.modules.workflows import runtime
from app.modules.workflows.chat import ChatMessage, chat_version
from app.modules.workflows.checkpoints import rows as checkpoint_rows
from app.modules.workflows.checkpoints import view as checkpoint_view
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion
from app.modules.workflows.node_test import run_node_test
from app.modules.workflows.preview import run_preview, validation
from app.modules.workflows.schemas import (
    DraftCheck,
    Graph,
    NodeTest,
    ValidateRequest,
    WorkflowCallOptions,
    WorkflowCreate,
    WorkflowRunList,
    WorkflowRunRead,
    WorkflowStepDetail,
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


@router.get("/call-options", response_model=WorkflowCallOptions)
def call_options(workspace_id: uuid.UUID, request: Request, exclude_workflow_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    versions = db.scalars(select(WorkflowVersion).where(WorkflowVersion.workspace_id == workspace_id).order_by(WorkflowVersion.created_at.desc(), WorkflowVersion.id.desc()).limit(100)).all()
    items = []
    for version in versions:
        if version.workflow_id == exclude_workflow_id:
            continue
        checked = validation(db, workspace_id, Graph.model_validate(version.graph), request.app.state.settings.mcp_catalog_json, root_workflow_id=version.workflow_id)
        if checked["publishable"]:
            items.append({"id": version.id, "workflow_id": version.workflow_id, "name": version.name, "number": version.number, "input_schema": version.graph["input_schema"], "output_schema": version.graph["output_schema"], "limits": version.graph["limits"], **{key: checked[key] for key in ("expanded_steps", "agent_steps", "has_external", "has_pause")}})
    return {"items": items}


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
        **validation(db, workspace_id, Graph.model_validate(row.graph), request.app.state.settings.mcp_catalog_json, root_workflow_id=workflow_id),
    }


@router.post("/{workflow_id}/chat", status_code=202, dependencies=[Depends(check_csrf)])
def send_chat_message(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: ChatMessage,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    """Start a run of the latest published version with one chat message."""
    _, member = authorize(request, db, workspace_id, write=True)
    find(db, workspace_id, workflow_id)
    version = chat_version(db, workspace_id, workflow_id)
    conversation_id = body.conversation_id or str(uuid.uuid4())
    master = load_master_key(request.app.state.settings.credential_key_path)
    run, created = runtime.submit(
        db, workspace_id, member.user_id, version.id, {"conversation_id": conversation_id, "message": body.message},
        idempotency_key, master, mcp_catalog_json=request.app.state.settings.mcp_catalog_json, source="chat",
    )
    if not created:
        response.status_code = 200
    return {"conversation_id": conversation_id, "version_id": version.id, "run": runtime.public_run(run, master)}


@router.post("/{workflow_id}/check", dependencies=[Depends(check_csrf)])
def check_draft(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: DraftCheck,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Validate an unsaved draft so the builder can show field errors while editing."""
    authorize(request, db, workspace_id)
    find(db, workspace_id, workflow_id)
    if len(json.dumps(body.graph.model_dump()).encode()) > 524288:
        fail(422, "GRAPH_TOO_LARGE", "Workflow graphs must be smaller than 512 KiB.")
    return validation(db, workspace_id, body.graph, request.app.state.settings.mcp_catalog_json, root_workflow_id=workflow_id)


@router.post("/{workflow_id}/nodes/{node_id}/test", dependencies=[Depends(check_csrf)])
def test_draft_node(
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    node_id: str,
    body: NodeTest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    """Run one step of the unsaved draft on sample input."""
    _, member = authorize(request, db, workspace_id, write=True)
    find(db, workspace_id, workflow_id)
    if len(json.dumps(body.graph.model_dump()).encode()) > 524288:
        fail(422, "GRAPH_TOO_LARGE", "Workflow graphs must be smaller than 512 KiB.")
    settings = request.app.state.settings
    return run_node_test(
        db, workspace_id, workflow_id, member.user_id, body.graph, node_id, body.input, body.outputs,
        body.confirm_external, idempotency_key, settings, request.app.state.redis,
    )


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
    return run_preview(db, workspace_id, Graph.model_validate(row.graph), body["input"], mcp_catalog_json=request.app.state.settings.mcp_catalog_json, root_workflow_id=workflow_id)


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


@run_router.post("", status_code=202, response_model=WorkflowRunRead, dependencies=[Depends(check_csrf)])
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


@run_router.get("", response_model=WorkflowRunList)
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
    return {"items": [runtime.public_run(row, master, detail=False) for row in rows]}


@run_router.get("/{run_id}", response_model=WorkflowRunRead)
def workflow_run_detail(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    authorize(request, db, workspace_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return runtime.public_run(runtime.get_run(db, workspace_id, run_id), master)


@run_router.post("/{run_id}/cancel", response_model=WorkflowRunRead, dependencies=[Depends(check_csrf)])
def cancel_workflow_run(
    workspace_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return runtime.public_run(runtime.cancel(db, workspace_id, run_id, member.user_id), master)


class ReplayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_external: bool = Field(default=False, strict=True)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


@run_router.post("/{run_id}/approvals/{pause_id}/decision", response_model=WorkflowRunRead, dependencies=[Depends(check_csrf)])
def approval_decision(workspace_id: uuid.UUID, run_id: uuid.UUID, pause_id: uuid.UUID, body: ApprovalDecision, request: Request, db: Session = Depends(get_db)):
    from app.modules.workflows.pauses import decide
    _, member = authorize(request, db, workspace_id, write=True)
    master = load_master_key(request.app.state.settings.credential_key_path)
    return runtime.public_run(decide(db, workspace_id, run_id, pause_id, member.user_id, body.decision, master), master)


@run_router.get("/{run_id}/steps/{node_id}", response_model=WorkflowStepDetail)
def workflow_step(workspace_id: uuid.UUID, run_id: uuid.UUID, node_id: str, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    runtime.get_run(db, workspace_id, run_id)
    row = next((row for row in checkpoint_rows(db, workspace_id, run_id) if row.node_id == node_id), None)
    if not row:
        fail(404, "NOT_FOUND", "Step evidence not found.")
    return checkpoint_view(row, load_master_key(request.app.state.settings.credential_key_path), include_input=True)


@run_router.post("/{run_id}/replay", status_code=202, response_model=WorkflowRunRead, dependencies=[Depends(check_csrf)])
def replay_workflow(workspace_id: uuid.UUID, run_id: uuid.UUID, body: ReplayInput, request: Request, response: Response,
                    idempotency_key: str = Header(default="", alias="Idempotency-Key"), db: Session = Depends(get_db)):
    _, member = authorize(request, db, workspace_id, write=True)
    source = runtime.get_run(db, workspace_id, run_id)
    if source.state in {"queued", "running", "waiting"}:
        fail(409, "REPLAY_NOT_TERMINAL", "Wait for this run to finish or cancel it before replaying.")
    if not 8 <= len(idempotency_key) <= 128 or any(char.isspace() for char in idempotency_key):
        fail(422, "IDEMPOTENCY_KEY_INVALID", "Use an 8–128 character replay key without spaces.")
    version = db.get(WorkflowVersion, source.version_id)
    checked = validation(db, workspace_id, Graph.model_validate(version.graph), request.app.state.settings.mcp_catalog_json, root_workflow_id=version.workflow_id)
    if checked["has_external"] and not body.confirm_external:
        fail(422, "EXTERNAL_REPLAY_UNCONFIRMED", "Confirm replay first: a new run can repeat external requests and provider charges.")
    master = load_master_key(request.app.state.settings.credential_key_path)
    value = json.loads(decrypt_secret(master, workspace_id, source.id, 1, source.input_nonce, source.input_ciphertext))
    run, created = runtime.submit(db, workspace_id, member.user_id, source.version_id, value,
                                  f"replay:{source.id}:" + hashlib.sha256(idempotency_key.encode()).hexdigest(),
                                  master, mcp_catalog_json=request.app.state.settings.mcp_catalog_json, commit=False, source="replay")
    if created:
        record(db, workspace_id, member.user_id, "workflow_run.replayed", run.id, {"source_run_id": str(source.id)})
    else:
        response.status_code = 200
    db.commit()
    return runtime.public_run(run, master)
