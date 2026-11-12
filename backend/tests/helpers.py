import uuid

from sqlalchemy import func, select

from app.core.security import DEV_IDS
from app.db import Application, AuditLog, Candidate, Event, Outbox, SessionLocal


def create(client, code="A10001"):
    return client.post(
        "/api/v1/applications",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={
            "candidate_name": "虚构候选甲",
            "position_title": "数据分析师",
            "application_code": code,
        },
    )


def advance(client, application, headers=None):
    for stage in ("screening", "interview_1"):
        response = client.patch(
            f"/api/v1/applications/{application['id']}",
            json={"stage": stage, "change_reason": "虚构样本面试准备"},
            headers={
                **(headers or {}),
                "Idempotency-Key": uuid.uuid4().hex,
                "If-Match": str(application["version"]),
            },
        )
        assert response.status_code == 200, response.text
        application = response.json()["data"]["application"]
    return application


def counts():
    with SessionLocal() as db:
        return tuple(
            db.scalar(select(func.count(model.id))) or 0
            for model in (Candidate, Application, Event, AuditLog, Outbox)
        )


def headers(user="admin", version=None, key=None):
    result = {"X-Dev-User": user, "Idempotency-Key": key or uuid.uuid4().hex}
    if version is not None:
        result["If-Match"] = str(version)
    return result


def setup_owned_application(client, user="hr-a", code="A10001"):
    department = "sales" if user == "hr-b" else "engineering"
    position = client.post(
        "/api/v1/positions",
        json={"title": "虚构测试岗位", "department": department, "owner_user_id": DEV_IDS[user]},
        headers=headers(),
    ).json()["data"]
    candidate = client.post(
        "/api/v1/candidates", json={"display_name": "虚构同名甲"}, headers=headers(user)
    ).json()["data"]
    response = client.post(
        "/api/v1/applications",
        json={"candidate_id": candidate["id"], "position_id": position["id"], "application_code": code},
        headers=headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"], candidate, position
