from dataclasses import dataclass
from typing import Protocol

from app.schemas import ApplicationProjection


class SheetError(Exception):
    """Only allowlisted error codes are persisted; never store upstream messages."""

    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class SheetHealth:
    provider: str
    status: str


class SmartSheetAdapter(Protocol):
    async def health_check(self) -> SheetHealth: ...
    async def upsert_application(
        self, application: ApplicationProjection, remote_record_id: str | None
    ) -> str: ...
    async def list_remote_records(self, limit: int = 100) -> list[ApplicationProjection]: ...
