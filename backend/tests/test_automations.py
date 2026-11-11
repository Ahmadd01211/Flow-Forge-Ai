import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.modules.automations import service
from app.modules.automations.models import WorkflowAutomation
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def automation(client, owner, kind="webhook"):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}"
    workflow = client.post(
        base + "/workflows", headers=headers(client), json={"name": "Echo trigger"}
    ).json()
    graph = workflow["graph"]
    graph["nodes"][0]["type"] = kind + "_trigger"
    graph["input_schema"] = {
        "type": "object",
        "properties": {"ticket": {"type": "string"}},
        "required": ["ticket"],
        "additionalProperties": False,
    }
    path = f"{base}/workflows/{workflow['id']}"
    assert (
        client.patch(
            path,
            headers=headers(client),
            json={"name": workflow["name"], "expected_revision": 1, "graph": graph},
        ).status_code
        == 200
    )
    published = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 2}
    )
    assert published.status_code == 201, published.text
    body = {"name": "Ticket automation", "kind": kind, "version_id": published.json()["id"]}
    if kind == "schedule":
        body.update(interval_seconds=60, input={"ticket": "private scheduled input"})
    created = client.post(base + "/automations", headers=headers(client), json=body)
    assert created.status_code == 201, created.text
    return base, created.json()


def test_webhook_durable_idempotency_rotation_pause_and_isolation(client, owner, db):
    base, hook = automation(client, owner)
    path = f"/api/v1/webhooks/{hook['id']}"
    head = {
        "Authorization": "Bearer " + hook["webhook_key"],
        "Idempotency-Key": "ticket-event-0001",
    }
    payload = {"ticket": "private hook input"}
    assert client.post(path, json=payload).status_code == 401
    first = client.post(path, headers=head, json=payload)
    assert first.status_code == 202, first.text
    run_id = first.json()["id"]
    replay = client.post(path, headers=head, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == run_id
    assert client.post(path, headers=head, json={"ticket": "different"}).status_code == 409
    assert (
        client.post(
            path, headers={**head, "Idempotency-Key": "invalid-input-001"}, json={}
        ).status_code
        == 422
    )
    execute(run_id, client.app.state.settings)
    completed = client.get(f"{path}/runs/{run_id}", headers=head)
    assert completed.json()["state"] == "completed" and completed.json()["output"] == payload
    listing = client.get(base + "/automations").json()
    assert "ff_hook_" not in str(listing) and "private hook input" not in str(listing)
    stored = db.get(WorkflowAutomation, uuid.UUID(hook["id"]))
    assert stored.key_hash != hook["webhook_key"]
    rotated = client.post(f"{base}/automations/{hook['id']}/rotate", headers=headers(client)).json()
    assert client.post(path, headers=head, json=payload).status_code == 401
    head["Authorization"] = "Bearer " + rotated["webhook_key"]
    assert (
        client.patch(
            f"{base}/automations/{hook['id']}", headers=headers(client), json={"state": "paused"}
        ).status_code
        == 200
    )
    assert client.post(path, headers=head, json=payload).status_code == 409
    assert (
        client.patch(
            f"{base}/automations/{hook['id']}", headers=headers(client), json={"state": "active"}
        ).status_code
        == 200
    )
    assert client.get(f"{path}/runs/{uuid.uuid4()}", headers=head).status_code == 404
    client.cookies.clear()
    register(client, "other-automation@example.com")
    assert client.get(base + "/automations").status_code == 404
    assert (
        client.post(f"{base}/automations/{hook['id']}/rotate", headers=headers(client)).status_code
        == 404
    )


def test_schedule_coalesces_downtime_and_concurrent_ticks(client, owner, db):
    base, schedule = automation(client, owner, "schedule")
    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))
    assert b"private scheduled input" not in row.input_ciphertext
    due = row.next_due_at
    now = due + timedelta(hours=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: service.tick(client.app.state.settings, now), range(2)))
    assert sum(counts) == 1
    db.expire_all()
    assert row.next_due_at == now + timedelta(seconds=60) and row.last_due_at == due
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.automation_id == row.id))
    execute(str(run.id), client.app.state.settings)
    assert client.get(f"{base}/workflow-runs/{run.id}").json()["output"] == {
        "ticket": "private scheduled input"
    }
    assert service.tick(client.app.state.settings, now) == 0
    assert "private scheduled input" not in str(client.get(base + "/automations").json())


