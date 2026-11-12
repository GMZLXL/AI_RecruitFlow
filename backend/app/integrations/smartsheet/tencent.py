import os
from typing import Literal

from app.schemas import ApplicationProjection

from .base import SheetError, SheetHealth


def tencent_status() -> Literal["blocked_by_credentials", "blocked_by_schema"]:
    return "blocked_by_schema" if os.getenv("TENCENT_DOCS_TOKEN", "").strip() else "blocked_by_credentials"


class TencentDocsMcpAdapter:
    """Fail closed until authorized tools/list and field mappings have been verified.

    Discovery is available separately. There are intentionally no invented write parameters.
    """

    async def health_check(self) -> SheetHealth:
        return SheetHealth("tencent_docs", tencent_status())

    async def upsert_application(
        self, application: ApplicationProjection, remote_record_id: str | None
    ) -> str:
        raise SheetError(tencent_status().upper())

    async def list_remote_records(self, limit: int = 100) -> list[ApplicationProjection]:
        raise SheetError(tencent_status().upper())
