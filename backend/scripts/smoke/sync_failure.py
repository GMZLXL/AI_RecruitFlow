"""With API stopped, leave one synthetic dead Mock task for Web retry demonstration."""

import asyncio
import os
import uuid

from sqlalchemy import select

from app.core.security import DEV_IDS, seed_dev_users
from app.db import Outbox, SessionLocal, User, init_db
from app.schemas import ApplicationCreate
from app.services.common import application_read, mutate
from app.services.recruitment import create_application
from app.services.sync import process_batch


def main():
    if os.getenv("APP_MODE", "mock") != "mock" or os.getenv("SMARTSHEET_PROVIDER", "mock") != "mock":
        raise RuntimeError("Failure demonstration requires explicit local Mock mode")
    init_db()
    seed_dev_users()
    with SessionLocal() as db:
        actor = db.get(User, DEV_IDS["admin"])
        assert actor is not None
        data = ApplicationCreate(
            candidate_name="虚构同步重试" + uuid.uuid4().hex[:6], position_title="虚构同步验收岗"
        )
        created = mutate(
            db,
            actor,
            "smoke_sync_failure",
            uuid.uuid4().hex,
            data.model_dump(mode="json"),
            lambda: application_read(create_application(db, actor, data)),
        )
    previous = os.environ.get("MOCK_SHEET_FAILURE")
    os.environ["MOCK_SHEET_FAILURE"] = "permission"
    try:
        asyncio.run(process_batch())
    finally:
        if previous is None:
            os.environ.pop("MOCK_SHEET_FAILURE", None)
        else:
            os.environ["MOCK_SHEET_FAILURE"] = previous
    with SessionLocal() as db:
        job = db.scalar(
            select(Outbox).where(Outbox.entity_type == "applications", Outbox.entity_id == created["id"])
        )
        assert job is not None and job.status == "dead", (
            "Stop the API worker before running this demonstration"
        )
        print(
            f"Synthetic application {created['application_code']} saved locally; Mock job {job.id} is dead."
        )
        print(
            "Start API with MOCK_SHEET_FAILURE=none, filter dead tasks in Sync Center and retry with a reason."
        )


if __name__ == "__main__":
    main()
