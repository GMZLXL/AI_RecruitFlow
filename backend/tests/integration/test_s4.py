from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from app.db import Application, AuditLog, Interview, Offer, Outbox, SessionLocal
from tests.helpers import create, headers, setup_owned_application


def offer_stage(client, obj, user="admin"):
    for stage in ("screening", "interview_1", "interview_2", "offer"):
        result = client.patch(
            f"/api/v1/applications/{obj['id']}",
            headers=headers(user, obj["version"]),
            json={"stage": stage, "change_reason": "虚构Offer准备"},
        )
        assert result.status_code == 200, result.text
        obj = result.json()["data"]["application"]
    return obj


def send(client, obj, user="admin"):
    result = client.post(
        f"/api/v1/applications/{obj['id']}/offer",
        headers=headers(user, obj["version"]),
        json={"sent_at": datetime.now(timezone.utc).isoformat(), "change_reason": "登记虚构发出事实"},
    )
    assert result.status_code == 201, result.text
    return result.json()["data"]


def test_empty_workbench_has_no_fake_metrics_or_tasks(client):
    data = client.get("/api/v1/dashboard/overview").json()["data"]
    assert (
        data["new_applications"]
        == data["offers_sent"]
        == data["offers_accepted"]
        == data["hired_applications"]
        == 0
    )
    assert data["offer_acceptance_rate"] is None and data["weekly_new"] == data["by_position"] == []
    assert client.get("/api/v1/tasks").json()["data"] == []
    policy = client.get("/api/v1/settings/policy").json()["data"]
    assert policy["stage_transitions"]["applied"] == ["screening"]


def test_offer_response_is_independent_from_hire_and_audited(client):
    obj = offer_stage(client, create(client).json()["data"])
    offer = send(client, obj)
    path = f"/api/v1/applications/{obj['id']}/offer"
    body = {
        "status": "accepted",
        "responded_at": datetime.now(timezone.utc).isoformat(),
        "change_reason": "虚构明确反馈",
    }
    key = headers(version=offer["version"])
    result = client.patch(path, headers=key, json=body)
    assert result.status_code == 200
    assert client.patch(path, headers=key, json=body).json()["data"] == result.json()["data"]
    assert (
        client.patch(path, headers=headers(version=2), json={**body, "status": "declined"}).status_code == 409
    )
    current = client.get(f"/api/v1/applications/{obj['id']}").json()["data"]
    assert current["stage"] == "offer" and current["version"] == obj["version"] + 2
    metrics = client.get("/api/v1/dashboard/overview").json()["data"]
    assert metrics["offers_sent"] == metrics["offers_accepted"] == 1
    assert metrics["hired_applications"] == 0 and metrics["offer_acceptance_rate"] == 1
    history = client.get(f"/api/v1/applications/{obj['id']}/history").json()["data"]
    assert any(row["action"] == "record_offer_response" for row in history)
    assert all("contact_encrypted" not in str(row) for row in history)
    with SessionLocal() as db:
        jobs = db.scalars(
            select(Outbox).where(Outbox.entity_type == "applications").order_by(Outbox.version.desc())
        ).all()
        assert jobs[0].payload_json["projection"]["offer_status"] == "accepted"
        assert db.scalar(select(Outbox).where(Outbox.entity_type == "offers", Outbox.version == 2))


def test_offer_decline_and_waiting_denominator(client):
    for index, status in enumerate(("accepted", "declined", "sent")):
        obj = offer_stage(client, create(client, f"A{index}0001").json()["data"])
        offer = send(client, obj)
        if status != "sent":
            result = client.patch(
                f"/api/v1/applications/{obj['id']}/offer",
                headers=headers(version=offer["version"]),
                json={
                    "status": status,
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                    "change_reason": "虚构回复",
                },
            )
            assert result.status_code == 200
    metrics = client.get("/api/v1/dashboard/overview").json()["data"]
    assert metrics["offers_sent"] == 3 and metrics["offers_declined"] == 1
    assert metrics["offer_acceptance_rate"] == 0.5


