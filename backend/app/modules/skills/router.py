import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.agents.models import Agent, user_built
from app.modules.audit.service import record
from app.modules.identity.service import check_csrf
from app.modules.skills import service
from app.modules.skills.catalog import STARTERS
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.schemas import SkillPublish, SkillUpdate, SkillVersionRead, SkillWrite
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/skills", tags=["skills"])


def _used_by(db: Session, workspace_id: uuid.UUID) -> dict[str, list[str]]:
    """Names of the user-built agents whose draft attaches each skill."""
    used: dict[str, list[str]] = {}
    for agent in db.scalars(select(Agent).where(Agent.workspace_id == workspace_id, Agent.archived_at.is_(None), user_built()).limit(200)):
        for grant in agent.config.get("skills", []):
            used.setdefault(grant["skill_id"], []).append(agent.name)
    return used


@router.get("")
def listing(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    skills = db.scalars(
        select(Skill).where(Skill.workspace_id == workspace_id, Skill.archived_at.is_(None)).order_by(Skill.updated_at.desc()).limit(200)
    ).all()
    latest = service.latest_versions(db, [skill.id for skill in skills])
    used = _used_by(db, workspace_id)
    return {"items": [
        {**service.serialize(skill, latest.get(skill.id)), "used_by": used.get(str(skill.id), []),
         "tool_count": sum(len(skill.config.get(key, [])) for key in ("tool_keys", "mcp_tools", "http_tools"))}
        for skill in skills
    ]}


@router.get("/starters")
def starters(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    added = set(db.scalars(select(Skill.starter_key).where(Skill.workspace_id == workspace_id, Skill.archived_at.is_(None), Skill.starter_key.is_not(None))))
    return {"items": [
        {"key": key, "group": item["group"], "emoji": item["emoji"], "name": item["name"], "description": item["description"], "added": key in added}
        for key, item in STARTERS.items()
    ]}


@router.post("/starters/{key}", status_code=201, dependencies=[Depends(check_csrf)])
def add_starter(workspace_id: uuid.UUID, key: str, request: Request, db: Session = Depends(get_db)) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    skill = service.add_starter(db, workspace_id, key, member.user_id)
    record(db, workspace_id, member.user_id, "skill.created", skill.id, {"starter": key})
    db.commit()
    return service.serialize(skill)


@router.post("", status_code=201, dependencies=[Depends(check_csrf)])
def create(workspace_id: uuid.UUID, body: SkillWrite, request: Request, db: Session = Depends(get_db)) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    skill = Skill(workspace_id=workspace_id, name=body.name, description=body.description, config=body.config.model_dump(), created_by=member.user_id)
    db.add(skill)
    db.flush()
    record(db, workspace_id, member.user_id, "skill.created", skill.id, {})
    db.commit()
    return service.serialize(skill)


@router.get("/{skill_id}")
def detail(workspace_id: uuid.UUID, skill_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    skill = service.get_skill(db, workspace_id, skill_id)
    return {**service.serialize(skill, service.latest_versions(db, [skill.id]).get(skill.id)), "used_by": _used_by(db, workspace_id).get(str(skill.id), [])}


@router.patch("/{skill_id}", dependencies=[Depends(check_csrf)])
def update(workspace_id: uuid.UUID, skill_id: uuid.UUID, body: SkillUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id, write=True)
    skill = service.get_skill(db, workspace_id, skill_id, lock=True)
    if skill.revision != body.expected_revision:
        fail(409, "REVISION_CONFLICT", "This skill changed elsewhere. Reload before saving.")
    skill.name, skill.description, skill.config = body.name, body.description, body.config.model_dump()
    skill.revision += 1
    db.commit()
    return service.serialize(skill, service.latest_versions(db, [skill.id]).get(skill.id))


@router.post("/{skill_id}/publish", status_code=201, dependencies=[Depends(check_csrf)])
def publish(workspace_id: uuid.UUID, skill_id: uuid.UUID, body: SkillPublish, request: Request, db: Session = Depends(get_db)) -> dict:
    _, member = authorize(request, db, workspace_id, write=True)
    skill = service.get_skill(db, workspace_id, skill_id, lock=True)
    if skill.revision != body.expected_revision:
        fail(409, "REVISION_CONFLICT", "Save the latest draft before publishing.")
    version, created = service.publish(db, workspace_id, skill, member.user_id, request.app.state.settings.mcp_catalog_json)
    if created:
        record(db, workspace_id, member.user_id, "skill.published", version.id, {"skill_id": str(skill.id), "number": version.number})
    db.commit()
    return {"id": version.id, "number": version.number, "created": created}


@router.get("/{skill_id}/versions")
def versions(workspace_id: uuid.UUID, skill_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    service.get_skill(db, workspace_id, skill_id)
    rows = db.scalars(select(SkillVersion).where(SkillVersion.workspace_id == workspace_id, SkillVersion.skill_id == skill_id).order_by(SkillVersion.number.desc()).limit(50)).all()
    return {"items": [SkillVersionRead.model_validate(row).model_dump() for row in rows]}


@router.post("/{skill_id}/archive", dependencies=[Depends(check_csrf)])
def archive(workspace_id: uuid.UUID, skill_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    from datetime import UTC, datetime

    _, member = authorize(request, db, workspace_id, write=True)
    skill = service.get_skill(db, workspace_id, skill_id, lock=True)
    skill.archived_at = datetime.now(UTC)
    record(db, workspace_id, member.user_id, "skill.archived", skill.id, {})
    db.commit()
    return {"id": skill.id, "archived": True}
