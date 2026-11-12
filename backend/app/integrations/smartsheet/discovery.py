"""Read-only MCP Streamable HTTP discovery. No tools/call or business parameters."""

import asyncio
import json
import os

import httpx

from .base import SheetError

MCP_URL = "https://docs.qq.com/openapi/mcp"
PROTOCOLS = {"2025-11-25", "2025-06-18", "2025-03-26"}
MAX_BYTES = 2_000_000


async def discover_tools(*, transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    token = os.getenv("TENCENT_DOCS_TOKEN", "").strip()
    if not token:
        raise SheetError("BLOCKED_BY_CREDENTIALS")
    if os.getenv("TENCENT_DOCS_MCP_URL", MCP_URL) != MCP_URL:
        raise SheetError("MCP_URL_NOT_ALLOWED")
    async with httpx.AsyncClient(
        transport=transport,
        timeout=15,
        follow_redirects=False,
        trust_env=False,
        headers={"Authorization": token, "Accept": "application/json, text/event-stream"},
    ) as client:

        async def send(method, params=None, request_id=None):
            message = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                message["params"] = params
            if request_id is not None:
                message["id"] = request_id
            try:
                async with asyncio.timeout(20):
                    async with client.stream("POST", MCP_URL, json=message) as response:
                        if response.status_code in {401, 403}:
                            raise SheetError("MCP_AUTH_FAILED")
                        if response.status_code >= 300:
                            raise SheetError("MCP_HTTP_ERROR")
                        session = response.headers.get("mcp-session-id")
                        if session:
                            if len(session) > 500 or not session.isascii():
                                raise SheetError("MCP_INVALID_RESPONSE")
                            client.headers["Mcp-Session-Id"] = session
                        if request_id is None:
                            return {}
                        size = 0
                        if response.headers.get("content-type", "").startswith("text/event-stream"):
                            lines = []
                            async for line in response.aiter_lines():
                                size += len(line.encode())
                                if size > MAX_BYTES:
                                    raise SheetError("MCP_RESPONSE_TOO_LARGE")
                                if line.startswith("data:"):
                                    lines.append(line[5:].lstrip())
                                elif line == "" and lines:
                                    data = "\n".join(lines)
                                    lines = []
                                    if not data.strip():
                                        continue
                                    item = json.loads(data)
                                    if item.get("id") == request_id:
                                        return checked(item)
                            raise SheetError("MCP_INVALID_RESPONSE")
                        chunks = []
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise SheetError("MCP_RESPONSE_TOO_LARGE")
                            chunks.append(chunk)
                        item = json.loads(b"".join(chunks))
                        if item.get("id") != request_id:
                            raise SheetError("MCP_INVALID_RESPONSE")
                        return checked(item)
            except (httpx.HTTPError, TimeoutError):
                raise SheetError("MCP_UNAVAILABLE") from None
            except (ValueError, AttributeError, TypeError):
                raise SheetError("MCP_INVALID_RESPONSE") from None

        initialized = await send(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "recruitflow-readonly-discovery", "version": "0.4.0"},
            },
            1,
        )
        version = initialized.get("protocolVersion")
        if (
            version not in PROTOCOLS
            or not isinstance(initialized.get("capabilities"), dict)
            or "tools" not in initialized["capabilities"]
        ):
            raise SheetError("MCP_UNSUPPORTED_PROTOCOL")
        client.headers["MCP-Protocol-Version"] = version
        await send("notifications/initialized")
        tools, cursor, seen = [], None, set()
        for index in range(20):
            result = await send("tools/list", {"cursor": cursor} if cursor else {}, index + 2)
            page = result.get("tools")
            if not isinstance(page, list):
                raise SheetError("MCP_INVALID_RESPONSE")
            for tool in page:
                if (
                    not isinstance(tool, dict)
                    or not isinstance(tool.get("name"), str)
                    or not isinstance(tool.get("inputSchema"), dict)
                ):
                    raise SheetError("MCP_INVALID_RESPONSE")
                # Only schema metadata; no tokens, server instructions or arbitrary response bodies.
                tools.append(
                    {
                        "name": tool["name"],
                        "inputSchema": tool["inputSchema"],
                        **({"outputSchema": tool["outputSchema"]} if "outputSchema" in tool else {}),
                    }
                )
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
            if not isinstance(cursor, str) or cursor in seen:
                raise SheetError("MCP_INVALID_CURSOR")
            seen.add(cursor)
        raise SheetError("MCP_PAGINATION_LIMIT")


def checked(item: dict) -> dict:
    if "error" in item:
        # Known Tencent error codes are never accompanied by raw provider messages.
        code = item["error"].get("code") if isinstance(item["error"], dict) else None
        raise SheetError(
            "MCP_AUTH_FAILED"
            if code == 400006
            else "MCP_MEMBERSHIP_REQUIRED"
            if code == 400007
            else "MCP_RPC_ERROR"
        )
    result = item.get("result")
    if not isinstance(result, dict):
        raise SheetError("MCP_INVALID_RESPONSE")
    return result
