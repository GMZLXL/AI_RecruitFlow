"""Online SQLite backup, integrity manifest and restore to a NEW, inactive path."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

TABLES = ("users", "positions", "applications", "candidates", "interviews", "offers", "confirmations",
          "recruitment_events", "audit_logs", "sync_outbox", "ingestion_jobs", "notifications", "reminders",
          "reminder_policy", "auth_identities", "ai_settings", "remote_record_links", "mock_sheet_records", "idempotency_records")


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_db(db):
    if db.execute("PRAGMA quick_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("DATABASE_INTEGRITY_FAILED")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    revision = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    counts = {table: db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in TABLES if table in tables}
    return {"schema_revision": revision, "counts": counts}


def copy_sqlite(source, destination):
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError("DESTINATION_MUST_BE_NEW")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve exclusively, never overwrite a file created concurrently by another operator.
    with destination.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            origin.execute("BEGIN")  # pin one consistent snapshot through verification and backup
            expected = inspect_db(origin)
            with closing(sqlite3.connect(destination)) as target:
                origin.backup(target)
                if inspect_db(target) != expected:
                    raise ValueError("BACKUP_VERIFICATION_FAILED")
        return expected
    except Exception:
        destination.unlink(missing_ok=True)  # only the exclusively reserved new target
        raise


def backup(source, destination):
    destination = Path(destination).resolve()
    manifest = Path(str(destination) + ".manifest.json")
    if manifest.exists():
        raise ValueError("MANIFEST_MUST_BE_NEW")
    details = copy_sqlite(source, destination)
    payload = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": checksum(destination), **details}
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return payload


def restore(source, destination):
    source = Path(source).resolve(strict=True)
    manifest = json.loads(Path(str(source) + ".manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or manifest.get("sha256") != checksum(source):
        raise ValueError("BACKUP_CHECKSUM_FAILED")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        details = inspect_db(db)
    if details != {key: manifest[key] for key in ("schema_revision", "counts")}:
        raise ValueError("BACKUP_MANIFEST_MISMATCH")
    details = copy_sqlite(source, destination)
    # Clear only coordination metadata. Durable business/notification states keep normal recovery rules.
    with closing(sqlite3.connect(Path(destination).resolve())) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "worker_states" in tables:
            db.execute("UPDATE worker_states SET owner_token=NULL,expires_at=NULL")
        if "sync_worker_leases" in tables:
            db.execute("UPDATE sync_worker_leases SET token=NULL,expires_at=NULL")
        db.commit()
        assert inspect_db(db) == details
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (backup if args.operation == "backup" else restore)(args.source, args.destination)
    except (OSError, ValueError, sqlite3.DatabaseError, KeyError):
        print("BACKUP_OR_RESTORE_FAILED: check input, manifest, integrity and NEW destination")
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
