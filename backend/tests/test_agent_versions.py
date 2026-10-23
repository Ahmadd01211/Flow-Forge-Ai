import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.agents.models import AgentVersion
from app.modules.agents.schemas import SnapshotCreate
from app.modules.agents.service import snapshot
from app.modules.audit.models import AuditEvent
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def draft(client, owner, name="Triage"):
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}/agents"
    result = client.post(
        base,
        headers=headers(client),
        json={
            "name": name,
            "config": {"instructions": "Classify support tickets as urgent or normal."},
        },
    )
    assert result.status_code == 201, result.text
    return base, result.json()


def freeze(client, base, agent, summary="Initial contract"):
    response = client.post(
        f"{base}/{agent['id']}/test-snapshots",
        headers=headers(client),
        json={"expected_revision": agent["revision"], "change_summary": summary},
    )
    assert response.status_code in (200, 201), response.text
    return response


def test_snapshot_is_stable_after_draft_change_and_duplicate_request(client, owner, db):
    base, agent = draft(client, owner)
    version = freeze(client, base, agent).json()
    repeat = freeze(client, base, agent, "Does not replace immutable summary")
    assert repeat.status_code == 200 and repeat.json()["id"] == version["id"]
    body = {
        "name": "Edited draft",
        "description": "",
        "expected_revision": 1,
        "config": {**agent["config"], "instructions": "New instructions"},
    }
    assert (
        client.patch(f"{base}/{agent['id']}", headers=headers(client), json=body).status_code == 200
    )
    stored = client.get(f"{base}/{agent['id']}/versions/{version['id']}").json()
    assert stored == version
    assert stored["config"]["instructions"] != "New instructions"
    assert stored["change_summary"] == "Initial contract"
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_snapshot_revision_conflict_and_blank_instructions(client, owner):
    base, agent = draft(client, owner)
    assert (
        client.post(
            f"{base}/{agent['id']}/test-snapshots",
            headers=headers(client),
            json={"expected_revision": 99},
        ).status_code
        == 409
    )
    blank = client.post(base, headers=headers(client), json={"name": "Blank"}).json()
    assert (
        client.post(
            f"{base}/{blank['id']}/test-snapshots",
            headers=headers(client),
            json={"expected_revision": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1}
        ).status_code
        == 409
    )


def test_restore_increments_draft_without_altering_version(client, owner, db):
    base, agent = draft(client, owner)
    version = freeze(client, base, agent).json()
    changed = client.patch(
        f"{base}/{agent['id']}",
        headers=headers(client),
        json={
            "name": "Changed",
            "description": "changed",
            "config": agent["config"],
            "expected_revision": 1,
        },
    ).json()
    restored = client.post(
        f"{base}/{agent['id']}/restore",
        headers=headers(client),
        json={"version_id": version["id"], "expected_revision": changed["revision"]},
    )
    assert restored.status_code == 200
    assert restored.json()["name"] == agent["name"] and restored.json()["revision"] == 3
    assert client.get(f"{base}/{agent['id']}/versions/{version['id']}").json() == version
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "agent.version_restored")
        )
        == 1
    )
    assert (
        client.post(
            f"{base}/{agent['id']}/restore",
            headers=headers(client),
            json={"version_id": version["id"], "expected_revision": 1},
        ).status_code
        == 409
    )


def test_history_has_stable_pagination_and_survives_archive(client, owner):
    base, agent = draft(client, owner)
    for i in range(3):
        freeze(client, base, agent)
        agent = client.patch(
            f"{base}/{agent['id']}",
            headers=headers(client),
            json={
                "name": agent["name"],
                "description": str(i),
                "config": agent["config"],
                "expected_revision": agent["revision"],
            },
        ).json()
    first = client.get(f"{base}/{agent['id']}/versions?limit=2").json()
    second = client.get(
        f"{base}/{agent['id']}/versions?limit=2&cursor={first['next_cursor']}"
    ).json()
    assert [v["number"] for v in first["items"] + second["items"]] == [3, 2, 1]
    assert second["next_cursor"] is None
    assert client.get(f"{base}/{agent['id']}/versions?cursor=broken").status_code == 422
    assert client.post(f"{base}/{agent['id']}/archive", headers=headers(client)).status_code == 200
    assert len(client.get(f"{base}/{agent['id']}/versions").json()["items"]) == 3


