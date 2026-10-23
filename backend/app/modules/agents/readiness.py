"""One publication checklist shared by the editor and the publish boundary."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.core.json_contracts import validate_user_schema
from app.modules.tools.models import ToolInstallation
from app.providers.openai import validate_output_schema
from app.providers.profiles import capability


def assess(db, workspace_id, config, connection):
    errors, warnings = [], []

    def issue(code, message, section, warning=False):
        (warnings if warning else errors).append(
            {"code": code, "message": message, "section": section}
        )

    if not config["instructions"].strip():
        issue("INSTRUCTIONS_REQUIRED", "Add instructions before publishing.", "instructions")
    for key in ("input_schema", "output_schema"):
        try:
            validate_user_schema(config[key])
        except HTTPException as exc:
            issue(exc.detail["code"], f"{key}: {exc.detail['message']}", "schemas")
    if not connection or connection.state != "active":
        issue(
            "PROVIDER_REQUIRED",
            "Connect and verify the selected provider before publishing.",
            "model",
        )
    elif config["model_id"] not in connection.verified_models:
        issue("MODEL_UNSUPPORTED", "Select a model listed by the selected provider.", "model")
    profile = capability(config["provider"], config["model_id"])
    if not profile.runnable:
        issue(
            "RUNTIME_UNSUPPORTED",
            "This model is setup only. Its version can be published, but cannot run yet.",
            "model",
            True,
        )
    if config["tool_keys"]:
        if config["limits"]["max_tool_calls"] < 1:
            issue(
                "TOOL_CALL_LIMIT", "Allow at least one tool call when tools are selected.", "limits"
            )
        if not profile.local_tools:
            issue(
                "TOOLS_RUNTIME_UNSUPPORTED",
                "Select a model marked as supporting local tools.",
                "model",
            )
        installed = set(
            db.scalars(
                select(ToolInstallation.tool_key).where(
                    ToolInstallation.workspace_id == workspace_id
                )
            )
        )
        if set(config["tool_keys"]) - installed:
            issue(
                "TOOL_NOT_APPROVED",
                "Approve every selected tool in the workspace before publishing.",
                "model",
            )
    if Decimal(config["limits"]["max_cost_usd"]) <= 0:
        issue("BUDGET_TOO_SMALL", "Set a run budget above zero.", "limits")
    if config["provider"] in {"openai", "openrouter"}:
        try:
            validate_output_schema(config["output_schema"])
        except HTTPException as exc:
            issue(exc.detail["code"], exc.detail["message"], "schemas")
    if config["limits"]["timeout_seconds"] > 30:
        issue(
            "PROVIDER_CALL_TIMEOUT",
            "The run deadline includes queue time; each model execution is limited to 30 seconds (25 seconds inside a workflow).",
            "limits",
            True,
        )
    return {
        "publishable": not errors,
        "runnable": not errors and profile.runnable,
        "errors": errors,
        "warnings": warnings,
        "max_output_tokens": config["limits"].get("max_output_tokens", 4096),
        "model_called": False,
    }
