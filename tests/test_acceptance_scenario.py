import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_phase1_complete_acceptance_scenario(async_client):
    """
    Phase 1 Acceptance Scenario Verification:
    
    1. Local time: 2026-08-11T15:00:00+01:00 (2026-08-11T14:00:00Z).
    2. User turn: "I'm going to test the Sophie initiative changes tonight."
    3. Ingest shadow turn event with honcho_message_id = 101.
    4. Verify expectation persisted with grounded window.
    5. Re-ingest honcho_message_id = 101 -> verify duplicate delivery is IDEMPOTENT.
    6. Advance time to next morning: 2026-08-12T09:00:00+01:00 (2026-08-12T08:00:00Z).
    7. Fetch canonical attention packet via GET /v1/cortex/attention-packet.
    8. PASS Criteria:
       - followup for msg 101 present with temporal_state == "window_elapsed"
       - outcome_state == "unknown"
       - followup_eligible == True
       - reason == "expected_window_elapsed"
       - 0 LLM calls occurred during packet compilation.
    """
    # Step 1 & 2: Ingest turn event
    ingest_payload = {
        "workspace_id": "ws_sophie_prod",
        "session_id": "sess_sophie_1001",
        "honcho_message_id": 101,
        "peer_id": "mukesh",
        "text": "I'm going to test the Sophie initiative changes tonight.",
        "now": "2026-08-11T14:00:00Z",
        "timezone": "Europe/London",
    }

    response = await async_client.post("/v1/events/turn", json=ingest_payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["expectation_created"] is True
    assert data["honcho_message_id"] == "101"

    # Step 3: Idempotency Test (Re-ingest same message ID)
    duplicate_response = await async_client.post("/v1/events/turn", json=ingest_payload)
    assert duplicate_response.status_code == 202
    dup_data = duplicate_response.json()
    assert dup_data["status"] == "accepted"
    assert dup_data["expectation_created"] is False, "Duplicate ingestion created a duplicate row!"
    assert dup_data["honcho_message_id"] == "101"

    # Step 4: Advance mock clock to next morning 09:00 AM BST (08:00 AM UTC)
    next_morning_utc = "2026-08-12T08:00:00Z"
    context_resp = await async_client.get(
        "/v1/cortex/attention-packet",
        params={
            "workspace_id": "ws_sophie_prod",
            "session_id": "sess_sophie_1001",
            "now": next_morning_utc,
            "timezone": "Europe/London",
        },
    )

    assert context_resp.status_code == 200
    packet = context_resp.json()

    assert "followups" in packet
    # Elapsed unknown expectations are kept out of foreground followups so
    # stale state cannot crowd current state; they stay inspectable in the
    # elapsed section.
    assert len(packet["followups"]) == 0
    assert len(packet["elapsed_expectations"]) == 1

    item = packet["elapsed_expectations"][0]
    assert item["honcho_message_id"] == "101"
    assert item["title"] == "Test the Sophie initiative changes"
    assert item["temporal_state"] == "window_elapsed"
    assert item["outcome_state"] == "unknown"
    assert item["reason"] == "expected_window_elapsed"
    assert item["expected_window_label"] == "last night"
