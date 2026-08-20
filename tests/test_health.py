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
    """Test Phase 1 event ingestion and context packet endpoints."""
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

    context_resp = await async_client.get(
        "/v1/context/followup-packet",
        params={
            "workspace_id": "ws_123",
            "session_id": "sess_456",
            "now": "2026-08-12T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    assert context_resp.status_code == 200
    followups = context_resp.json()["followups"]
    assert len(followups) == 1
    assert followups[0]["honcho_message_id"] == "999"
    assert followups[0]["temporal_state"] == "window_elapsed"
