import pytest


@pytest.mark.asyncio
async def test_multi_expectation_single_message_id(async_client):
    """
    Verifies that a turn containing multiple distinct action clauses:
    "I'll send Morgan the report tonight and call James tomorrow."
    emits 2 candidates under the same honcho_message_id, persisted with distinct candidate_keys.
    """
    turn_payload = {
        "workspace_id": "ws_multi_test",
        "session_id": "sess_multi_1",
        "honcho_message_id": 501,
        "peer_id": "mukesh",
        "text": "I'll send Morgan the report tonight and call James tomorrow.",
        "now": "2026-08-11T14:00:00Z",
        "timezone": "Europe/London",
    }

    resp = await async_client.post("/v1/events/turn", json=turn_payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["expectation_created"] is True

    # Inspect debug decisions
    debug_resp = await async_client.get("/v1/debug/decisions", params={"message_id": 501})
    assert debug_resp.status_code == 200
    decisions = debug_resp.json()["decisions"]
    
    assert len(decisions) == 2, f"Expected 2 expectations, got {len(decisions)}"
    keys = {d["candidate_key"] for d in decisions}
    assert len(keys) == 2, "Candidate keys must be distinct!"

    # Test Duplicate Re-delivery
    dup_resp = await async_client.post("/v1/events/turn", json=turn_payload)
    assert dup_resp.status_code == 202
    assert dup_resp.json()["expectation_created"] is False

    # Debug count remains 2
    debug_resp2 = await async_client.get("/v1/debug/decisions", params={"message_id": 501})
    assert len(debug_resp2.json()["decisions"]) == 2
