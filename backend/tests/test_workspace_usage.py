import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.core.credentials import load_master_key
from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import ProviderFailure, execute
from app.modules.workflows import runtime
from app.modules.workflows.models import WorkflowRun
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent, submit


def limits(client, workspace, **overrides):
    path = f"/api/v1/workspaces/{workspace}/usage"
    current = client.get(path).json()
    return client.patch(
        path,
        headers=headers(client),
        json={
            "expected_revision": current["revision"],
            "daily_budget_usd": current["daily_budget_usd"],
            "daily_run_limit": current["daily_run_limit"],
            "active_run_limit": current["active_run_limit"],
            **overrides,
        },
    )


def echo_version(client, workspace):
    base = f"/api/v1/workspaces/{workspace}/workflows"
    draft = client.post(base, headers=headers(client), json={"name": "Quota echo"}).json()
    return client.post(
        f"{base}/{draft['id']}/versions", headers=headers(client), json={"expected_revision": 1}
    ).json()


def workflow_submit(client, workspace, version, key):
    return client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs",
        headers={**headers(client), "Idempotency-Key": key},
        json={"version_id": version["id"], "input": {}},
    )


def test_agent_reservation_settles_to_usage_and_cancellation_releases(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    path = f"/api/v1/workspaces/{workspace}/usage"
    run = submit(client, workspace, version).json()
    pending = client.get(path).json()
    assert pending["accepted_runs"] == 1 and pending["active_runs"] == 1
    assert Decimal(pending["reserved_usd"]) == Decimal(run["reserved_max_usd"]) > 0
    assert submit(client, workspace, version).status_code == 200
    assert client.get(path).json()["accepted_runs"] == 1
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate", lambda *_: ({"priority": "urgent"}, 100, 20)
    )
    execute(run["id"], client.app.state.settings)
    settled = client.get(path).json()
    assert settled["active_runs"] == 0 and Decimal(settled["reserved_usd"]) == 0
    assert Decimal(settled["measured_usd"]) > 0 and settled["input_tokens"] == 100
    assert Decimal(settled["remaining_usd"]) > Decimal(pending["remaining_usd"])
    second = submit(client, workspace, version, key="usage-cancel-001").json()
    client.post(
        f"/api/v1/workspaces/{workspace}/runs/{second['id']}/cancel", headers=headers(client)
    )
    cancelled = client.get(path).json()
    assert cancelled["accepted_runs"] == 2 and cancelled["active_runs"] == 0
    assert cancelled["measured_usd"] == settled["measured_usd"]


def test_budget_blocks_paid_admission_and_unknown_outcome_stays_committed(
    client, owner, monkeypatch
):
    workspace, version = published_agent(client, owner, monkeypatch)
    assert limits(client, workspace, daily_budget_usd="0").status_code == 200
    denied = submit(client, workspace, version)
    assert denied.status_code == 429 and denied.json()["error"]["code"] == "WORKSPACE_DAILY_BUDGET"
    local = echo_version(client, workspace)
    assert workflow_submit(client, workspace, local, "free-quota-0001").status_code == 202
    assert limits(client, workspace, daily_budget_usd="1").status_code == 200
    run = submit(client, workspace, version).json()

    def uncertain(*_):
        raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)

    monkeypatch.setattr("app.modules.executions.runtime.generate", uncertain)
    execute(run["id"], client.app.state.settings)
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert Decimal(usage["uncertain_usd"]) == Decimal(run["reserved_max_usd"])
    assert Decimal(usage["measured_usd"]) == 0
    limits(client, workspace, daily_budget_usd=usage["uncertain_usd"])
    assert submit(client, workspace, version, key="another-uncertain-001").status_code == 429


