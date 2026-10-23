import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.agents.models import AgentVersion
from app.modules.audit.service import record
from app.modules.executions.models import AgentRun
from app.modules.executions.schemas import RunCreate
from app.modules.integrations.models import IntegrationConnection
from app.modules.tools.models import ToolInstallation
from app.modules.workspaces.models import Workspace
from app.providers.profiles import MODEL_PRICES as MODEL_PRICES

MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_BYTES = 120_000


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def public_run(run: AgentRun, master: bytes) -> dict:
    output = None
    if run.output_nonce and run.output_ciphertext:
        output = json.loads(
            decrypt_secret(
                master, run.workspace_id, run.id, 2, run.output_nonce, run.output_ciphertext
            )
        )
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "version_id": run.version_id,
        "state": run.state,
        "output": output,
        "error_code": run.error_code,
        "cancel_requested": run.cancel_requested_at is not None,
        "model_started": run.model_started_at is not None,
        "reserved_max_usd": str(run.reserved_max_usd),
        "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
        "uncertain_cost_usd": str(run.uncertain_cost_usd)
        if run.uncertain_cost_usd is not None
        else None,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def submit(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: RunCreate,
    idempotency_key: str,
    master: bytes,
    deployment_id: uuid.UUID | None = None,
) -> tuple[AgentRun, bool]:
    if not 8 <= len(idempotency_key) <= 128 or any(c.isspace() for c in idempotency_key):
        fail(
            422, "IDEMPOTENCY_KEY_INVALID", "Use an 8–128 character idempotency key without spaces."
        )
    bounded_json(body.input, max_bytes=MAX_INPUT_BYTES)
    key_hash = digest(f"{deployment_id}:{idempotency_key}" if deployment_id else idempotency_key)
    request_hash = digest(canonical(body.model_dump(mode="json")))
    # Serialize duplicate submissions even when they arrive before either insert.
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    existing = db.scalar(
        select(AgentRun).where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.requested_by == actor_id,
            AgentRun.idempotency_key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            fail(409, "IDEMPOTENCY_CONFLICT", "This key was already used for another request.")
        return existing, False
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.workspace_id == workspace_id,
                AgentRun.state.in_(["queued", "running"]),
            )
        )
        or 0
    )
    if active_count >= 2:
        fail(429, "RUN_CONCURRENCY_LIMIT", "This workspace already has two active runs.")
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.workspace_id == workspace_id,
            AgentVersion.id == body.version_id,
            AgentVersion.purpose == "published",
        )
    )
    if not version:
        fail(404, "NOT_FOUND", "Published agent version not found.")
    config = version.config
    model = (config.get("provider", "openai"), config.get("model_id"))
    if model not in MODEL_PRICES:
        fail(422, "RUNTIME_UNSUPPORTED", "This model does not have a live execution adapter yet.")
    if config.get("tool_keys"):
        installed = set(
            db.scalars(
                select(ToolInstallation.tool_key).where(
                    ToolInstallation.workspace_id == workspace_id
                )
            )
        )
        if set(config["tool_keys"]) - installed:
            fail(
                409,
                "TOOL_APPROVAL_REVOKED",
                "A tool approved for this agent version is no longer available.",
            )
    input_price, output_price = MODEL_PRICES[model]
    if errors := example_errors(config["input_schema"], body.input, "input"):
        fail(422, "INPUT_SCHEMA_INVALID", errors[0]["message"])
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.id == version.connection_id,
        )
    )
    if (
        not connection
        or connection.state != "active"
        or connection.credential_generation != version.credential_generation
        or config["model_id"] not in connection.verified_models
    ):
        fail(
            409,
            "CREDENTIAL_CHANGED",
            "The published version uses an older or revoked credential. Publish a new version.",
        )
    input_text = canonical(body.input)
    estimated_input_bytes = (
        len((config["instructions"] + input_text + canonical(config["output_schema"])).encode())
        + 4096
    )
    if estimated_input_bytes > MAX_INPUT_BYTES:
        fail(
            422,
            "INPUT_TOO_LARGE",
            "Agent input and instructions exceed the supported execution size.",
        )
    budget = Decimal(config["limits"]["max_cost_usd"])
    input_reserve = input_price * estimated_input_bytes
    max_output = min(MAX_OUTPUT_TOKENS, config["limits"].get("max_output_tokens", 4096), int((budget - input_reserve) / output_price))
    if max_output < 16:
        fail(
            422,
            "BUDGET_TOO_SMALL",
            "The run budget cannot cover the input and minimum output allowance.",
        )
    # Multi-turn tool runs may consume the whole configured budget across calls.
    reserved = budget if config.get("tool_keys") else input_reserve + output_price * max_output
    run_id = uuid.uuid4()
    nonce, encrypted = encrypt_secret(master, workspace_id, run_id, 1, input_text)
    run = AgentRun(
        id=run_id,
        workspace_id=workspace_id,
        version_id=version.id,
        deployment_id=deployment_id,
        requested_by=actor_id,
        idempotency_key_hash=key_hash,
        request_hash=request_hash,
        state="queued",
        input_nonce=nonce,
        input_ciphertext=encrypted,
        deadline_at=datetime.now(UTC) + timedelta(seconds=config["limits"]["timeout_seconds"]),
        max_output_tokens=max_output,
        reserved_max_usd=reserved,
    )
    db.add(run)
    record(
        db, workspace_id, actor_id, "agent_run.submitted", run.id, {"version_id": str(version.id)}
    )
    db.commit()
    return run, True


def get_run(
    db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, lock: bool = False
) -> AgentRun:
    query = select(AgentRun).where(AgentRun.workspace_id == workspace_id, AgentRun.id == run_id)
    run = db.scalar(query.with_for_update() if lock else query)
    if not run:
        fail(404, "NOT_FOUND", "Run not found.")
    return run


def cancel(
    db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID
) -> AgentRun:
    run = get_run(db, workspace_id, run_id, lock=True)
    if run.state in ("completed", "failed", "cancelled"):
        return run
    now = datetime.now(UTC)
    run.cancel_requested_at = now
    if run.state == "queued" or not run.model_started_at:
        run.state = "cancelled"
        run.finished_at = now
    record(db, workspace_id, actor_id, "agent_run.cancel_requested", run.id, {"state": run.state})
    db.commit()
    return run
