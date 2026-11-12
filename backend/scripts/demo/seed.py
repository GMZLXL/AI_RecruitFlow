"""Add repeatable fictional records without overwriting existing business data."""

import asyncio
import os
from datetime import timedelta

from sqlalchemy import select, update

from app import schemas as s
from app import services as svc
from app.core.security import DEV_IDS, seed_dev_users
from app.db import Application, Candidate, Interview, SessionLocal, User, init_db, utcnow
from app.domain import Stage
from app.integrations.parsers.mock import MockParser
from app.services.ingestion import ingest
from app.services.offers import create_offer, respond_offer

NAMES = [
    "林沐",
    "陈禾",
    "周宁",
    "许清",
    "宋言",
    "顾川",
    "叶知",
    "苏晓",
    "林沐",
    "程悦",
    "唐栩",
    "沈夏",
    "何舟",
    "陆遥",
    "秦安",
    "温晴",
    "林沐",
    "江澄",
    "夏予",
    "方铭",
    "孟初",
    "白榆",
    "余乐",
    "梁溪",
]
POSITIONS = [
    ("前端工程师（演示）", "hr-a", 3),
    ("数据分析师（演示）", "hr-a", 2),
    ("Python工程师（演示）", "hr-a", 2),
    ("客户成功经理（演示）", "hr-b", 3),
]
STAGES = ["applied", "screening", "interview_1", "interview_2", "offer", "hired", "rejected", "withdrawn"]
MARKER: s.CustomFields = {"organization.referral_tag": "S4虚构演示"}


