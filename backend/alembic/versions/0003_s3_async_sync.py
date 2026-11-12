"""Durable outbox claims, single-instance lease and persistent Mock projection."""

import json
from datetime import datetime

import sqlalchemy as sa

from alembic import context, op

revision = "0003_s3"
down_revision = "0002_s2"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("provider", sa.String(40), nullable=False, server_default="mock"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cycle_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_token", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("sync_outbox", column)
    op.execute("UPDATE sync_outbox SET cycle_attempts = attempts")
    op.create_table(
        "sync_worker_leases",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("token", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.execute("INSERT INTO sync_worker_leases (name) VALUES ('smartsheet')")
    op.create_table(
        "mock_sheet_records",
        sa.Column("application_id", sa.String(36), primary_key=True),
        sa.Column("remote_record_id", sa.String(100), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    if not context.is_offline_mode():
        # Prior Mock sync had mappings but no separate remote store. Preserve those IDs.
        connection = op.get_bind()
        rows = (
            connection.execute(
                sa.text("""
            SELECT l.entity_id, l.remote_record_id, l.last_synced_version, a.application_code,
                   a.stage, a.outcome, a.deleted_at, a.updated_at, c.display_name, p.title
            FROM remote_record_links l JOIN applications a ON a.id=l.entity_id
            JOIN candidates c ON c.id=a.candidate_id JOIN positions p ON p.id=a.position_id
            WHERE l.provider='mock' AND l.entity_type='applications'
        """)
            )
            .mappings()
            .all()
        )
        table = sa.table(
            "mock_sheet_records",
            sa.column("application_id"),
            sa.column("remote_record_id"),
            sa.column("version"),
            sa.column("payload_json", sa.JSON()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        for row in rows:
            raw = connection.execute(
                sa.text("""SELECT payload_json FROM sync_outbox
                WHERE entity_type='applications' AND entity_id=:id AND version=:version"""),
                {"id": row["entity_id"], "version": row["last_synced_version"]},
            ).scalar()
            payload = json.loads(raw) if isinstance(raw, str) else raw or {}
            entity = payload.get("entity", {})
            timestamp = str(entity.get("updated_at", row["updated_at"])).replace(" ", "T")
            if not timestamp.endswith("Z") and "+" not in timestamp[10:]:
                timestamp += "+00:00"
            version = max(1, row["last_synced_version"])
            data = {
                "schema_version": 1,
                "application_id": row["entity_id"],
                "application_code": row["application_code"],
                "candidate_name": row["display_name"],
                "position_title": row["title"],
                "stage": entity.get("stage", row["stage"]),
                "outcome": entity.get("outcome", row["outcome"]),
                "version": version,
                "deleted": bool(entity.get("deleted_at", row["deleted_at"])),
                "updated_at": timestamp,
            }
            connection.execute(
                table.insert().values(
                    application_id=row["entity_id"],
                    remote_record_id=row["remote_record_id"],
                    version=version,
                    payload_json=data,
                    updated_at=datetime.fromisoformat(str(row["updated_at"])),
                )
            )


def downgrade():
    op.drop_table("mock_sheet_records")
    op.drop_table("sync_worker_leases")
    for name in (
        "completed_at",
        "lease_expires_at",
        "processing_token",
        "cycle_attempts",
        "revision",
        "provider",
    ):
        op.drop_column("sync_outbox", name)
