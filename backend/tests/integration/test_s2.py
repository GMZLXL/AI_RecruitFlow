import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app.core.security import DEV_IDS
from app.db import Confirmation, IngestionJob, Interview, SessionLocal, engine
from app.integrations.parsers.base import ParseOutcome
from app.integrations.parsers.factory import get_parser
from app.main import app
from app.schemas.ai import Extraction, ScheduleProposal
from tests.helpers import advance, counts, create, headers, setup_owned_application


def submit(client, text, event_id=None, **extra):
    return client.post(
        "/api/v1/ingestions", json={"text": text, "external_event_id": event_id or uuid.uuid4().hex, **extra}
    )


def queued(client, result):
    rows = client.get("/api/v1/confirmations").json()["data"]
    return next(row for row in rows if row["id"] == result["confirmation_id"])


def resolve(client, row, body, user="admin", key=None):
    return client.post(
        f"/api/v1/confirmations/{row['id']}/resolve", json=body, headers=headers(user, row["version"], key)
    )


def test_three_business_messages_and_no_invented_interview_plan(client):
    first = submit(client, "新增虚构流程甲应聘测试工程岗").json()["data"]
    assert first["status"] == "applied"
    application = advance(client, first["application"])
    result = submit(client, application["application_code"] + " 一面通过").json()["data"]
    assert result["status"] == "applied" and result["application"]["stage"] == "interview_2"
    rounds = client.get(f"/api/v1/applications/{application['id']}/interviews").json()["data"]
    assert rounds[0]["round"] == 1 and rounds[0]["result"] == "passed"
    assert rounds[0]["scheduled_at"] is None and rounds[0]["interviewer"] is None
    scheduled = submit(client, application["application_code"] + " 安排二面 明天15:00 面试官虚构王").json()[
        "data"
    ]
    assert scheduled["status"] == "applied"
    rounds = client.get(f"/api/v1/applications/{application['id']}/interviews").json()["data"]
    second = next(row for row in rounds if row["round"] == 2)
    assert second["status"] == "scheduled" and second["result"] == "pending"
    assert second["scheduled_at"].endswith("Z")


def test_name_conflict_confirm_select_replay_and_only_once(client):
    a = advance(client, create(client, "A10001").json()["data"])
    b = advance(client, create(client, "A10002").json()["data"])
    event_id = "same-name-event"
    result = submit(client, "虚构候选甲一面通过", event_id).json()["data"]
    assert result["status"] == "needs_confirmation"
    row = queued(client, result)
    assert len(row["candidates"]) == 2
    body = {
        "decision": "confirm",
        "change_reason": "人工核实申请编号A10001",
        "application_id": a["id"],
        "expected_application_version": a["version"],
    }
    key = uuid.uuid4().hex
    approved = resolve(client, row, body, key=key)
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["application"]["id"] == a["id"]
    before = counts()
    assert resolve(client, row, body, key=key).json()["data"] == approved.json()["data"]
    assert counts() == before
    assert resolve(client, row, body).status_code == 409
    assert submit(client, "虚构候选甲一面通过", event_id).json()["data"]["status"] == "duplicate"
    assert client.get(f"/api/v1/applications/{b['id']}").json()["data"]["stage"] == "interview_1"


def test_even_unique_name_requires_explicit_confirmation(client):
    advance(client, create(client).json()["data"])
    result = submit(client, "虚构候选甲一面通过").json()["data"]
    assert result["status"] == "needs_confirmation"
    assert len(queued(client, result)["candidates"]) == 1


