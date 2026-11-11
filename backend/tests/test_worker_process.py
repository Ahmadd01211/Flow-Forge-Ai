import os
import subprocess
import sys
import time
import uuid

from celery import Celery
from redis.exceptions import RedisError

from app.modules.workflows.models import WorkflowRun
from tests.conftest import headers


def test_readiness_fails_when_required_broker_is_unavailable(client, monkeypatch):
    assert client.get("/health/ready").status_code == 200

    def unavailable():
        raise RedisError("Unavailable")

    monkeypatch.setattr(client.app.state.redis, "ping", unavailable)
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200


def test_worker_standalone_import_resolves_every_foreign_key():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.modules.executions.worker; from app.core.db import Base; print(len(Base.metadata.sorted_tables))",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, "Standalone worker model registration failed"
    assert int(result.stdout.strip()) >= 20


def test_real_celery_worker_completes_a_durable_workflow(client, owner):
    settings = client.app.state.settings
    assert settings.database_url.split("?")[0].endswith("_test")
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/workflows"
    workflow = client.post(base, headers=headers(client), json={"name": "Process smoke"}).json()
    graph = workflow["graph"]
    graph["nodes"][1:1] = [
        {
            "id": "left",
            "type": "transform",
            "label": "Message",
            "position": {"x": 200, "y": 0},
            "config": {"fields": {"message": {"kind": "input", "pointer": "/message"}}},
        },
        {
            "id": "right",
            "type": "transform",
            "label": "Status",
            "position": {"x": 200, "y": 200},
            "config": {"fields": {"status": {"kind": "literal", "value": "received"}}},
        },
        {
            "id": "merge",
            "type": "merge",
            "label": "Merge",
            "position": {"x": 400, "y": 100},
            "config": {"mode": "all"},
        },
    ]
    graph["nodes"][-1]["config"] = {
        "fields": {
            "message": {"kind": "input", "pointer": "/left/message"},
            "status": {"kind": "input", "pointer": "/right/status"},
        }
    }
    graph["edges"] = [
        {"id": f"{source}-{target}", "source": source, "target": target}
        for source, target in [
            ("input", "left"),
            ("input", "right"),
            ("left", "merge"),
            ("right", "merge"),
            ("merge", "result"),
        ]
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
    version = client.post(
        f"{base}/{workflow['id']}/versions", headers=headers(client), json={"expected_revision": 2}
    ).json()
    created = client.post(
        f"/api/v1/workspaces/{workspace}/workflow-runs",
        headers={**headers(client), "Idempotency-Key": "real-worker-0001"},
        json={"version_id": version["id"], "input": {"message": "Durable worker check"}},
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    queue = "process-test-" + uuid.uuid4().hex
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "CREDENTIAL_KEY_PATH": settings.credential_key_path,
        "C_FORCE_ROOT": "1",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.modules.executions.worker:celery",
            "worker",
            "--pool=solo",
            "--queues=" + queue,
            "--loglevel=ERROR",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        broker = Celery("process-test", broker=settings.redis_url)
        broker.send_task("flowforge.execute_workflow", args=[run_id], queue=queue)
        deadline = time.monotonic() + 12
        state = "queued"
        while time.monotonic() < deadline:
            with client.app.state.sessions() as db:
                state = db.get(WorkflowRun, uuid.UUID(run_id)).state
            if state not in {"queued", "running"}:
                break
            assert process.poll() is None, "Celery worker exited before completing its run"
            time.sleep(0.1)
        result = client.get(f"/api/v1/workspaces/{workspace}/workflow-runs/{run_id}").json()
        assert state == "completed", {"state": state, "error_code": result.get("error_code")}
        assert result["output"] == {"message": "Durable worker check", "status": "received"}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
