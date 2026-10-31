import uuid

from app.modules.agents.evaluations import EvaluationSuite
from app.modules.executions.runtime import execute
from tests.conftest import headers, register
from tests.test_agent_runs import published_agent, submit


def test_regressions_require_observed_evidence_and_encrypt_examples(client, owner, db, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/agents/{version['agent_id']}/evaluations"
    suite = client.post(
        base,
        headers=headers(client),
        json={
            "name": "Ticket regressions",
            "cases": [
                {
                    "name": "Urgent",
                    "input": {"ticket": "confidential outage"},
                    "expected_output": {"priority": "urgent"},
                },
                {
                    "name": "Not run",
                    "input": {"ticket": "A different ticket"},
                    "expected_output": {"priority": "normal"},
                },
            ],
        },
    )
    assert suite.status_code == 201, suite.text
    row = db.get(EvaluationSuite, uuid.UUID(suite.json()["id"]))
    assert b"confidential outage" not in row.ciphertext
    path = f"{base}/{row.id}/evaluate"
    body = {"version_id": version["id"]}
    initial = client.post(path, headers=headers(client), json=body).json()
    assert initial["passed"] == 0 and all(r["status"] == "untested" for r in initial["items"])
    created = submit(client, workspace, version, value="confidential outage")
    monkeypatch.setattr(
        "app.modules.executions.runtime.generate", lambda *_: ({"priority": "urgent"}, 20, 5)
    )
    execute(created.json()["id"], client.app.state.settings)
    observed = client.post(path, headers=headers(client), json=body).json()
    assert observed["passed"] == 1 and observed["total"] == 2
    assert (
        observed["items"][0]["status"] == "passed" and observed["items"][1]["status"] == "untested"
    )
    assert observed["model_called"] is False
    assert "confidential outage" not in str(observed)
    client.cookies.clear()
    register(client, "other-evals@example.com")
    assert client.post(path, headers=headers(client), json=body).status_code == 404


def test_bad_examples_are_contract_failures_not_passes(client, owner, monkeypatch):
    workspace, version = published_agent(client, owner, monkeypatch)
    base = f"/api/v1/workspaces/{workspace}/agents/{version['agent_id']}/evaluations"
    suite = client.post(
        base,
        headers=headers(client),
        json={
            "name": "Invalid",
            "cases": [
                {"name": "Wrong input", "input": {}, "expected_output": {"priority": "unsupported"}}
            ],
        },
    ).json()
    result = client.post(
        f"{base}/{suite['id']}/evaluate",
        headers=headers(client),
        json={"version_id": version["id"]},
    ).json()
    assert result["items"][0]["status"] == "contract_failed" and result["passed"] == 0