def test_ambiguous_schedule_can_be_corrected_and_executed(client):
    application = advance(client, create(client).json()["data"])
    application = submit(client, "A10001 一面通过").json()["data"]["application"]
    result = submit(client, "A10001 安排二面 明天下午 面试官虚构王").json()["data"]
    row = queued(client, result)
    correction = {
        **row["proposal"],
        "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "should_confirm": False,
        "missing_fields": [],
        "ambiguities": [],
    }
    response = resolve(
        client,
        row,
        {
            "decision": "modify",
            "change_reason": "已向面试官确认具体时间",
            "application_id": application["id"],
            "expected_application_version": application["version"],
            "correction": correction,
        },
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/confirmations").json()["pagination"]["total"] == 0
    with SessionLocal() as db:
        saved = db.get(Confirmation, row["id"])
        assert saved is not None
        assert datetime.fromisoformat(
            saved.proposed_json["reviewed_extraction"]["scheduled_at"]
        ) == datetime.fromisoformat(correction["scheduled_at"])


def test_reject_does_not_modify_application_and_replay_stays_rejected(client):
    application = create(client).json()["data"]
    before = counts()[:3]
    result = submit(client, "A10001 明天下午二面", "reject-event").json()["data"]
    row = queued(client, result)
    response = resolve(client, row, {"decision": "reject", "change_reason": "消息不完整，驳回补充"})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
    assert counts()[:3] == before
    assert client.get(f"/api/v1/applications/{application['id']}").json()["data"]["version"] == 1
    assert submit(client, "A10001 明天下午二面", "reject-event").json()["data"]["status"] == "failed"


def test_stale_confirmation_keeps_pending_and_rejects_409(client):
    application = advance(client, create(client).json()["data"])
    result = submit(client, "虚构候选甲一面通过").json()["data"]
    row = queued(client, result)
    client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"stage": "interview_2", "change_reason": "另一次人工更新"},
        headers=headers(version=application["version"]),
    )
    response = resolve(
        client,
        row,
        {
            "decision": "confirm",
            "change_reason": "不应覆盖新版本",
            "application_id": application["id"],
            "expected_application_version": application["version"],
        },
    )
    assert response.status_code == 409
    assert queued(client, result)["status"] == "pending"


def test_confirmation_scope_and_record_scope_rechecked(client):
    application, _, _ = setup_owned_application(client, "hr-a")
    result = client.post(
        "/api/v1/ingestions", json={"text": "A10001 安排一面 明天下午"}, headers=headers("hr-a")
    ).json()["data"]
    row = queued(client, result)
    assert (
        resolve(client, row, {"decision": "reject", "change_reason": "越权驳回"}, "hr-b").status_code == 403
    )
    assert client.get("/api/v1/confirmations", headers=headers("hr-b")).json()["data"] == []
    assert client.get("/api/v1/ingestions", headers=headers("hr-b")).json()["data"] == []


def test_network_phase_releases_all_database_connections(client):
    checked_out = [0]
    observed = []

    def checkout(*_):
        checked_out[0] += 1

    def checkin(*_):
        checked_out[0] -= 1

    class CheckingParser:
        async def parse(self, text, reference_time, timezone):
            observed.append(checked_out[0])
            return ParseOutcome(Extraction(intent="unknown", should_confirm=True))

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    app.dependency_overrides[get_parser] = lambda: CheckingParser()
    try:
        assert submit(client, "不能确定的虚构消息").status_code == 200
        assert observed == [0]
    finally:
        app.dependency_overrides.pop(get_parser, None)
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "checkin", checkin)


def test_compound_message_failure_rolls_back_result_and_stage(client):
    application = advance(client, create(client).json()["data"])
    before = counts()[:3]

    class IncompleteParser:
        async def parse(self, text, reference_time, timezone):
            return ParseOutcome(
                Extraction(
                    intent="record_result",
                    application_code="A10001",
                    interview_round=1,
                    interview_result="passed",
                    next_interview=ScheduleProposal(round=2),
                )
            )

    app.dependency_overrides[get_parser] = lambda: IncompleteParser()
    try:
        result = submit(client, "A10001 一面通过并安排二面").json()["data"]
    finally:
        app.dependency_overrides.pop(get_parser, None)
    assert result["status"] == "needs_confirmation"
    assert counts()[:3] == before
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Interview.id))) == 0
    assert client.get(f"/api/v1/applications/{application['id']}").json()["data"]["stage"] == "interview_1"


