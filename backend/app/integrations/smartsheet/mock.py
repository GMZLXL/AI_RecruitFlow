import os
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import MockSheetRecord, SessionLocal, utcnow
from app.schemas import ApplicationProjection

from .base import SheetError, SheetHealth


class MockSmartSheetAdapter:
    """Independent durable store, including stable create keys and version fencing."""

    async def health_check(self) -> SheetHealth:
        return SheetHealth("mock", "mock_only")

    async def upsert_application(
        self, application: ApplicationProjection, remote_record_id: str | None
    ) -> str:
        fault = os.getenv("MOCK_SHEET_FAILURE", "none")
        if fault == "timeout":
            raise SheetError("REMOTE_TIMEOUT", retryable=True)
        if fault == "permission":
            raise SheetError("REMOTE_PERMISSION_DENIED")
        # This transaction is the simulated REMOTE system, never the business transaction.
        with SessionLocal() as remote:
            existing = remote.get(MockSheetRecord, application.application_id)
            if remote_record_id and (not existing or existing.remote_record_id != remote_record_id):
                raise SheetError("REMOTE_RECORD_MISSING")
            record_id = (
                existing.remote_record_id
                if existing
                else "MOCK-" + str(uuid5(NAMESPACE_URL, "recruitflow/" + application.application_id))
            )
            insert = (
                sqlite_insert
                if remote.bind is not None and remote.bind.dialect.name == "sqlite"
                else postgres_insert
            )
            stmt = insert(MockSheetRecord).values(
                application_id=application.application_id,
                remote_record_id=record_id,
                version=application.version,
                payload_json=application.model_dump(mode="json"),
                updated_at=utcnow(),
            )
            remote.execute(
                stmt.on_conflict_do_update(
                    index_elements=[MockSheetRecord.application_id],
                    set_={
                        "version": stmt.excluded.version,
                        "payload_json": stmt.excluded.payload_json,
                        "updated_at": stmt.excluded.updated_at,
                    },
                    where=MockSheetRecord.version < application.version,
                )
            )
            remote.commit()
        if fault == "after_write_timeout":
            raise SheetError("REMOTE_TIMEOUT", retryable=True)
        return record_id

    async def list_remote_records(self, limit: int = 100) -> list[ApplicationProjection]:
        with SessionLocal() as remote:
            records = remote.scalars(
                select(MockSheetRecord)
                .order_by(MockSheetRecord.application_id)
                .limit(min(max(limit, 1), 100))
            )
            return [ApplicationProjection.model_validate(row.payload_json) for row in records]
