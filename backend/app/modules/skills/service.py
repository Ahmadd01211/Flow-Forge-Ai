"""Skills: drafts people edit, immutable versions agents pin when they are published."""

import hashlib
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.modules.skills.catalog import STARTERS
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.schemas import SkillConfig
from app.modules.tools.catalog import CATALOG


def get_skill(db: Session, workspace_id: uuid.UUID, skill_id: uuid.UUID, lock: bool = False) -> Skill:
    query = select(Skill).where(Skill.workspace_id == workspace_id, Skill.id == skill_id, Skill.archived_at.is_(None))
    skill = db.scalar(query.with_for_update() if lock else query)
    if not skill:
        fail(404, "NOT_FOUND", "Skill not found.")
    return skill


def latest_versions(db: Session, skill_ids: list) -> dict:
    ids = [uuid.UUID(str(identity)) for identity in skill_ids]
    if not ids:
        return {}
    return {
        version.skill_id: version
        for version in db.scalars(
            select(SkillVersion)
            .where(SkillVersion.skill_id.in_(ids))
            .distinct(SkillVersion.skill_id)
            .order_by(SkillVersion.skill_id, SkillVersion.number.desc())
        ).all()
    }


def serialize(skill: Skill, version: SkillVersion | None = None) -> dict:
    return {
        "id": skill.id, "name": skill.name, "description": skill.description, "config": skill.config,
        "revision": skill.revision, "starter_key": skill.starter_key, "updated_at": skill.updated_at,
        "status": "draft" if not version else "published" if version.source_revision == skill.revision else "changed",
        "latest": {"version_id": version.id, "number": version.number} if version else None,
    }


def check_tools(db: Session, workspace_id: uuid.UUID, config: dict, raw_catalog: str) -> None:
    """Fail early when a skill asks for tools the workspace can't grant right now."""
    unknown = set(config["tool_keys"]) - set(CATALOG)
    if unknown:
        fail(422, "SKILL_TOOL_UNKNOWN", "Choose built-in tools from the Tool Registry.")
    if config["mcp_tools"]:
        from app.modules.mcp.agent_grants import pin
        pin(db, workspace_id, config["mcp_tools"], raw_catalog)
    if config["http_tools"]:
        from app.modules.http_tools.service import pin as pin_http
        pin_http(db, workspace_id, config["http_tools"])


def publish(db: Session, workspace_id: uuid.UUID, skill: Skill, actor_id: uuid.UUID, raw_catalog: str) -> tuple[SkillVersion, bool]:
    config = SkillConfig.model_validate(skill.config).model_dump()
    if not config["instructions"].strip():
        fail(422, "SKILL_INSTRUCTIONS_REQUIRED", "Write the skill's instructions before publishing it.")
    check_tools(db, workspace_id, config, raw_catalog)
    latest = latest_versions(db, [skill.id]).get(skill.id)
    digest = hashlib.sha256(json.dumps([skill.name, skill.description, config], sort_keys=True).encode()).hexdigest()
    if latest and latest.config_hash == digest:
        return latest, False
    version = SkillVersion(
        workspace_id=workspace_id, skill_id=skill.id,
        number=(db.scalar(select(func.max(SkillVersion.number)).where(SkillVersion.skill_id == skill.id)) or 0) + 1,
        source_revision=skill.revision, name=skill.name, description=skill.description,
        config=config, config_hash=digest, created_by=actor_id,
    )
    db.add(version)
    db.flush()
    return version, True


def pin_for_agent(db: Session, workspace_id: uuid.UUID, config: dict) -> dict:
    """Pin each attached skill's latest published version and merge the tools it needs.

    Returns a new agent config; callers pin the merged MCP and HTTP grants afterwards as usual.
    """
    grants = config.get("skills") or []
    if not grants:
        return config
    skills = {
        skill.id: skill
        for skill in db.scalars(select(Skill).where(
            Skill.workspace_id == workspace_id, Skill.id.in_([uuid.UUID(grant["skill_id"]) for grant in grants]),
        )).all()
    }
    versions = latest_versions(db, list(skills))
    pinned, merged = [], {key: list(config.get(key) or []) for key in ("tool_keys", "mcp_tools", "http_tools")}
    for grant in grants:
        identity = uuid.UUID(grant["skill_id"])
        skill = skills.get(identity)
        if not skill or skill.archived_at:
            fail(422, "SKILL_UNAVAILABLE", f"The skill “{grant.get('name') or grant['skill_id']}” was archived or removed. Detach it.")
        version = versions.get(identity)
        if not version:
            fail(422, "SKILL_UNPUBLISHED", f"Publish the skill “{skill.name}” before using it.")
        pinned.append({
            "skill_id": str(skill.id), "version_id": str(version.id), "number": version.number,
            "name": version.name, "description": version.description,
            "instructions": version.config["instructions"], "examples": version.config["examples"],
        })
        for key in version.config["tool_keys"]:
            if key not in merged["tool_keys"]:
                merged["tool_keys"].append(key)
        for tool in version.config["mcp_tools"]:
            if not any(item["server_id"] == tool["server_id"] and item["tool_name"] == tool["tool_name"] for item in merged["mcp_tools"]):
                merged["mcp_tools"].append(tool)
        for tool in version.config["http_tools"]:
            if not any(item["tool_id"].lower() == tool["tool_id"].lower() for item in merged["http_tools"]):
                merged["http_tools"].append(tool)
    return {**config, **merged, "skills": pinned}


def stale(db: Session, config: dict) -> bool:
    """True when a pinned skill has a newer published version than the one frozen in `config`."""
    grants = config.get("skills") or []
    if not grants:
        return False
    latest = latest_versions(db, [grant["skill_id"] for grant in grants])
    for grant in grants:
        version = latest.get(uuid.UUID(grant["skill_id"]))
        if not version or str(version.id) != grant.get("version_id"):
            return True
    return False


def check_attached(db: Session, workspace_id: uuid.UUID, config: dict) -> list[str]:
    """Readiness messages for attached skills, without pinning anything."""
    try:
        pin_for_agent(db, workspace_id, config)
    except HTTPException as exc:
        return [exc.detail["message"]]
    return []


def add_starter(db: Session, workspace_id: uuid.UUID, key: str, actor_id: uuid.UUID) -> Skill:
    starter = STARTERS.get(key)
    if not starter:
        fail(404, "NOT_FOUND", "Starter skill not found.")
    skill = Skill(
        workspace_id=workspace_id, name=starter["name"], description=starter["description"], starter_key=key,
        config=SkillConfig(instructions=starter["instructions"], examples=starter["examples"]).model_dump(),
        created_by=actor_id,
    )
    db.add(skill)
    db.flush()
    return skill