def test_cross_agent_workspace_and_viewer_boundaries(client, owner, db):
    base, agent = draft(client, owner)
    version = freeze(client, base, agent).json()
    _, other = draft(client, owner, "Another")
    assert client.get(f"{base}/{other['id']}/versions/{version['id']}").status_code == 404
    assert (
        client.post(
            f"{base}/{other['id']}/restore",
            headers=headers(client),
            json={"version_id": version["id"], "expected_revision": 1},
        ).status_code
        == 404
    )
    member = db.scalar(select(WorkspaceMember))
    member.role = "viewer"
    db.commit()
    assert client.get(f"{base}/{agent['id']}/versions").status_code == 200
    assert (
        client.post(
            f"{base}/{agent['id']}/test-snapshots",
            headers=headers(client),
            json={"expected_revision": 1},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/{agent['id']}/versions/{version['id']}/validate-example",
            headers=headers(client),
            json={"input": {}},
        ).status_code
        == 403
    )
    client.cookies.clear()
    second = register(client, "other@example.com")
    assert client.get(f"{base}/{agent['id']}/versions").status_code == 404
    new_base = f"/api/v1/workspaces/{second['workspaces'][0]['id']}/agents"
    assert client.get(f"{new_base}/{agent['id']}/versions/{version['id']}").status_code == 404


def test_contract_playground_checks_frozen_schemas_without_model_call(client, owner):
    base, agent = draft(client, owner)
    version = freeze(client, base, agent).json()
    url = f"{base}/{agent['id']}/versions/{version['id']}/validate-example"
    valid = client.post(
        url,
        headers=headers(client),
        json={"input": {"ticket": "Damaged package"}, "output": {"priority": "urgent"}},
    ).json()
    assert valid["input_valid"] and valid["output_valid"] and valid["model_called"] is False
    assert valid["config_hash"] == version["config_hash"]
    secret = "must-not-echo-secret"
    invalid = client.post(
        url, headers=headers(client), json={"input": {"ticket": 7}, "output": {"priority": secret}}
    )
    assert not invalid.json()["input_valid"] and not invalid.json()["output_valid"]
    assert secret not in invalid.text
    assert {e["path"] for e in invalid.json()["errors"]} == {"/input/ticket", "/output/priority"}
    input_only = client.post(
        url, headers=headers(client), json={"input": {"ticket": "test"}}
    ).json()
    assert input_only["output_valid"] is None
    explicit_null = client.post(
        url, headers=headers(client), json={"input": {}, "output": None}
    ).json()
    assert explicit_null["output_valid"] is False


def test_concurrent_snapshot_requests_share_one_version(client, owner):
    _, agent = draft(client, owner)

    def create_snapshot(_):
        with client.app.state.sessions() as db:
            version, _created = snapshot(
                db,
                uuid.UUID(owner["workspaces"][0]["id"]),
                uuid.UUID(agent["id"]),
                uuid.UUID(owner["user"]["id"]),
                SnapshotCreate(expected_revision=1),
            )
            return str(version.id)

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create_snapshot, range(8)))
    assert len(set(ids)) == 1


def test_database_enforces_immutability_and_composite_ownership(client, owner, db):
    base, agent = draft(client, owner)
    version = freeze(client, base, agent).json()
    with pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE agent_version SET name='tampered' WHERE id=:id"), {"id": version["id"]}
        )
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM agent_version WHERE id=:id"), {"id": version["id"]})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_event"))
    db.rollback()
    client.cookies.clear()
    other = register(client, "second@example.com")
    bad = AgentVersion(
        workspace_id=uuid.UUID(other["workspaces"][0]["id"]),
        agent_id=uuid.UUID(agent["id"]),
        number=2,
        purpose="test",
        source_revision=2,
        name="forged",
        description="",
        config=agent["config"],
        config_hash="0" * 64,
        change_summary="",
        created_by=uuid.UUID(other["user"]["id"]),
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
