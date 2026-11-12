"""Strict envelope checks around wechatpy's enterprise AES implementation."""

import base64
import os
import re
import time
from xml.etree import ElementTree as ET

from wechatpy.enterprise.crypto import WeChatCrypto

from app.services.common import fail

from .config import status


def xml_fields(data: bytes | str) -> dict[str, str]:
    raw = data.encode() if isinstance(data, str) else data
    # UTF-8 only, before parsing: also rejects UTF-16 DTD bypasses and entity expansion.
    try:
        text = raw.decode("utf-8")
        if len(raw) > 65536 or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper() or "\x00" in text:
            raise ValueError()
        root = ET.fromstring(text)
        if root.tag != "xml" or len(root) > 30:
            raise ValueError()
        fields = {}
        for child in root:
            if child.tag in fields or len(child):
                raise ValueError()
            fields[child.tag] = child.text or ""
        return fields
    except (ValueError, ET.ParseError):
        fail(400, "INVALID_CALLBACK", "回调XML结构无效")


def decrypt(signature: str, timestamp: str, nonce: str, encrypted: str) -> bytes:
    if status().callback != "configured_not_verified":
        fail(503, "CALLBACK_NOT_CONFIGURED", "真实企微回调未启用或凭证未配置")
    if (not re.fullmatch(r"[0-9a-f]{40}", signature) or not re.fullmatch(r"\d{1,12}", timestamp)
            or not re.fullmatch(r"[A-Za-z0-9_\-]{1,128}", nonce)
            or abs(time.time() - int(timestamp)) > 300):
        fail(403, "INVALID_SIGNATURE", "签名参数或时间窗口无效")
    try:
        key = os.environ["WECOM_ENCODING_AES_KEY"]
        if len(key) != 43 or len(base64.b64decode(key + "=", validate=True)) != 32:
            fail(503, "INVALID_CALLBACK_CONFIG", "回调加密配置无效")
        cipher = base64.b64decode(encrypted, validate=True)
        if not cipher or len(cipher) % 16 or len(cipher) > 49152:
            raise ValueError()
        crypto = WeChatCrypto(os.environ["WECOM_CALLBACK_TOKEN"], key, os.environ["WECOM_CORP_ID"])
        return crypto.check_signature(signature, timestamp, nonce, encrypted).encode("utf-8")
    except Exception:
        fail(403, "INVALID_SIGNATURE", "回调签名、密文或企业标识无效")
