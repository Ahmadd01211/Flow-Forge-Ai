import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import select

from app.modules.agents.models import Agent
from app.modules.audit.models import AuditEvent
from app.modules.skills.models import Skill, SkillVersion
from app.modules.workflows.models import Workflow
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def test_templates_create_workspace_editable_drafts(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    preview = client.get("/api/v1/templates/support-triage").json()
    assert preview["setup_steps"]
    assert "Integrations" in preview["setup_steps"][0]
    assert preview["sample_input"] == {
        "ticket": "Our payment service is down and customers cannot check out."
    }
    items = client.get("/api/v1/templates").json()["items"]
    assert {item["key"] for item in items} == {
        "support-triage",
        "faq-answer",
        "customer-reply-draft",
        "meeting-action-items",
        "input-output",
        "text-cleanup",
        "decision-routing",
        "webhook-api-action",
        "scheduled-api-digest",
        "agent-priority-action",
        "customer-profile-step",
        "batch-customer-profiles",
        "review-and-release",
    }
    agent = client.post(
        f"/api/v1/workspaces/{workspace}/templates/support-triage/instantiate",
        headers=headers(client),
    )
    assert agent.status_code == 201 and agent.json()["kind"] == "agent"
    saved_agent = db.get(Agent, agent.json()["id"])
    assert saved_agent.config["model_id"] == "" and saved_agent.config["instructions"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace}/templates/decision-routing/instantiate",
        headers=headers(client),
    )
    assert workflow.status_code == 201 and workflow.json()["kind"] == "workflow"
    saved_workflow = db.get(Workflow, workflow.json()["id"])
    assert len(saved_workflow.graph["nodes"]) == 5
    assert {event.action for event in db.scalars(select(AuditEvent))} >= {"template.instantiated"}
    assert (
        client.get(f"/api/v1/workspaces/{workspace}/workflows/{saved_workflow.id}").status_code
        == 200
    )


