from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import advance, counts, create, headers


def test_two_concurrent_writes_only_one_wins(client):
    application = create(client).json()["data"]
    before = counts()

    def update(_):
        return client.patch(
            f"/api/v1/applications/{application['id']}",
            json={"stage": "screening", "change_reason": "并发修改测试"},
            headers=headers(version=1),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(update, range(2)))
    assert sorted(statuses) == [200, 409]
    after = counts()
    assert after[:2] == before[:2]
    assert after[2:] == tuple(value + 1 for value in before[2:])


def test_unreferenced_candidate_position_and_interview_soft_deletes(client):
    candidate = client.post(
        "/api/v1/candidates", json={"display_name": "虚构可删除"}, headers=headers()
    ).json()["data"]
    position = client.post(
        "/api/v1/positions", json={"title": "虚构可删除", "department": "engineering"}, headers=headers()
    ).json()["data"]
    for route, obj in (("candidates", candidate), ("positions", position)):
        assert (
            client.request(
                "DELETE",
                f"/api/v1/{route}/{obj['id']}",
                json={"change_reason": "清理虚构资料"},
                headers=headers(version=1),
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/{route}/{obj['id']}").status_code == 404
    application = advance(client, create(client).json()["data"])
    appointment = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    response = client.post(
        f"/api/v1/applications/{application['id']}/interviews",
        json={"round": 1, "scheduled_at": appointment, "interviewer": "虚构官"},
        headers=headers(version=application["version"]),
    )
    assert response.status_code == 201
    interview = response.json()["data"]
    assert (
        client.request(
            "DELETE",
            f"/api/v1/interviews/{interview['id']}",
            json={"change_reason": "清理虚构面试"},
            headers=headers(version=1),
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/interviews/{interview['id']}").status_code == 404


@pytest.mark.parametrize("scheduled_at", ["2026-01-01T00:00:00Z", "2026-11-20T14:00:00"])
def test_past_and_naive_interview_times_are_rejected(client, scheduled_at):
    application = advance(client, create(client).json()["data"])
    result = client.post(
        f"/api/v1/applications/{application['id']}/interviews",
        json={"round": 1, "scheduled_at": scheduled_at, "interviewer": "虚构官"},
        headers=headers(version=application["version"]),
    )
    assert result.status_code in {400, 422}
