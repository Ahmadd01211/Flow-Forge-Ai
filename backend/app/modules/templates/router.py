import uuid
from copy import deepcopy
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.core.json_contracts import bounded_json
from app.modules.agents.models import Agent
from app.modules.agents.schemas import AgentConfig
from app.modules.agents.service import validate_schemas
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf, current_session
from app.modules.templates.catalog import public_catalog, templates
from app.modules.templates.models import UserTemplate
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.models import Workflow
from app.modules.workflows.schemas import Graph
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.workspaces.service import authorize

router = APIRouter(tags=["templates"])


@router.get("/templates")
def listing(request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    memberships = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    rows = db.scalars(
        select(UserTemplate)
        .where(
            or_(
                UserTemplate.created_by == user.id,
                UserTemplate.visibility == "public",
                (UserTemplate.visibility == "workspace")
                & UserTemplate.workspace_id.in_(memberships),
            )
        )
        .order_by(UserTemplate.created_at.desc(), UserTemplate.id.desc())
    ).all()
    return {"items": public_catalog()["items"] + [summary(row, user.id) for row in rows]}


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
        row = accessible(template_key, request, db)
        item = {**summary(row, member.user_id), **deepcopy(row.definition)}
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
        if not result["valid"] and template_key in templates():
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


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["agent", "workflow"]
    source_id: uuid.UUID
    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="Community", min_length=1, max_length=60)
    visibility: Literal["private", "workspace", "public"] = "private"

    @field_validator("name", "category")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("This field is required")
        return value.strip()


class SharingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visibility: Literal["private", "workspace", "public"]


class TemplatePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["flowforge-template"] = "flowforge-template"
    format_version: Literal[1] = 1
    kind: Literal["agent", "workflow"]
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="Imported", min_length=1, max_length=60)
    definition: dict

    @field_validator("name", "category")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("This field is required")
        return value.strip()


def reserve_template_slot(db, workspace_id):
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    count = db.scalar(select(func.count()).select_from(UserTemplate).where(UserTemplate.workspace_id == workspace_id))
    if count >= 100:
        fail(422, "TEMPLATE_LIMIT", "This workspace has reached its 100 saved-template limit.")


def summary(row, user_id):
    return {
        "key": str(row.id),
        "kind": row.kind,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "template_version": 1,
        "visibility": row.visibility,
        "owned": row.created_by == user_id,
    }


def accessible(key, request, db):
    user, _ = current_session(request, db)
    try:
        template_id = uuid.UUID(key)
    except ValueError:
        fail(404, "TEMPLATE_NOT_FOUND", "Template not found.")
    row = db.get(UserTemplate, template_id)
    if row and (row.created_by == user.id or row.visibility == "public"):
        return row
    if (
        row
        and row.visibility == "workspace"
        and db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == row.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ):
        return row
    fail(404, "TEMPLATE_NOT_FOUND", "Template not found.")


@router.post(
    "/workspaces/{workspace_id}/templates", status_code=201, dependencies=[Depends(check_csrf)]
)
def create_template(
    workspace_id: uuid.UUID, body: TemplateCreate, request: Request, db: Session = Depends(get_db)
):
    _, member = authorize(request, db, workspace_id, write=True)
    model = Agent if body.kind == "agent" else Workflow
    source = db.scalar(
        select(model)
        .where(model.id == body.source_id, model.workspace_id == workspace_id)
        .with_for_update()
    )
    if not source:
        fail(404, "NOT_FOUND", "Source draft not found.")
    if source.revision != body.expected_revision:
        fail(
            409,
            "REVISION_CONFLICT",
            "Save and reload your latest draft before creating a template.",
        )
    definition = portable_definition(
        body.kind, source.config if body.kind == "agent" else source.graph
    )
    reserve_template_slot(db, workspace_id)
    row = UserTemplate(
        workspace_id=workspace_id,
        created_by=member.user_id,
        kind=body.kind,
        name=body.name,
        description=body.description,
        category=body.category,
        visibility=body.visibility,
        definition=definition,
    )
    db.add(row)
    db.flush()
    record(
        db, workspace_id, member.user_id, "template.created", row.id, {"visibility": row.visibility}
    )
    db.commit()
    return summary(row, member.user_id)


