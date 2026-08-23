import pytest
from datetime import datetime, timezone
from src.models.expectation import OutcomeState
from src.models.open_loop import OpenLoopStatus
from src.models.suppression import SuppressionStatus


@pytest.mark.asyncio
async def test_indirect_acceptance_does_not_resolve_unrelated_sole_expectation(async_client):
    # Regression: an arbitrary success report must not resolve the only open
    # expectation when there is no deictic tie and no lexical overlap. "will be
    # starting there Monday" shares no evidence with "whether I got the role".
    base = {
        "workspace_id": "ws_indirect_role",
        "session_id": "sess_indirect_role",
        "peer_id": "user",
        "timezone": "Europe/London",
    }
    created = await async_client.post("/v1/events/turn", json={
        **base,
        "honcho_message_id": "role-question",
        "text": "Ask me tomorrow whether I got the role.",
        "now": "2026-08-13T18:00:00Z",
    })
    assert created.json()["expectation_created"] is True

    resolved = await async_client.post("/v1/events/turn", json={
        **base,
        "honcho_message_id": "role-answer",
        "text": "Looks like I will be starting there Monday!",
        "now": "2026-08-14T07:50:00Z",
    })
    assert len(resolved.json()["mutated_expectation_ids"]) == 0

    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": base["workspace_id"],
        "session_id": base["session_id"],
        "now": "2026-08-14T10:00:00Z",
        "timezone": base["timezone"],
    })
    # Expectation is still carried (window elapsed, outcome unknown).
    assert any(
        item.get("type") == "expectation_due"
        for item in packet.json()["continuity_context"]["continuity"]
    )


@pytest.mark.asyncio
async def test_v4_runtime_scenarios(async_client):
    """
    Comprehensive integration test covering all 10 V4 Core runtime scenarios:
    1. "I'll test Sophie tonight."
    2. "Actually, I'm not doing that tonight."
    3. "James said he'll send it tomorrow."
    4. "James sent it."
    5. "Don't ask me about Ashley until next week."
    6. "Ask me tomorrow how the appointment went."
    7. "I think Ashley might be stressed because of work."
    8. "Actually I said Friday, not Saturday."
    9. Multi-expectation / multi-person turn.
    10. Ordinary social turn producing no state.
    """
    ws = "ws_v4_test"
    sess = "sess_v4_1"
    now_utc = "2026-08-11T14:00:00Z"
    tz_str = "Europe/London"

    # --- Scenario 1: "I'll test Sophie tonight." ---
    resp1 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1001,
        "peer_id": "mukesh", "text": "I'll test Sophie tonight.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp1.status_code == 202
    assert resp1.json()["expectation_created"] is True

    # --- Scenario 2: "Actually, I'm not doing that tonight." (Cancellation) ---
    resp2 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1002,
        "peer_id": "mukesh", "text": "Actually, I'm not doing that tonight.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp2.status_code == 202
    assert len(resp2.json()["mutated_expectation_ids"]) > 0

    # Verify expectation state is now CANCELLED
    debug_resp = await async_client.get("/v1/debug/decisions", params={"message_id": 1001})
    decisions = debug_resp.json()["decisions"]
    assert decisions[0]["outcome_state"] == "cancelled"

    # --- Scenario 3: "James said he'll send it tomorrow." (External Dependency) ---
    resp3 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1003,
        "peer_id": "mukesh", "text": "James said he'll send it tomorrow.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp3.status_code == 202
    assert resp3.json()["expectation_created"] is True

    # --- Scenario 4: "James sent it." (Fulfillment) ---
    resp4 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1004,
        "peer_id": "mukesh", "text": "James sent it.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp4.status_code == 202
    assert len(resp4.json()["mutated_expectation_ids"]) > 0

    # Verify dependency marked FULFILLED
    debug_resp3 = await async_client.get("/v1/debug/decisions", params={"message_id": 1003})
    assert debug_resp3.json()["decisions"][0]["outcome_state"] == "fulfilled"

    # --- Scenario 5: "Don't ask me about Ashley until next week." (Suppression) ---
    resp5 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1005,
        "peer_id": "mukesh", "text": "Don't ask me about Ashley until next week.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp5.status_code == 202
    
    # Check debug suppressions
    debug_supp = await async_client.get("/v1/debug/decisions", params={"message_id": 1005})
    suppressions = debug_supp.json()["suppressions"]
    assert len(suppressions) > 0
    assert "ashley" in suppressions[0]["topic_or_entity"].lower()

    # --- Scenario 6: "Ask me tomorrow how the appointment went." (Open Loop) ---
    resp6 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1006,
        "peer_id": "mukesh", "text": "Ask me tomorrow how the appointment went.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp6.status_code == 202
    
    debug_loop = await async_client.get("/v1/debug/decisions", params={"message_id": 1006})
    loops = debug_loop.json()["open_loops"]
    assert len(loops) > 0

    # --- Scenario 7: "I think Ashley might be stressed because of work." (Epistemic Attribution) ---
    resp7 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1007,
        "peer_id": "mukesh", "text": "I think Ashley might be stressed because of work.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp7.status_code == 202
    
    debug_ep = await async_client.get("/v1/debug/decisions", params={"message_id": 1007})
    epistemics = debug_ep.json()["epistemic_annotations"]
    assert len(epistemics) > 0
    assert epistemics[0]["provenance_type"] == "attributed_belief"
    assert epistemics[0]["target_peer_id"] == "ashley"

    # --- Scenario 8: "Actually I said Friday, not Saturday." (Correction) ---
    resp8 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1008,
        "peer_id": "mukesh", "text": "Actually I said Friday, not Saturday.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp8.status_code == 202

    # --- Scenario 9: Multi-expectation turn ---
    resp9 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1009,
        "peer_id": "mukesh", "text": "I'll send Morgan the report tonight and call James tomorrow.",
        "now": now_utc, "timezone": tz_str
    })
    assert resp9.status_code == 202
    assert resp9.json()["expectations_created_count"] == 2

    # --- Scenario 10: Ordinary social turn producing no state ---
    resp10 = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": sess, "honcho_message_id": 1010,
        "peer_id": "mukesh", "text": "lol that's awesome",
        "now": now_utc, "timezone": tz_str
    })
    assert resp10.status_code == 202
    assert resp10.json()["expectation_created"] is False
    assert resp10.json()["candidates_extracted"] == 0

    # --- Test Cortex Handshake & Route & Attention Packet Endpoints ---
    handshake_resp = await async_client.post("/v1/cortex/handshake", json={
        "workspace_id": ws, "session_id": sess,
        "now": "2026-08-11T21:00:00Z", "timezone": tz_str
    })
    assert handshake_resp.status_code == 200
    hs = handshake_resp.json()
    assert hs["daypart"] == "night"
    assert "avoid_surface" in hs

    route_resp = await async_client.post("/v1/cortex/route", json={"query": "What was I supposed to follow up on?"})
    assert route_resp.status_code == 200
    assert route_resp.json()["route"] == "SYNAPSE_STATE"


