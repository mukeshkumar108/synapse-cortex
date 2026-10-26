"""The opportunities read (H11): tense from dates, a stakes threshold, facts-only wording, background kept apart, only the person's own boundary honoured. No model, no network."""
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
    assert "Priya's wedding" in out["text"].split("Also held")[0]
    bg = out["text"].split("Also held")[1]
    assert "Staying up late reading" in bg and "Lentil chilli experiment" in bg


@pytest.mark.asyncio
async def test_a_health_matter_is_just_a_fact_and_only_what_the_person_asked_not_to_raise_is_withheld():
    async with async_session_maker() as db:
        await _entity(db, "Mum's fall", kind="health", form="happening", occurred_on=datetime(2026, 10, 25), significance=3)
        e = await _entity(db, "Do not mention", kind="situation", form="situation", significance=3)
        e.suppressed = True
        await db.commit()
        out = await opportunities.read(db, WS, OWNER, CTX)
    assert "Mum's fall [Sun 25 Oct, yesterday]" in out["text"] and "private" not in out["text"].lower()
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


async def _seed_packet_world(db):
    await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2)
    await _entity(db, "Chronic back pain affecting sleep", kind="health", form="situation", significance=1)
    await _entity(db, "Project with shifting requirements", kind="work", form="situation", significance=1)
    await db.commit()


@pytest.mark.asyncio
async def test_opening_packet_is_one_minimal_item_and_empty_when_nothing_fits():
    async with async_session_maker() as db:
        await _seed_packet_world(db)
        out = await opportunities.read(db, WS, OWNER, CTX)
        empty = await opportunities.read(db, "nothing-here", "nobody", CTX)
    pk = opportunities.build_packet(out, stage="opening")
    assert pk["version"] == 1 and pk["purpose"] == "reconnect" and len(pk["items"]) == 1
    assert pk["items"][0]["text"] == "Leo breaks his leg in rugby" and "Background" not in pk["text"] and pk["valid_until"] > pk["built_at"]
    assert opportunities.build_packet(empty, stage="opening")["items"] == []


@pytest.mark.asyncio
async def test_moment_packet_follows_the_persons_words_and_retires_used_items_but_not_the_matter():
    async with async_session_maker() as db:
        await _seed_packet_world(db)
        out = await opportunities.read(db, WS, OWNER, CTX)
    pk = opportunities.build_packet(out, stage="moment", user_text="I'm shattered, barely slept, my back is killing me")
    assert [i["text"] for i in pk["items"]] == ["Chronic back pain affecting sleep"] and pk["purpose"] == "touched"
    used_id = pk["items"][0]["id"]
    again = opportunities.build_packet(out, stage="moment", user_text="my back again", used=[used_id])
    assert again["items"] == []                                  # the packet is retired once used...
    assert out["background_items"][0]["source"] == "world" and out["background_items"][0]["ref"]      # ...while the matter stays in the records with its own life cycle


@pytest.mark.asyncio
async def test_a_task_withholds_unrelated_relational_items():
    async with async_session_maker() as db:
        await _seed_packet_world(db)
        out = await opportunities.read(db, WS, OWNER, CTX)
    pk = opportunities.build_packet(out, stage="moment", user_text="Can you help me tighten this email to my boss? It has to go before ten.")
    assert pk["items"] == [] and pk["purpose"] == "task_support"


@pytest.mark.asyncio
async def test_three_letter_words_count_and_function_words_do_not():
    async with async_session_maker() as db:
        await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2)
        out = await opportunities.read(db, WS, OWNER, CTX)
    assert opportunities.build_packet(out, stage="moment", user_text="How's Leo's leg?")["items"]
    assert not opportunities.build_packet(out, stage="moment", user_text="Can you tell me with that, the and his")["items"]


@pytest.mark.asyncio
async def test_a_packet_carries_labels_and_facts_and_no_instruction_or_stance_or_privacy_marking():
    async with async_session_maker() as db:
        await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2)
        await _entity(db, "Mum's fall", kind="health", form="happening", occurred_on=datetime(2026, 10, 25), significance=3)
        out = await opportunities.read(db, WS, OWNER, CTX)
    for pk in (opportunities.build_packet(out, stage="moment", user_text="Leo broke his leg and Mum had a fall"), opportunities.build_packet(out, stage="opening"),
               opportunities.build_packet(out, stage="survey")):
        t = pk["text"].lower()
        assert pk["items"] and not any(w in t for w in ("private", "gentle", "lightly", "do not", "optional", "open with", "probe", "naturally", "if the moment"))
        assert "stance" not in pk and "usage" not in pk and all("private" not in i for i in pk["items"])
    assert opportunities.build_packet(out, stage="opening")["text"].startswith("What is on my mind about them right now:")


@pytest.mark.asyncio
async def test_a_packet_says_who_a_named_person_is_so_a_weak_model_cannot_mistake_them_for_the_user():
    async with async_session_maker() as db:
        await _entity(db, "Leo", kind="person", summary="The person's twelve-year-old nephew.")
        await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2)
        out = await opportunities.read(db, WS, OWNER, CTX)
    pk = opportunities.build_packet(out, stage="opening")
    assert "Who this is:\n- Leo: The person's twelve-year-old nephew." in pk["text"] and pk["who"]
    assert "Who this is" not in opportunities.build_packet(out, stage="moment", user_text="send the invoice")["text"]


@pytest.mark.asyncio
async def test_an_opening_is_her_own_thought_with_tense_from_the_date():
    async with async_session_maker() as db:
        await _entity(db, "Leo breaks his leg in rugby", kind="injury", form="happening", occurred_on=datetime(2026, 10, 17), significance=2)
        out = await opportunities.read(db, WS, OWNER, CTX, ledger_rows=[_row("Leadership presentation", "2026-10-27", importance=3)])
    t = opportunities.build_packet(out, stage="survey")["text"]
    assert "- Leo breaks his leg in rugby (Sat 17 Oct, 9 days ago). I want to ask how it has gone." in t
    assert "- Leadership presentation (Tue 27 Oct, tomorrow). I want to know how they feel about it and whether I can help." in t
