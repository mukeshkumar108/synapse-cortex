"""Attention/surfacing controller tests: report-back and background sweep.

(The pure per-turn selection policy and the session/scene working set were
retired with the cutover: per-turn selection is the Turn Working Set —
tests/test_turn_working_set.py — and policy belongs to Runtime/product.)
Report-back and sweep touch only existing durable machinery.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker


@pytest.mark.asyncio
async def test_report_back_lifecycle():
    from datetime import datetime, timezone

    from src.models.clarification import ClarificationCandidate, ClarificationStatus
    from src.services.surfacing import report_back

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws-surf", honcho_session_id="s1",
            honcho_message_id="m1", description="Which day?"))
        await db.commit()
        clar = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == "ws-surf"))).scalar_one()
        out = await report_back(
            db, workspace_id="ws-surf", session_id="s1", owner_peer_id="kai",
            events=[
                {"matter_kind": "clarification", "matter_id": str(clar.id),
                 "outcome": "answered", "move_key": "q1"},
                {"matter_kind": "open_loop", "matter_id": "nope",
                 "outcome": "bogus", "move_key": "q2"},
                {"matter_kind": "attention", "matter_id": "a1",
                 "outcome": "dismissed", "move_key": "q3"},
                {"matter_kind": "attention", "matter_id": "a2",
                 "outcome": "ignored", "move_key": "q4"},
            ],
            now=now, message_id="m9")
        assert out["ok"] == 3
        clar2 = await db.get(ClarificationCandidate, clar.id)
        assert clar2.status == ClarificationStatus.RESOLVED
        from src.models.suppression import Suppression
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == "ws-surf"))).scalars().all()
        # dismissed -> strong suppression; ignored -> none.
        assert len(supps) == 1 and supps[0].surface_scope == "all_surfaces"


@pytest.mark.asyncio
async def test_background_sweep_detects_new():
    from datetime import datetime, timezone

    from src.models.clarification import ClarificationCandidate
    from src.services.background_sweep import background_sweep

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        first = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert first["new"] == []
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws-bg", honcho_session_id="s1",
            honcho_message_id="m1", description="Which dentist day?"))
        await db.commit()
        second = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert any("dentist" in i["title"].lower() for i in second["new"])
        third = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert third["new"] == []  # already seen: no repeat nag


@pytest.mark.asyncio
async def test_surfacing_report_route(async_client):
    from datetime import datetime, timezone

    r = await async_client.post("/v1/cortex/surfacing/report", json={
        "workspace_id": "ws-rroute", "session_id": "s1", "peer_id": "kai",
        "message_id": "m9",
        "now": datetime.now(timezone.utc).isoformat(),
        "events": [
            {"matter_kind": "attention", "matter_id": "a1",
             "outcome": "ignored", "move_key": "q1"},
            {"matter_kind": "attention", "matter_id": "a2",
             "outcome": "bogus", "move_key": "q2"},
        ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] == 1
    assert body["applied"][1]["applied"] is False


@pytest.mark.asyncio
async def test_background_sweep_route(async_client):
    from datetime import datetime, timezone

    r = await async_client.post("/v1/cortex/background-sweep", json={
        "workspace_id": "ws-bgr", "session_id": "s1", "peer_id": "kai",
        "now": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["new"] == []
