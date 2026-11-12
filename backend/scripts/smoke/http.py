"""Smoke-test running local servers with synthetic data; never connects to external services."""

import time
import uuid

import httpx

with httpx.Client(base_url="http://127.0.0.1:5173", trust_env=False, timeout=15) as client:
    html = client.get("/")
    html.raise_for_status()
    assert '<div id="root">' in html.text
    assert "/src/main.tsx" in html.text
    # Exercise the Vite /api proxy as well as the direct FastAPI endpoint.
    proxy_health = client.get("/api/v1/health")
    proxy_health.raise_for_status()
    assert proxy_health.json()["data"]["mode"] == "mock"

with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", trust_env=False, timeout=15) as client:
    assert client.get("/health").json()["data"]["status"] == "ok"
    before = client.get("/dashboard/overview").json()["data"]["new_applications"]
    event_id = "http-smoke-" + uuid.uuid4().hex
    body = {
        "text": "新增虚构冒烟" + uuid.uuid4().hex[:6] + "应聘测试工程岗",
        "source": "manual",
        "external_event_id": event_id,
    }
    created = client.post("/ingestions", json=body)
    created.raise_for_status()
    application = created.json()["data"]["application"]
    code = application["application_code"]
    for stage in ("screening", "interview_1"):
        prepared = client.patch(
            f"/applications/{application['id']}",
            json={"stage": stage, "change_reason": "HTTP虚构面试准备"},
            headers={"If-Match": str(application["version"]), "Idempotency-Key": uuid.uuid4().hex},
        )
        prepared.raise_for_status()
        application = prepared.json()["data"]["application"]
    update = {"text": f"{code} 一面通过", "external_event_id": event_id + "-update"}
    changed = client.post("/ingestions", json=update).json()["data"]
    assert changed["application"]["id"] == application["id"]
    assert changed["application"]["version"] == 4
    assert client.post("/ingestions", json=update).json()["data"]["status"] == "duplicate"
    planned = client.post(
        "/ingestions",
        json={"text": f"{code} 安排二面 明天15:00 面试官虚构王", "external_event_id": event_id + "-schedule"},
    )
    planned.raise_for_status()
    assert planned.json()["data"]["status"] == "applied"
    assert planned.json()["data"]["application"]["version"] == 5
    pending = client.post(
        "/ingestions",
        json={
            "text": f"{code} 进入Offer",
            "external_event_id": event_id + "-review",
            "execute_if_unambiguous": False,
        },
    ).json()["data"]
    assert pending["status"] == "needs_confirmation"
    review = next(
        row for row in client.get("/confirmations").json()["data"] if row["id"] == pending["confirmation_id"]
    )
    review_body = {"decision": "reject", "change_reason": "HTTP虚构审核演示"}
    review_headers = {"If-Match": str(review["version"]), "Idempotency-Key": uuid.uuid4().hex}
    resolved = client.post(f"/confirmations/{review['id']}/resolve", json=review_body, headers=review_headers)
    resolved.raise_for_status()
    assert resolved.json()["data"]["status"] == "rejected"
    assert (
        client.post(
            f"/confirmations/{review['id']}/resolve", json=review_body, headers=review_headers
        ).json()["data"]
        == resolved.json()["data"]
    )
    assert client.get("/dashboard/overview").json()["data"]["new_applications"] == before + 1
    sync = client.post("/sync/run", headers={"Idempotency-Key": uuid.uuid4().hex}).json()["data"]
    assert sync["accepted"] is True
    deadline = time.monotonic() + 20
    while True:
        jobs = client.get("/sync/jobs", params={"page_size": 100, "application_id": application["id"]}).json()["data"]
        target_jobs = [job for job in jobs if job["entity_type"] == "applications"]
        if len(target_jobs) == 5 and all(job["status"] in {"mock_synced", "superseded"} for job in target_jobs):
            break
        assert time.monotonic() < deadline, "Background Mock sync did not complete in 20 seconds"
        time.sleep(0.1)
    assert len(target_jobs) == 5
    assert len({job["remote_record_id"] for job in target_jobs}) == 1
    assert all(job["provider"] == "mock" for job in target_jobs)
    assert client.get("/sync/summary").json()["data"]["last_success_at"] is not None
    print("PASS: web 5173 + proxy + API 8000 + create/result/schedule/review/dedupe/dashboard/async mock sync")
    print("Synthetic record remains in the local Mock database. Browser rendering was not tested.")
