import json
import logging
import time
import uuid

from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import make_sessions
from app.modules.agents.router import router as agents
from app.modules.deployments.router import invoke as hosted_invocation
from app.modules.deployments.router import manage as deployments
from app.modules.executions.router import router as executions
from app.modules.identity.router import router as identity
from app.modules.integrations.router import router as integrations
from app.modules.mcp.router import router as mcp
from app.modules.templates.router import router as templates
from app.modules.tools.router import router as tools
from app.modules.workflows.router import router as workflows
from app.modules.workflows.router import run_router as workflow_runs
from app.modules.workspaces.router import router as workspaces

log = logging.getLogger("flowforge")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="FlowForge AI", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.settings = settings or Settings()
    app.state.sessions = make_sessions(app.state.settings.database_url)
    app.state.redis = Redis.from_url(
        app.state.settings.redis_url, socket_connect_timeout=1, socket_timeout=1
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        start = time.monotonic()
        if int(request.headers.get("content-length", "0") or "0") > 600000:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "Request is too large.",
                        "request_id": request.state.request_id,
                    }
                },
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        log.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                }
            )
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {**detail, "request_id": request.state.request_id}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [
            {"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "Check the highlighted fields.",
                    "details": details,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.error(
            json.dumps(
                {
                    "event": "request_failed",
                    "request_id": request.state.request_id,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong. Use the request ID when reporting this error.",
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "ok", "service": "flowforge-api"}

    @app.get("/health/ready")
    def ready() -> dict:
        try:
            with app.state.sessions() as db:
                installed = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                if installed != ScriptDirectory("migrations").get_current_head():
                    raise RuntimeError("Schema revision mismatch")
        except Exception:
            raise HTTPException(
                503, {"code": "NOT_READY", "message": "Database or migrations unavailable."}
            ) from None
        return {"status": "ready"}

    for router in [
        identity,
        workspaces,
        agents,
        integrations,
        tools,
        mcp,
        workflows,
        workflow_runs,
        executions,
        templates,
        deployments,
        hosted_invocation,
    ]:
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
