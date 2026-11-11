"""Execute the saved artifact asserted by the real frontend insertion test."""

import json
from pathlib import Path

import pytest

from app.modules.workflows.runtime import execute
from tests.conftest import headers


@pytest.mark.parametrize("value, port", [("match", "case-inserted"), ("other", "default")])
def test_builder_inserted_switch_reaches_ordinary_continuation(client, owner, value, port):
    workspace = owner["workspaces"][0]["id"]
    graph = json.loads(
        (Path(__file__).parent / "fixtures" / "builder-switch-continuation.json").read_text(
            encoding="utf-8"
        )
    )
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Inserted Switch"}).json()
    path = f"{base}/{workflow['id']}"
    saved = client.patch(path, headers=headers(client), json={
        "name": "Inserted Switch", "expected_revision": 1, "graph": graph,
    })
    assert saved.status_code == 200, saved.text
    input_data = {"route": value, "items": ["a", "b", "a", "b", "c"]}
    preview = client.post(f"{path}/preview", headers=headers(client), json={
        "expected_revision": 2, "input": input_data,
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["output"] == {"items": ["a", "b", "c"], "count": 3, "removed": 2}
    assert all(step["status"] == "completed" for step in preview.json()["steps"])
    assert next(step for step in preview.json()["steps"] if step["type"] == "switch")["selected_port"] == port

    published = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert published.status_code == 201, published.text
    runs = f"/api/v1/workspaces/{workspace}/workflow-runs"
    submitted = client.post(runs, headers={**headers(client), "Idempotency-Key": f"inserted-{port}"}, json={
        "version_id": published.json()["id"], "input": input_data,
    })
    assert submitted.status_code == 202, submitted.text
    execute(submitted.json()["id"], client.app.state.settings)
    durable = client.get(f"{runs}/{submitted.json()['id']}").json()
    assert durable["state"] == "completed"
    assert durable["output"] == preview.json()["output"]
