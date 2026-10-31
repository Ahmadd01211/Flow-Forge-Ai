import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import register


def test_activity_keyset_ties_filter_and_export_payload(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    stamp = datetime(2026, 10, 25, tzinfo=UTC)
    for index in range(5):
        db.add(
            AuditEvent(
                id=uuid.UUID(int=index + 1),
                workspace_id=uuid.UUID(workspace),
                actor_id=uuid.UUID(owner["user"]["id"]),
                action="test.checked",
                target_id=uuid.uuid4(),
                details={"ordinal": index},
                created_at=stamp,
            )
        )
    db.commit()
    base = f"/api/v1/workspaces/{workspace}/activity"
    cursor, received = None, []
    for _ in range(3):
        result = client.get(
            base,
            params={"limit": 2, "action": "test.checked", **({"cursor": cursor} if cursor else {})},
        )
        assert result.status_code == 200, result.text
        received.extend(item["details"]["ordinal"] for item in result.json()["items"])
        cursor = result.json()["next_cursor"]
    assert received == [4, 3, 2, 1, 0] and cursor is None
    assert client.get(base, params={"action": "missing.action"}).json()["items"] == []
    for value in ["!bad!", "e30=", "WyJ0aW1lIiwiaWQiXQ=="]:
        assert client.get(base, params={"cursor": value}).status_code == 422
    assert client.get(base, params={"limit": 101}).status_code == 422
    assert client.get(base, params={"action": "test%"}).status_code == 422


def test_activity_requires_current_admin_and_workspace_membership(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/activity"
    member = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == uuid.UUID(workspace))
    )
    for role, code in [("viewer", 403), ("editor", 403), ("admin", 200), ("owner", 200)]:
        member.role = role
        db.commit()
        assert client.get(base).status_code == code
    register(client, "unrelated-activity@example.com")
    assert client.get(base).status_code == 404


def test_new_approval_decisions_appear_in_activity_without_input_or_credentials(client, owner):
    from app.modules.workflows.runtime import execute
    from tests.test_workflow_pauses import decision, detail, setup

    workspace, _, _, run_id = setup(client, owner)
    execute(run_id, client.app.state.settings)
    pause_id = detail(client, workspace, run_id)["pauses"][0]["id"]
    assert decision(client, workspace, run_id, pause_id).status_code == 200
    result = client.get(
        f"/api/v1/workspaces/{workspace}/activity", params={"action": "workflow_pause.approved"}
    )
    assert len(result.json()["items"]) == 1
    assert result.json()["items"][0]["details"] == {"run_id": run_id, "node_id": "review"}
    assert "Ada" not in result.text and "customer" not in result.text
