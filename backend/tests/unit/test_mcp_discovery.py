import asyncio
import json

import httpx
import pytest

from app.integrations.smartsheet.base import SheetError
from app.integrations.smartsheet.discovery import MCP_URL, discover_tools


def test_credentials_and_url_fail_before_network(monkeypatch):
    with pytest.raises(SheetError, match="BLOCKED_BY_CREDENTIALS"):
        asyncio.run(discover_tools())
    monkeypatch.setenv("TENCENT_DOCS_TOKEN", "synthetic-not-a-token")
    monkeypatch.setenv("TENCENT_DOCS_MCP_URL", "http://127.0.0.1/private")
    with pytest.raises(SheetError, match="MCP_URL_NOT_ALLOWED"):
        asyncio.run(discover_tools())


@pytest.mark.parametrize("sse", [False, True])
def test_initialize_then_paginated_tools_list_only(monkeypatch, sse):
    monkeypatch.setenv("TENCENT_DOCS_TOKEN", "synthetic-not-a-token")
    calls = []

    def handler(request):
        assert str(request.url) == MCP_URL
        assert request.headers["Authorization"] == "synthetic-not-a-token"
        body = json.loads(request.content)
        calls.append(body)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}
        elif body["method"] == "notifications/initialized":
            assert request.headers["Mcp-Session-Id"] == "synthetic-session"
            return httpx.Response(202)
        else:
            assert body["method"] == "tools/list"
            assert request.headers["MCP-Protocol-Version"] == "2025-11-25"
            result: dict = {"tools": [{"name": "synthetic.example", "inputSchema": {"type": "object"}}]}
            if not body["params"].get("cursor"):
                result["nextCursor"] = "second"
        payload = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if sse:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream", "Mcp-Session-Id": "synthetic-session"},
                text="id: prime\ndata:\n\nevent: message\ndata: " + json.dumps(payload) + "\n\n",
            )
        return httpx.Response(200, json=payload, headers={"Mcp-Session-Id": "synthetic-session"})

    tools = asyncio.run(discover_tools(transport=httpx.MockTransport(handler)))
    assert len(tools) == 2
    assert [call["method"] for call in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/list",
    ]
    assert calls[-1]["params"] == {"cursor": "second"}


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (401, None, "MCP_AUTH_FAILED"),
        (403, None, "MCP_AUTH_FAILED"),
        (500, None, "MCP_HTTP_ERROR"),
        (200, 400006, "MCP_AUTH_FAILED"),
        (200, 400007, "MCP_MEMBERSHIP_REQUIRED"),
        (200, -1, "MCP_RPC_ERROR"),
    ],
)
def test_safe_errors_never_echo_upstream(monkeypatch, status, code, expected):
    monkeypatch.setenv("TENCENT_DOCS_TOKEN", "synthetic-not-a-token")

    def handler(request):
        return httpx.Response(
            status,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": code, "message": "synthetic-private-provider-message"},
            },
        )

    with pytest.raises(SheetError, match=expected) as error:
        asyncio.run(discover_tools(transport=httpx.MockTransport(handler)))
    assert "private-provider" not in str(error.value)


def test_discovery_rejects_redirect_without_leaking_authorization(monkeypatch):
    monkeypatch.setenv("TENCENT_DOCS_TOKEN", "synthetic-not-a-token")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.com/unsafe"})

    with pytest.raises(SheetError, match="MCP_HTTP_ERROR"):
        asyncio.run(discover_tools(transport=httpx.MockTransport(handler)))
    assert calls == [MCP_URL]
