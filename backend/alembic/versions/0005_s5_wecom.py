"""Durable WeCom inbox, notifications, replay protection and reminder policy."""

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "0005_s5"
down_revision = "0004_s4"
branch_labels = None
depends_on = None


def entity():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True))]


def upgrade():
    op.add_column("reminders", sa.Column("source_id", sa.String(36)))
    with op.batch_alter_table("reminders") as batch:
        batch.add_column(sa.Column("recipient_id", sa.String(36)))
        batch.create_foreign_key("fk_reminder_recipient", "users", ["recipient_id"], ["id"])
    policy = op.create_table("reminder_policy", *entity(),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interview_hours", sa.Integer(), nullable=False),
        sa.Column("feedback_hours", sa.Integer(), nullable=False),
        sa.Column("stalled_days", sa.Integer(), nullable=False))
    now = datetime.now(timezone.utc)
    op.bulk_insert(policy, [{"id": "a3958afe-1892-4ef2-b415-435c3fe2ca85", "version": 1,
        "created_at": now, "updated_at": now, "enabled": False,
        "interview_hours": 24, "feedback_hours": 24, "stalled_days": 7}])
    op.create_table("wecom_inbox", *entity(),
        sa.Column("event_key", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_hash", sa.String(64), nullable=False), sa.Column("safe_text", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("ingestion_id", sa.String(36), sa.ForeignKey("ingestion_jobs.id")),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("last_error", sa.String(80)),
        sa.Column("processing_token", sa.String(36)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.create_index("ix_wecom_inbox_status_retry", "wecom_inbox", ["status", "next_retry_at"])
    op.create_table("wecom_replays", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_wecom_replays_expires_at", "wecom_replays", ["expires_at"])
    op.create_table("notifications", *entity(),
        sa.Column("dedupe_key", sa.String(150), nullable=False, unique=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id")),
        sa.Column("reminder_id", sa.String(36), sa.ForeignKey("reminders.id"), unique=True),
        sa.Column("text", sa.String(1000), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("last_error", sa.String(80)),
        sa.Column("platform_message_id", sa.String(150)), sa.Column("processing_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_notification_status_retry", "notifications", ["status", "next_retry_at"])


def downgrade():
    op.drop_table("notifications")
    op.drop_table("wecom_replays")
    op.drop_table("wecom_inbox")
    op.drop_table("reminder_policy")
    with op.batch_alter_table("reminders") as batch:
        batch.drop_constraint("fk_reminder_recipient", type_="foreignkey")
        batch.drop_column("recipient_id")
        batch.drop_column("source_id")