def test_templates_enforce_roles_and_tenant_boundary(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    path = f"/api/v1/workspaces/{workspace}/templates/faq-answer/instantiate"
    member = db.scalar(select(WorkspaceMember))
    member.role = "viewer"
    db.commit()
    assert client.post(path, headers=headers(client)).status_code == 403
    member.role = "editor"
    db.commit()
    assert client.post(path, headers=headers(client)).status_code == 201
    client.cookies.clear()
    register(client, "other-template@example.com")
    assert client.post(path, headers=headers(client)).status_code == 404


def test_user_templates_sharing_copy_and_revocation(client, owner, db):
    from app.modules.templates.models import UserTemplate

    workspace = owner["workspaces"][0]["id"]
    source = client.post(
        f"/api/v1/workspaces/{workspace}/templates/input-output/instantiate",
        headers=headers(client),
    ).json()
    draft = client.get(f"/api/v1/workspaces/{workspace}/workflows/{source['id']}").json()
    payload = {
        "kind": "workflow",
        "source_id": source["id"],
        "expected_revision": draft["revision"],
        "name": "My reusable workflow",
    }
    path = f"/api/v1/workspaces/{workspace}/templates"
    assert (
        client.post(
            path, json={**payload, "expected_revision": 999}, headers=headers(client)
        ).status_code
        == 409
    )
    created = client.post(path, json=payload, headers=headers(client))
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    assert created.json()["visibility"] == "private"
    owner_cookies = dict(client.cookies)
    client.cookies.clear()
    other = register(client, "template-consumer@example.com")
    other_workspace = other["workspaces"][0]["id"]
    detail = f"/api/v1/templates/{key}"
    copy_path = f"/api/v1/workspaces/{other_workspace}/templates/{key}/instantiate"
    assert client.get(detail).status_code == 404
    assert key not in {item["key"] for item in client.get("/api/v1/templates").json()["items"]}
    assert client.post(copy_path, headers=headers(client)).status_code == 404
    # Cross-workspace source IDs cannot be used to publish someone else's draft.
    assert (
        client.post(
            f"/api/v1/workspaces/{other_workspace}/templates", json=payload, headers=headers(client)
        ).status_code
        == 404
    )
    other_cookies = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    assert (
        client.patch(detail, json={"visibility": "workspace"}, headers=headers(client)).status_code
        == 200
    )
    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace))
    member.role = "viewer"
    db.commit()
    assert client.post(path, json=payload, headers=headers(client)).status_code == 403
    member.role = "owner"
    db.commit()
    client.cookies.clear()
    client.cookies.update(other_cookies)
    assert client.get(detail).status_code == 404
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    assert (
        client.patch(detail, json={"visibility": "public"}, headers=headers(client)).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.update(other_cookies)
    assert client.get(detail).status_code == 200
    assert (
        client.patch(detail, json={"visibility": "private"}, headers=headers(client)).status_code
        == 403
    )
    copy = client.post(copy_path, headers=headers(client))
    assert copy.status_code == 201, copy.text
    copied_id = copy.json()["id"]
    assert copied_id != source["id"]
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    assert (
        client.patch(detail, json={"visibility": "private"}, headers=headers(client)).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.update(other_cookies)
    assert client.get(detail).status_code == 404
    assert client.post(copy_path, headers=headers(client)).status_code == 404
    assert (
        client.get(f"/api/v1/workspaces/{other_workspace}/workflows/{copied_id}").status_code == 200
    )
    assert db.get(UserTemplate, __import__("uuid").UUID(key)).visibility == "private"


def test_agent_templates_exclude_model_bindings(client, owner):
    workspace = owner["workspaces"][0]["id"]
    source = client.post(
        f"/api/v1/workspaces/{workspace}/agents",
        json={
            "name": "Agent",
            "config": {"instructions": "Reusable instructions", "model_id": "private-model"},
        },
        headers=headers(client),
    ).json()
    created = client.post(
        f"/api/v1/workspaces/{workspace}/templates",
        json={
            "kind": "agent",
            "source_id": source["id"],
            "expected_revision": source["revision"],
            "name": "Agent template",
        },
        headers=headers(client),
    )
    assert created.status_code == 201, created.text
    detail = client.get(f"/api/v1/templates/{created.json()['key']}").json()
    assert detail["config"]["model_id"] == ""
    assert detail["config"]["instructions"] == "Reusable instructions"


def test_recipe_copies_and_attaches_an_editable_unpublished_skill(client, owner, db, monkeypatch):
    from app.modules.skills.catalog import STARTERS

    workspace = owner["workspaces"][0]["id"]
    # Even a future starter with grants or credentials must copy only portable know-how.
    monkeypatch.setitem(STARTERS, "plain-language", {
        "group": "Writing & tone", "emoji": "speech",
        "name": "Plain-language replies", "description": "Explain technical topics clearly.",
        "instructions": "Use everyday words.",
        "examples": [{"input": "What is latency?", "output": "The time spent waiting."}],
        "tool_keys": ["text.replace"], "mcp_tools": [{"server_id": "private"}],
        "http_tools": [{"tool_id": "private"}], "credentials": "do-not-copy",
    })
    response = client.post(
        f"/api/v1/workspaces/{workspace}/templates/support-triage/instantiate",
        headers=headers(client),
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["kind"] == "agent" and result["template_key"] == "support-triage"
    assert len(result["skill_ids"]) == 1
    skill_id = result["skill_ids"][0]
    skill = client.get(f"/api/v1/workspaces/{workspace}/skills/{skill_id}").json()
    assert skill["name"] == "Plain-language replies"
    assert skill["description"] == "Explain technical topics clearly."
    assert skill["starter_key"] == "plain-language"
    assert skill["status"] == "draft" and skill["latest"] is None
    assert skill["config"] == {
        "instructions": "Use everyday words.",
        "examples": [{"input": "What is latency?", "output": "The time spent waiting."}],
        "tool_keys": [], "mcp_tools": [], "http_tools": [],
    }
    agent = db.get(Agent, result["id"])
    assert str(agent.workspace_id) == workspace
    assert [(grant["skill_id"], grant["name"]) for grant in agent.config["skills"]] == [
        (skill_id, "Plain-language replies")
    ]
    assert agent.config["skills"][0]["version_id"] is None
    assert agent.config["tool_keys"] == agent.config["mcp_tools"] == agent.config["http_tools"] == []
    assert not db.scalars(select(SkillVersion)).all()
    assert {event.action for event in db.scalars(select(AuditEvent)).all()} >= {
        "skill.created", "template.instantiated",
    }
    edited = client.patch(
        f"/api/v1/workspaces/{workspace}/skills/{skill_id}", headers=headers(client),
        json={"name": skill["name"], "description": skill["description"],
              "config": {**skill["config"], "instructions": "Our team's own guidance."},
              "expected_revision": 1},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2 and edited.json()["status"] == "draft"
    assert STARTERS["plain-language"]["instructions"] == "Use everyday words."


def test_recipe_without_skills_creates_only_an_agent(client, owner, db, monkeypatch):
    from app.modules.templates import router as template_router

    catalog = template_router.templates()
    catalog["faq-answer"].pop("starter_skills", None)
    monkeypatch.setattr(template_router, "templates", lambda: catalog)
    workspace = owner["workspaces"][0]["id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace}/templates/faq-answer/instantiate",
        headers=headers(client),
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["skill_ids"] == []
    assert db.get(Agent, result["id"]).config["skills"] == []
    assert not db.scalars(select(Skill)).all()


def test_repeated_recipe_instantiation_creates_independent_skill_drafts(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    results = []
    for _ in range(2):
        response = client.post(
            f"/api/v1/workspaces/{workspace}/templates/support-triage/instantiate",
            headers=headers(client),
        )
        assert response.status_code == 201, response.text
        results.append(response.json())
    assert results[0]["id"] != results[1]["id"]
    assert len(results[0]["skill_ids"]) == len(results[1]["skill_ids"]) == 1
    assert results[0]["skill_ids"] != results[1]["skill_ids"]
    assert len(db.scalars(select(Skill)).all()) == 2
    for result in results:
        assert db.get(Agent, result["id"]).config["skills"][0]["skill_id"] == result["skill_ids"][0]


def test_missing_recipe_starter_rolls_back_all_copies_and_audit_events(client, owner, db, monkeypatch):
    from app.modules.templates import router as template_router

    workspace = owner["workspaces"][0]["id"]
    catalog = template_router.templates()
    catalog["support-triage"]["starter_skills"] = ["plain-language", "missing-starter"]
    monkeypatch.setattr(template_router, "templates", lambda: catalog)
    before = {model: set(db.scalars(select(model.id)).all()) for model in (Agent, Skill, AuditEvent)}
    response = client.post(
        f"/api/v1/workspaces/{workspace}/templates/support-triage/instantiate",
        headers=headers(client),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"
    for model, ids in before.items():
        assert set(db.scalars(select(model.id)).all()) == ids


def test_workflow_recipe_response_preserves_fields_and_has_no_skills(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace}/templates/input-output/instantiate",
        headers=headers(client),
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result == {"kind": "workflow", "id": result["id"], "template_key": "input-output", "skill_ids": []}
    assert db.get(Workflow, result["id"])
    assert not db.scalars(select(Skill)).all()


@pytest.mark.parametrize(("key", "starter_keys", "inputs", "outputs"), [
    ("support-triage", ["plain-language"], ["ticket"], ["priority", "reason"]),
    ("faq-answer", ["plain-language", "summarise-sources"], ["question", "context"], ["answer", "found_in_context"]),
    ("customer-reply-draft", ["brand-voice", "polite-refusal"], ["customer_message", "brand_guidelines"], ["draft_reply", "needs_human"]),
    ("meeting-action-items", ["extract-tables"], ["notes"], ["summary", "action_items"]),
])
def test_recipe_metadata_and_skill_mappings(client, owner, db, key, starter_keys, inputs, outputs):
    listed = {item["key"]: item for item in client.get("/api/v1/templates").json()["items"]}
    preview = client.get(f"/api/v1/templates/{key}")
    assert preview.status_code == 200, preview.text
    detail = preview.json()
    assert detail["setup_steps"] and detail["sample_input"] and detail["expected_result"]
    assert "draft" in detail["expected_result"].lower() and "review" in detail["expected_result"].lower()
    for field in ("setup_steps", "sample_input", "expected_result", "starter_skills"):
        assert listed[key][field] == detail[field]
    assert detail["starter_skills"] == starter_keys
    config = detail["config"]
    for field, properties in (("input_schema", inputs), ("output_schema", outputs)):
        Draft202012Validator.check_schema(config[field])
        assert set(config[field]["properties"]) == set(properties)
        assert set(config[field]["required"]) == set(properties)
        assert config[field]["additionalProperties"] is False
    Draft202012Validator(config["input_schema"]).validate(detail["sample_input"])
    if key == "customer-reply-draft":
        assert detail["sample_input"]["brand_guidelines"] == ""
        assert config["output_schema"]["properties"]["needs_human"]["type"] == "boolean"
    if key == "meeting-action-items":
        items = config["output_schema"]["properties"]["action_items"]
        assert items["type"] == "array"
        assert set(items["items"]["properties"]) == {"task", "owner", "due_date"}
        assert all(field["type"] == "string" for field in items["items"]["properties"].values())
        assert set(items["items"]["required"]) == {"task", "owner", "due_date"}
        assert items["items"]["additionalProperties"] is False
    workspace = owner["workspaces"][0]["id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace}/templates/{key}/instantiate", headers=headers(client),
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert len(result["skill_ids"]) == len(starter_keys)
    skills = [db.get(Skill, identity) for identity in result["skill_ids"]]
    assert [skill.starter_key for skill in skills] == starter_keys
    assert all(str(skill.workspace_id) == workspace for skill in skills)
    assert [(grant["skill_id"], grant["name"]) for grant in db.get(Agent, result["id"]).config["skills"]] == [
        (str(skill.id), skill.name) for skill in skills
    ]
    assert not db.scalars(select(SkillVersion)).all()