@router.get("/templates/{template_key}")
def template_detail(template_key: str, request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    if template_key in templates():
        return templates()[template_key]
    row = accessible(template_key, request, db)
    return {**summary(row, user.id), **row.definition}


@router.patch("/templates/{template_key}", dependencies=[Depends(check_csrf)])
def update_sharing(
    template_key: str, body: SharingUpdate, request: Request, db: Session = Depends(get_db)
):
    row = accessible(template_key, request, db)
    user, _ = current_session(request, db)
    if row.created_by != user.id:
        fail(403, "FORBIDDEN", "Only the template creator can change sharing.")
    authorize(request, db, row.workspace_id, write=True)
    row.visibility = body.visibility
    record(
        db,
        row.workspace_id,
        user.id,
        "template.sharing_changed",
        row.id,
        {"visibility": row.visibility},
    )
    db.commit()
    return summary(row, user.id)


def portable_definition(kind: str, payload: dict) -> dict:
    if kind == "agent":
        config = AgentConfig.model_validate(deepcopy(payload)).model_dump()
        # Provider credentials live outside agent config and are never copied.
        config["model_id"] = ""
        config["mcp_tools"] = []
        config["http_tools"] = []
        definition = {"config": config}
    else:
        graph = Graph.model_validate(deepcopy(payload)).model_dump()
        for node in graph["nodes"]:
            # Published agent and MCP bindings belong to the source workspace.
            # Clear their entire configuration, including cached connection metadata.
            if node["type"] == "for_each":
                node["config"] = {key: value for key, value in node["config"].items() if key in {"source", "max_items", "input_mode"}}
            elif node["type"] in ("agent", "mcp_tool", "http_tool", "subworkflow", "webhook_trigger", "schedule_trigger"):
                node["config"] = {}
        definition = {"graph": graph}
    return definition


@router.get("/templates/{template_key}/export", response_model=TemplatePackage)
def export_template(template_key: str, request: Request, db: Session = Depends(get_db)):
    detail = template_detail(template_key, request, db)
    kind = detail["kind"]
    definition = portable_definition(kind, detail["config" if kind == "agent" else "graph"])
    package = {"format": "flowforge-template", "format_version": 1, "kind": kind, "name": detail["name"], "description": detail["description"], "category": detail["category"], "definition": definition}
    bounded_json(package)
    return package


@router.post("/workspaces/{workspace_id}/templates/import", status_code=201, dependencies=[Depends(check_csrf)])
def import_template(workspace_id: uuid.UUID, body: TemplatePackage, request: Request, db: Session = Depends(get_db)):
    _, member = authorize(request, db, workspace_id, write=True)
    bounded_json(body.model_dump())
    field = "config" if body.kind == "agent" else "graph"
    if set(body.definition) != {field}:
        fail(422, "TEMPLATE_PACKAGE_INVALID", f"This package needs only a {field} definition.")
    # Imported files never restore source connections, published versions or credentials.
    from pydantic import ValidationError
    try:
        definition = portable_definition(body.kind, body.definition[field])
    except (ValidationError, TypeError, ValueError):
        fail(422, "TEMPLATE_PACKAGE_INVALID", "The definition does not match the supported template format.")
    if body.kind == "agent":
        validate_schemas(definition["config"])
    else:
        graph = Graph.model_validate(definition["graph"])
        checked = validate_graph(graph)
        if not checked["valid"]:
            fail(422, "TEMPLATE_GRAPH_INVALID", checked["errors"][0]["message"])
    reserve_template_slot(db, workspace_id)
    row = UserTemplate(workspace_id=workspace_id, created_by=member.user_id, kind=body.kind, name=body.name, description=body.description, category=body.category, visibility="private", definition=definition)
    db.add(row)
    db.flush()
    record(db, workspace_id, member.user_id, "template.imported", row.id, {"kind": body.kind})
    db.commit()
    return summary(row, member.user_id)
