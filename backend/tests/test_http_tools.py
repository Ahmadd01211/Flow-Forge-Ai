import json
import socket
import uuid

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.modules.http_tools import service, transport
from app.modules.http_tools.models import HttpTool
from app.modules.workflows.models import WorkflowRun, WorkflowVersion
from app.modules.workflows.runtime import execute
from tests.conftest import headers


def create_tool(client, owner, monkeypatch, **changes):
    monkeypatch.setattr(transport, "public_address", lambda *_a, **_k: "93.184.216.34")
    base = f"/api/v1/workspaces/{owner['workspaces'][0]['id']}"
    body = {"name": "Ticket API", "url": "https://api.example.com/tickets", "method": "GET",
            "read_only": True, "auth_mode": "bearer", "credential": "test-http-secret",
            "confirm_permissions": True, "input_schema": {"type": "object", "properties": {"ticket": {"type": "string"}}, "required": ["ticket"], "additionalProperties": False}}
    result = client.post(f"{base}/http-tools", headers=headers(client), json={**body, **changes})
    assert result.status_code == 201, result.text
    return base, result.json()


@pytest.mark.parametrize("url", ["http://api.example.com/", "https://localhost/", "https://a.internal/", "https://127.0.0.1/", "https://169.254.169.254/latest", "https://api.example.com:444/", "https://user:secret@api.example.com/", "https://api.example.com/?key=secret", "https://api.example.com/#x", "https://api.example.com\\@internal/", "https://api.example.com/\n"])
def test_http_blocks_unapproved_url_forms(url):
    with pytest.raises(HTTPException):
        transport.canonical_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.2", "0.0.0.0", "224.0.0.1", "192.0.2.1", "100.64.0.1"])
def test_http_checks_every_dns_answer(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(socket.AF_INET, 1, 6, "", (ip, 443)) for ip in ["93.184.216.34", address]])
    with pytest.raises(HTTPException) as error:
        transport.public_address("api.example.com")
    assert error.value.detail["code"] == "HTTP_ENDPOINT_BLOCKED"


def test_dns_deadline_does_not_release_a_stalled_resolver_slot_early(monkeypatch):
    import threading
    import time
    release = threading.Event()
    entered = threading.Event()
    def blocked(*_a, **_k):
        entered.set()
        release.wait(2)
        return [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))]
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(transport, "DNS_SLOTS", slots)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    try:
        began = time.monotonic()
        with pytest.raises(HTTPException) as error:
            transport.public_address("api.example.com", timeout=0.02)
        assert error.value.detail["code"] == "HTTP_DNS_TIMEOUT" and entered.is_set()
        assert time.monotonic() - began < 1
        with pytest.raises(HTTPException) as busy:
            transport.public_address("api.example.com")
        assert busy.value.detail["code"] == "HTTP_DNS_BUSY"
    finally:
        release.set()
        assert slots.acquire(timeout=2)
        slots.release()


def test_http_pins_address_preserves_tls_identity_and_scrubs_secret(monkeypatch):
    real_client = httpx.AsyncClient
    seen = []
    def response(request):
        seen.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(b'{"echo":"test-http-secret"}'))
    def client(**kwargs):
        assert kwargs["verify"] is True and kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return real_client(**kwargs, transport=httpx.MockTransport(response))
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(transport, "public_address", lambda *_a, **_k: "93.184.216.34")
    spec = {"url": "https://api.example.com/tickets", "method": "GET", "auth_mode": "bearer", "auth_header": "Authorization"}
    output = transport.request(spec, "test-http-secret", {"ticket": "hello & goodbye"})
    assert output["body"]["echo"] == "[redacted credential]"
    request = seen[0]
    assert request.url.host == "93.184.216.34" and request.headers["host"] == "api.example.com"
    assert request.extensions["sni_hostname"] == "api.example.com"
    assert request.headers["authorization"] == "Bearer test-http-secret"
    assert request.url.params["ticket"] == "hello & goodbye"


@pytest.mark.parametrize("status,body,headers_,code", [(302, b'', {"Location": "http://127.0.0.1"}, "HTTP_STATUS_302"), (200, b'x'*65537, {"Content-Type": "application/json"}, "HTTP_RESULT_TOO_LARGE"), (200, b'{}', {"Content-Type": "text/html"}, "HTTP_RESPONSE_INVALID"), (200, b'{}', {"Content-Type": "application/json", "Content-Encoding": "gzip"}, "HTTP_ENCODING_UNSUPPORTED")])
def test_http_rejects_redirects_oversize_and_non_json(monkeypatch, status, body, headers_, code):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(status, headers=headers_, stream=httpx.ByteStream(body)))))
    monkeypatch.setattr(transport, "public_address", lambda *_a, **_k: "93.184.216.34")
    with pytest.raises(HTTPException) as error:
        transport.request({"url": "https://api.example.com/", "method": "GET", "auth_mode": "none"}, "", {})
    assert error.value.detail["code"] == code


