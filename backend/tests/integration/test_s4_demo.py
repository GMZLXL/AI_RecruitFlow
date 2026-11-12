from sqlalchemy import func, select

from app.db import Application, Offer, SessionLocal
from scripts.demo.seed import seed_demo
from tests.helpers import create


def test_demo_seed_is_repeatable_and_does_not_overwrite_existing(client):
    existing = create(client, "KEEP_REAL_LOCAL_TEST").json()["data"]
    assert seed_demo() == (24, 0)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Offer.id))) == 6
        before = db.scalar(select(func.count(Application.id)))
    assert seed_demo() == (0, 24)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Application.id))) == before
        obj = db.get(Application, existing["id"])
        assert obj is not None and obj.version == existing["version"] and obj.stage == "applied"
        first = db.scalar(select(Application).where(Application.application_code == "DEMO_S4_01"))
        other = db.scalar(select(Application).where(Application.application_code == "DEMO_S4_09"))
        assert first is not None and other is not None
        assert first.candidate_id == other.candidate_id and first.position_id != other.position_id
    metrics = client.get("/api/v1/dashboard/overview").json()["data"]
    assert metrics["offers_sent"] == 6 and metrics["offers_accepted"] == 4 and metrics["offers_declined"] == 1
    assert metrics["offer_acceptance_rate"] == 0.8 and metrics["hired_applications"] == 3
