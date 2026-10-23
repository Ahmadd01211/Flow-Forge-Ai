from tests.conftest import headers, register


def test_linear_workflow_preview_with_approved_tool(client, owner):
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Replace"}).json()
    graph = workflow["graph"]
    graph["input_schema"] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "find": {"type": "string"},
            "replacement": {"type": "string"},
        },
        "required": ["text", "find", "replacement"],
        "additionalProperties": False,
    }
    graph["nodes"].insert(
        1,
        {
            "id": "replace",
            "type": "tool",
            "label": "Replace",
            "position": {"x": 300, "y": 180},
            "config": {"tool_key": "text.replace"},
        },
    )
    graph["nodes"][-1]["config"] = {
        "value": {"kind": "output", "node_id": "replace", "pointer": ""}
    }
    graph["edges"] = [
        {"id": "input-replace", "source": "input", "target": "replace"},
        {"id": "replace-result", "source": "replace", "target": "result"},
    ]
    updated = client.patch(
        f"{base}/{workflow['id']}",
        headers=headers(client),
        json={"name": "Replace", "description": "", "expected_revision": 1, "graph": graph},
    )
    assert updated.status_code == 200, updated.text
    path = f"{base}/{workflow['id']}"
    validation = client.post(
        f"{path}/validate", headers=headers(client), json={"expected_revision": 2}
    ).json()
    assert not validation["valid"] and validation["errors"][0]["code"] == "TOOL_NOT_APPROVED"
    client.put(f"/api/v1/workspaces/{workspace}/tools/text.replace", headers=headers(client))
    validation = client.post(
        f"{path}/validate", headers=headers(client), json={"expected_revision": 2}
    ).json()
    assert validation["valid"] and validation["publishable"]
    payload = {
        "expected_revision": 2,
        "input": {"text": "Hello world", "find": "world", "replacement": "team"},
    }
    preview = client.post(f"{path}/preview", headers=headers(client), json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["output"] == {"text": "Hello team"}
    assert [step["node_id"] for step in preview.json()["steps"]] == ["input", "replace", "result"]
    assert preview.json()["durable"] is False
    client.cookies.clear()
    register(client, "other-preview@example.com")
    assert client.post(f"{path}/preview", headers=headers(client), json=payload).status_code == 404


def test_minimal_workflow_preview_and_revision_guard(client, owner):
    workspace = owner["workspaces"][0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace}/workflows", headers=headers(client), json={"name": "Echo"}
    ).json()
    path = f"/api/v1/workspaces/{workspace}/workflows/{workflow['id']}/preview"
    assert (
        client.post(
            path, headers=headers(client), json={"expected_revision": 2, "input": {"ticket": "A"}}
        ).status_code
        == 409
    )
    preview = client.post(
        path, headers=headers(client), json={"expected_revision": 1, "input": {"ticket": "A"}}
    )
    assert preview.status_code == 200 and preview.json()["output"] == {"ticket": "A"}
