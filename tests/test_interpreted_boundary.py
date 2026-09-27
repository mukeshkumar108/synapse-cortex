"""Boundary-first interpreter path: refusal framings bury topics, never mint loops."""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.open_loop import OpenLoop
from src.models.suppression import Suppression, SuppressionStatus
from src.services.lifecycle_service import boundary_topic


@pytest.mark.parametrize("text,expected", [
    ("Don't bring up the work trip again for now.", "work trip"),
    ("do not mention the dentist", "dentist"),
    ("Leave the school money alone.", "school money"),
    ("Stop talking about Matt.", "matt"),
    ("forget about the invoice", "invoice"),
    ("Drop the subject of overtime.", "subject of overtime"),
    # Non-boundaries: must fall through (None)
    ("Don't forget to call the dentist tomorrow.", None),
    ("Don't worry about the meeting.", None),
    ("Leave it alone.", None),
    ("Do you remember the work trip?", None),
    ("The work trip was fine.", None),
    ("", None),
])
def test_boundary_topic_shapes(text, expected):
    assert boundary_topic(text) == expected


@pytest.mark.asyncio
async def test_boundary_utterance_suppresses_instead_of_minting(async_client, monkeypatch):
    """'Don't bring up X' via the interpreter-new path creates a suppression
    and no open loop — the packet must never offer the buried topic."""
    from src.services import turn_interpretation as ti
    from src.routers import v1_events

    async def fake_interpret(text, matters):
        from src.services.turn_interpretation import TurnInterpretation
        return TurnInterpretation(decision="new", primary_id=None, also_ids=[],
                                  confidence=0.9, evidence_span=text[:20])

    monkeypatch.setattr(ti, "interpret_turn", fake_interpret)
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates",
                        lambda *a, **k: [])
    ws = "ws-boundary-lane"
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": "s1", "honcho_message_id": "m-bound-1",
        "peer_id": "user-1", "text": "Don't bring up the work trip again for now.",
        "now": "2026-09-27T10:00:00+01:00", "timezone": "Europe/London",
        "is_assistant_turn": False})
    assert r.status_code in (200, 202)
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
        assert [l.title for l in loops] == [], [l.title for l in loops]
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == ws,
            Suppression.status == SuppressionStatus.ACTIVE))).scalars().all()
        assert len(supps) == 1
        assert supps[0].topic_or_entity == "work trip"
        assert supps[0].surface_scope == "followup_prompt"
        assert supps[0].reopen_condition == "user re-raises topic"


@pytest.mark.asyncio
async def test_non_boundary_new_still_mints(async_client, monkeypatch):
    """A genuine new matter through the same path still creates a loop."""
    from src.services import turn_interpretation as ti
    from src.routers import v1_events

    async def fake_interpret(text, matters):
        from src.services.turn_interpretation import TurnInterpretation
        return TurnInterpretation(decision="new", primary_id=None, also_ids=[],
                                  confidence=0.9, evidence_span=text[:20])

    monkeypatch.setattr(ti, "interpret_turn", fake_interpret)
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates",
                        lambda *a, **k: [])
    ws = "ws-boundary-lane-2"
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": ws, "session_id": "s1", "honcho_message_id": "m-new-1",
        "peer_id": "user-1", "text": "I need to sort out the car insurance this week.",
        "now": "2026-09-27T10:00:00+01:00", "timezone": "Europe/London",
        "is_assistant_turn": False})
    assert r.status_code in (200, 202)
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
        assert len(loops) == 1
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == ws))).scalars().all()
        assert supps == []
