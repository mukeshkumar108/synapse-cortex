import pytest


@pytest.mark.asyncio
async def test_handshake_consumes_authoritative_temporal_session(async_client):
    response = await async_client.post(
        "/v1/cortex/handshake",
        json={
            "workspace_id": "ws_chronology",
            "session_id": "chat_thread",
            "now": "2026-08-22T09:45:00Z",
            "timezone": "Europe/London",
            "last_interaction_time": "2026-08-22T09:30:00Z",
            "chronology": {
                "temporalSession": "new",
                "gapMinutes": 553,
                "userDay": "2026-08-22",
                "firstContactUserDay": True,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["orientation"] == "returning"
    assert payload["time_since_last_interaction_minutes"] == 553
    assert payload["chronology"]["firstContactUserDay"] is True


@pytest.mark.asyncio
async def test_handshake_does_not_recompute_legacy_120_minute_orientation(async_client):
    response = await async_client.post(
        "/v1/cortex/handshake",
        json={
            "workspace_id": "ws_chronology",
            "session_id": "chat_thread",
            "now": "2026-08-22T09:45:00Z",
            "timezone": "Europe/London",
            "last_interaction_time": "2026-08-22T09:30:00Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["orientation"] == "unknown"