def test_offer_permission_version_and_time_validation(client):
    obj, _, _ = setup_owned_application(client)
    obj = offer_stage(client, obj, "hr-a")
    path = f"/api/v1/applications/{obj['id']}/offer"
    now = datetime.now(timezone.utc)
    body = {"sent_at": now.isoformat(), "change_reason": "虚构"}
    assert client.post(path, headers=headers("hr-b", obj["version"]), json=body).status_code == 403
    assert client.post(path, headers=headers("manager-a", obj["version"]), json=body).status_code == 403
    assert client.post(path, headers=headers("hr-a", 1), json=body).status_code == 409
    assert (
        client.post(
            path,
            headers=headers("hr-a", obj["version"]),
            json={**body, "sent_at": (now + timedelta(days=1)).isoformat()},
        ).status_code
        == 400
    )
    assert (
        client.post(
            path, headers={"X-Dev-User": "hr-a", "If-Match": str(obj["version"])}, json=body
        ).status_code
        == 400
    )
    offer = send(client, obj, "hr-a")
    assert (
        client.patch(
            path,
            headers=headers("hr-a", 99),
            json={"status": "declined", "responded_at": now.isoformat(), "change_reason": "过期"},
        ).status_code
        == 400
    )  # response predates the actual sent fact
    assert (
        client.patch(
            path,
            headers=headers("hr-a", 99),
            json={
                "status": "declined",
                "responded_at": datetime.now(timezone.utc).isoformat(),
                "change_reason": "过期",
            },
        ).status_code
        == 409
    )
    assert offer["status"] == "sent"


def test_offer_audit_failure_rolls_back_offer_application_and_outbox(client):
    obj = offer_stage(client, create(client).json()["data"])

    def broken(*_):
        raise RuntimeError("synthetic-offer-audit")

    event.listen(AuditLog, "before_insert", broken)
    try:
        with pytest.raises(RuntimeError, match="synthetic-offer-audit"):
            send(client, obj)
    finally:
        event.remove(AuditLog, "before_insert", broken)
    with SessionLocal() as db:
        assert db.scalar(select(Offer)) is None
        stored = db.get(Application, obj["id"])
        assert stored is not None and stored.version == obj["version"]


def test_dashboard_filters_scope_match_list_and_shanghai_week(client):
    first, _, pos = setup_owned_application(client)
    second, _, _ = setup_owned_application(client, "hr-b", "B10001")
    instant = datetime(2026, 11, 8, 17, tzinfo=timezone.utc)  # Monday Nov 9 in Shanghai
    with SessionLocal() as db:
        row = db.get(Application, first["id"])
        assert row is not None
        row.created_at = instant
        db.commit()
    params = {
        "from": "2026-11-09T00:00:00+08:00",
        "to": "2026-11-10T00:00:00+08:00",
        "position_id": pos["id"],
    }
    data = client.get("/api/v1/dashboard/overview", params=params).json()["data"]
    assert (
        data["new_applications"]
        == client.get("/api/v1/applications", params=params).json()["pagination"]["total"]
        == 1
    )
    assert data["weekly_new"] == [{"week": "2026-11-09", "count": 1}]
    assert data["by_position"][0]["applications"] == 1
    assert (
        client.get("/api/v1/dashboard/overview", headers=headers("hr-a")).json()["data"]["new_applications"]
        == 1
    )
    for suffix in ("", "/history", "/offer"):
        assert (
            client.get(f"/api/v1/applications/{second['id']}{suffix}", headers=headers("hr-a")).status_code
            == 403
        )
    opts = client.get("/api/v1/recruitment/options", headers=headers("hr-a")).json()["data"]
    assert all(row["department"] == "engineering" for row in opts["positions"])
    assert len(opts["owners"]) == 1
    bad = {"from": "2026-11-10T00:00:00Z", "to": "2026-11-09T00:00:00Z"}
    assert client.get("/api/v1/dashboard/overview", params=bad).status_code == 422
    assert client.get("/api/v1/applications", params=bad).status_code == 422


def test_tasks_are_paginated_facts_and_respect_scope(client):
    first, _, _ = setup_owned_application(client)
    second, _, _ = setup_owned_application(client, "hr-b", "B10001")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for application, days in ((first, 1), (first, -1), (second, 1)):
            db.add(
                Interview(
                    application_id=application["id"],
                    round=1,
                    scheduled_at=now + timedelta(days=days),
                    interviewer="虚构面试官",
                )
            )
        row = db.get(Application, first["id"])
        assert row is not None
        row.updated_at = now - timedelta(days=8)
        db.commit()
    response = client.get("/api/v1/tasks", headers=headers("hr-a")).json()
    assert {row["kind"] for row in response["data"]} == {"interview", "feedback", "stalled"}
    assert {row["application_id"] for row in response["data"]} == {first["id"]}
    assert response["pagination"]["total"] == 3
    assert (
        client.get("/api/v1/tasks?kind=feedback&page_size=1", headers=headers("hr-a")).json()["pagination"][
            "total"
        ]
        == 1
    )
    assert client.get("/api/v1/tasks?kind=unknown").status_code == 422
