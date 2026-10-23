from sqlalchemy import select

from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register


def test_cross_workspace_read_and_write_denied(client, owner):
    first = owner["workspaces"][0]["id"]
    agent = client.post(
        f"/api/v1/workspaces/{first}/agents",
        headers=headers(client),
        json={"name": "Private agent"},
    ).json()
    client.cookies.clear()
    second = register(client, "other@example.com")["workspaces"][0]["id"]
    assert client.get(f"/api/v1/workspaces/{first}/agents").status_code == 404
    assert (
        client.post(
            f"/api/v1/workspaces/{first}/agents",
            headers=headers(client),
            json={"name": "Forbidden"},
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/workspaces/{second}/agents/{agent['id']}").status_code == 404


def test_agent_save_conflict_preserves_latest(client, owner):
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}/agents"
    created = client.post(base, headers=headers(client), json={"name": "Triage"})
    assert created.status_code == 201
    agent = created.json()
    body = {
        "name": "Triage v2",
        "description": "",
        "config": agent["config"],
        "expected_revision": 1,
    }
    saved = client.patch(f"{base}/{agent['id']}", headers=headers(client), json=body)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    body["name"] = "Stale overwrite"
    assert (
        client.patch(f"{base}/{agent['id']}", headers=headers(client), json=body).status_code == 409
    )
    assert client.get(f"{base}/{agent['id']}").json()["name"] == "Triage v2"


def test_viewer_cannot_write(client, owner, db):
    member = db.scalar(select(WorkspaceMember))
    member.role = "viewer"
    db.commit()
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}/agents"
    assert client.get(base).status_code == 200
    assert client.post(base, headers=headers(client), json={"name": "No"}).status_code == 403


def test_limits_and_external_schema_refs_rejected(client, owner):
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}/agents"
    assert (
        client.post(
            base,
            headers=headers(client),
            json={"name": "Unbounded", "config": {"limits": {"max_iterations": 999}}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            base,
            headers=headers(client),
            json={
                "name": "Ref",
                "config": {"input_schema": {"type": "object", "$ref": "http://metadata/secret"}},
            },
        ).status_code
        == 422
    )


def test_workflow_roundtrip_and_revision_validation(client, owner):
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}/workflows"
    result = client.post(base, headers=headers(client), json={"name": "My workflow"})
    assert result.status_code == 201
    row = result.json()
    validated = client.post(
        f"{base}/{row['id']}/validate", headers=headers(client), json={"expected_revision": 1}
    )
    assert validated.status_code == 200
    assert validated.json()["valid"] is True
    assert validated.json()["publishable"] is True
    row["graph"]["nodes"][0]["position"]["x"] = 333
    saved = client.patch(
        f"{base}/{row['id']}",
        headers=headers(client),
        json={
            "name": row["name"],
            "description": "",
            "expected_revision": 1,
            "graph": row["graph"],
        },
    )
    assert saved.status_code == 200
    assert client.get(f"{base}/{row['id']}").json()["graph"]["nodes"][0]["position"]["x"] == 333
    assert (
        client.post(
            f"{base}/{row['id']}/validate", headers=headers(client), json={"expected_revision": 1}
        ).status_code
        == 409
    )
