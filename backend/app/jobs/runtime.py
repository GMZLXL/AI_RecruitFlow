"""One renewable task leader per database; metadata contains no credentials."""

import asyncio
from datetime import timedelta

from sqlalchemy import or_, update

from app.db import SessionLocal, WorkerState, new_id, utcnow

NAME = "background-runtime"
LEASE_SECONDS = 45


def upsert(db, name, **values):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return db.execute(insert(WorkerState).values(name=name, **values).on_conflict_do_nothing())


def acquire(token):
    now = utcnow()
    with SessionLocal() as db:
        upsert(db, NAME)
        result = db.execute(update(WorkerState).where(WorkerState.name == NAME,
            or_(WorkerState.owner_token.is_(None), WorkerState.expires_at <= now))
            .values(owner_token=token, heartbeat_at=now, expires_at=now + timedelta(seconds=LEASE_SECONDS))
            .returning(WorkerState.name)).scalar_one_or_none()
        db.commit()
        return result is not None


def renew(token):
    now = utcnow()
    with SessionLocal() as db:
        result = db.execute(update(WorkerState).where(WorkerState.name == NAME,
            WorkerState.owner_token == token, WorkerState.expires_at > now)
            .values(heartbeat_at=now, expires_at=now + timedelta(seconds=LEASE_SECONDS))
            .returning(WorkerState.name)).scalar_one_or_none()
        db.commit()
        return result is not None


def release(token):
    with SessionLocal() as db:
        db.execute(update(WorkerState).where(WorkerState.name == NAME, WorkerState.owner_token == token)
            .values(owner_token=None, expires_at=utcnow()))
        db.commit()


def record_cycle(name, success):
    with SessionLocal() as db:
        upsert(db, name)
        values = {"last_cycle_at": utcnow(), "last_error": None if success else "WORKER_CYCLE_FAILED"}
        if success:
            values["last_success_at"] = utcnow()
        db.execute(update(WorkerState).where(WorkerState.name == name).values(**values))
        db.commit()


async def supervise(app, runners, interval: float = 5):
    token, tasks = new_id(), []
    app.state.worker_role = "standby"
    try:
        while True:
            owned = renew(token) if tasks else acquire(token)
            if owned:
                app.state.worker_role = "leader"
                if not tasks:
                    tasks = [asyncio.create_task(run()) for run in runners]
            else:
                app.state.worker_role = "standby"
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
            if any(task.done() for task in tasks):
                raise RuntimeError("Background worker stopped unexpectedly")
            await asyncio.sleep(interval)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        release(token)
        app.state.worker_role = "disabled"
