"""Match and apply typed proposals through deterministic domain checks."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as s
from app.core.security import require_writer
from app.db import Application, Candidate, Interview, Position, User, utcnow
from app.domain import TERMINAL_STAGES, Stage

from .common import (
    application_read,
    conditional_update,
    fail,
    get_entity,
    record_change,
    snapshot,
    visibility,
)
from .interviews import create_interview
from .recruitment import create_application, patch_application, touch_application


@dataclass
class ReviewNeeded(Exception):
    code: str
    message: str
    candidates: list[dict] = field(default_factory=list)
    candidate_ids: list[str] = field(default_factory=list)


def matches(db: Session, actor: User, proposal: s.Extraction) -> list[Application]:
    query = select(Application).where(visibility(Application, actor))
    if proposal.application_code:
        query = query.where(Application.application_code == proposal.application_code)
    elif proposal.candidate_name:
        query = query.where(Application.candidate.has(Candidate.display_name == proposal.candidate_name))
    else:
        return []
    if proposal.position_name:
        query = query.where(Application.position.has(Position.title == proposal.position_name))
    return list(db.scalars(query.order_by(Application.id).limit(20)))


def apply_proposal(
    db: Session,
    actor: User,
    proposal: s.Extraction,
    *,
    event_key: str,
    source: str,
    approved=False,
    selected_application: str | None = None,
    candidate_id: str | None = None,
    position_id: str | None = None,
    create_new_candidate=False,
    interview_id: str | None = None,
    manual_origin=False,
) -> Application:
    require_writer(actor)
    candidates = matches(db, actor, proposal)
    options = [application_read(row).model_dump(mode="json") for row in candidates]
    if not approved and (proposal.should_confirm or proposal.missing_fields or proposal.ambiguities):
        raise ReviewNeeded("AMBIGUOUS_EXTRACTION", "消息存在缺失字段或歧义，请人工确认", options)
    if proposal.intent == "create_application":
        if not proposal.candidate_name and not candidate_id:
            raise ReviewNeeded("MISSING_CANDIDATE", "缺少候选人姓名或候选人ID")
        if not proposal.position_name and not position_id:
            raise ReviewNeeded("MISSING_POSITION", "缺少岗位名称或ID")
        same_name = list(
            db.scalars(
                select(Candidate)
                .where(visibility(Candidate, actor), Candidate.display_name == proposal.candidate_name)
                .limit(20)
            )
        )
        if same_name and not candidate_id and not (approved and create_new_candidate):
            all_apps = list(
                db.scalars(
                    select(Application)
                    .where(
                        visibility(Application, actor),
                        Application.candidate_id.in_([c.id for c in same_name]),
                    )
                    .limit(20)
                )
            )
            raise ReviewNeeded(
                "CANDIDATE_AMBIGUOUS",
                "存在同名资料，必须显式选择已有候选人或确认新建",
                [application_read(a).model_dump(mode="json") for a in all_apps],
                [c.id for c in same_name],
            )
        data = s.ApplicationCreate(
            candidate_id=candidate_id,
            candidate_name=None if candidate_id else proposal.candidate_name,
            position_id=position_id,
            position_title=None if position_id else proposal.position_name,
            application_code=proposal.application_code,
        )
        return create_application(db, actor, data, event_key, source)
    if selected_application:
        application = get_entity(db, Application, selected_application, actor, write=True)
    elif proposal.application_code:
        raw = db.scalar(
            select(Application).where(
                Application.application_code == proposal.application_code, Application.deleted_at.is_(None)
            )
        )
        if raw is None:
            raise ReviewNeeded("APPLICATION_NOT_FOUND", "申请编号不存在，不能新建同名记录", options)
        application = get_entity(db, Application, raw.id, actor, write=True)
    else:
        raise ReviewNeeded("APPLICATION_ID_REQUIRED", "只凭姓名不能自动更新，请明确选择申请", options)
    options = [application_read(application).model_dump(mode="json")]
    if proposal.intent == "update_stage":
        if proposal.stage is None:
            raise ReviewNeeded("MISSING_STAGE", "缺少目标阶段", options)
        if proposal.stage in {Stage.HIRED, Stage.REJECTED} and not (approved and manual_origin):
            raise ReviewNeeded("MANUAL_DECISION_REQUIRED", "录用或淘汰只能通过人工申请管理操作记录", options)
        if approved and application.stage in TERMINAL_STAGES:
            before = snapshot(application)
            conditional_update(
                db,
                application,
                application.version,
                {
                    "stage": proposal.stage.value,
                    "outcome": proposal.stage.value if proposal.stage in TERMINAL_STAGES else "pending",
                },
            )
            record_change(db, application, actor, "confirm_terminal_reversal", before)
            return application
        changed = patch_application(
            db,
            actor,
            application,
            s.ApplicationPatch(
                stage=proposal.stage, change_reason="人工审核提议" if approved else "明确消息阶段更新"
            ),
            application.version,
            event_key,
            source,
        )
        if changed.status != "applied":
            # Discard the S1 helper's pending write; the ingestion workflow creates its own linked task.
            raise ReviewNeeded("TERMINAL_REVERSAL", "终态逆转必须经人工审核", options)
    elif proposal.intent == "record_result":
        round_ = proposal.interview_round
        result = proposal.interview_result
        if round_ not in {1, 2} or result not in {"passed", "failed"}:
            raise ReviewNeeded("MISSING_INTERVIEW_RESULT", "须明确面试轮次与通过/未通过结果", options)
        expected_stage = Stage.INTERVIEW_1 if round_ == 1 else Stage.INTERVIEW_2
        if application.stage != expected_stage:
            raise ReviewNeeded("STAGE_CONFLICT", "当前阶段与消息轮次不一致，不能跳阶段或逆转", options)
        query = select(Interview).where(
            Interview.application_id == application.id,
            Interview.round == round_,
            Interview.deleted_at.is_(None),
        )
        if interview_id:
            query = query.where(Interview.id == interview_id)
        interviews = list(db.scalars(query))
        if len(interviews) > 1:
            raise ReviewNeeded("INTERVIEW_AMBIGUOUS", "同轮有多次面试，请在审核时选择面试ID", options)
        if interviews:
            interview = interviews[0]
            if interview.status != "scheduled":
                raise ReviewNeeded("INTERVIEW_ALREADY_RECORDED", "面试已有结果，不自动覆盖", options)
            before = snapshot(interview)
            conditional_update(
                db,
                interview,
                interview.version,
                {"status": "completed", "result": result, "feedback_at": utcnow()},
            )
            record_change(db, interview, actor, "record_interview_result", before)
        else:
            if interview_id:
                fail(404, "NOT_FOUND", "所选面试不存在或不属于本申请/轮次")
            interview = Interview(
                application_id=application.id,
                round=round_,
                scheduled_at=None,
                interviewer=None,
                status="completed",
                result=result,
                feedback_at=utcnow(),
            )
            db.add(interview)
            record_change(db, interview, actor, "record_interview_result")
        if result == "passed":
            patch_application(
                db,
                actor,
                application,
                s.ApplicationPatch(
                    stage=Stage.INTERVIEW_2 if round_ == 1 else Stage.OFFER,
                    change_reason="记录本轮通过，进入下一阶段",
                ),
                application.version,
                event_key,
                source,
            )
        else:
            touch_application(db, actor, application)  # a failed round does not automatically reject a person
        if proposal.next_interview:
            plan = proposal.next_interview
            if plan.round != round_ + 1 or result != "passed":
                raise ReviewNeeded("INVALID_NEXT_ROUND", "下一轮安排与本轮结果不一致", options)
            schedule(db, actor, application, plan.round, plan.scheduled_at, plan.interviewer, options)
    elif proposal.intent == "schedule_interview":
        schedule(
            db,
            actor,
            application,
            proposal.interview_round,
            proposal.scheduled_at,
            proposal.interviewer,
            options,
        )
    else:
        raise ReviewNeeded("UNKNOWN_INTENT", "无法识别可执行招聘操作，请修正或驳回", options)
    return application


def schedule(db, actor, application, round_, when, interviewer, options):
    if round_ not in {1, 2} or when is None or not interviewer:
        raise ReviewNeeded("MISSING_INTERVIEW_PLAN", "安排面试必须有明确轮次、具体时点和面试官", options)
    expected = Stage.INTERVIEW_1 if round_ == 1 else Stage.INTERVIEW_2
    if application.stage != expected:
        raise ReviewNeeded("STAGE_CONFLICT", "当前阶段不支持该轮面试安排", options)
    existing = db.scalar(
        select(Interview.id).where(
            Interview.application_id == application.id,
            Interview.round == round_,
            Interview.status == "scheduled",
            Interview.deleted_at.is_(None),
        )
    )
    if existing:
        raise ReviewNeeded("INTERVIEW_ALREADY_SCHEDULED", "该轮已有面试安排，不重复创建", options)
    create_interview(
        db,
        actor,
        application,
        s.InterviewCreate(round=round_, scheduled_at=when, interviewer=interviewer),
        application.version,
    )
