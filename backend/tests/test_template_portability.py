from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.templates.router import accessible, portable_definition
from app.modules.workflows.schemas import initial_graph


def test_workflow_snapshot_clears_private_bindings_without_mutating_draft():
    graph = initial_graph()
    for kind in ("agent", "mcp_tool", "http_tool", "subworkflow", "for_each", "webhook_trigger", "schedule_trigger"):
        graph["nodes"].append(
            {
                "id": kind,
                "type": kind,
                "label": kind,
                "position": {"x": 0, "y": 0},
                "config": {
                    "connection_id": "secret",
                    "version_id": "private",
                    "headers": {"Authorization": "secret"},
                },
            }
        )
    original = deepcopy(graph)
    snapshot = portable_definition("workflow", graph)["graph"]
    assert graph == original
    assert all(node["config"] == {} for node in snapshot["nodes"][2:])
    assert snapshot["edges"] == original["edges"]


def test_agent_snapshot_clears_model_and_preserves_instructions():
    source = {"model_id": "private-model", "instructions": "Reusable instructions"}
    snapshot = portable_definition("agent", source)["config"]
    assert snapshot["model_id"] == ""
    assert snapshot["instructions"] == source["instructions"]
    assert snapshot["http_tools"] == []
    assert source["model_id"] == "private-model"


@pytest.mark.parametrize(
    "visibility,owner,member,allowed",
    [
        ("private", True, False, True),
        ("private", False, True, False),
        ("workspace", False, True, True),
        ("workspace", False, False, False),
        ("public", False, False, True),
    ],
)
def test_template_access(monkeypatch, visibility, owner, member, allowed):
    user_id = uuid4()
    row = SimpleNamespace(
        created_by=user_id if owner else uuid4(), visibility=visibility, workspace_id=uuid4()
    )
    db = MagicMock()
    db.get.return_value = row
    db.scalar.return_value = object() if member else None
    monkeypatch.setattr(
        "app.modules.templates.router.current_session",
        lambda *_: (SimpleNamespace(id=user_id), None),
    )
    if allowed:
        assert accessible(str(uuid4()), None, db) is row
    else:
        with pytest.raises(Exception) as error:
            accessible(str(uuid4()), None, db)
        assert error.value.status_code == 404
