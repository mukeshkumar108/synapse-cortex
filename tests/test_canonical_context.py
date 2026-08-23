from datetime import datetime, timezone

import pytest

from src.services.daypart import resolve_daypart


@pytest.mark.asyncio
async def test_canonical_daypart_single_source():
    cases = [
        (datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc), "Europe/London", "morning"),
        (datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc), "Europe/London", "afternoon"),
        (datetime(2026, 8, 22, 20, 0, tzinfo=timezone.utc), "Europe/London", "evening"),
        (datetime(2026, 8, 22, 1, 0, tzinfo=timezone.utc), "Europe/London", "night"),
    ]
    for now, tz, expected in cases:
        assert resolve_daypart(now, tz) == expected


@pytest.mark.asyncio
async def test_handshake_and_packet_agree_on_daypart(async_client):
    now = "2026-08-22T09:00:00Z"
    spot = {
        "workspace_id": "ws_daypart",
        "session_id": "sess_daypart",
    }
    handshake = await async_client.post("/v1/cortex/handshake", json={
        **spot, "now": now, "timezone": "Europe/London",
    })
    hs = handshake.json()
    packet = await async_client.get("/v1/cortex/attention-packet", params={
        **spot, "now": now, "timezone": "Europe/London",
    })
    ctx = packet.json()["continuity_context"]
    assert hs["daypart"] == ctx["now"]["daypart"] == "morning"


@pytest.mark.asyncio
async def test_continuity_context_is_bounded_with_large_backend_state(async_client):
    ws, sess = "ws_bounded", "sess_bounded"
    for index in range(12):
        resp = await async_client.post("/v1/events/turn", json={
            "workspace_id": ws, "session_id": sess,
            "honcho_message_id": f"m{index}",
            "peer_id": "user",
            "text": f"I'll finish task number {index} tomorrow at 9am.",
            "now": "2026-08-22T09:00:00Z",
            "timezone": "Europe/London",
        })
        assert resp.status_code == 202

    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": ws, "session_id": sess,
        "now": "2026-08-23T09:00:00Z", "timezone": "Europe/London",
    })
    body = packet.json()
    continuity = body["continuity_context"]["continuity"]
    assert len(continuity) <= 5
    assert len(body["followups"]) <= 3
    assert all(item["type"] in {"deadline", "expectation_due", "recurring_intention", "open_loop"}
               for item in continuity)
    assert all(item["topic"] and item["status"] for item in continuity)