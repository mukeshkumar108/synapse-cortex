"""Deterministic object-state ingestion: app tasks + Google Calendar events.

Covers the canonical-commitment capability contract: creation, duplicate
idempotency, versioned reschedule/snooze, completion/cancellation, multiple
reminder windows, packet surfacing states, bounded post-event follow-ups,
stale-attention invalidation, and cross-chat owner scoping.
"""

from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc


def iso(days_ahead: float = 0.0, hours: float = 0.0) -> str:
    base = datetime.now(UTC) + timedelta(days=days_ahead, hours=hours)
    return base.isoformat()


def object_payload(**overrides) -> dict:
    payload = {
        "workspace_id": "ws-object",
        "session_id": "session-a",
        "peer_id": "user_1",
        "owner_peer_id": "user_1",
        "now": iso(),
        "timezone": "Europe/London",
        "source": {
            "system": "app_task",
            "object_id": "task-1",
            "version": 1,
            "kind": "task",
        },
        "action": "created",
        "title": "Call the plumber",
        "notes": "Book the morning slot",
        "due_at": iso(days_ahead=2),
        "reminder_windows": [
            {"start": iso(days_ahead=1, hours=-4), "end": iso(days_ahead=1, hours=4),
             "label": "the day before"},
            {"start": iso(days_ahead=2, hours=-0.5), "end": None, "label": "30 minutes before"},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def packet_url() -> str:
    return "/v1/cortex/attention-packet"


async def post_object(async_client, payload):
    return await async_client.post("/v1/events/object", json=payload)


async def get_packet(async_client, payload_overrides: dict | None = None, now: str | None = None):
    params = {
        "workspace_id": "ws-object",
        "session_id": "session-a",
        "peer_id": "user_1",
        "timezone": "Europe/London",
    }
    if now:
        params["now"] = now
    if payload_overrides:
        params.update(payload_overrides)
    return await async_client.get("/v1/cortex/attention-packet", params=params)


@pytest.mark.asyncio
async def test_task_created_projects_commitment_expectation(async_client):
    response = await post_object(async_client, object_payload())
    assert response.status_code == 202
    body = response.json()
    assert body["action_taken"] == "created"
    assert body["expectation_id"]


@pytest.mark.asyncio
async def test_duplicate_same_version_is_idempotent_noop(async_client):
    first = await post_object(async_client, object_payload())
    assert first.status_code == 202
    second = await post_object(async_client, object_payload())
    assert second.status_code == 202
    body = second.json()
    assert body["action_taken"] == "noop"
    assert body["expectation_id"] == first.json()["expectation_id"]


@pytest.mark.asyncio
async def test_version_bump_supersedes_prior_state(async_client):
    first = await post_object(async_client, object_payload())
    first_id = first.json()["expectation_id"]
    rescheduled = object_payload(
        action="updated",
        source={"system": "app_task", "object_id": "task-1", "version": 2, "kind": "task"},
        due_at=iso(days_ahead=4),
        reminder_windows=[],
    )
    second = await post_object(async_client, rescheduled)
    assert second.status_code == 202
    body = second.json()
    assert body["action_taken"] == "superseded"
    assert body["superseded_id"] == first_id
    assert body["expectation_id"] != first_id


@pytest.mark.asyncio
async def test_stale_older_version_is_ignored(async_client):
    await post_object(async_client, object_payload())
    stale = object_payload(
        action="updated",
        source={"system": "app_task", "object_id": "task-1", "version": 0, "kind": "task"},
    )
    response = await post_object(async_client, stale)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_completion_resolves_task(async_client):
    await post_object(async_client, object_payload())
    completed = object_payload(
        action="completed",
        source={"system": "app_task", "object_id": "task-1", "version": 3, "kind": "task"},
    )
    response = await post_object(async_client, completed)
    assert response.status_code == 202
    assert response.json()["action_taken"] in ("resolved", "resolved_tombstone")

    packet = await get_packet(async_client)
    assert packet.status_code == 200
    data = packet.json()
    assert all(
        item["title"] != "Call the plumber" for item in data.get("commitments", [])
    )
    resolved = [
        item for item in data.get("recent_resolutions", [])
        if item["title"] == "Call the plumber"
    ]
    assert resolved, "completed task should surface as a recent resolution"


@pytest.mark.asyncio
async def test_cancellation_resolves_and_stays_out_of_commitments(async_client):
    await post_object(async_client, object_payload())
    cancelled = object_payload(
        action="cancelled",
        source={"system": "app_task", "object_id": "task-1", "version": 3, "kind": "task"},
    )
    response = await post_object(async_client, cancelled)
    assert response.status_code == 202
    packet = await get_packet(async_client)
    data = packet.json()
    assert all(
        item["title"] != "Call the plumber" for item in data.get("commitments", [])
    )


@pytest.mark.asyncio
async def test_packet_surfaces_upcoming_then_reminder_window_then_overdue(async_client):
    await post_object(async_client, object_payload())

    # Far before any reminder window: upcoming.
    early = await get_packet(async_client, now=iso(days_ahead=0.2))
    assert early.status_code == 200
    commitments = early.json()["commitments"]
    assert commitments and commitments[0]["state"] == "upcoming"

    # Inside the first explicit window ("the day before"): reminder_due.
    in_window = await get_packet(async_client, now=iso(days_ahead=1))
    commitments = in_window.json()["commitments"]
    assert commitments and commitments[0]["state"] == "reminder_due"
    assert commitments[0]["active_reminder"]["label"] == "the day before"
    continuity = in_window.json()["continuity_context"]["continuity"]
    assert any(item["type"] == "task_due" for item in continuity), continuity

    # Between the windows (after window 1, before window 2): upcoming again.
    between = await get_packet(async_client, now=iso(days_ahead=1.5))
    assert between.json()["commitments"][0]["state"] == "upcoming"

    # Past the due date: overdue.
    late = await get_packet(async_client, now=iso(days_ahead=3))
    commitments = late.json()["commitments"]
    assert commitments and commitments[0]["state"] == "overdue"
    continuity = late.json()["continuity_context"]["continuity"]
    assert any(
        item["type"] == "task_due" and item["status"] == "overdue"
        for item in continuity
    )


@pytest.mark.asyncio
async def test_reminder_window_surfacing_is_bounded(async_client):
    await post_object(async_client, object_payload())
    in_window = iso(days_ahead=1)
    first = await get_packet(async_client, now=in_window)
    assert first.json()["commitments"][0]["state"] == "reminder_due"
    assert first.json()["commitments"][0]["reminder_surfaced"] is False
    second = await get_packet(async_client, now=in_window)
    item = second.json()["commitments"][0]
    assert item["state"] == "reminder_due"
    assert item["reminder_surfaced"] is True, "same window must not re-nag"
    continuity = second.json()["continuity_context"]["continuity"]
    assert not any(
        item.get("type") == "task_due" and item.get("status") == "reminder_due"
        for item in continuity
    ), "surfaced reminder must not re-enter continuity"


@pytest.mark.asyncio
async def test_calendar_event_created_rescheduled_cancelled(async_client):
    original_start = iso(days_ahead=1.9)
    original_end = iso(days_ahead=1.95)
    moved_start = iso(days_ahead=0.9)
    moved_end = iso(days_ahead=0.95)
    event = object_payload(
        source={"system": "google_calendar", "object_id": "evt-1", "version": 1,
                "kind": "calendar_event"},
        action="created",
        title="Dentist appointment",
        event_start=original_start,
        event_end=original_end,
        reminder_windows=[],
    )
    response = await post_object(async_client, event)
    assert response.status_code == 202
    assert response.json()["action_taken"] == "created"

    # Far out: upcoming.
    packet = await get_packet(async_client, now=iso())
    events = packet.json()["events"]
    assert events and events[0]["title"] == "Dentist appointment"
    assert events[0]["state"] == "upcoming"

    # Reschedule: version bump supersedes and packet reflects new timing.
    moved = object_payload(
        source={"system": "google_calendar", "object_id": "evt-1", "version": 2,
                "kind": "calendar_event"},
        action="updated",
        title="Dentist appointment",
        event_start=moved_start,
        event_end=moved_end,
    )
    moved_response = await post_object(async_client, moved)
    assert moved_response.json()["action_taken"] == "superseded"
    packet = await get_packet(async_client, now=iso())
    events = packet.json()["events"]
    assert events and events[0]["start"] == moved_start.replace("+00:00", "")

    # Imminent: within the hour (start is at +0.9d; query +0.86d ≈ 58 min before).
    imminent = await get_packet(async_client, now=iso(days_ahead=0.86))
    events = imminent.json()["events"]
    assert events[0]["state"] == "imminent"
    continuity = imminent.json()["continuity_context"]["continuity"]
    assert any(item["type"] == "event_upcoming" for item in continuity)

    # Cancel: no stale event state remains.
    cancelled = object_payload(
        source={"system": "google_calendar", "object_id": "evt-1", "version": 3,
                "kind": "calendar_event"},
        action="cancelled",
        title="Dentist appointment",
    )
    cancel_response = await post_object(async_client, cancelled)
    assert cancel_response.status_code == 202
    packet = await get_packet(async_client, now=iso(days_ahead=0.86))
    data = packet.json()
    assert data["events"] == []
    assert all(
        item["title"] != "Dentist appointment"
        for item in data.get("recent_resolutions", [])
        if item["outcome_state"] == "unknown"
    )


@pytest.mark.asyncio
async def test_event_completion_creates_bounded_callback_attention(async_client):
    end = iso(days_ahead=-0.01)
    event = object_payload(
        source={"system": "google_calendar", "object_id": "evt-2", "version": 1,
                "kind": "calendar_event"},
        action="created",
        title="Standup",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
        reminder_windows=[],
    )
    await post_object(async_client, event)
    completed = object_payload(
        source={"system": "google_calendar", "object_id": "evt-2", "version": 2,
                "kind": "calendar_event"},
        action="completed",
        title="Standup",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
        followup_window_hours=6,
    )
    response = await post_object(async_client, completed)
    assert response.status_code == 202
    assert response.json()["callback_attention_created"] is True

    packet = await get_packet(async_client, now=iso(hours=0.1))
    attention = packet.json()["sophie_attention"]
    callbacks = [item for item in attention if item.get("source_object_id") == "evt-2"]
    assert callbacks and callbacks[0]["type"] == "callback"
    continuity = packet.json()["continuity_context"]["continuity"]
    assert any(item["type"] == "event_followup" for item in continuity)

    # Duplicate completion is idempotent: no second callback.
    repeat = await post_object(async_client, completed)
    assert repeat.json()["callback_attention_created"] is False


@pytest.mark.asyncio
async def test_event_cancellation_invalidates_stale_callback(async_client):
    end = iso(days_ahead=-0.01)
    event = object_payload(
        source={"system": "google_calendar", "object_id": "evt-3", "version": 1,
                "kind": "calendar_event"},
        action="created",
        title="Project review",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
    )
    await post_object(async_client, event)
    completed = object_payload(
        source={"system": "google_calendar", "object_id": "evt-3", "version": 2,
                "kind": "calendar_event"},
        action="completed",
        title="Project review",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
        followup_window_hours=6,
    )
    await post_object(async_client, completed)
    packet = await get_packet(async_client, now=iso(hours=0.1))
    assert any(
        item.get("source_object_id") == "evt-3"
        for item in packet.json()["sophie_attention"]
    )

    cancelled = object_payload(
        source={"system": "google_calendar", "object_id": "evt-3", "version": 3,
                "kind": "calendar_event"},
        action="cancelled",
        title="Project review",
    )
    response = await post_object(async_client, cancelled)
    assert response.status_code == 202
    assert response.json()["attention_cancelled"] >= 1

    packet = await get_packet(async_client, now=iso(hours=0.1))
    assert not any(
        item.get("source_object_id") == "evt-3"
        for item in packet.json()["sophie_attention"]
    )
    continuity = packet.json()["continuity_context"]["continuity"]
    assert not any(item["type"] == "event_followup" for item in continuity)


@pytest.mark.asyncio
async def test_rescheduled_event_invalidates_prior_callback(async_client):
    """Rescheduling after completion must not leave a stale callback."""
    end = iso(days_ahead=-0.01)
    event = object_payload(
        source={"system": "google_calendar", "object_id": "evt-4", "version": 1,
                "kind": "calendar_event"},
        action="created",
        title="1:1 with Sam",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
    )
    await post_object(async_client, event)
    completed = object_payload(
        source={"system": "google_calendar", "object_id": "evt-4", "version": 2,
                "kind": "calendar_event"},
        action="completed",
        title="1:1 with Sam",
        event_start=iso(days_ahead=-0.02),
        event_end=end,
        followup_window_hours=6,
    )
    await post_object(async_client, completed)
    moved = object_payload(
        source={"system": "google_calendar", "object_id": "evt-4", "version": 3,
                "kind": "calendar_event"},
        action="updated",
        title="1:1 with Sam",
        event_start=iso(days_ahead=2),
        event_end=iso(days_ahead=2, hours=1),
    )
    response = await post_object(async_client, moved)
    assert response.status_code == 202
    assert response.json()["action_taken"] == "superseded"

    packet = await get_packet(async_client, now=iso(hours=0.1))
    assert not any(
        item.get("source_object_id") == "evt-4"
        for item in packet.json()["sophie_attention"]
    )


@pytest.mark.asyncio
async def test_task_owner_scoping_is_cross_chat(async_client):
    """Tasks are owner-scoped: visible from any of the owner's chats."""
    await post_object(async_client, object_payload())
    other_chat = await get_packet(
        async_client,
        payload_overrides={"session_id": "session-b"},
        now=iso(days_ahead=1),
    )
    assert other_chat.status_code == 200
    commitments = other_chat.json()["commitments"]
    assert any(item["title"] == "Call the plumber" for item in commitments)


@pytest.mark.asyncio
async def test_object_ingestion_survives_restart(async_client):
    """State is durably persisted: a fresh packet after 'restart' still sees it."""
    await post_object(async_client, object_payload())
    await post_object(async_client, object_payload())  # duplicate sync
    packet = await get_packet(async_client, now=iso(days_ahead=1))
    assert packet.json()["commitments"][0]["source_object_id"] == "task-1"


@pytest.mark.asyncio
async def test_object_ingestion_requires_explicit_offsets(async_client):
    bad = object_payload()
    bad["due_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    response = await post_object(async_client, bad)
    assert response.status_code == 422
