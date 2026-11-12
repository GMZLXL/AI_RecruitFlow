import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.core.security import DEV_IDS
from app.db import (
    Application,
    Candidate,
    Confirmation,
    Event,
    IdempotencyRecord,
    Outbox,
    SessionLocal,
    engine,
)
from tests.helpers import advance, counts, create, headers, setup_owned_application


def test_one_candidate_two_positions_and_no_name_merge(client):
    app, candidate, _ = setup_owned_application(client)
    position = client.post(
        "/api/v1/positions", json={"title": "另一虚构岗位", "department": "engineering"}, headers=headers()
    ).json()["data"]
    second = client.post(
        "/api/v1/applications",
        json={"candidate_id": candidate["id"], "position_id": position["id"], "application_code": "A10002"},
        headers=headers("hr-a"),
    )
    assert second.status_code == 201
    assert second.json()["data"]["candidate_id"] == app["candidate_id"]
    assert second.json()["data"]["id"] != app["id"]
    moved = client.patch(f"/api/v1/applications/{app['id']}", headers=headers("hr-a", app["version"]),
        json={"stage": "screening", "change_reason": "虚构多岗状态隔离验收"})
    assert moved.status_code == 200
    assert client.get(f"/api/v1/applications/{second.json()['data']['id']}", headers=headers("hr-a")).json()["data"]["stage"] == "applied"
    assert (
        client.get(
            "/api/v1/applications", params={"candidate_id": candidate["id"]}, headers=headers("hr-a")
        ).json()["pagination"]["total"]
        == 2
    )
    duplicate_person = client.post(
        "/api/v1/candidates", json={"display_name": candidate["display_name"]}, headers=headers("hr-a")
    ).json()["data"]
    assert duplicate_person["id"] != candidate["id"]


@pytest.mark.parametrize(
    "endpoint", ["applications", "candidates", "positions", "sync/jobs", "integrations/status"]
)
def test_rbac_read_scopes(client, endpoint):
    app_a, person_a, position_a = setup_owned_application(client, "hr-a", "A10001")
    app_b, _, _ = setup_owned_application(client, "hr-b", "A10002")
    result = client.get("/api/v1/" + endpoint, headers=headers("hr-a"))
    if endpoint in {"sync/jobs", "integrations/status"}:
        assert result.status_code == 403
    else:
        assert result.status_code == 200
        assert result.json()["pagination"]["total"] == 1
    for route, entity_id in (
        ("applications", app_a["id"]),
        ("candidates", person_a["id"]),
        ("positions", position_a["id"]),
    ):
        assert client.get(f"/api/v1/{route}/{entity_id}", headers=headers("hr-b")).status_code == 403
    assert (
        client.get(f"/api/v1/applications/{app_b['id']}/events", headers=headers("hr-a")).status_code == 403
    )
    assert (
        client.get("/api/v1/dashboard/overview", headers=headers("hr-a")).json()["data"]["new_applications"]
        == 1
    )
    manager = client.get("/api/v1/applications", headers=headers("manager-a")).json()
    assert [row["id"] for row in manager["data"]] == [app_a["id"]]


