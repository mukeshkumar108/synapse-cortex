"""The opportunities read (H11): tense from dates, a stakes threshold, neutral wording, private marking, background kept apart. No model, no network."""
from datetime import datetime

import pytest

from src.db import async_session_maker
from src.services import known_world, memory_pipeline, opportunities

WS, OWNER = "wo", "u1"
CTX = known_world.Ctx(datetime.fromisoformat("2026-10-26T09:00:00+01:00"), "Europe/London")


async def _entity(db, name, **kw):
    return await known_world.create(db, WS, OWNER, name=name, **kw)


def _row(title, date, importance=2, status="open"):
    return memory_pipeline.LedgerItem(honcho_workspace_id=WS, owner_peer_id=OWNER, kind="commitment", title=title, detail="d", status=status,
                                      situation_key=title.lower().replace(" ", "-"), expected_date=datetime.fromisoformat(date) if date else None, importance=importance)


@pytest.mark.asyncio
async def test_tense_comes_from_dates_and_stale_words_never_appear():
    async with async_session_maker() as db:
        await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2,
                      summary="Leo broke his leg on Saturday, the day before today, tomorrow he gets a cast")
        await db.commit()
        out = await opportunities.read(db, WS, OWNER, CTX)
    assert "Leo breaks his leg in rugby [Sat 17 Oct, 9 days ago]" in out["text"]
    assert "tomorrow" not in out["text"] and "day before" not in out["text"]


@pytest.mark.asyncio
async def test_a_future_dated_matter_is_ahead_and_trivia_is_background():
    async with async_session_maker() as db:
        await _entity(db, "Priya's wedding", kind="event", form="situation", significance=2)
        await _entity(db, "Staying up late reading", kind="habit", form="situation", significance=1)
        rows = [_row("Leadership presentation", "2026-10-27", importance=3), _row("Lentil chilli experiment", "2026-10-24", importance=1)]
        out = await opportunities.read(db, WS, OWNER, CTX, ledger_rows=rows)
    assert "Leadership presentation [Tue 27 Oct, tomorrow]" in out["text"]
    assert "Priya's wedding" in out["text"].split("Background")[0]
    bg = out["text"].split("Background")[1]
    assert "Staying up late reading" in bg and "Lentil chilli experiment" in bg


@pytest.mark.asyncio
async def test_private_items_are_marked_and_suppressed_ones_never_appear():
    async with async_session_maker() as db:
        await _entity(db, "Mum's fall", kind="health", form="happening", occurred_on=datetime(2026, 10, 25), significance=3, sensitive=True)
        e = await _entity(db, "Do not mention", kind="situation", form="situation", significance=3)
        e.suppressed = True
        await db.commit()
        out = await opportunities.read(db, WS, OWNER, CTX)
    assert "Mum's fall [Sun 25 Oct, yesterday]  (private: acknowledge lightly, do not probe)" in out["text"]
    assert "Do not mention" not in out["text"]


@pytest.mark.asyncio
async def test_nothing_held_means_nothing_offered():
    async with async_session_maker() as db:
        out = await opportunities.read(db, "empty-ws", "nobody", CTX)
    assert out["text"] == "" and out["candidates"] == []


def test_next_weekday_names_both_dates_and_plain_weekdays_are_unchanged():
    from datetime import date
    wed = date(2026, 10, 21)
    out = memory_pipeline._annotate_timing("The deadline is next Thursday", wed)
    assert "next Thursday (2026-10-29; or 2026-10-22 if they meant the coming one)" in out
    assert memory_pipeline._annotate_timing("Thursday at 3", wed) == "Thursday (2026-10-22) at 3"
    assert memory_pipeline._annotate_timing("tomorrow", wed) == "tomorrow (2026-10-22)"


def test_relative_time_words_in_a_summary_are_refused_by_code():
    from src.services.world_agent import relative_time_problem as bad
    assert bad("Priya's wedding, this Saturday.") and bad("made a pot of chilli the day before today") and bad("Meeting next week")
    assert not bad("Friend who is getting married; asked to do a reading") and not bad("Leo's parent, currently run ragged driving him around.")
