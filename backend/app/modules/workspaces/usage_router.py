import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf
from app.modules.workspaces.router import administration
from app.modules.workspaces.service import authorize
from app.modules.workspaces.usage import summary

router = APIRouter(prefix="/workspaces/{workspace_id}/usage", tags=["usage"])


class UsageRead(BaseModel):
    window_start: datetime
    resets_at: datetime
    daily_budget_usd: str
    daily_run_limit: int
    active_run_limit: int
    revision: int
    accepted_runs: int
    active_runs: int
    measured_usd: str
    uncertain_usd: str
    reserved_usd: str
    committed_usd: str
    remaining_usd: str
    input_tokens: int
    output_tokens: int


class UsageLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    daily_budget_usd: str = Field(pattern=r"^(0|[1-9][0-9]{0,4})(\.[0-9]{1,8})?$")
    daily_run_limit: int = Field(ge=1, le=10000, strict=True)
    active_run_limit: int = Field(ge=1, le=4, strict=True)


@router.get("", response_model=UsageRead)
def usage(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    workspace, _ = authorize(request, db, workspace_id)
    return summary(db, workspace)


@router.patch("", response_model=UsageRead, dependencies=[Depends(check_csrf)])
def limits(
    workspace_id: uuid.UUID, body: UsageLimits, request: Request, db: Session = Depends(get_db)
):
    workspace, member = administration(workspace_id, request, db)
    if workspace.quota_revision != body.expected_revision:
        fail(409, "REVISION_CONFLICT", "Budget settings changed elsewhere. Refresh before saving.")
    amount = Decimal(body.daily_budget_usd)
    if amount > 10000:
        fail(422, "BUDGET_TOO_LARGE", "Daily budget must be between $0 and $10,000.")
    workspace.daily_budget_usd = amount
    workspace.daily_run_limit = body.daily_run_limit
    workspace.active_run_limit = body.active_run_limit
    workspace.quota_revision += 1
    record(
        db,
        workspace_id,
        member.user_id,
        "workspace.limits_changed",
        workspace_id,
        {
            "revision": workspace.quota_revision,
            "daily_budget_usd": str(amount),
            "daily_run_limit": body.daily_run_limit,
            "active_run_limit": body.active_run_limit,
        },
    )
    db.commit()
    return summary(db, workspace)
