from datetime import datetime, timedelta, timezone

import pytest

from src.routers.v1_events import _naive_utc


def test_attention_timestamps_are_normalized_to_naive_utc_for_postgres():
    value = datetime(2026, 8, 20, 21, 0, tzinfo=timezone(timedelta(hours=1)))
    normalized = _naive_utc(value)
    assert normalized == datetime(2026, 8, 20, 20, 0)
    assert normalized.tzinfo is None


@pytest.mark.asyncio
async def test_attention_candidate_is_idempotent_and_reaches_continuity(async_client):
    now = datetime.now(timezone.utc)
    payload = {
        "workspace_id": "ws_attention",
        "session_id": "session_attention",
        "source_message_id": "user-message-1",
        "source_assistant_message_id": "assistant-message-1",
        "candidates": [
            {
                "key": "course_reason",
                "kind": "pending_question",
                "content": "Understand why the course matters beyond career advancement.",
                "salience": 0.8,
                "confidence": 0.9,
                "not_before": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(days=7)).isoformat(),
            }
        ],
    }
    first = await async_client.post("/v1/events/attention", json=payload)
    duplicate = await async_client.post("/v1/events/attention", json=payload)
    assert first.status_code == 202
    assert first.json()["candidates_created"] == 1
    assert duplicate.json()["candidates_created"] == 0

    packet = await async_client.get(
        "/v1/cortex/attention-packet",
        params={
            "workspace_id": "ws_attention",
            "session_id": "session_attention",
            "now": now.isoformat(),
            "timezone": "Europe/London",
        },
    )
    attention = packet.json()["continuity_context"]["sophie_attention"]
    assert attention[0]["type"] == "pending_question"
    assert "course matters" in attention[0]["content"]
    assert attention[0]["evidence_refs"] == [
        "user-message-1",
        "assistant-message-1",
    ]


@pytest.mark.asyncio
async def test_future_attention_candidate_is_not_yet_visible(async_client):
    now = datetime.now(timezone.utc)
    await async_client.post(
        "/v1/events/attention",
        json={
            "workspace_id": "ws_future_attention",
            "session_id": "session_future_attention",
            "source_message_id": "user-message-2",
            "candidates": [
                {
                    "key": "later_callback",
                    "kind": "callback",
                    "content": "Return to the unfinished joke later.",
                    "salience": 0.5,
                    "confidence": 0.8,
                    "not_before": (now + timedelta(hours=2)).isoformat(),
                    "expires_at": (now + timedelta(days=2)).isoformat(),
                }
            ],
        },
    )
    packet = await async_client.get(
        "/v1/cortex/attention-packet",
        params={
            "workspace_id": "ws_future_attention",
            "session_id": "session_future_attention",
            "now": now.isoformat(),
        },
    )
    assert packet.json()["continuity_context"]["sophie_attention"] == []
