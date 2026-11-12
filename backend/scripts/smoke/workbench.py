"""Running HTTP S4 acceptance using fictional local Mock facts only."""

import os
import uuid
from datetime import datetime, timezone

import httpx


def headers(version=None):
    result = {"Idempotency-Key": uuid.uuid4().hex}
    if version is not None:
        result["If-Match"] = str(version)
    return result


with httpx.Client(base_url=os.getenv("RECRUITFLOW_API_URL", "http://127.0.0.1:8000/api/v1"), trust_env=False, timeout=20) as client:
    assert client.get("/integrations/status").json()["data"]["sync_provider"] == "mock"
    before = client.get("/dashboard/overview").json()["data"]
    options = client.get("/recruitment/options").json()["data"]
    position = next(row for row in options["positions"] if row["title"] == "前端工程师（演示）")
    created = client.post("/applications", headers=headers(), json={
        "candidate_name": "虚构S4联调" + uuid.uuid4().hex[:4], "position_id": position["id"],
        "source_channel": "演示样本", "application_code": "WEB_S4_" + uuid.uuid4().hex[:8].upper(),
    })
    created.raise_for_status()
    app = created.json()["data"]
    for stage in ("screening", "interview_1", "interview_2", "offer"):
        response = client.patch(f"/applications/{app['id']}", headers=headers(app["version"]),
                                json={"stage": stage, "change_reason": "虚构S4端到端准备"})
        response.raise_for_status()
        app = response.json()["data"]["application"]
    path = f"/applications/{app['id']}/offer"
    sent = client.post(path, headers=headers(app["version"]), json={
        "sent_at": datetime.now(timezone.utc).isoformat(), "change_reason": "虚构已发出事实，无实际发送"})
    sent.raise_for_status()
    key = headers(sent.json()["data"]["version"])
    body = {"status": "accepted", "responded_at": datetime.now(timezone.utc).isoformat(), "change_reason": "虚构已接受事实"}
    accepted = client.patch(path, headers=key, json=body)
    accepted.raise_for_status()
    assert client.patch(path, headers=key, json=body).json()["data"] == accepted.json()["data"]
    app = client.get(f"/applications/{app['id']}").json()["data"]
    assert app["stage"] == "offer"  # acceptance alone never hires
    metrics = client.get("/dashboard/overview").json()["data"]
    assert metrics["offers_accepted"] == before["offers_accepted"] + 1
    assert metrics["hired_applications"] == before["hired_applications"]
    result = client.patch(f"/applications/{app['id']}", headers=headers(app["version"]), json={"stage": "hired", "change_reason": "人工登记虚构录用，仅本地验收"})
    result.raise_for_status()
    filtered = {"position_id": position["id"]}
    assert client.get("/dashboard/overview", params=filtered).json()["data"]["new_applications"] == client.get("/applications", params=filtered).json()["pagination"]["total"]
    for suffix in ("", "/offer", "/history"):
        assert client.get(f"/applications/{app['id']}{suffix}", headers={"X-Dev-User": "hr-b"}).status_code == 403
    assert any(row["action"] == "record_offer_response" for row in client.get(f"/applications/{app['id']}/history").json()["data"])
    assert client.get("/tasks?kind=feedback").status_code == 200
    assert client.get("/settings/policy").status_code == 200
    print("PASS: S4 filters + Offer sent/accepted/replay + independent manual hire + history + tasks + RBAC")
    print(f"Synthetic local application retained: {app['application_code']}")
