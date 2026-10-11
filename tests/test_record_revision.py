"""Record-first corrections: a dated correction of an open record revises the record
instead of becoming competing prose; genuine preferences still store as standing
requests; nothing is ever silently dropped."""
from datetime import datetime

import pytest

from src.db import async_session_maker
from src.models.expectation import Expectation
from src.models.world import WorldEvent
from src.services import record_revision as rr
from src.services import standing_requests as sr

WS, OWNER = "w-rev", "user_ashley"
WED = datetime(2026, 10, 7, 12, 0, 0)  # a Wednesday, noon UTC


async def _seed(db, event_label="Corporate flowers job", exp_title="Pay school fee"):
    db.add(WorldEvent(honcho_workspace_id=WS, owner_peer_id=OWNER, label=event_label,
                      kind="work_event", when_phrase="Wednesday", status="current"))
    db.add(Expectation(honcho_workspace_id=WS, honcho_session_id="s", honcho_message_id="m",
                       owner_peer_id=OWNER, subject_peer_id=OWNER, title=exp_title, summary="s",
                       expected_window_start=datetime(2026, 10, 8, 6), expected_window_end=datetime(2026, 10, 8, 23)))
    await db.commit()


@pytest.mark.asyncio
async def test_dated_correction_revises_event_and_skips_prose():
    async with async_session_maker() as db:
        await _seed(db)
        out = await sr.sync(db, WS, OWNER, ["Do not describe the corporate flower delivery as today; it is Friday 08:00"],
                            source="interpreter", revise=True, now=WED, timezone_str="America/Guatemala")
        assert len(out["revised"]) == 1 and out["revised"][0]["kind"] == "event" and out["created"] == 0
        ev = (await db.execute(__import__("sqlmodel").select(WorldEvent).where(WorldEvent.label == "Corporate flowers job"))).scalars().one()
        # naive UTC storage: 08:00 America/Guatemala == 14:00 UTC; the phrase keeps the human intent
        assert ev.when_start.date().isoformat() == "2026-10-09" and ev.when_start.hour == 14 and ev.when_precision == "exact"
        assert "friday" in (ev.when_phrase or "").lower()
        assert await sr.active(db, WS, OWNER) == []


@pytest.mark.asyncio
async def test_repeat_correction_is_already_current_not_prose():
    async with async_session_maker() as db:
        await _seed(db)
        text = "Corporate flowers moved to Friday"
        first = await sr.sync(db, WS, OWNER, [text], source="interpreter", revise=True, now=WED, timezone_str="UTC")
        assert len(first["revised"]) == 1
        second = await sr.sync(db, WS, OWNER, [text], source="interpreter", revise=True, now=WED, timezone_str="UTC")
        assert second["revised"] == [] and second["already_current"][0]["reason"] == "already_current"
        assert await sr.active(db, WS, OWNER) == []


@pytest.mark.asyncio
async def test_genuine_preference_stores_and_leaves_records_alone():
    async with async_session_maker() as db:
        await _seed(db)
        out = await sr.sync(db, WS, OWNER, ["Don't frame things as therapy"], source="scene_pass", revise=True, now=WED)
        assert out["created"] == 1 and out["revised"] == []
        assert await sr.active(db, WS, OWNER) == ["Don't frame things as therapy"]
        ev = (await db.execute(__import__("sqlmodel").select(WorldEvent).where(WorldEvent.label == "Corporate flowers job"))).scalars().one()
        assert ev.when_start is None


@pytest.mark.asyncio
async def test_spanish_correction_revises_spanish_record():
    async with async_session_maker() as db:
        await _seed(db, event_label="Entrega de flores corporativas")
        out = await sr.sync(db, WS, OWNER, ["La entrega de flores se movió al viernes a las 8"], source="interpreter",
                            revise=True, now=WED, timezone_str="America/Guatemala")
        assert len(out["revised"]) == 1
        ev = (await db.execute(__import__("sqlmodel").select(WorldEvent).where(WorldEvent.label == "Entrega de flores corporativas"))).scalars().one()
        assert ev.when_start.date().isoformat() == "2026-10-09" and ev.when_start.hour == 14 and ev.when_precision == "exact"