@pytest.mark.parametrize("vendor_code,expected", [("not_in_channel", "SLACK_NOT_IN_CHANNEL"), ("arbitrary test-http-secret", "SLACK_REQUEST_REJECTED")])
def test_slack_http_200_rejection_is_a_failure_without_echoing_vendor_text(monkeypatch, vendor_code, expected):
    real_client = httpx.AsyncClient
    payload = json.dumps({"ok": False, "error": vendor_code}).encode()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={"Content-Type": "application/json"}, stream=httpx.ByteStream(payload)))))
    monkeypatch.setattr(transport, "public_address", lambda *_a, **_k: "93.184.216.34")
    with pytest.raises(HTTPException) as error:
        transport.request({"url": "https://slack.com/api/chat.postMessage", "method": "POST", "auth_mode": "bearer", "auth_header": "Authorization"}, "test-http-secret", {"channel": "C0123456789", "text": "A controlled test"})
    assert error.value.detail["code"] == expected
    assert "test-http-secret" not in str(error.value.detail)


def test_http_encryption_scoping_rotation_and_test_contract(client, owner, db, monkeypatch):
    base, tool = create_tool(client, owner, monkeypatch)
    assert "test-http-secret" not in json.dumps(tool)
    row = db.get(HttpTool, uuid.UUID(tool["id"]))
    assert row.ciphertext and b"test-http-secret" not in row.ciphertext
    with pytest.raises(HTTPException) as error:
        service.resolve(db, uuid.uuid4(), {"tool_id": tool["id"]}, pinned=False)
    assert error.value.status_code == 404
    grant = service.pin(db, row.workspace_id, [{"tool_id": tool["id"], "connection_generation": 999}])[0]
    assert grant["connection_generation"] == 1
    calls = []
    monkeypatch.setattr(service, "request", lambda spec, secret, args, timeout: calls.append((secret, args)) or {"status_code": 200, "body": {"ok": True}})
    path = f"{base}/http-tools/{tool['id']}"
    assert client.post(f"{path}/test", headers=headers(client), json={"input": {"ticket": "123"}}).status_code == 422
    invalid = client.post(f"{path}/test", headers=headers(client), json={"input": {}, "confirm_external": True})
    assert invalid.status_code == 422 and not calls
    assert client.post(f"{path}/test", headers=headers(client), json={"input": {"ticket": "123"}, "confirm_external": True}).status_code == 200
    assert calls == [("test-http-secret", {"ticket": "123"})]
    assert client.post(f"{path}/rotate", headers=headers(client), json={"expected_generation": 2, "credential": "next-http-secret"}).status_code == 409
    assert client.post(f"{path}/rotate", headers=headers(client), json={"expected_generation": 1, "credential": "next-http-secret"}).status_code == 200
    with pytest.raises(HTTPException) as error:
        service.resolve(db, row.workspace_id, grant)
    assert error.value.detail["code"] == "HTTP_TOOL_CHANGED"
    assert client.post(f"{path}/revoke", headers=headers(client), json={"expected_generation": 2}).status_code == 200
    db.refresh(row)
    assert not row.ciphertext and row.state == "revoked"


def test_http_writes_require_workflow_and_checkpoint_receipts(client, owner, db, monkeypatch):
    base, tool = create_tool(client, owner, monkeypatch, method="POST", read_only=False)
    with pytest.raises(HTTPException) as error:
        service.pin(db, uuid.UUID(owner['workspaces'][0]['id']), [{"tool_id": tool["id"]}])
    assert error.value.detail["code"] == "HTTP_WRITE_GRANT_DENIED"
    assert client.post(f"{base}/http-tools/{tool['id']}/test", headers=headers(client), json={"input": {"ticket": "123"}, "confirm_external": True}).status_code == 422
    workflow = client.post(f"{base}/workflows", headers=headers(client), json={"name": "Create ticket"}).json()
    graph = workflow["graph"]
    graph["nodes"].insert(1, {"id": "send", "type": "http_tool", "label": "Create ticket", "position": {"x": 200, "y": 200}, "config": {"tool_id": tool["id"]}})
    graph["nodes"][-1]["config"] = {"value": {"kind": "output", "node_id": "send", "pointer": ""}}
    graph["edges"] = [{"id": "e1", "source": "input", "target": "send"}, {"id": "e2", "source": "send", "target": "result"}]
    path = f"{base}/workflows/{workflow['id']}"
    assert client.patch(path, headers=headers(client), json={"name": workflow["name"], "expected_revision": 1, "graph": graph}).status_code == 200
    version = client.post(f"{path}/versions", headers=headers(client), json={"expected_revision": 2})
    assert version.status_code == 201, version.text
    frozen = db.get(WorkflowVersion, uuid.UUID(version.json()["id"]))
    assert frozen.graph["nodes"][1]["config"]["connection_generation"] == 1
    calls = []
    def send(spec, secret, args, timeout):
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(queued.json()["id"])).execution_options(populate_existing=True))
        assert run.external_inflight and 0 < timeout <= 12
        calls.append(args)
        return {"status_code": 201, "body": {"receipt": "ticket-123"}}
    monkeypatch.setattr(service, "request", send)
    queued = client.post(f"{base}/workflow-runs", headers={**headers(client), "Idempotency-Key": "http-workflow-001"}, json={"version_id": version.json()["id"], "input": {"ticket": "123"}})
    assert queued.status_code == 202, queued.text
    execute(queued.json()["id"], client.app.state.settings)
    execute(queued.json()["id"], client.app.state.settings)
    result = client.get(f"{base}/workflow-runs/{queued.json()['id']}").json()
    assert result["state"] == "completed", result
    assert len(calls) == 1 and result["output"]["body"]["receipt"] == "ticket-123"
    assert result["steps"][1]["status"] == "completed"
    db.expire_all()
    assert not db.get(WorkflowRun, uuid.UUID(queued.json()["id"])).external_inflight