@pytest.mark.asyncio
async def test_ambiguous_cancellation_is_shielded_by_clarification(async_client):
    base = {
        "workspace_id": "ws_ambiguous",
        "session_id": "sess_ambiguous",
        "peer_id": "mukesh",
        "now": "2026-08-11T14:00:00Z",
        "timezone": "Europe/London",
    }
    for message_id, text in [
        (2001, "I'll test Sophie tonight."),
        (2002, "I will call James tomorrow."),
    ]:
        response = await async_client.post(
            "/v1/events/turn", json={**base, "honcho_message_id": message_id, "text": text}
        )
        assert response.json()["expectation_created"] is True

    cancellation = await async_client.post(
        "/v1/events/turn",
        json={
            **base,
            "honcho_message_id": 2003,
            "text": "Actually, I'm not doing that.",
        },
    )
    assert cancellation.json()["mutated_expectation_ids"] == []

    decisions = await async_client.get(
        "/v1/debug/decisions",
        params={"workspace_id": "ws_ambiguous", "session_id": "sess_ambiguous"},
    )
    payload = decisions.json()
    assert {item["outcome_state"] for item in payload["decisions"]} == {"unknown"}
    assert len(payload["clarifications"]) == 1
    assert payload["clarifications"][0]["clarification_type"] == "unclear_target"


@pytest.mark.asyncio
async def test_suppression_target_excludes_duration(async_client):
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_suppression",
            "session_id": "sess_suppression",
            "honcho_message_id": 2101,
            "peer_id": "mukesh",
            "text": "Don't ask me about Ashley until next week.",
            "now": "2026-08-11T14:00:00Z",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202
    decisions = await async_client.get(
        "/v1/debug/decisions", params={"message_id": 2101}
    )
    assert decisions.json()["suppressions"][0]["topic_or_entity"] == "ashley"

    reopened = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_suppression",
            "session_id": "sess_suppression",
            "honcho_message_id": 2102,
            "peer_id": "mukesh",
            "text": "Actually we can talk about Ashley now.",
            "now": "2026-08-11T15:00:00Z",
            "timezone": "Europe/London",
        },
    )
    assert reopened.status_code == 202
    original = await async_client.get(
        "/v1/debug/decisions", params={"message_id": 2101}
    )
    assert original.json()["suppressions"][0]["status"] == "reopened"
