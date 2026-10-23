import uuid

from sqlalchemy import select

from app.modules.deployments.models import Deployment
from app.modules.executions.models import AgentRun
from app.modules.workflows.models import WorkflowRun
from app.modules.workflows.runtime import execute as execute_workflow
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent


def workflow_version(client, workspace):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    draft = client.post(base, headers=headers(client), json={"name": "Hosted echo"}).json()
    published = client.post(
        f"{base}/{draft['id']}/versions", headers=headers(client), json={"expected_revision": 1}
    )
    assert published.status_code == 201, published.text
    return published.json()


def test_hosted_workflow_key_lifecycle_and_run_isolation(client, owner, db):
    workspace = owner["workspaces"][0]["id"]
    version = workflow_version(client, workspace)
    base = f"/api/v1/workspaces/{workspace}/deployments"
    assert client.get(f"{base}/eligible").json()["items"][0]["version_id"] == version["id"]
    created = client.post(
        base,
        headers=headers(client),
        json={"name": "Website", "kind": "workflow", "version_id": version["id"]},
    )
    assert created.status_code == 201, created.text
    deployment = created.json()
    key = deployment["api_key"]
    assert key.startswith("ff_live_")
    saved = db.get(Deployment, uuid.UUID(deployment["id"]))
    assert key not in saved.key_hash
    assert "api_key" not in client.get(base).json()["items"][0]
    public = f"/api/v1/deployments/{deployment['id']}"
    payload = {"input": {"ticket": "A-1"}}
    auth = {"Authorization": f"Bearer {key}", "Idempotency-Key": "website-echo-001"}
    assert client.post(f"{public}/invoke", json=payload).status_code == 401
    limit_key = f"deployment:{deployment['id']}:invoke"
    client.app.state.redis.set(limit_key, 60, ex=60)
    assert client.post(f"{public}/invoke", headers=auth, json=payload).status_code == 429
    client.app.state.redis.delete(limit_key)
    created_run = client.post(f"{public}/invoke", headers=auth, json=payload)
    assert created_run.status_code == 202, created_run.text
    run_id = created_run.json()["id"]
    assert client.post(f"{public}/invoke", headers=auth, json=payload).status_code == 200
    assert (
        client.post(f"{public}/invoke", headers=auth, json={"input": {"ticket": "B"}}).status_code
        == 409
    )
    assert db.scalar(
        select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(run_id))
    ).deployment_id == uuid.UUID(deployment["id"])
    execute_workflow(run_id, client.app.state.settings)
    status = client.get(f"{public}/runs/{run_id}", headers=auth)
    assert status.status_code == 200 and status.json()["output"] == payload["input"]
    recent = client.get(f"{base}/{deployment['id']}/runs")
    assert recent.status_code == 200 and recent.json()["items"][0]["id"] == run_id
    other = client.post(
        base,
        headers=headers(client),
        json={"name": "Second", "kind": "workflow", "version_id": version["id"]},
    ).json()
    assert (
        client.get(
            f"/api/v1/deployments/{other['id']}/runs/{run_id}",
            headers={"Authorization": f"Bearer {other['api_key']}"},
        ).status_code
        == 404
    )
    rotated = client.post(f"{base}/{deployment['id']}/rotate", headers=headers(client))
    assert rotated.status_code == 200 and rotated.json()["api_key"] != key
    assert client.get(f"{public}/runs/{run_id}", headers=auth).status_code == 401
    new_auth = {
        "Authorization": f"Bearer {rotated.json()['api_key']}",
        "Idempotency-Key": "website-echo-002",
    }
    queued = client.post(f"{public}/invoke", headers=new_auth, json=payload).json()
    revoked = client.post(f"{base}/{deployment['id']}/revoke", headers=headers(client))
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    assert client.get(f"{public}/runs/{run_id}", headers=new_auth).status_code == 401
    assert (
        client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{queued['id']}").json()["state"]
        == "cancelled"
    )
    client.cookies.clear()
    register(client, "other-deploy@example.com")
    assert client.get(base).status_code == 404


def test_hosted_agent_is_pinned_to_published_version(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/deployments"
    created = client.post(
        base,
        headers=headers(client),
        json={"name": "Agent API", "kind": "agent", "version_id": version["id"]},
    )
    assert created.status_code == 201, created.text
    deployment = created.json()
    api = f"/api/v1/deployments/{deployment['id']}"
    result = client.post(
        f"{api}/invoke",
        headers={
            "Authorization": f"Bearer {deployment['api_key']}",
            "Idempotency-Key": "agent-hosted-001",
        },
        json={"input": {"ticket": "urgent"}},
    )
    assert result.status_code == 202, result.text
    row = db.get(AgentRun, uuid.UUID(result.json()["id"]))
    assert row.version_id == uuid.UUID(version["id"])
    assert row.deployment_id == uuid.UUID(deployment["id"])
    assert (
        client.post(
            f"{api}/invoke",
            headers={
                "Authorization": f"Bearer {deployment['api_key']}",
                "Idempotency-Key": "agent-hosted-002",
            },
            json={"input": {"ticket": "urgent"}, "version_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )
