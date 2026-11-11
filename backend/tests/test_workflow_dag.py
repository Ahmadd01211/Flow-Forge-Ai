from decimal import Decimal

import pytest

from app.modules.executions.runtime import ProviderFailure
from tests.conftest import headers
from tests.test_workflow_data_nodes import _run, _save


def node(identity, kind, config=None):
    return {
        "id": identity,
        "type": kind,
        "label": identity,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge(source, target, port="out", mappings=None):
    return {
        "id": f"{source}-{port}-{target}",
        "source": source,
        "target": target,
        "source_port": port,
        "mappings": mappings or [],
    }


def condition(identity, field):
    return node(
        identity,
        "condition",
        {
            "operator": "eq",
            "left": {"kind": "input", "pointer": field},
            "right": {"kind": "literal", "value": True},
        },
    )


def transform(identity, value):
    return node(identity, "transform", {"fields": {"queue": {"kind": "literal", "value": value}}})


@pytest.mark.parametrize(
    "urgent,vip,expected",
    [(False, False, "standard"), (True, False, "urgent"), (True, True, "vip")],
)
def test_nested_conditions_rejoin_with_inactive_paths(client, owner, urgent, vip, expected):
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "nodes": [
            node("input", "manual_input"),
            condition("urgent", "/urgent"),
            condition("vip", "/vip"),
            transform("standard", "standard"),
            transform("priority", "urgent"),
            transform("dedicated", "vip"),
            node("merge", "merge", {"mode": "active"}),
            node("result", "result"),
        ],
        "edges": [
            edge("input", "urgent"),
            edge("urgent", "vip", "true"),
            edge("urgent", "standard", "false"),
            edge("vip", "dedicated", "true"),
            edge("vip", "priority", "false"),
            edge("dedicated", "merge"),
            edge("priority", "merge"),
            edge("standard", "merge"),
            edge("merge", "result"),
        ],
    }
    path = _save(client, workspace, "Nested routing", graph)
    preview = client.post(
        path + "/preview",
        headers=headers(client),
        json={"expected_revision": 2, "input": {"urgent": urgent, "vip": vip}},
    )
    assert preview.status_code == 200 and preview.json()["output"] == {"queue": expected}, (
        preview.text
    )
    assert any(step["status"] == "skipped" for step in preview.json()["steps"])
    version = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 2}
    )
    assert version.status_code == 201, version.text
    run = _run(
        client,
        workspace,
        version.json()["id"],
        {"urgent": urgent, "vip": vip},
        "nested-routing-001",
    )
    assert run["state"] == "completed" and run["output"] == preview.json()["output"]


def test_fanout_namespaces_mapped_outputs_and_rejects_mapping_collisions(client, owner):
    workspace = owner["workspaces"][0]["id"]
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node("left", "transform", {"fields": {"raw": {"kind": "literal", "value": 1}}}),
            node("right", "transform", {"fields": {"raw": {"kind": "literal", "value": 2}}}),
            node("merge", "merge", {"mode": "all"}),
            node(
                "result",
                "result",
                {
                    "fields": {
                        "left": {"kind": "input", "pointer": "/left/value"},
                        "right": {"kind": "input", "pointer": "/right/value"},
                    }
                },
            ),
        ],
        "edges": [
            edge("input", "left"),
            edge("input", "right"),
            edge("left", "merge", mappings=[{"from": "/raw", "to": "/value"}]),
            edge("right", "merge", mappings=[{"from": "/raw", "to": "/value"}]),
            edge("merge", "result"),
        ],
    }
    path = _save(client, workspace, "Mapped fanout", graph)
    result = client.post(
        path + "/preview", headers=headers(client), json={"expected_revision": 2, "input": {}}
    )
    assert result.status_code == 200 and result.json()["output"] == {"left": 1, "right": 2}, (
        result.text
    )
    graph["edges"][2]["mappings"] = [
        {"from": "/raw", "to": "/value"},
        {"from": "/raw", "to": "/value/nested"},
    ]
    checked = client.post(path + "/check", headers=headers(client), json={"graph": graph}).json()
    assert not checked["valid"] and any(
        issue["code"] == "MAPPING_CONFLICT" and issue["edge_id"] == "left-out-merge"
        for issue in checked["errors"]
    )