@pytest.mark.asyncio
async def test_cross_language_mismatch_falls_back_to_prose_without_loss():
    # Deterministic binding shares tokens: an English-titled record corrected in Spanish
    # cannot bind — it stores as prose (today's behavior) for the interpreter backstop,
    # which reads both languages. Pointer refs (language-independent ids) are the primary
    # path for exactly this case.
    async with async_session_maker() as db:
        await _seed(db, event_label="Corporate flowers job")
        out = await sr.sync(db, WS, OWNER, ["La entrega se movió al viernes a las 8"], source="interpreter",
                            revise=True, now=WED, timezone_str="America/Guatemala")
        assert out["revised"] == [] and out["created"] == 1
        ev = (await db.execute(__import__("sqlmodel").select(WorldEvent).where(WorldEvent.label == "Corporate flowers job"))).scalars().one()
        assert ev.when_start is None


@pytest.mark.asyncio
async def test_expectation_window_revises_and_match_without_date_stays_prose():
    async with async_session_maker() as db:
        await _seed(db)
        out = await sr.sync(db, WS, OWNER, ["School fee moved to Friday"], source="interpreter", revise=True, now=WED, timezone_str="UTC")
        assert len(out["revised"]) == 1 and out["revised"][0]["kind"] == "expectation"
        nodate = await sr.sync(db, WS, OWNER, ["School fee is still a worry"], source="interpreter", revise=True, now=WED, timezone_str="UTC")
        assert nodate["revised"] == [] and nodate["created"] == 1   # matched but undateable: today's behavior, stored


def test_matcher_refuses_ties_and_amounts_are_not_times():
    assert rr.extract_when("Client owes Q4,500 deposit") is None          # amounts are not clock times
    assert rr.extract_when("It is Friday 08:00")[0] == 4
    assert rr.extract_when("moved to Saturday")[0] == 5
    assert rr.match_record("unrelated prose about nothing", [], []) is None


@pytest.mark.asyncio
async def test_picture_pass_correction_revises_record_end_to_end():
    """Entry-point coverage: the picture pass emits the S12-style prose; the record moves
    and no competing standing request is stored — the exact replay failure, deterministically."""
    from src.services import scene_narrative

    class _Adapter:
        async def generate_structured(self, *, system, prompt, **_):
            assert "[ref:" not in prompt  # no pointers yet; binding is by match
            return {"scene": "Flower delivery moved.", "standing_requests": [
                "Do not describe the corporate flower delivery as today; it is Friday 08:00"]}

    async with async_session_maker() as db:
        await _seed(db)
        out = await scene_narrative.narrate(db, adapter=_Adapter(), workspace_id=WS, session_id="s-pic",
                                            names={"user": "Ashley", "assistant": "Sophie"},
                                            messages=[{"speaker": "user", "text": "flowers moved to Friday 8am"},
                                                      {"speaker": "assistant", "text": "got it, Friday 8am"},
                                                      {"speaker": "user", "text": "and Thursday just the vases"},
                                                      {"speaker": "assistant", "text": "noted"}],
                                            force=True, owner=OWNER)
        assert out["standing_requests"] == []                              # consumed into the record
        import sqlmodel
        ev = (await db.execute(sqlmodel.select(WorldEvent).where(WorldEvent.label == "Corporate flowers job"))).scalars().one()
        # picture path grounds against wall-clock now, so assert the weekday + precision, not the date
        assert ev.when_start.weekday() == 4 and ev.when_precision == "exact"


@pytest.mark.asyncio
async def test_polluted_state_repairs_without_duplicates():
    """Migration case: the replay's fragmented state (stale Wednesday event + active flower
    prose, written before the fix) converges on the next routed pass — event moves, old
    prose withdraws, no second copy appears."""
    from src.services import standing_requests as sr2
    from src.services.standing_requests import StandingRequest

    async with async_session_maker() as db:
        await _seed(db)
        db.add(StandingRequest(honcho_workspace_id=WS, owner_peer_id=OWNER,
                               text="Do not describe the corporate flower delivery as today; it is Friday 08:00",
                               key="do not describe the corporate flower delivery as today it is friday 08 00",
                               source="interpreter"))
        await db.commit()
        out = await sr2.sync(db, WS, OWNER, ["Do not describe the corporate flower delivery as today; it is Friday 08:00"],
                             source="interpreter", revise=True, now=WED, timezone_str="America/Guatemala")
        assert len(out["revised"]) == 1
        import sqlmodel
        ev = (await db.execute(sqlmodel.select(WorldEvent).where(WorldEvent.label == "Corporate flowers job"))).scalars().one()
        assert ev.when_start.date().isoformat() == "2026-10-09"
        rows = (await db.execute(sqlmodel.select(StandingRequest).where(
            StandingRequest.honcho_workspace_id == WS, StandingRequest.owner_peer_id == OWNER))).scalars().all()
        assert [r.status for r in rows] == ["withdrawn"]                  # old prose retired, no duplicate
        assert await sr2.active(db, WS, OWNER) == []
