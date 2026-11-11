"""Encrypted regression examples and deterministic scoring of observed runs; no model calls."""

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKeyConstraint, LargeBinary, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.db import Base, get_db
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.agents import service
from app.modules.audit.service import record
from app.modules.executions.models import AgentRun
from app.modules.identity.service import check_csrf
from app.modules.workspaces.service import authorize


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suite"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    input: dict
    expected_output: dict


class SuiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=20)


class SuiteEvaluate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: uuid.UUID


class SuitePublic(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class SuiteList(BaseModel):
    items: list[SuitePublic]


class CaseResult(BaseModel):
    name: str
    status: Literal["passed", "failed", "untested", "contract_failed"]
    run_id: uuid.UUID | None
    contract_valid: bool


class EvaluationResult(BaseModel):
    version_id: uuid.UUID
    suite_id: uuid.UUID
    items: list[CaseResult]
    model_called: Literal[False] = False
    scope: Literal["observed_exact_output"] = "observed_exact_output"
    history_limit: Literal[100] = 100
    passed: int
    total: int


router = APIRouter(
    prefix="/workspaces/{workspace_id}/agents/{agent_id}/evaluations", tags=["agent-evaluations"]
)


@router.get("", response_model=SuiteList)
def listing(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    authorize(request, db, workspace_id)
    service.get_agent(db, workspace_id, agent_id)
    rows = db.scalars(
        select(EvaluationSuite)
        .where(EvaluationSuite.workspace_id == workspace_id, EvaluationSuite.agent_id == agent_id)
        .order_by(EvaluationSuite.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [{"id": s.id, "name": s.name, "created_at": s.created_at} for s in rows]}


@router.post("", status_code=201, response_model=SuitePublic, dependencies=[Depends(check_csrf)])
def create(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: SuiteCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id, write=True)
    service.get_agent(db, workspace_id, agent_id)
    data = [c.model_dump() for c in body.cases]
    bounded_json(data, max_bytes=65536)
    suite_id = uuid.uuid4()
    nonce, ciphertext = encrypt_secret(
        load_master_key(request.app.state.settings.credential_key_path),
        workspace_id,
        suite_id,
        1,
        json.dumps(data),
    )
    row = EvaluationSuite(
        id=suite_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        name=body.name,
        nonce=nonce,
        ciphertext=ciphertext,
    )
    db.add(row)
    record(
        db,
        workspace_id,
        member.user_id,
        "agent.evaluation_created",
        suite_id,
        {"agent_id": str(agent_id), "case_count": len(data)},
    )
    db.commit()
    return {"id": row.id, "name": row.name, "created_at": row.created_at}


@router.post(
    "/{suite_id}/evaluate", response_model=EvaluationResult, dependencies=[Depends(check_csrf)]
)
def evaluate(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    suite_id: uuid.UUID,
    body: SuiteEvaluate,
    request: Request,
    db: Session = Depends(get_db),
):
    authorize(request, db, workspace_id)
    version = service.get_version(db, workspace_id, agent_id, body.version_id)
    suite = db.scalar(
        select(EvaluationSuite).where(
            EvaluationSuite.id == suite_id,
            EvaluationSuite.workspace_id == workspace_id,
            EvaluationSuite.agent_id == agent_id,
        )
    )
    if not suite:
        fail(404, "NOT_FOUND", "Regression suite not found.")
    master = load_master_key(request.app.state.settings.credential_key_path)
    cases = json.loads(
        decrypt_secret(master, workspace_id, suite.id, 1, suite.nonce, suite.ciphertext)
    )
    runs = db.scalars(
        select(AgentRun)
        .where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.version_id == version.id,
            AgentRun.state == "completed",
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(100)
    ).all()
    observed = {}
    for run in runs:
        input_value = json.loads(
            decrypt_secret(master, workspace_id, run.id, 1, run.input_nonce, run.input_ciphertext)
        )
        key = json.dumps(input_value, sort_keys=True, separators=(",", ":"))
        if key not in observed and run.output_nonce and run.output_ciphertext:
            observed[key] = (
                run.id,
                json.loads(
                    decrypt_secret(
                        master, workspace_id, run.id, 2, run.output_nonce, run.output_ciphertext
                    )
                ),
            )
    results = []
    for case in cases:
        errors = example_errors(
            version.config["input_schema"], case["input"], "input"
        ) + example_errors(
            version.config["output_schema"], case["expected_output"], "expected_output"
        )
        found = observed.get(json.dumps(case["input"], sort_keys=True, separators=(",", ":")))
        status = (
            "contract_failed"
            if errors
            else "untested"
            if not found
            else "passed"
            if found[1] == case["expected_output"]
            else "failed"
        )
        results.append(
            {
                "name": case["name"],
                "status": status,
                "run_id": str(found[0]) if found else None,
                "contract_valid": not errors,
            }
        )
    return {
        "version_id": version.id,
        "suite_id": suite.id,
        "items": results,
        "model_called": False,
        "scope": "observed_exact_output",
        "history_limit": 100,
        "passed": sum(r["status"] == "passed" for r in results),
        "total": len(results),
    }
