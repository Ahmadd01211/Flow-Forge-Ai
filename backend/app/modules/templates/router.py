import uuid
from copy import deepcopy

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.agents.models import Agent
from app.modules.agents.schemas import AgentConfig
from app.modules.agents.service import validate_schemas
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf, current_session
from app.modules.templates.catalog import public_catalog, templates
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.models import Workflow
from app.modules.workflows.schemas import Graph
from app.modules.workspaces.service import authorize

router = APIRouter(tags=["templates"])


@router.get("/templates")
def listing(request: Request, db: Session = Depends(get_db)):
    current_session(request, db)
    return public_catalog()


@router.post(
    "/workspaces/{workspace_id}/templates/{template_key}/instantiate",
    status_code=201,
    dependencies=[Depends(check_csrf)],
)
def instantiate(
    workspace_id: uuid.UUID, template_key: str, request: Request, db: Session = Depends(get_db)
):
    _, member = authorize(request, db, workspace_id, write=True)
    item = templates().get(template_key)
    if not item:
        fail(404, "TEMPLATE_NOT_FOUND", "Template not found.")
    if item["kind"] == "agent":
        config = AgentConfig.model_validate(deepcopy(item["config"])).model_dump()
        validate_schemas(config)
        row = Agent(
            workspace_id=workspace_id,
            name=item["name"],
            description=item["description"],
            config=config,
        )
    else:
        graph = Graph.model_validate(deepcopy(item["graph"]))
        result = validate_graph(graph)
        if not result["valid"]:
            fail(503, "TEMPLATE_INVALID", "This workflow template is temporarily unavailable.")
        row = Workflow(
            workspace_id=workspace_id,
            name=item["name"],
            description=item["description"],
            graph=graph.model_dump(),
        )
    db.add(row)
    db.flush()
    record(
        db,
        workspace_id,
        member.user_id,
        "template.instantiated",
        row.id,
        {
            "template_key": template_key,
            "kind": item["kind"],
            "template_version": item["template_version"],
        },
    )
    db.commit()
    return {"kind": item["kind"], "id": row.id, "template_key": template_key}
