import uuid
from copy import deepcopy

import pytest
from sqlalchemy import select

from app.modules.agents.models import AgentVersion
from app.modules.agents.service import config_hash
from app.modules.executions.models import AgentRun
from app.modules.executions.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent, submit


def test_checklist_lists_errors_and_matches_publication_boundary(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/agents"
    agent = client.post(
        base,
        headers=headers(client),
        json={"name": "Incomplete", "config": {"limits": {"max_cost_usd": "0"}}},
    ).json()
    path = f"{base}/{agent['id']}"
    checked = client.get(f"{path}/readiness")
    assert checked.status_code == 200
    data = checked.json()
    assert not data["publishable"] and not data["model_called"]
    codes = {i["code"] for i in data["errors"]}
    assert {"INSTRUCTIONS_REQUIRED", "PROVIDER_REQUIRED", "BUDGET_TOO_SMALL"} <= codes
    denied = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 1})
    assert denied.status_code == 422 and denied.json()["error"]["code"] == data["errors"][0]["code"]


def test_checklist_tool_approval_and_limit_issues(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/agents/{version['agent_id']}"
    draft = client.get(base).json()
    config = {
        **draft["config"],
        "tool_keys": ["text.replace"],
        "limits": {**draft["config"]["limits"], "max_tool_calls": 0},
    }
    saved = client.patch(
        base,
        headers=headers(client),
        json={"name": draft["name"], "config": config, "expected_revision": 1},
    )
    assert saved.status_code == 200
    result = client.get(f"{base}/readiness").json()
    assert {"TOOL_NOT_APPROVED", "TOOL_CALL_LIMIT"} <= {i["code"] for i in result["errors"]}
    assert result["revision"] == 2


def test_checklist_is_read_only_and_workspace_scoped(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/agents/{version['agent_id']}"
    member = db.scalar(select(WorkspaceMember))
    member.role = "viewer"
    db.commit()
    checked = client.get(f"{base}/readiness").json()
    assert checked["publishable"] and checked["runnable"]
    assert client.get(base).json()["revision"] == 1
    assert (
        client.post(
            f"{base}/versions", headers=headers(client), json={"expected_revision": 1}
        ).status_code
        == 403
    )
    client.cookies.clear()
    register(client, "other-builder@example.com")
    assert client.get(f"{base}/readiness").status_code == 404


@pytest.mark.parametrize("cap", [15, 4097, -1])
def test_output_cap_bounds_rejected_before_save(client, owner, cap):
    workspace = owner["workspaces"][0]["id"]
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace}/agents",
            headers=headers(client),
            json={"name": "Invalid cap", "config": {"limits": {"max_output_tokens": cap}}},
        ).status_code
        == 422
    )


def test_output_cap_is_versioned_and_enforced_by_worker(client, owner, db, monkeypatch):
    workspace, first = published_agent(client, owner, monkeypatch)
    path = f"/api/v1/workspaces/{workspace}/agents/{first['agent_id']}"
    agent = client.get(path).json()
    config = {**agent["config"], "limits": {**agent["config"]["limits"], "max_output_tokens": 128}}
    saved = client.patch(
        path,
        headers=headers(client),
        json={"name": agent["name"], "config": config, "expected_revision": 1},
    )
    assert saved.status_code == 200
    checked = client.get(f"{path}/readiness").json()
    assert checked["publishable"] and checked["max_output_tokens"] == 128
    version = client.post(
        f"{path}/versions", headers=headers(client), json={"expected_revision": 2}
    ).json()
    assert (
        client.get(f"{path}/versions/{first['id']}").json()["config"]["limits"]["max_output_tokens"]
        == 4096
    )
    run = submit(client, workspace, version)
    assert run.status_code == 202
    assert db.get(AgentRun, uuid.UUID(run.json()["id"])).max_output_tokens == 128
    seen = []

    def generate(key, version, data, cap, timeout):
        seen.append(cap)
        return {"priority": "urgent"}, 100, 20

    monkeypatch.setattr("app.modules.executions.runtime.generate", generate)
    execute(run.json()["id"], client.app.state.settings)
    assert seen == [128]
    restored = client.post(
        f"{path}/restore",
        headers=headers(client),
        json={"expected_revision": 2, "version_id": first["id"]},
    )
    assert (
        restored.status_code == 200
        and restored.json()["config"]["limits"]["max_output_tokens"] == 4096
    )

    # The workflow uses its pinned version even after the draft is restored.
    from app.modules.workflows.runtime import execute as execute_workflow

    flows = f"/api/v1/workspaces/{workspace}/workflows"
    flow = client.post(flows, headers=headers(client), json={"name": "Capped agent flow"}).json()
    graph = flow["graph"]
    graph["nodes"].insert(
        1,
        {
            "id": "agent",
            "type": "agent",
            "label": "Capped agent",
            "position": {"x": 300, "y": 180},
            "config": {"version_id": version["id"]},
        },
    )
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "agent", "pointer": ""}}
    graph["edges"] = [
        {"id": "input-agent", "source": "input", "target": "agent"},
        {"id": "agent-result", "source": "agent", "target": "result"},
    ]
    assert (
        client.patch(
            f"{flows}/{flow['id']}",
            headers=headers(client),
            json={"name": flow["name"], "expected_revision": 1, "graph": graph},
        ).status_code
        == 200
    )
    published = client.post(
        f"{flows}/{flow['id']}/versions", headers=headers(client), json={"expected_revision": 2}
    )
    assert published.status_code == 201, published.text
    workflow_run = client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs",
        headers={**headers(client), "Idempotency-Key": "workflow-output-cap"},
        json={"version_id": published.json()["id"], "input": {"ticket": "Urgent"}},
    )
    assert workflow_run.status_code == 202, workflow_run.text
    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    execute_workflow(workflow_run.json()["id"], client.app.state.settings)
    assert seen == [128, 128]


def test_legacy_snapshot_without_new_limit_stays_immutable_and_runs(client, owner, db, monkeypatch):
    workspace, current = published_agent(client, owner, monkeypatch)
    original = db.get(AgentVersion, uuid.UUID(current["id"]))
    raw = deepcopy(original.config)
    raw["limits"].pop("max_output_tokens")
    legacy = AgentVersion(
        workspace_id=original.workspace_id,
        agent_id=original.agent_id,
        connection_id=original.connection_id,
        credential_generation=original.credential_generation,
        number=2,
        source_revision=2,
        purpose="published",
        name=original.name,
        description=original.description,
        config=raw,
        config_hash=config_hash(raw),
        change_summary="Legacy fixture",
        created_by=original.created_by,
    )
    db.add(legacy)
    db.commit()
    run = submit(client, workspace, {"id": str(legacy.id)})
    assert run.status_code == 202, run.text
    assert run.json()["reserved_max_usd"]
    seen = []

    def generate(key, version, data, cap, timeout):
        seen.append(cap)
        return {"priority": "urgent"}, 100, 20

    monkeypatch.setattr("app.modules.executions.runtime.generate", generate)
    execute(run.json()["id"], client.app.state.settings)
    assert seen == [4096]
    db.expire_all()
    assert "max_output_tokens" not in db.get(AgentVersion, legacy.id).config["limits"]