def test_schedule_run_and_cursor_rollback_together(client, owner, db, monkeypatch):
    _, schedule = automation(client, owner, "schedule")
    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))
    due = row.next_due_at
    original = service.submit

    def crash(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Worker crash before transaction commit")

    monkeypatch.setattr(service, "submit", crash)
    with pytest.raises(RuntimeError):
        service.tick(client.app.state.settings, due)
    db.expire_all()
    assert row.next_due_at == due
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 0
    monkeypatch.setattr(service, "submit", original)
    assert service.tick(client.app.state.settings, due) == 1


def test_schedule_backpressure_then_permission_loss(client, owner, db):
    base, schedule = automation(client, owner, "schedule")
    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))
    due = row.next_due_at
    for i in range(2):
        created = client.post(
            base + "/workflow-runs",
            headers={**headers(client), "Idempotency-Key": f"busy-workflow-00{i}"},
            json={"version_id": schedule["version_id"], "input": {"ticket": "busy"}},
        )
        assert created.status_code == 202, created.text
    assert service.tick(client.app.state.settings, due) == 0
    db.expire_all()
    assert row.next_due_at == due and row.next_attempt_at == due + timedelta(seconds=10)
    assert row.last_error_code == "RUN_CONCURRENCY_LIMIT" and row.state == "active"
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == row.workspace_id,
            WorkspaceMember.user_id == row.created_by,
        )
    )
    member.role = "editor"
    db.commit()
    assert service.tick(client.app.state.settings, due + timedelta(seconds=10)) == 0
    db.expire_all()
    assert row.state == "paused" and row.last_error_code == "AUTOMATION_OWNER_ACCESS_CHANGED"
    assert (
        client.post(
            base + "/automations",
            headers=headers(client),
            json={
                "name": "Denied",
                "kind": "schedule",
                "version_id": schedule["version_id"],
                "input": {},
                "interval_seconds": 60,
            },
        ).status_code
        == 403
    )


def test_trigger_contract_and_intervals(client, owner):
    base, hook = automation(client, owner)
    for interval in (1, 86401, True):
        assert (
            client.post(
                base + "/automations",
                headers=headers(client),
                json={
                    "name": "Bad",
                    "kind": "schedule",
                    "version_id": hook["version_id"],
                    "input": {},
                    "interval_seconds": interval,
                },
            ).status_code
            == 422
        )
    mismatch = client.post(
        base + "/automations",
        headers=headers(client),
        json={
            "name": "Wrong trigger",
            "kind": "schedule",
            "version_id": hook["version_id"],
            "input": {},
            "interval_seconds": 60,
        },
    )
    assert mismatch.status_code == 422 and mismatch.json()["error"]["code"] == "TRIGGER_MISMATCH"


def test_archived_webhook_cannot_resume_or_read_other_webhook_run(client, owner):
    base, hook = automation(client, owner)
    _, other = automation(client, owner)
    head = {
        "Authorization": "Bearer " + hook["webhook_key"],
        "Idempotency-Key": "archived-event-001",
    }
    run = client.post(
        f"/api/v1/webhooks/{hook['id']}", headers=head, json={"ticket": "test"}
    ).json()
    assert (
        client.get(
            f"/api/v1/webhooks/{other['id']}/runs/{run['id']}",
            headers={"Authorization": "Bearer " + other["webhook_key"]},
        ).status_code
        == 404
    )
    path = f"{base}/automations/{hook['id']}"
    assert client.delete(path, headers=headers(client)).status_code == 204
    assert (
        client.post(
            f"/api/v1/webhooks/{hook['id']}", headers=head, json={"ticket": "test"}
        ).status_code
        == 409
    )
    assert client.patch(path, headers=headers(client), json={"state": "active"}).status_code == 409
    assert client.post(path + "/rotate", headers=headers(client)).status_code == 409
    assert hook["id"] not in str(client.get(base + "/automations").json())


def test_schedule_pauses_on_invalid_target(client, owner, db, monkeypatch):
    from app.core.errors import fail

    _, schedule = automation(client, owner, "schedule")
    row = db.get(WorkflowAutomation, uuid.UUID(schedule["id"]))

    def revoked(*_):
        fail(422, "MCP_GRANT_CHANGED", "Connection no longer approved.")

    monkeypatch.setattr(service, "target", revoked)
    assert service.tick(client.app.state.settings, row.next_due_at) == 0
    db.expire_all()
    assert row.state == "paused" and row.last_error_code == "MCP_GRANT_CHANGED"
    assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 0
