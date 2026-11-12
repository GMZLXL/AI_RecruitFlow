"""Smoke-test running local servers with synthetic data; never connects to external services."""

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
    assert client.get("/dashboard/overview").json()["data"]["new_applications"] == before + 1
    sync = client.post("/sync/run", headers={"Idempotency-Key": uuid.uuid4().hex}).json()["data"]
    assert sync["mode"] == "mock"
    jobs = client.get("/sync/jobs", params={"page_size": 100}).json()["data"]
    target_jobs = [
        job
        for job in jobs
        if job["entity_type"] == "applications" and job["application_id"] == application["id"]
    ]
    assert len(target_jobs) == 4
    assert len({job["remote_record_id"] for job in target_jobs}) == 1
    assert all(job["status"] == "mock_synced" for job in target_jobs)
    print("PASS: web 5173 + Vite proxy + API 8000 + create/update/dedupe/dashboard/mock sync")
    print("Synthetic record remains in the local Mock database. Browser rendering was not tested.")
