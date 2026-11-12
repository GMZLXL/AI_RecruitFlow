from __future__ import annotations

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import BACKEND_ROOT, DATABASE_URL

SCHEMA_REVISION = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_current_head()


@event.listens_for(Engine, "connect")
def sqlite_foreign_keys(connection, _record):
    if connection.__class__.__module__ == "sqlite3":
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    with engine.connect() as connection:
        if MigrationContext.configure(connection).get_current_revision() != SCHEMA_REVISION:
            raise RuntimeError(
                "Database migration required: run alembic upgrade head; S0 databases require scripts/upgrade_s0.py"
            )


def get_db():
    with SessionLocal() as db:
        yield db