def test_shared_capacity_and_daily_count_across_agent_and_workflow(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    local = echo_version(client, workspace)
    limits(client, workspace, active_run_limit=1, daily_run_limit=1)
    agent = submit(client, workspace, version).json()
    blocked = workflow_submit(client, workspace, local, "shared-capacity-001")
    assert (
        blocked.status_code == 429
        and blocked.json()["error"]["code"] == "WORKSPACE_CONCURRENCY_LIMIT"
    )
    client.post(
        f"/api/v1/workspaces/{workspace}/runs/{agent['id']}/cancel", headers=headers(client)
    )
    daily = workflow_submit(client, workspace, local, "shared-capacity-002")
    assert daily.status_code == 429 and daily.json()["error"]["code"] == "WORKSPACE_DAILY_RUN_LIMIT"


def test_concurrent_admission_uses_one_workspace_lock(client, owner):
    workspace = owner["workspaces"][0]["id"]
    local = echo_version(client, workspace)
    limits(client, workspace, active_run_limit=1)
    settings = client.app.state.settings
    master = load_master_key(settings.credential_key_path)
    actor_id = uuid.UUID(owner["user"]["id"])

    def attempt(i):
        with client.app.state.sessions() as db:
            try:
                runtime.submit(
                    db,
                    uuid.UUID(workspace),
                    actor_id,
                    uuid.UUID(local["id"]),
                    {},
                    f"concurrent-admission-00{i}",
                    master,
                )
                return 202
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(attempt, range(2)))
    assert sorted(result) == [202, 429]


def test_limit_boundaries_and_csrf(client, owner):
    workspace = owner["workspaces"][0]["id"]
    assert limits(client, workspace, daily_budget_usd="10000").status_code == 200
    assert limits(client, workspace, daily_budget_usd="10000.00000001").status_code == 422
    assert limits(client, workspace, daily_budget_usd="NaN").status_code == 422
    assert limits(client, workspace, daily_run_limit=True).status_code == 422
    path = f"/api/v1/workspaces/{workspace}/usage"
    assert (
        client.patch(
            path,
            json={
                "expected_revision": 1,
                "daily_budget_usd": "1",
                "daily_run_limit": 1,
                "active_run_limit": 1,
            },
        ).status_code
        == 403
    )


def test_utc_reset_keeps_carry_in_reservation_and_settings_permissions(
    client, owner, db, monkeypatch
):
    workspace, version = published_agent(client, owner, monkeypatch)
    run = submit(client, workspace, version).json()
    row = db.get(AgentRun, uuid.UUID(run["id"]))
    row.created_at = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(seconds=1)
    db.commit()
    path = f"/api/v1/workspaces/{workspace}/usage"
    usage = client.get(path).json()
    assert usage["accepted_runs"] == 0 and usage["active_runs"] == 1
    assert Decimal(usage["reserved_usd"]) > 0
    saved = limits(client, workspace, daily_run_limit=42)
    assert saved.status_code == 200
    stale = client.patch(
        path,
        headers=headers(client),
        json={
            "expected_revision": usage["revision"],
            "daily_budget_usd": "10",
            "daily_run_limit": 5,
            "active_run_limit": 2,
        },
    )
    assert stale.status_code == 409
    member = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == uuid.UUID(workspace))
    )
    member.role = "viewer"
    db.commit()
    assert client.get(path).status_code == 200 and limits(client, workspace).status_code == 403
    client.cookies.clear()
    register(client, "usage-other@example.com")
    assert client.get(path).status_code == 404


def test_workflow_agent_reserves_its_budget(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Budgeted agent"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(
        1,
        {
            "id": "agent",
            "type": "agent",
            "label": "Agent",
            "position": {"x": 300, "y": 180},
            "config": {"version_id": version["id"]},
        },
    )
    graph["nodes"][-1]["config"]["value"]["node_id"] = "agent"
    graph["edges"] = [
        {"id": "input-agent", "source": "input", "target": "agent"},
        {"id": "agent-result", "source": "agent", "target": "result"},
    ]
    path = f"{base}/{workflow['id']}"
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
    ).json()
    limits(client, workspace, daily_budget_usd="0.05")
    assert workflow_submit(client, workspace, published, "budgeted-workflow-001").status_code == 429
    limits(client, workspace, daily_budget_usd="0.10")
    created = workflow_submit(client, workspace, published, "budgeted-workflow-001")
    assert created.status_code == 202, created.text
    assert db.get(WorkflowRun, uuid.UUID(created.json()["id"])).reserved_max_usd == Decimal("0.10")
