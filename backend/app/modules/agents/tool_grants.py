"""Agent permission composition, shared by standalone, workflow and hosted entry points."""
from app.modules.http_tools.service import validate_grants as validate_http
from app.modules.mcp.agent_grants import validate_grants as validate_mcp


def validate_grants(db, workspace_id, config, raw_catalog="[]"):
    validate_mcp(db, workspace_id, config, raw_catalog)
    validate_http(db, workspace_id, config)
    from app.core.errors import fail
    from app.modules.workflows.tools import inspect
    if config.get("skills"):
        from sqlalchemy import select

        from app.modules.skills.models import SkillVersion
        pinned = [grant.get("version_id") for grant in config["skills"]]
        if None in pinned:
            fail(409, "SKILL_UNPINNED", "Publish again to pin the skills this agent uses.")
        found = set(map(str, db.scalars(select(SkillVersion.id).where(SkillVersion.workspace_id == workspace_id, SkillVersion.id.in_(pinned)))))
        if set(pinned) - found:
            fail(409, "SKILL_UNAVAILABLE", "A pinned skill version is no longer available. Publish again.")
    for grant in config.get("workflow_tools", []):
        if not grant.get("graph_hash"):
            fail(409, "WORKFLOW_TOOL_UNPINNED", "Publish again to pin the workflows this model can run.")
        inspect(db, workspace_id, grant, raw_catalog)
