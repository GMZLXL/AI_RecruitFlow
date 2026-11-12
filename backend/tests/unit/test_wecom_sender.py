import asyncio
import json

import httpx
import pytest

from app.integrations.wecom.sender import WecomSender


def configure(monkeypatch):
    for key, value in {"APP_MODE": "hybrid", "WECOM_PROVIDER": "wecom", "WECOM_SEND_ENABLED": "true",
        "WECOM_CORP_ID": "synthetic-corp", "WECOM_SECRET": "synthetic-secret", "WECOM_AGENT_ID": "1000001"}.items():
        monkeypatch.setenv(key, value)


def test_mock_and_unconfigured_never_use_network(monkeypatch):
    def blocked(_):
        raise AssertionError("no network allowed")
    sender = WecomSender(httpx.MockTransport(blocked))
    assert asyncio.run(sender.send("mock", None, "虚构通知", "synthetic-task")).state == "mock_sent"
    assert asyncio.run(sender.send("wecom", "synthetic-hr", "虚构通知", "synthetic-task")).state == "blocked"
    configure(monkeypatch)
    assert asyncio.run(sender.send("wecom", "@all", "虚构通知", "synthetic-task")).state == "blocked"
    assert asyncio.run(sender.send("wecom", "a|b", "虚构通知", "synthetic-task")).state == "blocked"


@pytest.mark.parametrize("payload,code,expected", [
    ({"errcode": 0, "msgid": "synthetic-remote-id"}, 200, "accepted"),
    ({"errcode": 0, "msgid": "synthetic-remote-id", "invaliduser": "synthetic-hr"}, 200, "failed"),
    ({"errcode": 0, "msgid": "synthetic-remote-id", "unlicenseduser": "synthetic-hr"}, 200, "failed"),
    ({"errcode": 40014}, 200, "failed"),
    ({"errcode": 48002}, 200, "failed"),
    ({"errcode": 0}, 200, "uncertain"),
    ({"errcode": "0"}, 200, "uncertain"),
    (["invalid"], 200, "uncertain"),
    (None, 503, "uncertain"),
])
def test_sender_response_semantics_and_no_post_retries(monkeypatch, payload, code, expected):
    configure(monkeypatch)
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "qyapi.weixin.qq.com"
        if request.url.path.endswith("gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "synthetic-access-token", "expires_in": 7200})
        body = json.loads(request.content)
        assert body == {"touser": "synthetic-hr", "msgtype": "text", "agentid": 1000001, "text": {"content": "虚构通知"}}
        return httpx.Response(code, json=payload)

    sender = WecomSender(httpx.MockTransport(handle))
    result = asyncio.run(sender.send("wecom", "synthetic-hr", "虚构通知", "synthetic-task"))
    assert result.state == expected
    assert len(requests) == 2
    if expected == "accepted":
        assert result.message_id == "synthetic-remote-id"


def test_token_cache_and_timeout_uncertain(monkeypatch):
    configure(monkeypatch)
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.path.endswith("gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "synthetic-access-token", "expires_in": 7200})
        raise httpx.ReadTimeout("synthetic timeout")

    sender = WecomSender(httpx.MockTransport(handle))
    for _ in range(2):
        assert asyncio.run(sender.send("wecom", "synthetic-hr", "虚构通知", "synthetic-task")).state == "uncertain"
    assert calls.count("/cgi-bin/gettoken") == 1
    assert calls.count("/cgi-bin/message/send") == 2


@pytest.mark.parametrize("payload", [{"errcode": 40013}, {}, ["bad"], {"access_token": "test", "expires_in": "bad"}])
def test_token_failure_does_not_send(monkeypatch, payload):
    configure(monkeypatch)
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=payload)

    result = asyncio.run(WecomSender(httpx.MockTransport(handle)).send("wecom", "synthetic-hr", "虚构通知", "synthetic-task"))
    assert result.state in {"failed", "blocked"}
    assert calls == ["/cgi-bin/gettoken"]