def ticket_agent(client, owner, monkeypatch):
    workspace = owner["workspaces"][0]["id"]
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    base = f"/api/v1/workspaces/{workspace}"
    assert (
        client.post(
            base + "/integrations/providers/openai",
            headers=headers(client),
            json={"api_key": "test-dag-provider-key"},
        ).status_code
        == 200
    )
    schema = {
        "type": "object",
        "properties": {"ticket": {"type": "string"}},
        "required": ["ticket"],
        "additionalProperties": False,
    }
    agent = client.post(
        base + "/agents",
        headers=headers(client),
        json={
            "name": "Enrich ticket",
            "config": {
                "instructions": "Enrich the ticket text.",
                "model_id": "gpt-5-mini",
                "input_schema": schema,
                "output_schema": schema,
            },
        },
    ).json()
    version = client.post(
        f"{base}/agents/{agent['id']}/versions",
        headers=headers(client),
        json={"expected_revision": 1},
    ).json()
    graph = {
        "nodes": [
            node("input", "manual_input"),
            node("first", "agent", {"version_id": version["id"]}),
            node("second", "agent", {"version_id": version["id"]}),
            node("result", "result"),
        ],
        "edges": [edge("input", "first"), edge("first", "second"), edge("second", "result")],
        "limits": {"max_cost_usd": "0.01"},
    }
    path = _save(client, workspace, "Two agent pipeline", graph)
    published = client.post(
        path + "/versions", headers=headers(client), json={"expected_revision": 2}
    )
    assert published.status_code == 201, published.text
    return workspace, published.json()


def test_multiple_agents_share_workflow_cost_output_and_token_limits(client, owner, monkeypatch):
    workspace, version = ticket_agent(client, owner, monkeypatch)
    caps = []

    def generate(_, __, data, max_tokens, timeout):
        caps.append(max_tokens)
        assert timeout <= 25
        return {"ticket": data["ticket"] + "!"}, 10000, 20

    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    run = _run(client, workspace, version["id"], {"ticket": "Help"}, "two-agent-pipeline-001")
    assert run["state"] == "completed" and run["output"] == {"ticket": "Help!!"}, run
    assert len(caps) == 2 and caps[1] < caps[0]
    assert run["input_tokens"] == 20000 and run["output_tokens"] == 40
    assert Decimal(run["cost_usd"]) == sum(
        Decimal(step["usage"]["cost_usd"]) for step in run["steps"] if step["type"] == "agent"
    )


def test_later_agent_unknown_outcome_preserves_known_plus_uncertain_cost(
    client, owner, monkeypatch
):
    workspace, version = ticket_agent(client, owner, monkeypatch)
    calls = []

    def generate(_, __, data, *___):
        calls.append(data)
        if len(calls) == 2:
            raise ProviderFailure("PROVIDER_OUTCOME_UNKNOWN", uncertain=True)
        return data, 10000, 20

    monkeypatch.setattr("app.modules.workflows.runtime.generate", generate)
    run = _run(client, workspace, version["id"], {"ticket": "Help"}, "two-agent-unknown-001")
    assert run["state"] == "failed" and run["error_code"] == "PROVIDER_OUTCOME_UNKNOWN"
    assert Decimal(run["cost_usd"]) > 0 and Decimal(run["uncertain_cost_usd"]) > 0
    usage = client.get(f"/api/v1/workspaces/{workspace}/usage").json()
    assert Decimal(usage["measured_usd"]) + Decimal(usage["uncertain_usd"]) == Decimal("0.01")
    assert Decimal(usage["committed_usd"]) == Decimal("0.01")
