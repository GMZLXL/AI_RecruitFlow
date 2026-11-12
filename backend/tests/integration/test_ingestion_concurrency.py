import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.db import IngestionJob, SessionLocal
from app.integrations.parsers.factory import get_parser
from app.integrations.parsers.mock import MockParser
from app.main import app
from tests.helpers import counts


def test_same_event_concurrent_requests_create_one_application(client):
    class SlowParser:
        async def parse(self, text, reference_time, timezone):
            await asyncio.sleep(0.05)
            return await MockParser().parse(text, reference_time, timezone)

    app.dependency_overrides[get_parser] = lambda: SlowParser()
    body = {"text": "新增虚构并发甲应聘工程师岗", "external_event_id": "concurrent-ingestion"}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post("/api/v1/ingestions", json=body), range(2)))
    finally:
        app.dependency_overrides.pop(get_parser, None)
    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["data"]["status"] for response in responses) in [
        ["applied", "parsing"],
        ["applied", "duplicate"],
    ]
    assert counts()[1] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count(IngestionJob.id))) == 1
