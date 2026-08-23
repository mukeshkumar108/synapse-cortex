import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Test health check endpoint returns 200 OK."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "synapse-cortex"


@pytest.mark.asyncio
async def test_phase1_ingest_and_context_endpoints(async_client):
    """Test Phase 1 event ingestion and the canonical context packet endpoint."""
    event_payload = {
        "workspace_id": "ws_123",
        "session_id": "sess_456",
        "honcho_message_id": 999,
        "peer_id": "mukesh",
        "text": "I'll test Sophie tonight.",
        "now": "2026-08-11T15:00:00Z",
        "timezone": "Europe/London",
    }
    resp = await async_client.post("/v1/events/turn", json=event_payload)
    assert resp.status_code == 202
    assert resp.json()["expectation_created"] is True

    # Canonical context path: /v1/cortex/attention-packet owns continuity.
    context_resp = await async_client.get(
        "/v1/cortex/attention-packet",
        params={
            "workspace_id": "ws_123",
            "session_id": "sess_456",
            "now": "2026-08-12T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    assert context_resp.status_code == 200
    packet = context_resp.json()
    messages = [f["honcho_message_id"] for f in packet["followups"]]
    assert "999" in messages
    assert packet["followups"][messages.index("999")]["temporal_state"] == "window_elapsed"