def test_processing_lease_and_crash_recovery(client):
    text = "新增虚构恢复甲应聘测试工程岗"
    with SessionLocal() as db:
        job = IngestionJob(
            actor_id=DEV_IDS["admin"],
            source="manual",
            external_event_id="recover-event",
            message_hash=hashlib.sha256(text.encode()).hexdigest(),
            state="parsing",
            processing_token=str(uuid.uuid4()),
            processing_started_at=datetime.now(timezone.utc),
            extracted_json={},
        )
        db.add(job)
        db.commit()
        job_id = job.id
    assert submit(client, text, "recover-event").json()["data"]["status"] == "parsing"
    with SessionLocal() as db:
        job = db.get(IngestionJob, job_id)
        assert job is not None
        job.processing_started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        db.commit()
    assert submit(client, text, "recover-event").json()["data"]["status"] == "applied"
    assert submit(client, text, "recover-event").json()["data"]["status"] == "duplicate"
    assert counts()[1] == 1


def test_missing_deepseek_credentials_is_visible_manual_review(client, monkeypatch):
    monkeypatch.setenv("APP_MODE", "hybrid")
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    result = submit(client, "A10001 一面通过").json()["data"]
    assert result["status"] == "needs_confirmation"
    assert result["reason_code"] == "BLOCKED_BY_CREDENTIALS"
    assert result["parser_provider"] == "deepseek"


def test_pending_terminal_reversal_from_s1_can_be_confirmed(client):
    application = create(client).json()["data"]
    route = f"/api/v1/applications/{application['id']}"
    client.patch(
        route, json={"stage": "withdrawn", "change_reason": "人工记录退出"}, headers=headers(version=1)
    )
    requested = client.patch(
        route, json={"stage": "screening", "change_reason": "人工确认恢复"}, headers=headers(version=2)
    ).json()["data"]
    row = queued(client, requested)
    result = resolve(
        client,
        row,
        {"decision": "confirm", "change_reason": "核实后恢复筛选", "expected_application_version": 2},
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["application"]["stage"] == "screening"


def test_failed_interview_does_not_reject_candidate(client):
    advance(client, create(client).json()["data"])
    result = submit(client, "A10001 一面未通过").json()["data"]
    assert result["status"] == "applied"
    assert result["application"]["stage"] == "interview_1"
    assert result["application"]["outcome"] == "pending"


@pytest.mark.parametrize(
    "text,code",
    [("A10001和A10002一面通过", "MULTIPLE_APPLICATIONS"), ("A10001一面通过，二面未通过", "MULTIPLE_RESULTS")],
)
def test_deterministic_conflicts_bypass_even_overconfident_parser(client, text, code):
    calls = []

    class OverconfidentParser:
        async def parse(self, *args):
            calls.append(args)
            return ParseOutcome(
                Extraction(intent="create_application", candidate_name="不应新增", position_name="测试岗")
            )

    app.dependency_overrides[get_parser] = lambda: OverconfidentParser()
    try:
        result = submit(client, text).json()["data"]
    finally:
        app.dependency_overrides.pop(get_parser, None)
    assert result["status"] == "needs_confirmation" and result["reason_code"] == code
    assert calls == [] and counts()[:3] == (0, 0, 0)


def test_explicit_review_option_and_conflicting_messages_never_autowrite(client):
    application = advance(client, create(client).json()["data"])
    result = submit(client, "A10001 一面通过", execute_if_unambiguous=False).json()["data"]
    assert result["status"] == "needs_confirmation" and result["reason_code"] == "REVIEW_REQUESTED"
    result = submit(client, "A10001 一面通过，二面未通过").json()["data"]
    assert result["status"] == "needs_confirmation"
    assert client.get(f"/api/v1/applications/{application['id']}").json()["data"]["version"] == 3
