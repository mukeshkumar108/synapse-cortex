from datetime import datetime, timedelta, timezone

import pytest


def task_payload(owner: str, object_id: str, title: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "workspace_id": "ws-inspector",
        "session_id": f"session-{owner}",
        "peer_id": owner,
        "owner_peer_id": owner,
        "now": now.isoformat(),
        "timezone": "Europe/London",
        "source": {
            "system": "app_task",
            "object_id": object_id,
            "version": 1,
            "kind": "task",
        },
        "action": "created",
        "title": title,
        "due_at": (now + timedelta(days=1)).isoformat(),
        "reminder_windows": [],
    }


@pytest.mark.asyncio
async def test_owner_state_is_strictly_owner_scoped(async_client):
    first = await async_client.post(
        "/v1/events/object",
        json=task_payload("user_a", "task-a", "User A private task"),
    )
    second = await async_client.post(
        "/v1/events/object",
        json=task_payload("user_b", "task-b", "User B private task"),
    )
    assert first.status_code == 202
    assert second.status_code == 202

    response = await async_client.get(
        "/v1/debug/owner-state",
        params={
            "workspace_id": "ws-inspector",
            "owner_peer_id": "user_a",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["expectations"] == 1
    assert [item["title"] for item in body["expectations"]] == [
        "User A private task"
    ]
    assert body["expectations"][0]["source_object_id"] == "task-a"
    assert "User B private task" not in response.text


@pytest.mark.asyncio
async def test_owner_state_rejects_blank_owner(async_client):
    response = await async_client.get(
        "/v1/debug/owner-state",
        params={"workspace_id": "ws-inspector", "owner_peer_id": ""},
    )
    assert response.status_code == 422
