from sqlalchemy import select

from app.modules.agents.models import Agent
from app.modules.audit.models import AuditEvent
from app.modules.workflows.models import Workflow
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def test_templates_create_private_editable_drafts(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    items = client.get("/api/v1/templates").json()["items"]
    assert {item["key"] for item in items} == {
        "support-triage",
        "faq-answer",
        "input-output",
        "text-cleanup",
        "decision-routing",
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
