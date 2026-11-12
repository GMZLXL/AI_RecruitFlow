import hashlib
import io
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.db import SCHEMA_REVISION, Application, Base, Event, RemoteLink
from scripts.migrations.upgrade_s0 import upgrade_s0


def configuration():
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def test_empty_database_upgrade_check_and_downgrade(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "migration.db").as_posix())
    config = configuration()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == SCHEMA_REVISION
        )
        command.check(config)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
    engine.dispose()


def test_postgres_migration_ddl_compiles_offline():
    buffer = io.StringIO()
    config = configuration()
    config.output_buffer = buffer
    config.attributes["database_url"] = "postgresql+psycopg://unused:unused@localhost/unused"
    command.upgrade(config, "head", sql=True)
    output = buffer.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in output
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table}" in output


def create_legacy(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE candidates (id INTEGER PRIMARY KEY, name TEXT, created_at TEXT);
            CREATE TABLE applications (id INTEGER PRIMARY KEY, code TEXT, candidate_id INTEGER, position TEXT, stage TEXT, version INTEGER, created_at TEXT, updated_at TEXT);
            CREATE TABLE recruitment_events (id INTEGER PRIMARY KEY, external_event_id TEXT, application_id INTEGER, action TEXT, created_at TEXT);
            CREATE TABLE sync_outbox (id INTEGER PRIMARY KEY, application_id INTEGER, version INTEGER, status TEXT, remote_record_id TEXT, attempts INTEGER, last_error TEXT, created_at TEXT);
            CREATE TABLE remote_record_links (id INTEGER PRIMARY KEY, application_id INTEGER, remote_record_id TEXT);
            CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, actor_id TEXT, action TEXT, target_type TEXT, target_id TEXT, metadata_json TEXT, created_at TEXT);
            INSERT INTO candidates VALUES (1,'虚构旧库甲','2026-11-12 01:00:00');
            INSERT INTO applications VALUES (1,'A10001',1,'虚构测试岗','interview_2',2,'2026-11-12 01:00:00','2026-11-12 02:00:00');
            INSERT INTO recruitment_events VALUES (1,'manual:event1',1,'create_application','2026-11-12 01:00:00');
            INSERT INTO recruitment_events VALUES (2,'manual:event2',1,'update_stage:interview_2','2026-11-12 02:00:00');
            INSERT INTO sync_outbox VALUES (1,1,1,'pending',NULL,0,NULL,'2026-11-12 01:00:00');
            INSERT INTO sync_outbox VALUES (2,1,2,'mock_synced','MOCK-legacy',1,NULL,'2026-11-12 02:00:00');
            INSERT INTO remote_record_links VALUES (1,1,'MOCK-legacy');
            INSERT INTO audit_logs VALUES (1,'local-mock','create_application','application','1','{}','2026-11-12 01:00:00');
        """)


def test_s0_copy_keeps_original_backup_uuid_history_and_links(tmp_path):
    source, destination = tmp_path / "old.db", tmp_path / "new.db"
    create_legacy(source)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    backup = upgrade_s0(source, destination)
    assert backup.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    with sqlite3.connect(backup) as old:
        assert old.execute("SELECT code FROM applications").fetchone()[0] == "A10001"
    engine = create_engine("sqlite:///" + destination.as_posix())
    with sessionmaker(bind=engine)() as db:
        application = db.scalar(select(Application))
        assert application is not None
        assert len(application.id) == len(application.candidate_id) == len(application.position_id) == 36
        assert application.application_code == "A10001" and application.version == 2
        assert application.created_at.isoformat().endswith("+00:00")
        events = db.scalars(select(Event)).all()
        assert len(events) == 2
        assert {event.external_event_key for event in events} == {
            hashlib.sha256(f"manual:event{n}".encode()).hexdigest() for n in (1, 2)
        }
        link = db.scalar(select(RemoteLink))
        assert link is not None and link.remote_record_id == "MOCK-legacy"
        assert link.last_synced_version == 2
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT status FROM sync_outbox WHERE version=1").scalar()
            == "superseded"
        )
    engine.dispose()
    with pytest.raises(ValueError, match="different new file"):
        upgrade_s0(source, destination)
    with pytest.raises(ValueError):
        upgrade_s0(source, source)