def seed_demo() -> tuple[int, int]:
    if (
        os.getenv("APP_ENV", "development") != "development"
        or os.getenv("APP_MODE", "mock") != "mock"
        or os.getenv("SMARTSHEET_PROVIDER", "mock") != "mock"
    ):
        raise RuntimeError("Synthetic fixtures only support development Mock; no real projection is allowed")
    seed_dev_users()
    position_ids = []
    for title, owner_alias, target in POSITIONS:
        with SessionLocal() as db:
            actor, owner = db.get(User, DEV_IDS["admin"]), db.get(User, DEV_IDS[owner_alias])
            assert actor is not None and owner is not None
            data = s.PositionCreate(
                title=title, department=owner.department, target_headcount=target, owner_user_id=owner.id
            )
            result = svc.mutate(
                db,
                actor,
                "seed_s4_position",
                title,
                data.model_dump(),
                lambda actor=actor: s.PositionRead.model_validate(svc.create_position(db, actor, data)),
            )
            position_ids.append(result["id"])
    added, skipped = 0, 0
    now = utcnow()
    for index, name in enumerate(NAMES):
        code = f"DEMO_S4_{index + 1:02}"
        position_index = (index + index // 8) % len(POSITIONS)
        owner_alias = POSITIONS[position_index][1]
        with SessionLocal() as db:
            existing = db.scalar(select(Application).where(Application.application_code == code))
            if existing:
                if existing.source_channel != "演示样本" or existing.custom_fields != MARKER:
                    raise RuntimeError(
                        "A non-demo record uses a reserved sample code; no record was overwritten"
                    )
                skipped += 1
                continue
            actor = db.get(User, DEV_IDS[owner_alias])
            assert actor is not None

            def build(actor: User = actor):
                if index == 8:
                    first = db.scalar(select(Application).where(Application.application_code == "DEMO_S4_01"))
                    assert first is not None and first.owner_id == actor.id
                    candidate = db.get(Candidate, first.candidate_id)
                    assert candidate is not None
                else:
                    candidate = svc.create_candidate(
                        db, actor, s.CandidateCreate(display_name=name, custom_fields=MARKER)
                    )
                application = svc.create_application(
                    db,
                    actor,
                    s.ApplicationCreate(
                        candidate_id=candidate.id,
                        position_id=position_ids[position_index],
                        application_code=code,
                        source_channel="演示样本",
                        custom_fields=MARKER,
                    ),
                )
                # Fixture-only historical dates are recorded explicitly; public APIs stay unchanged.
                before = svc.snapshot(application)
                created = now - timedelta(days=28 - index)
                previous = application.version
                changed = db.execute(
                    update(Application)
                    .where(
                        Application.id == application.id,
                        Application.version == previous,
                        Application.source_channel == "演示样本",
                    )
                    .values(created_at=created, version=previous + 1, updated_at=now)
                    .returning(Application.id)
                ).scalar_one_or_none()
                assert changed is not None
                db.refresh(application)
                svc.record_change(
                    db, application, actor, "seed_demo_history", before, "初始化明确标记的虚构历史日期"
                )
                target_stage = STAGES[index % len(STAGES)]
                path = ["screening", "interview_1", "interview_2", "offer"]
                if target_stage in {"rejected", "withdrawn"}:
                    path = [target_stage]
                elif target_stage == "applied":
                    path = []
                else:
                    path = path[: path.index(target_stage) + 1] if target_stage in path else path
                for stage in path:
                    svc.patch_application(
                        db,
                        actor,
                        application,
                        s.ApplicationPatch(stage=Stage(stage), change_reason="虚构演示阶段"),
                        application.version,
                    )
                if target_stage in {"offer", "hired"}:
                    offer = create_offer(
                        db,
                        actor,
                        application,
                        s.OfferCreate(sent_at=now - timedelta(days=2), change_reason="虚构Offer已发出事实"),
                        application.version,
                    )
                    response = (
                        "accepted"
                        if target_stage == "hired" or index == 12
                        else "declined"
                        if index == 20
                        else None
                    )
                    if response:
                        from app.db import Offer

                        stored = db.get(Offer, offer.id)
                        assert stored is not None
                        respond_offer(
                            db,
                            actor,
                            application,
                            stored,
                            s.OfferPatch(
                                status=response,
                                responded_at=now - timedelta(days=1),
                                change_reason="虚构Offer反馈",
                            ),
                            offer.version,
                        )
                if target_stage == "hired":
                    svc.patch_application(
                        db,
                        actor,
                        application,
                        s.ApplicationPatch(stage=Stage.HIRED, change_reason="人工登记虚构录用事实"),
                        application.version,
                    )
                if target_stage in {"interview_1", "interview_2"}:
                    planned = now + timedelta(days=2) if index // 8 else now - timedelta(days=1)
                    interview = Interview(
                        application_id=application.id,
                        round=1 if target_stage == "interview_1" else 2,
                        scheduled_at=planned,
                        interviewer=["虚构面试官陆宁", "虚构面试官许言"][index % 2],
                    )
                    db.add(interview)
                    svc.record_change(
                        db,
                        interview,
                        actor,
                        "create_interview",
                        reason="虚构计划样本（含过去时点用于待反馈演示）",
                    )
                    svc.touch_application(db, actor, application)
                if target_stage == "applied":
                    before = svc.snapshot(application)
                    previous = application.version
                    db.execute(
                        update(Application)
                        .where(Application.id == application.id, Application.version == previous)
                        .values(updated_at=now - timedelta(days=8), version=previous + 1)
                    )
                    db.refresh(application)
                    svc.record_change(db, application, actor, "seed_demo_history", before, "虚构停滞样本")
                return {"application_id": application.id}

            svc.mutate(db, actor, "seed_s4_application", code, {"code": code}, build)
            added += 1
    asyncio.run(
        ingest(
            DEV_IDS["hr-a"],
            s.IngestionRequest(text="林沐一面通过", external_event_id="s4-demo-review", source="manual"),
            MockParser(),
        )
    )
    return added, skipped


if __name__ == "__main__":
    init_db()
    added, skipped = seed_demo()
    print(
        f"Synthetic S4 fixtures: added={added}, kept_existing={skipped}; no records overwritten or deleted."
    )
