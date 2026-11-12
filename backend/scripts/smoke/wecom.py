"""Local Mock only; retains one explicitly synthetic application and notification."""

import time
import uuid

import httpx


def run():
    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=10, trust_env=False) as client:
        status = client.get("/wecom/status").json()["data"]
        assert status["provider"] == "mock" and status["worker_enabled"], "Requires local Mock + enabled worker"
        code = "A_S5_" + uuid.uuid4().hex[:8].upper()
        def key():
            return {"Idempotency-Key": uuid.uuid4().hex}
        response = client.post("/applications", headers=key(), json={"application_code": code,
            "candidate_name": "虚构S5联调候选人", "position_title": "企微流程验证岗（虚构）", "source_channel": "演示样本"})
        response.raise_for_status()
        application = response.json()["data"]
        data = {"message_id": "s5-smoke-" + code, "text": code + "进入筛选"}
        first = client.post("/wecom/mock/messages", headers=key(), json=data)
        assert first.status_code == 202, first.text
        inbox_id = first.json()["data"]["id"]
        for _ in range(2):
            assert client.post("/wecom/mock/messages", headers=key(), json=data).json()["data"]["id"] == inbox_id
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            inbox = client.get("/wecom/inbox", params={"page_size": 100}).json()["data"]
            task = next(row for row in inbox if row["id"] == inbox_id)
            notices = client.get("/notifications", params={"page_size": 100}).json()["data"]
            notices = [row for row in notices if row["application_id"] == application["id"]]
            if task["status"] == "completed" and notices and notices[0]["status"] == "mock_sent":
                break
            time.sleep(0.2)
        else:
            raise AssertionError("Mock background pipeline did not complete")
        final = client.get("/applications/" + application["id"]).json()["data"]
        assert final["stage"] == "screening" and final["version"] == 2
        assert len(notices) == 1 and notices[0]["platform_message_id"].startswith("MOCK-NOTICE-")
        assert client.get("/wecom/status", headers={"X-Dev-User": "hr-a"}).status_code == 403
        assert client.get("/notifications", headers={"X-Dev-User": "hr-b"}).json()["data"] == []
        assert client.post("/webhooks/wecom", params={"msg_signature": "0" * 40, "timestamp": str(int(time.time())), "nonce": "synthetic"},
            content="<xml><Encrypt>invalid</Encrypt></xml>").status_code == 503
        print("PASS: S5 durable ACK + triple-message dedupe + async ingestion + Mock notification + RBAC + unconfigured callback")
        print("Retained synthetic application: " + code)


if __name__ == "__main__":
    run()
