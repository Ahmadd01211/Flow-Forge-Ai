import json

from sqlalchemy import select

from app.modules.executions.models import RunEvent
from app.modules.executions.runtime import execute
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers
from tests.test_skills import _agent, _connect, _skill


def _scripted_model(monkeypatch, fail_tool=False):
    """Load a skill, look up an order, then answer: three model turns per run."""
    turns = []

    def model(_key, payload, _timeout, *_rest):
        turns.append(payload)
        step = (len(turns) - 1) % 3
        if step == 0:
            call = {"name": "use_skill", "arguments": json.dumps({"skill": "Brand voice"})}
        elif step == 1:
            call = {"name": "lookup_order", "arguments": json.dumps({"order_id": "A-17" if not fail_tool else 7})}
        else:
            return {"status": "completed", "usage": {"input_tokens": 30, "output_tokens": 9}, "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"reply": "Your jacket can be returned."})}]},
            ]}
        return {"status": "completed", "usage": {"input_tokens": 20, "output_tokens": 4}, "output": [{"type": "function_call", "call_id": f"c{len(turns)}", **call}]}

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    return turns


def _published_agent(client, workspace, monkeypatch):
    _connect(client, workspace, monkeypatch)
    client.put(f"/api/v1/workspaces/{workspace}/tools/demo.order_lookup", headers=headers(client))
    voice = _skill(client, workspace, tool_keys=["demo.order_lookup"])
    agent = _agent(client, workspace, [voice])
    version = client.post(f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    assert version.status_code == 201, version.text
    return agent, version.json()


def _run(client, workspace, version, key, message="Can I return A-17?"):
    submitted = client.post(f"/api/v1/workspaces/{workspace}/runs", headers={**headers(client), "Idempotency-Key": key},
                            json={"version_id": version["id"], "input": {"message": message}})
    assert submitted.status_code == 202, submitted.text
    execute(submitted.json()["id"], client.app.state.settings)
    return submitted.json()["id"]


def test_trace_shows_each_step_with_payloads_timing_and_cost(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    agent, version = _published_agent(client, workspace, monkeypatch)
    _scripted_model(monkeypatch)
    run_id = _run(client, workspace, version, "trace-run-0001")
    trace = client.get(f"/api/v1/workspaces/{workspace}/runs/{run_id}/trace").json()
    assert trace["run"]["state"] == "completed" and trace["input"] == {"message": "Can I return A-17?"}
    assert trace["agent"]["id"] == agent["id"] and trace["agent"]["skills"] == [{"name": "Brand voice", "number": 1}]
    assert [(step["kind"], step["label"]) for step in trace["steps"]] == [
        ("model", "Model call"), ("skill", "Brand voice"), ("model", "Model call"), ("tool", "demo.order_lookup"), ("model", "Model call"),
    ]
    skill, lookup = trace["steps"][1], trace["steps"][3]
    assert skill["output"]["instructions"] == "Write warmly." and lookup["arguments"] == {"order_id": "A-17"}
    assert lookup["output"]["found"] is True and lookup["output"]["status"] == "delivered"
    assert all(step["duration_ms"] is not None and step["duration_ms"] >= 0 for step in trace["steps"])
    assert trace["steps"][0]["input_tokens"] == 20 and trace["steps"][0]["cost_usd"] is not None
    assert trace["totals"] == {**trace["totals"], "model_calls": 3, "tool_calls": 2}
    stored = db.scalars(select(RunEvent.ciphertext).where(RunEvent.run_id == run_id, RunEvent.ciphertext.is_not(None))).all()
    assert len(stored) == 2 and all(b"A-17" not in blob for blob in stored)


def test_feedback_is_one_rating_per_person_and_viewers_can_rate(client, owner, db, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    _agent_, version = _published_agent(client, workspace, monkeypatch)
    _scripted_model(monkeypatch)
    run_id = _run(client, workspace, version, "feedback-run-001")
    path = f"/api/v1/workspaces/{workspace}/runs/{run_id}/feedback"
    assert client.put(path, headers=headers(client), json={"rating": "up"}).json()["up"] == 1
    changed = client.put(path, headers=headers(client), json={"rating": "down", "comment": "Too long"}).json()
    assert changed["up"] == 0 and changed["down"] == 1 and changed["mine"] == {"rating": "down", "comment": "Too long"}
    assert changed["comments"][0]["comment"] == "Too long"
    assert client.request("DELETE", path, headers=headers(client)).json() == {"up": 0, "down": 0, "mine": None, "comments": []}
    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace))
    member.role = "viewer"
    db.commit()
    assert client.put(path, headers=headers(client), json={"rating": "up"}).status_code == 200


def test_performance_summarises_runs_tools_errors_and_feedback(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    agent, version = _published_agent(client, workspace, monkeypatch)
    _scripted_model(monkeypatch)
    good = _run(client, workspace, version, "perf-run-000001")
    _run(client, workspace, version, "perf-run-000002")
    client.put(f"/api/v1/workspaces/{workspace}/runs/{good}/feedback", headers=headers(client), json={"rating": "down", "comment": "Wrong order"})

    def broken(*_args):
        return {"status": "incomplete", "usage": {"input_tokens": 1, "output_tokens": 1}, "output": []}

    monkeypatch.setattr("app.modules.executions.runtime._openai_response", broken)
    _run(client, workspace, version, "perf-run-000003")
    base = f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/performance"
    summary = client.get(base).json()
    assert summary["runs"] == 3 and summary["completed"] == 2 and summary["failed"] == 1
    assert summary["success_rate"] == round(2 / 3, 4) and summary["errors"] == [{"code": "PROVIDER_INCOMPLETE", "count": 1}]
    tools = {item["label"]: item for item in summary["tools"]}
    assert tools["demo.order_lookup"]["calls"] == 2 and tools["Brand voice"]["kind"] == "skill"
    assert summary["feedback"]["down"] == 1 and summary["feedback"]["recent_down"][0]["comment"] == "Wrong order"
    assert len(summary["daily"]) == 7 and summary["daily"][-1]["runs"] == 3
    assert summary["recent"][0]["state"] == "failed" and summary["duration_p50_s"] is not None

    _scripted_model(monkeypatch)
    draft = client.get(f"/api/v1/workspaces/{workspace}/agents/{agent['id']}").json()["config"]
    client.post(f"/api/v1/workspaces/{workspace}/agents/{agent['id']}/try", headers={**headers(client), "Idempotency-Key": "perf-try-00001"},
                json={"config": draft, "input": {"message": "hi"}})
    assert client.get(base).json()["runs"] == 3
    with_tests = client.get(base, params={"include_tests": True, "days": 30}).json()
    assert with_tests["runs"] == 4 and with_tests["recent"][0]["source"] == "test" and len(with_tests["daily"]) == 30
