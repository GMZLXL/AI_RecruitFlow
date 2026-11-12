from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Entity, UTCDateTime, new_id, utcnow


class User(Entity, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('HR','MANAGER','ADMIN')", name="ck_user_role"),)
    external_wecom_userid: Mapped[str | None] = mapped_column(String(150), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Position(Entity, Base):
    __tablename__ = "positions"
    __table_args__ = (CheckConstraint("target_headcount >= 0", name="ck_position_headcount"),)
    title: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(100), index=True)
    target_headcount: Mapped[int] = mapped_column(Integer, default=0)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Candidate(Entity, Base):
    __tablename__ = "candidates"
    display_name: Mapped[str] = mapped_column(String(100), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    contact_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    applications: Mapped[list[Application]] = relationship(back_populates="candidate")


class Application(Entity, Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('applied','screening','interview_1','interview_2','offer','hired','rejected','withdrawn')",
            name="ck_application_stage",
        ),
        CheckConstraint("version >= 1", name="ck_application_version"),
        Index("ix_application_owner_stage", "owner_id", "stage"),
    )
    application_code: Mapped[str] = mapped_column(String(40), unique=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_channel: Mapped[str | None] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(30), default="applied")
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    position: Mapped[Position] = relationship()


class Interview(Entity, Base):
    __tablename__ = "interviews"
    __table_args__ = (
        CheckConstraint("round >= 1", name="ck_interview_round"),
        CheckConstraint("status IN ('scheduled','completed','cancelled')", name="ck_interview_status"),
        CheckConstraint("result IN ('pending','passed','failed','cancelled')", name="ck_interview_result"),
    )
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    interviewer: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    result: Mapped[str] = mapped_column(String(30), default="pending")
    feedback_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class IngestionJob(Entity, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (UniqueConstraint("source", "external_event_id", name="uq_ingestion_source_event"),)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    message_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30))
    external_event_id: Mapped[str | None] = mapped_column(String(150))
    state: Mapped[str] = mapped_column(String(30), default="received")
    extracted_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Confirmation(Entity, Base):
    __tablename__ = "confirmations"
    ingestion_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_jobs.id"))
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(100))
    candidates_json: Mapped[list] = mapped_column(JSON, default=list)
    proposed_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Event(Base):
    __tablename__ = "recruitment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_event_key: Mapped[str | None] = mapped_column(String(150), unique=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(30), default="manual")
    event_type: Mapped[str] = mapped_column(String(60))
    before_json: Mapped[dict] = mapped_column(JSON, default=dict)
    after_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_text_redacted: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Outbox(Base):
    __tablename__ = "sync_outbox"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version", name="uq_outbox_entity_version"),
        Index("ix_outbox_status_retry", "status", "next_retry_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id"))
    op: Mapped[str] = mapped_column(String(20), default="upsert")
    version: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    remote_record_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class RemoteLink(Base):
    __tablename__ = "remote_record_links"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "provider", name="uq_remote_entity_provider"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id"))
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    remote_table_id: Mapped[str | None] = mapped_column(String(150))
    remote_record_id: Mapped[str] = mapped_column(String(100))
    last_synced_version: Mapped[int] = mapped_column(Integer, default=0)


class Reminder(Entity, Base):
    __tablename__ = "reminders"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"))
    reminder_type: Mapped[str] = mapped_column(String(40))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(30), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    dedupe_key: Mapped[str] = mapped_column(String(150), unique=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("actor_id", "operation", "key", name="uq_idempotency_actor_operation_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(150))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