@pytest.mark.parametrize("revoke_provider", [False, True])
def test_agent_http_grant_uses_server_contract_and_checks_provider_between_turns(client, owner, db, monkeypatch, revoke_provider):
    from app.modules.executions.runtime import execute as execute_agent
    from app.modules.http_tools.service import alias
    from app.modules.integrations.models import IntegrationConnection

    base, tool = create_tool(client, owner, monkeypatch)
    monkeypatch.setattr("app.modules.integrations.service.verify_key", lambda *_: ["gpt-5-mini"])
    assert client.post(f"{base}/integrations/providers/openai", headers=headers(client), json={"api_key": "test-provider-secret"}).status_code == 200
    draft = client.post(f"{base}/agents", headers=headers(client), json={"name": "Ticket reader", "config": {"instructions": "Look up ticket details.", "model_id": "gpt-5-mini", "http_tools": [{"tool_id": tool["id"], "connection_generation": 999, "input_schema": {"type": "object"}}]}}).json()
    version = client.post(f"{base}/agents/{draft['id']}/versions", headers=headers(client), json={"expected_revision": 1})
    assert version.status_code == 201, version.text
    grant = version.json()["config"]["http_tools"][0]
    assert grant["connection_generation"] == 1 and grant["input_schema"]["required"] == ["ticket"]
    calls = []
    def model(_key, payload, _timeout):
        calls.append(payload)
        if len(calls) == 1:
            return {"status": "completed", "usage": {"input_tokens": 40, "output_tokens": 10}, "output": [{"type": "function_call", "name": alias(grant), "call_id": "http-1", "arguments": '{"ticket":"123"}'}]}
        return {"status": "completed", "usage": {"input_tokens": 50, "output_tokens": 10}, "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"priority":"normal"}'}]}]}
    def request(spec, secret, arguments, timeout):
        assert secret == "test-http-secret" and arguments == {"ticket": "123"}
        if revoke_provider:
            connection = db.scalar(select(IntegrationConnection))
            connection.state = "revoked"
            db.commit()
        return {"status_code": 200, "body": {"found": True}}
    monkeypatch.setattr("app.modules.executions.runtime._openai_response", model)
    monkeypatch.setattr(service, "request", request)
    run = client.post(f"{base}/runs", headers={**headers(client), "Idempotency-Key": "http-agent-run-001"}, json={"version_id": version.json()["id"], "input": {"ticket": "123"}})
    assert run.status_code == 202, run.text
    execute_agent(run.json()["id"], client.app.state.settings)
    result = client.get(f"{base}/runs/{run.json()['id']}").json()
    assert "test-http-secret" not in json.dumps(calls)
    if revoke_provider:
        assert result["state"] == "failed" and result["error_code"] == "CREDENTIAL_CHANGED", result
        assert len(calls) == 1
    else:
        assert result["state"] == "completed", result
        assert len(calls) == 2


def test_http_administration_roles_csrf_and_unsafe_headers(client, owner, db, monkeypatch):
    from app.modules.workspaces.models import WorkspaceMember
    base, tool = create_tool(client, owner, monkeypatch)
    for header in ["Host", "Cookie", "Content-Type", "X-Forwarded-Host", "X-HTTP-Method-Override"]:
        result = client.post(f"{base}/http-tools", headers=headers(client), json={"name": "Bad auth", "url": "https://api.example.com/", "auth_mode": "api_key", "auth_header": header, "credential": "test-http-secret", "confirm_permissions": True})
        assert result.status_code == 422, header
    assert client.post(f"{base}/http-tools/{tool['id']}/revoke", json={"expected_generation": 1}).status_code == 403
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    assert client.post(f"{base}/http-tools/{tool['id']}/revoke", headers=headers(client), json={"expected_generation": 1}).status_code == 403
    assert client.get(f"{base}/http-tools").status_code == 200
    member.role = "viewer"
    db.commit()
    assert client.post(f"{base}/http-tools/{tool['id']}/test", headers=headers(client), json={"input": {"ticket": "123"}, "confirm_external": True}).status_code == 403
