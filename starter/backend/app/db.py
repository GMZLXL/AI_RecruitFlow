from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./recruitflow.db")
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applications: Mapped[list[Application]] = relationship(back_populates="candidate")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    position: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), default="applied", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    candidate: Mapped[Candidate] = relationship(back_populates="applications")


class Event(Base):
    __tablename__ = "recruitment_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_event_id: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    action: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "sync_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    remote_record_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RemoteLink(Base):
    __tablename__ = "remote_record_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    remote_record_id: Mapped[str] = mapped_column(String(60), unique=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(60), default="local-mock")
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str] = mapped_column(String(40), default="application")
    target_id: Mapped[str] = mapped_column(String(60))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def init_db() -> None:
    # Starter shortcut only; replace with Alembic migrations during Codex S1.
    Base.metadata.create_all(bind=engine)


def get_db():
    with SessionLocal() as db:
        yield db
