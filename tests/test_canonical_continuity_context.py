import pytest
from datetime import datetime, timezone

from src.services.attention_state_service import AttentionStateService


@pytest.mark.asyncio
async def test_due_plan_becomes_canonical_morning_continuity(async_client):
    base = {
        "workspace_id": "ws_continuity",
        "session_id": "sess_continuity",
        "peer_id": "user",
        "now": "2026-08-12T20:00:00Z",
        "timezone": "Europe/London",
    }
    created = await async_client.post(
        "/v1/events/turn",
        json={
            **base,
            "honcho_message_id": "walk-plan",
            "text": "I'm going to take a walk tomorrow morning.",
        },
    )
    assert created.json()["expectation_created"] is True

    response = await async_client.get(
        "/v1/cortex/attention-state",
        params={
            "workspace_id": base["workspace_id"],
            "session_id": base["session_id"],
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    state = response.json()
    assert state["window"]["daypart"] == "morning"
    assert state["eligible"]
    assert state["eligible"][0]["type"] == "expectation_due"
    assert "walk" in state["eligible"][0]["topic"].lower()
    assert len(state["eligible"]) <= 5


@pytest.mark.asyncio
async def test_empty_state_produces_no_forced_continuity(async_client):
    response = await async_client.get(
        "/v1/cortex/attention-state",
        params={
            "workspace_id": "empty",
            "session_id": "empty",
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    state = response.json()
    assert state["eligible"] == []
    assert state["open_loops"] == []
    assert state["recent_resolutions"] == []


@pytest.mark.asyncio
async def test_handshake_carries_same_canonical_context(async_client):
    response = await async_client.post(
        "/v1/cortex/handshake",
        json={
            "workspace_id": "empty",
            "session_id": "empty",
            "now": "2026-08-13T19:00:00Z",
            "timezone": "Europe/London",
        },
    )
    payload = response.json()
    assert payload["attention"]["window"]["daypart"] == "evening"
    assert payload["daypart"] == "evening"


def test_deadlines_are_prioritized_before_cap_and_keep_evidence_refs():
    packet = {
        "hard_deadlines": [{
            "title": "Submit tax return",
            "temporal_state": "deadline_approaching",
            "honcho_message_id": "deadline-source",
        }],
        "followups": [
            {
                "title": f"Follow-up {index}",
                "temporal_state": "window_elapsed",
                "reason": "expected_window_elapsed",
                "honcho_message_id": f"followup-{index}",
            }
            for index in range(5)
        ],
        "active_expectations": [],
    }
    eligible = AttentionStateService._compile_eligible(packet)
    assert len(eligible) == 4
    assert eligible[0]["topic"] == "Submit tax return"
    assert eligible[0]["evidence_refs"] == ["deadline-source"]


@pytest.mark.asyncio
async def test_linked_open_loop_uses_expectation_topic_not_internal_summary(async_client):
    await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_loop",
            "session_id": "sess_loop",
            "honcho_message_id": "appointment-loop",
            "peer_id": "user",
            "text": "Ask me tomorrow how the appointment went.",
            "now": "2026-08-12T20:00:00Z",
            "timezone": "Europe/London",
        },
    )
    response = await async_client.get(
        "/v1/cortex/attention-state",
        params={
            "workspace_id": "ws_loop",
            "session_id": "sess_loop",
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    thread = response.json()["open_loops"][0]
    assert "appointment" in thread["title"].lower()
    assert not thread["title"].startswith("Invited follow-up")
    assert thread["explicitly_invited"] is True


@pytest.mark.asyncio
async def test_owned_continuity_surfaces_across_chat_sessions(async_client):
    created = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_cross_chat",
            "session_id": "chat_one",
            "honcho_message_id": "walk-plan-cross-chat",
            "peer_id": "user_a",
            "text": "I'm going to take a walk tomorrow morning.",
            "now": "2026-08-12T20:00:00Z",
            "timezone": "Europe/London",
        },
    )
    assert created.json()["expectation_created"] is True

    response = await async_client.get(
        "/v1/cortex/attention-state",
        params={
            "workspace_id": "ws_cross_chat",
            "session_id": "chat_two",
            "peer_id": "user_a",
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    continuity = response.json()["eligible"]
    assert continuity
    assert "walk" in continuity[0]["topic"].lower()


@pytest.mark.asyncio
async def test_owned_continuity_never_leaks_to_another_peer(async_client):
    await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_isolation",
            "session_id": "chat_one",
            "honcho_message_id": "private-plan",
            "peer_id": "user_a",
            "text": "I'm going to take a walk tomorrow morning.",
            "now": "2026-08-12T20:00:00Z",
            "timezone": "Europe/London",
        },
    )
    response = await async_client.get(
        "/v1/cortex/attention-state",
        params={
            "workspace_id": "ws_isolation",
            "session_id": "chat_two",
            "peer_id": "user_b",
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    context = response.json()
    assert context["eligible"] == []
    assert context["open_loops"] == []


@pytest.mark.asyncio
async def test_handshake_uses_owned_cross_chat_continuity(async_client):
    await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws_handshake_cross_chat",
            "session_id": "chat_one",
            "honcho_message_id": "appointment-cross-chat",
            "peer_id": "user_a",
            "text": "Ask me tomorrow how the appointment went.",
            "now": "2026-08-12T20:00:00Z",
            "timezone": "Europe/London",
        },
    )
    response = await async_client.post(
        "/v1/cortex/handshake",
        json={
            "workspace_id": "ws_handshake_cross_chat",
            "session_id": "chat_two",
            "peer_id": "user_a",
            "now": "2026-08-13T09:00:00Z",
            "timezone": "Europe/London",
        },
    )
    context = response.json()["attention"]
    assert context["open_threads"]
    assert "appointment" in context["open_threads"][0]["title"].lower()
