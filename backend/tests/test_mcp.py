import json

from sqlalchemy import select

from app.modules.mcp.catalog import catalog, require_public_dns
from app.modules.mcp.models import McpConnection
from app.modules.workspaces.models import WorkspaceMember
from tests.conftest import headers, register

CATALOG = json.dumps(
    [
        {
            "id": "docs",
            "name": "Company docs",
            "url": "https://mcp.example.com/mcp",
            "allowed_tools": ["search", "get_document"],
        }
    ]
)


def test_curated_mcp_connect_test_and_revoke(client, owner, db, monkeypatch):
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr(
        "app.modules.mcp.service.discover", lambda _url, _key: [
            {"name": "search", "description": "Search documents", "input_schema": {"type": "object"}},
            {"name": "delete_everything", "description": "Unsafe", "input_schema": {"type": "object"}},
        ]
    )
    calls = []
    monkeypatch.setattr(
        "app.modules.mcp.service.call_tool",
        lambda url, key, name, args: (
            calls.append((url, key, name, args))
            or {"content": [{"type": "text", "text": "Found 2"}]}
        ),
    )
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/mcp"
    initial = client.get(base).json()["items"]
    assert initial[0]["state"] == "not_connected"
    response = client.put(
        f"{base}/docs", headers=headers(client), json={"bearer_token": "secret-mcp-token"}
    )
    assert response.status_code == 200 and "secret-mcp-token" not in response.text
    assert response.json()["items"][0]["verified_tools"] == ["search"]
    row = db.scalar(select(McpConnection))
    assert row.tool_snapshots == [{"name": "search", "description": "Search documents", "input_schema": {"type": "object"}}]
    assert b"secret-mcp-token" not in row.ciphertext
    assert (
        client.post(
            f"{base}/docs/tools/delete_everything/test",
            headers=headers(client),
            json={"arguments": {}},
        ).status_code
        == 403
    )
    tested = client.post(
        f"{base}/docs/tools/search/test",
        headers=headers(client),
        json={"arguments": {"query": "policy"}},
    )
    assert tested.status_code == 200 and calls == [
        ("https://mcp.example.com/mcp", "secret-mcp-token", "search", {"query": "policy"})
    ]
    assert client.delete(f"{base}/docs", headers=headers(client)).status_code == 200
    db.refresh(row)
    assert row.state == "revoked" and row.ciphertext is None
    assert (
        client.post(
            f"{base}/docs/tools/search/test", headers=headers(client), json={"arguments": {}}
        ).status_code
        == 403
    )


def test_mcp_roles_and_tenant_boundary(client, owner, db, monkeypatch):
    client.app.state.settings.mcp_catalog_json = CATALOG
    monkeypatch.setattr("app.modules.mcp.service.discover", lambda *_: [
        {"name": "search", "description": "Search documents", "input_schema": {"type": "object"}}
    ])
    workspace = owner["workspaces"][0]["id"]
    base = f"/api/v1/workspaces/{workspace}/mcp"
    member = db.scalar(select(WorkspaceMember))
    member.role = "editor"
    db.commit()
    assert client.put(f"{base}/docs", headers=headers(client), json={}).status_code == 403
    member.role = "owner"
    db.commit()
    assert client.put(f"{base}/docs", headers=headers(client), json={}).status_code == 200
    client.cookies.clear()
    register(client, "other-mcp@example.com")
    assert client.get(base).status_code == 404
    assert (
        client.post(
            f"{base}/docs/tools/search/test", headers=headers(client), json={"arguments": {}}
        ).status_code
        == 404
    )


def test_mcp_catalog_rejects_unsafe_urls(monkeypatch):
    from fastapi import HTTPException

    for url in (
        "http://example.com/mcp",
        "https://127.0.0.1/mcp",
        "https://localhost/mcp",
        "https://mcp.internal/mcp",
        "https://user:pass@example.com/mcp",
    ):
        try:
            catalog(
                json.dumps(
                    [{"id": "docs", "name": "Docs", "url": url, "allowed_tools": ["search"]}]
                )
            )
        except HTTPException as error:
            assert error.status_code == 503
        else:
            raise AssertionError(url)
    monkeypatch.setattr(
        "app.modules.mcp.catalog.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    try:
        require_public_dns("https://example.com/mcp")
    except HTTPException as error:
        assert error.status_code == 502
    else:
        raise AssertionError("Private DNS result must be blocked")
