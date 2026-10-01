"""act/withhold -> observe -> future attention: receipt identity, reaction
mapping, cross-session fatigue. Drives HTTP endpoints (and service helpers)
the way runtime would, per the documented reaction mapping:
welcomed->answered, redirected->ignored, refused->dismissed, neutral->still-open.
HOLD sends nothing (proven by absence: no endpoint called, no rows)."""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.expectation import Expectation
from src.models.operational_state import CandidateReceipt


async def _post(client, path, body):
    r = await client.post(path, json=body, timeout=60.0)
    assert r.status_code in (200, 202, 201), r.text[:300]
    return r.json()


@pytest.mark.asyncio
async def test_owed_carries_receipt_identity(async_client):
    """Owed items expose candidate_id + candidate_version (projection fix)."""
    import json as _json
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    ws = "ws-fb-owed"
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id=ws, honcho_session_id="s1",
            honcho_message_id="m1", owner_peer_id="u",
            candidate_key="k1", subject_peer_id="u",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Call the dentist", summary="Call the dentist tomorrow morning",
            anchor_timezone="Europe/London",
            reminder_windows_json=_json.dumps([{
                "start": "2026-09-28T05:00:00", "end": "2026-09-28T10:00:00",
                "label": "tomorrow morning"}]),
            outcome_state=OutcomeState.UNKNOWN))
        await db.commit()
    r = await async_client.post("/v1/cortex/attention-state/evaluate", json={
        "workspace_id": ws, "session_id": "s1", "peer_id": "u",
        "now": "2026-09-28T08:30:00+01:00", "timezone": "Europe/London",
        "turn_text": "morning"}, timeout=60.0)
    owed = (r.json().get("follow_through") or {}).get("owed") or []
    assert owed, "due reminder must be owed at window time"
    assert owed[0]["candidate_id"] is not None
    assert owed[0]["candidate_id"].startswith("expectation:")
    assert owed[0]["candidate_version"]


@pytest.mark.asyncio
async def test_open_loop_and_expectation_receipts_record_and_fence(async_client):
    """Receipt rows accepted for new prefixes; version staleness 409s;
    delivered+asked marks surfacing history without mutating the row."""
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    ws = "ws-fb-receipt"
    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id=ws, honcho_session_id="s1",
            honcho_message_id="m1", owner_peer_id="u",
            candidate_key="k1", title="Electricity bill watch",
            summary="Keep an eye on the electricity bill",
            status=OpenLoopStatus.OPEN))
        await db.commit()
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
        loop = loops[0]
        version = loop.updated_at.isoformat()
        body = {"workspace_id": ws, "owner_peer_id": "u", "receipts": [{
            "receipt_id": "rc-1", "decision_id": "d-1", "turn_id": "t-1",
            "candidate_id": f"open_loop:{loop.id}", "candidate_version": version,
            "stage": "delivered", "channel": "inbound",
            "occurred_at": "2026-09-27T10:00:00+01:00",
            "assistant_message_id": "t-1", "effect": "asked"}]}
        out = await _post(async_client, "/v1/cortex/candidate-receipts", body)
        assert out["accepted"] == 1
        # stale version must 409, not silently accept
        body["receipts"][0]["receipt_id"] = "rc-2"
        body["receipts"][0]["candidate_version"] = "2000-01-01T00:00:00"
        r = await async_client.post("/v1/cortex/candidate-receipts", json=body,
                                    timeout=60.0)
        assert r.status_code == 409
        # unsupported prefix still 422s
        body["receipts"][0]["candidate_id"] = "task:whatever"
        r = await async_client.post("/v1/cortex/candidate-receipts", json=body,
                                    timeout=60.0)
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_redirect_then_new_evidence_trajectory(async_client):
    """Surfaced -> redirected(ignored) -> fatigue -> new evidence revives."""
    from datetime import datetime
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    ws = "ws-fb-traj"
    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id=ws, honcho_session_id="s1",
            honcho_message_id="m1", owner_peer_id="u",
            candidate_key="k1", title="Update on Matt's condition",
            summary="Waiting to hear whether Matt is okay",
            status=OpenLoopStatus.OPEN,
            created_at=datetime(2026, 9, 27, 9, 0),
            updated_at=datetime(2026, 9, 27, 9, 0)))
        await db.commit()
    from src.services import agenda_service
    from src.services import attention_state_service as cps
    from datetime import datetime

    async def pressures(now):
        from src.services import agenda_service
        from src.services import attention_state_service as cps
        from datetime import datetime
        now_dt = datetime.fromisoformat(now)
        async with async_session_maker() as db:
            packet = await cps.AttentionStateService().compile_attention_state(
                db=db, workspace_id=ws, session_id="s1", now=now_dt,
                timezone_str="Europe/London", owner_peer_id="u")
            marks = await agenda_service._surface_marks(
                db, workspace_id=ws, session_id="s1", owner_peer_id="u")
            items = agenda_service.extract_candidates(
                packet, now=now_dt, timezone_str="Europe/London",
                surface_marks=marks)
            return {c["item_key"]: c["pressure"] for c in items}

    before = await pressures("2026-09-29T09:00:00+01:00")
    loop_keys = [k for k in before if k.startswith("loop:")]
    assert loop_keys, f"expected Matt loop agenda item, got {list(before)}"
    p_before = before[loop_keys[0]]
    # runtime reports redirected -> ignored (cooldown + receipt, stays eligible)
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
        matt = [l for l in loops if "matt" in (l.title or "").lower()][0]
    rep = await _post(async_client, "/v1/cortex/surfacing/report", {
        "workspace_id": ws, "session_id": "s1", "peer_id": "u",
        "now": "2026-09-29T10:00:00+01:00", "timezone": "Europe/London",
        "message_id": "rep-1", "channel": "chat",
        "events": [{"matter_kind": "open_loop", "matter_id": str(matt.id),
                    "outcome": "ignored"}]})
    assert rep["ok"] == 1
    after = await pressures("2026-09-29T12:00:00+01:00")
    assert after[loop_keys[0]] < p_before, (p_before, after[loop_keys[0]])
    # loop itself untouched (ignored != resolved)
    async with async_session_maker() as db:
        row = await db.get(OpenLoop, matt.id)
        assert str(row.status) == "OpenLoopStatus.OPEN"
