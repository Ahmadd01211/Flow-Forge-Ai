from sqlalchemy import select

from app.modules.agents.models import Agent
from app.modules.audit.models import AuditEvent
from app.modules.workflows.models import Workflow
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def test_templates_create_private_editable_drafts(client, owner, db):
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
