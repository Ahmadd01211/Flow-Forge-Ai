import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.automations import service
from app.modules.automations.models import WorkflowAutomation
from app.modules.deployments.service import throttle
from app.modules.identity.service import check_csrf
from app.modules.workflows.models import WorkflowRun, WorkflowVersion
from app.modules.workflows.runtime import public_run, submit
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/automations", tags=["automations"])
webhooks = APIRouter(prefix="/webhooks", tags=["webhooks"])


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["webhook", "schedule"]
    version_id: uuid.UUID
    interval_seconds: int | None = Field(default=None, ge=60, le=86400, strict=True)
    input: dict | None = None

    @model_validator(mode="after")
    def valid_binding(self):
        if not self.name.strip():
            raise ValueError("Give this automation a name.")
        if self.kind == "schedule" and (self.interval_seconds is None or self.input is None):
            raise ValueError("Schedules need an interval and input object.")
        if self.kind == "webhook" and (self.interval_seconds is not None or self.input is not None):
            raise ValueError("Webhook input comes from each incoming request.")
        return self


class StateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["active", "paused"]


class AutomationRead(BaseModel):
    id: uuid.UUID
    name: str
    version_id: uuid.UUID
    kind: Literal["webhook", "schedule"]
    state: Literal["active", "paused", "archived"]
    interval_seconds: int | None
    next_due_at: datetime | None
    next_attempt_at: datetime | None
    last_due_at: datetime | None
    last_error_code: str | None
    created_at: datetime


class AutomationSecret(AutomationRead):
    webhook_key: str | None


class AutomationList(BaseModel):
    items: list[AutomationRead]


class EligibleTrigger(BaseModel):
    version_id: uuid.UUID
    name: str
    number: int
    kind: Literal["webhook", "schedule"]


class EligibleTriggers(BaseModel):
    items: list[EligibleTrigger]


def admin(db, request, workspace_id):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "An owner or admin manages automations.")
    return member


def find(db, workspace_id, automation_id):
    row = db.scalar(
        select(WorkflowAutomation)
        .where(
            WorkflowAutomation.workspace_id == workspace_id, WorkflowAutomation.id == automation_id
        )
        .with_for_update()
    )
    if not row:
        fail(404, "NOT_FOUND", "Automation not found.")
    return row


@router.get("", response_model=AutomationList)
def listing(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    rows = db.scalars(
        select(WorkflowAutomation)
        .where(
            WorkflowAutomation.workspace_id == workspace_id, WorkflowAutomation.state != "archived"
        )
        .order_by(WorkflowAutomation.created_at.desc())
        .limit(50)
    ).all()
    return {"items": [service.public(row) for row in rows]}


@router.get("/eligible", response_model=EligibleTriggers)
def eligible(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    rows = db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workspace_id == workspace_id)
        .order_by(WorkflowVersion.created_at.desc())
        .limit(100)
    ).all()
    items = []
    for version in rows:
        for kind in ("webhook", "schedule"):
            if any(n["type"] == kind + "_trigger" for n in version.graph["nodes"]):
                items.append(
                    {
                        "version_id": version.id,
                        "name": version.name,
                        "number": version.number,
                        "kind": kind,
                    }
                )
    return {"items": items}


@router.post(
    "", status_code=201, response_model=AutomationSecret, dependencies=[Depends(check_csrf)]
)
def create(
    workspace_id: uuid.UUID, body: AutomationCreate, request: Request, db: Session = Depends(get_db)
):
    member = admin(db, request, workspace_id)
    return service.create(db, workspace_id, member.user_id, body, request.app.state.settings)


