"""CurrentScene truth + epoch protocol tests (deterministic, no models)."""

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.scene import CurrentScene, SceneEpoch
from src.services.scene_state import (
    apply_detections,
    close_epoch,
    get_active_scene,
    report_detections,
)


def test_authority_ranks_user_over_inference():
    fields = apply_detections(
        {"location": {"value": "kitchen", "source": "model_inferred",
                      "authority": "model_inferred", "confidence": 0.6,
                      "updated_at": "2026-09-25T10:00:00"}},
        {"location": "the park"}, source="model_inferred")
    assert fields["location"]["value"] == "the park"  # same rank, newer wins
    fields2 = apply_detections(fields, {"location": "kitchen"},
                               source="user_explicit")
    assert fields2["location"]["value"] == "kitchen"
    assert fields2["location"]["authority"] == "user_explicit"
    # Lower rank never overwrites higher.
    fields3 = apply_detections(fields2, {"location": "mall"},
                               source="model_inferred")
    assert fields3["location"]["value"] == "kitchen"


def test_participants_monotonic_add_explicit_remove():
    fields = apply_detections({}, {"arrived": ["Marco"]},
                              source="user_explicit")
    assert fields["participants"]["value"] == ["Marco"]
    fields = apply_detections(fields, {"arrived": ["Marco"]},
                              source="user_explicit")
    assert fields["participants"]["value"] == ["Marco"]  # no duplicates
    # Empty detections never remove.
    fields = apply_detections(fields, {}, source="user_explicit")
    assert fields["participants"]["value"] == ["Marco"]
    fields = apply_detections(fields, {"departed": ["Marco"]},
                              source="user_explicit")
    assert fields["participants"]["value"] == []


def test_empty_detections_noop():
    assert apply_detections({"a": {"value": 1}}, {}) == {"a": {"value": 1}}


@pytest.mark.asyncio
async def test_report_and_epoch_close(async_client):
    from datetime import datetime, timezone
    base = {"workspace_id": "ws-scene", "session_id": "s1"}
    r = await async_client.post("/v1/cortex/scene/report", json={
        **base, "owner_peer_id": "kai", "message_id": "m1",
        "detections": {"location": "kitchen", "arrived": ["Isa"]},
        "source": "user_explicit", "confidence": 0.9})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"]["epoch_id"] == 1
    assert body["scene"]["fields"]["location"]["value"] == "kitchen"
    assert body["epoch"] is None  # no epoch event: no close
    # Second report with epoch event closes + carries.
    r2 = await async_client.post("/v1/cortex/scene/report", json={
        **base, "owner_peer_id": "kai", "message_id": "m2",
        "detections": {"time_jump": True},
        "epoch_event": {"type": "scene", "reason": "scene_time_jump"}})
    assert r2.status_code == 200, r2.text
    assert r2.json()["epoch"]["new_epoch"] == 2
    async with async_session_maker() as db:
        epochs = (await db.execute(select(SceneEpoch).where(
            SceneEpoch.honcho_workspace_id == "ws-scene"))).scalars().all()
        assert len(epochs) == 1
        assert epochs[0].closed_at is not None
        active = await get_active_scene(db, "ws-scene", "s1")
        assert active.epoch_id == 2
    # Explicit epoch route + active GET.
    r3 = await async_client.get(
        "/v1/cortex/scene/active",
        params={"workspace_id": "ws-scene", "session_id": "s1"})
    assert r3.status_code == 200
    assert r3.json()["epoch_id"] == 2
    r4 = await async_client.post("/v1/cortex/scene/epoch", json={
        **base, "action": "close", "reason": "session_end"})
    assert r4.status_code == 200 and r4.json()["new_epoch"] == 3


@pytest.mark.asyncio
async def test_report_invalid_is_fail_open(async_client):
    r = await async_client.post("/v1/cortex/scene/report", json={
        "workspace_id": "ws-scene2", "session_id": "s1",
        "detections": None})
    assert r.status_code in (200, 422)