def test_role_spoofing_manager_write_and_owner_assignment_blocked(client):
    application, _, _ = setup_owned_application(client)
    result = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"stage": "screening", "change_reason": "越权测试"},
        headers={**headers("hr-b", 1), "X-User-Role": "ADMIN"},
    )
    assert result.status_code == 403
    assert (
        client.post(
            "/api/v1/candidates", json={"display_name": "虚构甲"}, headers=headers("manager-a")
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/candidates",
            json={"display_name": "虚构甲", "owner_id": DEV_IDS["hr-b"]},
            headers=headers("hr-a"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/positions",
            json={"title": "不应创建", "department": "engineering"},
            headers=headers("hr-a"),
        ).status_code
        == 403
    )
    assert client.get("/api/v1/me", headers=headers("nonexistent")).status_code == 401


def test_disabled_dev_auth_and_inactive_user(client, monkeypatch):
    monkeypatch.setenv("DEV_AUTH_ENABLED", "false")
    assert client.get("/api/v1/me", headers=headers()).status_code == 401
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    from app.db import User

    with SessionLocal() as db:
        user = db.get(User, DEV_IDS["hr-a"])
        assert user is not None
        user.active = False
        db.commit()
    assert client.get("/api/v1/me", headers=headers("hr-a")).status_code == 401


def test_optimistic_conflict_idempotent_replay_and_if_match_required(client):
    application = create(client).json()["data"]
    route = f"/api/v1/applications/{application['id']}"
    body = {"stage": "screening", "change_reason": "正常推进"}
    same = headers(version=1)
    first = client.patch(route, json=body, headers=same)
    assert first.status_code == 200
    assert first.json()["data"]["application"]["version"] == 2
    before = counts()
    replay = client.patch(route, json=body, headers=same)
    assert replay.json()["data"] == first.json()["data"]
    assert counts() == before
    assert (
        client.patch(route, json={**body, "stage": "interview_1"}, headers=headers(version=1)).status_code
        == 409
    )
    assert client.patch(route, json=body, headers=headers()).status_code == 422
    assert counts() == before


def test_terminal_reversal_persists_confirmation_without_changing_application(client):
    application = create(client).json()["data"]
    route = f"/api/v1/applications/{application['id']}"
    ended = client.patch(
        route, json={"stage": "withdrawn", "change_reason": "人工记录主动退出"}, headers=headers(version=1)
    ).json()["data"]["application"]
    response = client.patch(
        route,
        json={"stage": "screening", "change_reason": "申请恢复"},
        headers=headers(version=ended["version"]),
    )
    result = response.json()["data"]
    assert result["status"] == "needs_confirmation"
    assert result["application"]["version"] == ended["version"]
    assert result["application"]["stage"] == "withdrawn"
    with SessionLocal() as db:
        confirmation = db.get(Confirmation, result["confirmation_id"])
        assert confirmation is not None and confirmation.status == "pending"
        assert confirmation.proposed_json["expected_version"] == ended["version"]
        assert db.scalar(select(func.count(Outbox.id)).where(Outbox.entity_type == "confirmations")) == 1


def test_stage_skipping_and_ai_automatic_hiring_not_allowed(client):
    application = create(client).json()["data"]
    assert (
        client.patch(
            f"/api/v1/applications/{application['id']}",
            json={"stage": "offer", "change_reason": "不能跳阶段"},
            headers=headers(version=1),
        ).status_code
        == 409
    )
    for message in ("A10001 录用了", "A10001 淘汰", "A10001 一面通过"):
        assert (
            client.post("/api/v1/ingestions", json={"text": message}).json()["data"]["status"]
            == "needs_confirmation"
        )
    assert client.get(f"/api/v1/applications/{application['id']}").json()["data"]["stage"] == "applied"


def test_soft_delete_replay_and_retained_history(client):
    application = create(client).json()["data"]
    route = f"/api/v1/applications/{application['id']}"
    same = headers(version=1)
    assert client.delete(route, headers=same).status_code == 422
    removed = client.request("DELETE", route, json={"change_reason": "删除虚构测试资料"}, headers=same)
    assert removed.status_code == 200
    assert (
        client.request("DELETE", route, json={"change_reason": "删除虚构测试资料"}, headers=same).json()[
            "data"
        ]
        == removed.json()["data"]
    )
    assert client.get(route).status_code == 404
    assert client.get("/api/v1/applications").json()["pagination"]["total"] == 0
    assert client.get("/api/v1/dashboard/overview").json()["data"]["new_applications"] == 0
    with SessionLocal() as db:
        row = db.get(Application, application["id"])
        assert row is not None and row.deleted_at is not None
        assert db.scalar(select(func.count(Event.id)).where(Event.application_id == row.id)) == 2
        assert (
            db.scalar(select(func.count(Outbox.id)).where(Outbox.entity_id == row.id, Outbox.op == "delete"))
            == 1
        )


def test_candidate_and_position_crud_reference_guards_and_projection_versions(client):
    application = create(client).json()["data"]
    person = application["candidate_id"]
    position = application["position_id"]
    for route in (f"/api/v1/candidates/{person}", f"/api/v1/positions/{position}"):
        assert (
            client.request(
                "DELETE", route, json={"change_reason": "有关联不可删除"}, headers=headers(version=1)
            ).status_code
            == 409
        )
    changed = client.patch(
        f"/api/v1/candidates/{person}",
        json={"display_name": "虚构改名甲", "change_reason": "修正姓名"},
        headers=headers(version=1),
    )
    assert changed.status_code == 200
    application = client.get(f"/api/v1/applications/{application['id']}").json()["data"]
    assert application["candidate_name"] == "虚构改名甲" and application["version"] == 2
    changed = client.patch(
        f"/api/v1/positions/{position}",
        json={"title": "虚构新岗位名", "change_reason": "修正标题"},
        headers=headers(version=1),
    )
    assert changed.status_code == 200
    assert client.get(f"/api/v1/applications/{application['id']}").json()["data"]["version"] == 3


def test_extension_whitelist_roundtrip_and_rejection(client):
    body = {"display_name": "虚构扩展甲", "custom_fields": {"organization.referral_tag": "内推"}}
    created = client.post("/api/v1/candidates", json=body, headers=headers())
    assert created.status_code == 201
    result = created.json()["data"]
    assert (
        client.get(f"/api/v1/candidates/{result['id']}").json()["data"]["custom_fields"]
        == body["custom_fields"]
    )
    for invalid in (
        {"owner_id": "admin"},
        {"organization.referral_tag": {"nested": "no"}},
        {"organization.referral_tag": "x" * 121},
    ):
        assert (
            client.post(
                "/api/v1/candidates", json={**body, "custom_fields": invalid}, headers=headers()
            ).status_code
            == 422
        )
    assert client.get("/api/v1/candidates").json()["pagination"]["total"] == 1


def test_interview_utc_result_separation_version_and_permissions(client):
    application, _, _ = setup_owned_application(client)
    application = advance(client, application, headers("hr-a"))
    appointment = (
        (datetime.now(timezone.utc) + timedelta(days=3)).astimezone(timezone(timedelta(hours=8))).isoformat()
    )
    response = client.post(
        f"/api/v1/applications/{application['id']}/interviews",
        json={"round": 1, "scheduled_at": appointment, "interviewer": "虚构面试官"},
        headers=headers("hr-a", application["version"]),
    )
    assert response.status_code == 201, response.text
    interview = response.json()["data"]
    assert interview["scheduled_at"].endswith("Z")
    assert client.get(f"/api/v1/interviews/{interview['id']}", headers=headers("hr-b")).status_code == 403
    patched = client.patch(
        f"/api/v1/interviews/{interview['id']}",
        json={"status": "completed", "result": "passed", "change_reason": "人工录入一面结果"},
        headers=headers("hr-a", interview["version"]),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["result"] == "passed"
    assert patched.json()["data"]["feedback_at"].endswith("Z")
    current = client.get(f"/api/v1/applications/{application['id']}", headers=headers("hr-a")).json()["data"]
    assert current["stage"] == "interview_1"  # result does not imply a later round passed
    assert current["version"] == application["version"] + 2
    assert (
        client.patch(
            f"/api/v1/interviews/{interview['id']}",
            json={"result": "failed", "change_reason": "过期版本"},
            headers=headers("hr-a", 1),
        ).status_code
        == 409
    )


def test_filter_pagination_literal_sort_and_time_bounds(client):
    app_a, _, _ = setup_owned_application(client, "hr-a", "A10001")
    setup_owned_application(client, "hr-b", "A10002")
    params = {
        "owner_id": app_a["owner_id"],
        "candidate_id": app_a["candidate_id"],
        "position_id": app_a["position_id"],
        "stage": "applied",
        "keyword": "A100",
        "sort": "code_asc",
        "page_size": 1,
    }
    result = client.get("/api/v1/applications", params=params).json()
    assert result["pagination"]["total"] == 1
    assert result["data"][0]["id"] == app_a["id"]
    assert client.get("/api/v1/applications", params={"sort": "DROP TABLE applications"}).status_code == 422
    assert (
        client.get(
            "/api/v1/applications", params={"from": app_a["created_at"], "to": app_a["created_at"]}
        ).json()["data"]
        == []
    )


def test_foreign_keys_and_aware_time_enforced(client):
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    with SessionLocal() as db:
        db.add(Candidate(display_name="虚构坏外键", owner_id=str(uuid.uuid4())))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(
            Candidate(display_name="虚构坏时间", owner_id=DEV_IDS["admin"], created_at=datetime(2026, 1, 1))
        )
        with pytest.raises(StatementError):
            db.commit()


def test_multi_entity_failure_rolls_back_including_idempotency(client):
    before = counts()

    def fail_outbox(*_args):
        raise RuntimeError("synthetic outbox failure")

    event.listen(Outbox, "before_insert", fail_outbox)
    try:
        with pytest.raises(RuntimeError, match="synthetic outbox failure"):
            create(client)
    finally:
        event.remove(Outbox, "before_insert", fail_outbox)
    assert counts() == before
    with SessionLocal() as db:
        assert db.scalar(select(func.count(IdempotencyRecord.id))) == 0


def test_missing_idempotency_and_cross_user_event_conflict(client):
    assert client.post("/api/v1/candidates", json={"display_name": "虚构甲"}).status_code == 400
    body = {"text": "不能确定的消息", "external_event_id": "global-event-1"}
    assert client.post("/api/v1/ingestions", json=body, headers=headers("hr-a")).status_code == 200
    assert client.post("/api/v1/ingestions", json=body, headers=headers("hr-b")).status_code == 403
    assert (
        client.post(
            "/api/v1/ingestions", json={**body, "text": "不同内容"}, headers=headers("hr-a")
        ).status_code
        == 409
    )
