"""Hidden agents that freeze settings owned elsewhere: workflow LLM steps and playground chats.

Publishing through a hidden agent reuses agent validation, grant pinning, credential checks and
the agent runtime, without adding versions to an agent people can see.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.models import Agent, AgentVersion
from app.modules.integrations.service import get_connection


def freeze(
    db: Session, workspace_id: uuid.UUID, agent: Agent, config: dict, name: str,
    actor_id: uuid.UUID, raw_catalog: str, summary: str,
) -> AgentVersion:
    """Publish `config` as the hidden agent's version, reusing an identical, still-valid one.

    The caller locks or creates `agent`. Does not commit.
    """
    from app.modules.agents.service import publish_config
    from app.modules.agents.tool_grants import validate_grants

    if agent.config != config:
        agent.config, agent.name = config, name[:100]
        agent.revision += 1
        db.flush()
    existing = db.scalar(select(AgentVersion).where(
        AgentVersion.agent_id == agent.id,
        AgentVersion.source_revision == agent.revision,
        AgentVersion.purpose == "published",
    ))
    if existing:
        connection = get_connection(db, workspace_id, config["provider"])
        try:
            validate_grants(db, workspace_id, existing.config, raw_catalog)
            from app.modules.skills.service import stale
            current = bool(connection and existing.connection_id == connection.id
                           and existing.credential_generation == connection.credential_generation
                           and not stale(db, existing.config))
        except HTTPException:
            current = False
        if current:
            return existing
        # Same settings, but the credential or a tool connection changed: pin them again.
        agent.revision += 1
        db.flush()
    return publish_config(db, workspace_id, agent, actor_id, config, raw_catalog, summary)


def playground_version(db: Session, workspace_id: uuid.UUID, owner: Agent, raw_config: dict, actor_id: uuid.UUID, raw_catalog: str) -> AgentVersion:
    """Freeze an agent's unsaved draft into its hidden playground twin for a live test chat.

    The twin has its own memory, so test chats never mix with the agent's real conversations.
    """
    from app.modules.agents.schemas import AgentConfig

    config = AgentConfig.model_validate(raw_config).model_dump()
    twin = db.scalar(select(Agent).where(Agent.playground_for == owner.id).with_for_update())
    if not twin:
        twin = Agent(
            workspace_id=workspace_id, playground_for=owner.id, name=owner.name,
            description="Runs unsaved drafts in the builder's live chat.", config=config,
        )
        db.add(twin)
        db.flush()
    return freeze(db, workspace_id, twin, config, owner.name, actor_id, raw_catalog, "Playground chat.")
