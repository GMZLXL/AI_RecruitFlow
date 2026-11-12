import os
from typing import Literal, cast

from .base import SmartSheetAdapter
from .mock import MockSmartSheetAdapter
from .tencent import TencentDocsMcpAdapter


def sync_provider() -> Literal["mock", "tencent_docs"]:
    provider = os.getenv("SMARTSHEET_PROVIDER", "mock")
    if provider not in {"mock", "tencent_docs"}:
        raise ValueError("SMARTSHEET_PROVIDER must be mock or tencent_docs")
    return cast(Literal["mock", "tencent_docs"], provider)


def sheet_adapter(provider: str) -> SmartSheetAdapter:
    if provider == "mock":
        return MockSmartSheetAdapter()
    if provider == "tencent_docs":
        return TencentDocsMcpAdapter()
    raise ValueError("Unknown SmartSheet provider")
