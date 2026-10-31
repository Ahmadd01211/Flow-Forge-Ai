"""Agent permission composition, shared by standalone, workflow and hosted entry points."""
from app.modules.http_tools.service import validate_grants as validate_http
from app.modules.mcp.agent_grants import validate_grants as validate_mcp


def validate_grants(db, workspace_id, config, raw_catalog="[]"):
    validate_mcp(db, workspace_id, config, raw_catalog)
    validate_http(db, workspace_id, config)
