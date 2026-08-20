import asyncio
import pytest


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingestion(async_client):
    """
    Simulates simultaneous delivery of the exact same turn event across 5 concurrent tasks.
    Verifies zero uncaught IntegrityErrors and exactly 1 set of expectation rows created.
    """
    payload = {
        "workspace_id": "ws_concurrent_test",
        "session_id": "sess_conc_1",
        "honcho_message_id": 707,
        "peer_id": "mukesh",
        "text": "I'm going to test the Sophie initiative changes tonight.",
        "now": "2026-08-11T14:00:00Z",
        "timezone": "Europe/London",
    }

    # Fire 5 concurrent requests
    tasks = [async_client.post("/v1/events/turn", json=payload) for _ in range(5)]
    responses = await asyncio.gather(*tasks, return_exceptions=False)

    for r in responses:
        assert r.status_code == 202

    # Query debug endpoint
    debug_resp = await async_client.get("/v1/debug/decisions", params={"message_id": 707})
    assert debug_resp.status_code == 200
    decisions = debug_resp.json()["decisions"]
    assert len(decisions) == 1
