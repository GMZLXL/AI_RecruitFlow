"""Fixed official endpoint; one recipient, minimal text, no blind POST retries."""

import os
import re
import time
from dataclasses import dataclass

import httpx

from .config import status


@dataclass(frozen=True)
class SendResult:
    state: str
    error: str | None = None
    message_id: str | None = None


class WecomSender:
    def __init__(self, transport=None):
        self.transport = transport
        self._token = None
        self._expires = 0
        self._identity = None

    async def send(self, provider: str, recipient: str | None, text: str, task_id: str) -> SendResult:
        if provider == "mock":
            return SendResult("mock_sent", message_id="MOCK-NOTICE-" + task_id)
        if status().provider != "wecom" or status().sending != "configured_not_verified":
            return SendResult("blocked", "BLOCKED_BY_CREDENTIALS_OR_DISABLED")
        if not recipient or recipient == "@all" or not re.fullmatch(r"[A-Za-z0-9_@.\-]{1,150}", recipient):
            return SendResult("blocked", "RECIPIENT_NOT_BOUND")
        try:
            agent = int(os.environ["WECOM_AGENT_ID"])
            if agent <= 0:
                raise ValueError()
        except ValueError:
            return SendResult("blocked", "INVALID_AGENT_CONFIG")
        async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False, transport=self.transport) as client:
            identity = (os.environ["WECOM_CORP_ID"], os.environ["WECOM_SECRET"])
            if not self._token or self._expires <= time.monotonic() or self._identity != identity:
                try:
                    response = await client.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                        params={"corpid": identity[0], "corpsecret": identity[1]})
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or data.get("errcode", 0) != 0 or not isinstance(data.get("access_token"), str) or not data["access_token"]:
                        return SendResult("blocked", "TOKEN_REJECTED")
                    expires = int(data["expires_in"])
                    if expires <= 60:
                        return SendResult("blocked", "TOKEN_RESPONSE_INVALID")
                    self._token, self._expires, self._identity = data["access_token"], time.monotonic() + expires - 60, identity
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    return SendResult("failed", "TOKEN_UNAVAILABLE")
            try:
                response = await client.post("https://qyapi.weixin.qq.com/cgi-bin/message/send",
                    params={"access_token": self._token},
                    json={"touser": recipient, "msgtype": "text", "agentid": agent, "text": {"content": text}})
                # HTTP 5xx/malformed responses may follow a successful send. Do not retry automatically.
                if response.status_code != 200:
                    return SendResult("uncertain", "SEND_HTTP_UNCERTAIN")
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("errcode"), int):
                    return SendResult("uncertain", "SEND_RESPONSE_INVALID")
                if data["errcode"] != 0:
                    if data["errcode"] in {40014, 42001}:
                        self._token = None
                    return SendResult("failed", "SEND_REJECTED")
                if any(data.get(field) for field in ("invaliduser", "invalidparty", "invalidtag", "unlicenseduser")):
                    return SendResult("failed", "RECIPIENT_REJECTED")
                message_id = data.get("msgid")
                if not isinstance(message_id, str) or not 1 <= len(message_id) <= 150:
                    return SendResult("uncertain", "SEND_RESPONSE_INVALID")
                return SendResult("accepted", message_id=message_id)
            except (httpx.HTTPError, ValueError, TypeError):
                return SendResult("uncertain", "SEND_RESULT_UNKNOWN")


sender = WecomSender()