@router.patch("/{automation_id}", response_model=AutomationRead, dependencies=[Depends(check_csrf)])
def update(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    body: StateUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    member = admin(db, request, workspace_id)
    row = find(db, workspace_id, automation_id)
    if row.state == "archived":
        fail(409, "AUTOMATION_ARCHIVED", "Create a new automation to resume delivery.")
    if body.state == "active":
        if not service.actor_allowed(db, row):
            fail(
                409,
                "AUTOMATION_OWNER_ACCESS_CHANGED",
                "The creator must still be an owner or admin. Create a new automation under your account.",
            )
        service.target(
            db, workspace_id, row.version_id, row.kind, request.app.state.settings.mcp_catalog_json
        )
    row.state = body.state
    row.next_attempt_at = None
    row.last_error_code = None
    record(
        db, workspace_id, member.user_id, "automation.state_changed", row.id, {"state": row.state}
    )
    db.commit()
    return service.public(row)


@router.post(
    "/{automation_id}/rotate", response_model=AutomationSecret, dependencies=[Depends(check_csrf)]
)
def rotate(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    import secrets

    member = admin(db, request, workspace_id)
    row = find(db, workspace_id, automation_id)
    if row.state == "archived":
        fail(409, "AUTOMATION_ARCHIVED", "Archived webhooks cannot rotate keys.")
    if row.kind != "webhook":
        fail(422, "TRIGGER_MISMATCH", "Only webhooks have a bearer key.")
    raw = "ff_hook_" + secrets.token_urlsafe(32)
    row.key_hash = hashlib.sha256(raw.encode()).hexdigest()
    record(db, workspace_id, member.user_id, "automation.key_rotated", row.id, {})
    db.commit()
    return {**service.public(row), "webhook_key": raw}


@router.delete("/{automation_id}", status_code=204, dependencies=[Depends(check_csrf)])
def archive(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    member = admin(db, request, workspace_id)
    row = find(db, workspace_id, automation_id)
    if row.state != "archived":
        row.state = "archived"
        row.next_attempt_at = None
        record(db, workspace_id, member.user_id, "automation.archived", row.id, {})
        db.commit()
    return Response(status_code=204)


def authenticate(db, request, automation_id):
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ff_hook_") or len(header) > 160:
        fail(401, "WEBHOOK_KEY_INVALID", "A valid webhook bearer key is required.")
    row = db.scalar(
        select(WorkflowAutomation).where(WorkflowAutomation.id == automation_id).with_for_update()
    )
    candidate = hashlib.sha256(header.removeprefix("Bearer ").encode()).hexdigest()
    if not row or row.kind != "webhook" or not hmac.compare_digest(row.key_hash, candidate):
        fail(401, "WEBHOOK_KEY_INVALID", "A valid webhook bearer key is required.")
    if row.state != "active" or not service.actor_allowed(db, row):
        fail(
            409,
            "AUTOMATION_PAUSED",
            "This automation is paused or its creator no longer has access.",
        )
    throttle(request, row.id, "invoke" if request.method == "POST" else "poll")
    return row


@webhooks.post("/{automation_id}", status_code=202)
def delivery(
    automation_id: uuid.UUID,
    body: dict,
    request: Request,
    response: Response,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    row = authenticate(db, request, automation_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    run, created = submit(
        db,
        row.workspace_id,
        row.created_by,
        row.version_id,
        body,
        idempotency_key,
        master,
        mcp_catalog_json=request.app.state.settings.mcp_catalog_json,
        automation_id=row.id,
    )
    if not created:
        response.status_code = 200
    return {"id": run.id, "state": run.state, "replayed": not created}


@webhooks.get("/{automation_id}/runs/{run_id}")
def status(
    automation_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    row = authenticate(db, request, automation_id)
    run = db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.workspace_id == row.workspace_id,
            WorkflowRun.automation_id == row.id,
            WorkflowRun.id == run_id,
        )
    )
    if not run:
        fail(404, "NOT_FOUND", "Run not found for this webhook.")
    return public_run(run, load_master_key(request.app.state.settings.credential_key_path))


@router.get("/{automation_id}/runs")
def history(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    authorize(request, db, workspace_id)
    row = find(db, workspace_id, automation_id)
    runs = db.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.workspace_id == workspace_id, WorkflowRun.automation_id == row.id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(20)
    ).all()
    return {
        "items": [
            {
                "id": run.id,
                "state": run.state,
                "error_code": run.error_code,
                "created_at": run.created_at,
            }
            for run in runs
        ]
    }
