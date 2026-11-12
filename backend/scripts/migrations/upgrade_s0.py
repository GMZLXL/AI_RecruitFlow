"""Copy an S0 SQLite database into a new migrated S1 file. The original is never replaced."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import BACKEND_ROOT  # noqa: E402
from app.core.security import DEV_IDS, seed_dev_users  # noqa: E402
from app.db import Application, AuditLog, Candidate, Event, Outbox, Position, RemoteLink, utcnow  # noqa: E402
from app.services import snapshot  # noqa: E402


def old_time(value: str | None) -> datetime:
    parsed = datetime.fromisoformat(value) if value else utcnow()
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def upgrade_s0(source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or destination.exists() or not source.is_file():
        raise ValueError("Source must exist and destination must be a different new file")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as old:
        old.row_factory = sqlite3.Row
        columns = {row[1] for row in old.execute("PRAGMA table_info(applications)")}
        if "code" not in columns or "position_id" in columns:
            raise ValueError("Source is not an S0 Starter database")
        tables = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        data = {
            name: [dict(row) for row in old.execute(f'SELECT * FROM "{name}"')]
            for name in (
                "candidates",
                "applications",
                "recruitment_events",
                "sync_outbox",
                "remote_record_links",
                "audit_logs",
            )
            if name in tables
        }
        backup = source.with_name(source.name + ".backup-" + uuid.uuid4().hex[:8] + ".db")
        with sqlite3.connect(backup) as copy:
            old.backup(copy)
    destination.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine("sqlite:///" + destination.as_posix())
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    seed_dev_users(sessions)
    owner_id = DEV_IDS["admin"]
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, source.as_posix())

    def mapped(kind, key):
        return str(uuid.uuid5(namespace, f"{kind}:{key}"))

    try:
        with sessions.begin() as db:
            for row in data.get("candidates", []):
                db.add(
                    Candidate(
                        id=mapped("candidates", row["id"]),
                        display_name=row["name"],
                        owner_id=owner_id,
                        created_at=old_time(row["created_at"]),
                        updated_at=old_time(row["created_at"]),
                    )
                )
            positions = {}
            for row in data.get("applications", []):
                title = row["position"]
                if title not in positions:
                    positions[title] = Position(
                        id=mapped("positions", title),
                        title=title,
                        department="engineering",
                        owner_user_id=owner_id,
                    )
                    db.add(positions[title])
            db.flush()
            applications = {}
            for row in data.get("applications", []):
                obj = Application(
                    id=mapped("applications", row["id"]),
                    application_code=row["code"],
                    candidate_id=mapped("candidates", row["candidate_id"]),
                    position_id=positions[row["position"]].id,
                    owner_id=owner_id,
                    stage=row["stage"],
                    outcome=row["stage"] if row["stage"] in {"hired", "rejected", "withdrawn"} else "pending",
                    version=row["version"],
                    created_at=old_time(row["created_at"]),
                    updated_at=old_time(row["updated_at"]),
                )
                db.add(obj)
                applications[row["id"]] = obj
            db.flush()
            for row in data.get("recruitment_events", []):
                original_key = row["external_event_id"]
                normalized_key = (
                    original_key
                    if not original_key or original_key.startswith(("manual:", "wecom_mock:", "web-create:"))
                    else "manual:" + original_key
                )
                key = hashlib.sha256(normalized_key.encode()).hexdigest() if normalized_key else None
                db.add(
                    Event(
                        id=mapped("recruitment_events", row["id"]),
                        application_id=mapped("applications", row["application_id"]),
                        actor_id=owner_id,
                        source="legacy_s0",
                        event_type=row["action"],
                        external_event_key=key,
                        created_at=old_time(row["created_at"]),
                        after_json={"legacy_id": str(row["id"])},
                    )
                )
            for row in data.get("sync_outbox", []):
                obj = applications[row["application_id"]]
                status = row["status"]
                if status == "pending" and row["version"] < obj.version:
                    status = "superseded"
                db.add(
                    Outbox(
                        id=mapped("sync_outbox", row["id"]),
                        entity_type="applications",
                        entity_id=obj.id,
                        application_id=obj.id,
                        version=row["version"],
                        payload_json={
                            "schema_version": 1,
                            "entity": snapshot(obj),
                            "legacy_version": row["version"],
                        },
                        status=status,
                        remote_record_id=row["remote_record_id"],
                        attempts=row["attempts"],
                        last_error=row["last_error"],
                        created_at=old_time(row["created_at"]),
                    )
                )
            for row in data.get("remote_record_links", []):
                synced = [
                    job["version"]
                    for job in data.get("sync_outbox", [])
                    if job["application_id"] == row["application_id"] and job["status"] == "mock_synced"
                ]
                app_id = mapped("applications", row["application_id"])
                db.add(
                    RemoteLink(
                        id=mapped("remote_record_links", row["id"]),
                        entity_type="applications",
                        entity_id=app_id,
                        application_id=app_id,
                        provider="mock",
                        remote_record_id=row["remote_record_id"],
                        last_synced_version=max(synced, default=0),
                    )
                )
            for row in data.get("audit_logs", []):
                kind = row["target_type"]
                plural = "applications" if kind == "application" else kind
                db.add(
                    AuditLog(
                        id=mapped("audit_logs", row["id"]),
                        actor_id=owner_id,
                        action=row["action"],
                        target_type=plural,
                        target_id=mapped(plural, row["target_id"]),
                        metadata_json={"legacy_s0": json.loads(row["metadata_json"])},
                        created_at=old_time(row["created_at"]),
                    )
                )
            for obj in applications.values():
                db.add(
                    AuditLog(
                        actor_id=owner_id,
                        action="migrate_s0",
                        target_type="applications",
                        target_id=obj.id,
                        metadata_json={"legacy_database_preserved": True, "version": obj.version},
                    )
                )
    finally:
        engine.dispose()
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    backup = upgrade_s0(args.source, args.destination)
    print(f"S1 copy created: {args.destination.resolve()}; original retained; backup: {backup}")
