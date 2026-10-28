"""Notes: one write per sitting, and every view is a query. The model is an injected fake; no network."""
import asyncio
import json
import uuid
from datetime import date, datetime

import pytest
from sqlmodel import select

from src.config import settings
from src.db import async_session_maker
from src.models.note import Note
from src.services import memory_pipeline, notes

WS = "wsN"


def owner():
    return f"u-{uuid.uuid4().hex[:8]}"


def fake_notes(payload, fix=None):
    """A model that returns `payload` for the notes call, `fix` for the relative-word rewrite, and plain text for every other memory call."""
    calls = {"notes": 0, "fix": 0}

    def fn(kind, prompt, max_tokens, models):
        if kind == "notes":
            calls["notes"] += 1
            return {"text": json.dumps(payload), "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
        if kind == "notes-fix":
            calls["fix"] += 1
            return {"text": json.dumps(fix or {"fixed": []}), "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
        return {"text": "ok", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    return fn, calls


def note(**kw):
    base = {"subject": "the person", "area": "sleep-energy", "certainty": "stated", "when": "", "key": "", "text": "They barely slept all week.", "quote": "barely slept", "resolves": ""}
    base.update(kw)
    return base


async def write(o, payload, day, transcript="Him: i barely slept all week and i'm up till two\nSophie: oh no", fix=None, label="Him"):
    fn, calls = fake_notes(payload, fix)
    memory_pipeline.set_model_fn(fn)
    try:
        async with async_session_maker() as db:
            out = await notes.write(db, workspace_id=WS, owner=o, product="sophie", session_id=f"s-{day}", run_id=None, transcript=transcript, person_label=label,
                                    companion_name="Sophie", session_day=day, weekday=day.strftime("%A"))
        return out, calls
    finally:
        memory_pipeline.set_model_fn(None)


async def rows(o):
    async with async_session_maker() as db:
        return list((await db.execute(select(Note).where(Note.owner_peer_id == o).order_by(Note.sitting_on, Note.created_at))).scalars().all())


def test_clean_enforces_the_fixed_lists_and_the_quote_rule():
    out, stats = notes.clean([
        note(text="They hate small talk.", quote="i hate small talk"),                      # quote present in their words: stays stated
        note(text="They love hiking.", quote="i love hiking in the alps"),                   # quote NOT in their words: stated -> unclear
        note(text="Joke about a boat.", certainty="hypothetical", quote="buy a boat", area="no-such-area"),
        note(text="Joke about a boat."),                                                      # duplicate text: dropped
        {"subject": "THEY", "text": "x", "certainty": "wild"},
    ], "i hate small talk. if i won i would buy a boat. barely slept")
    by = {n["text"]: n for n in out}
    assert by["They hate small talk."]["certainty"] == "stated" and by["They hate small talk."]["quote_verified"]
    assert by["They love hiking."]["certainty"] == "unclear" and by["They love hiking."]["quote"] == ""
    assert by["Joke about a boat."]["area"] == "other" and by["Joke about a boat."]["certainty"] == "hypothetical"
    assert by["x"]["certainty"] == "unclear" and by["x"]["subject"] == notes.SELF
    assert stats["downgraded"] >= 1 and stats["dropped"] == 1


@pytest.mark.asyncio
async def test_a_sitting_is_stored_with_dates_and_a_later_note_with_the_same_key_replaces_it():
    o = owner()
    out, _ = await write(o, {"notes": [note(subject="Mara", area="identity", key="birthday", text="Mara's birthday is 31 October.", quote="barely slept")]}, datetime(2026, 9, 11))
    assert out["status"] == "ok" and out["notes"] == 1
    await write(o, {"notes": [note(subject="Mara", area="identity", key="birthday", text="Mara's birthday is 30 October.", quote="barely slept")]}, datetime(2026, 9, 21))
    rs = await rows(o)
    assert [r.status for r in rs] == ["superseded", "current"] and rs[0].replaced_by_id == rs[1].id
    async with async_session_maker() as db:
        card = await notes.card(db, WS, o, "Mara")
    assert card["current_facts"]["birthday"]["text"].endswith("30 October.")


@pytest.mark.asyncio
async def test_an_open_intention_is_closed_only_by_its_id():
    o = owner()
    await write(o, {"notes": [note(area="goals-plans", certainty="intention", text="They mean to walk before work.", quote="barely slept")]}, datetime(2026, 9, 14))
    short = (await rows(o))[0].id.hex[:8]
    str_id = str((await rows(o))[0].id)[:8]
    await write(o, {"notes": [note(area="exercise", text="They walked this morning on 2026-09-15.", quote="barely slept", resolves="nope")]}, datetime(2026, 9, 15))
    assert (await rows(o))[0].status == "current"                       # an unknown id closes nothing
    await write(o, {"notes": [note(area="exercise", text="They walked on 2026-09-16.", quote="barely slept", resolves=str_id)]}, datetime(2026, 9, 16))
    assert (await rows(o))[0].status == "resolved"
    assert short  # (hex prefix helper kept to show the id is a prefix of the uuid)


@pytest.mark.asyncio
async def test_relative_time_words_are_refused_once_and_re_asked():
    o = owner()
    out, calls = await write(o, {"notes": [note(text="They walked this morning.", area="exercise")]}, datetime(2026, 9, 16),
                             fix={"fixed": [{"i": 0, "text": "They walked on 2026-09-16."}]})
    assert calls["fix"] == 1 and out["retried"] and out["still_relative"] == 0
    assert (await rows(o))[0].text == "They walked on 2026-09-16."


@pytest.mark.asyncio
async def test_recurrence_is_a_count_of_distinct_sittings_with_the_dated_lines():
    o = owner()
    for d in (7, 8, 10):
        await write(o, {"notes": [note(text=f"They slept badly (night of {d} Sep)."), note(area="food", text="They had toast.")]}, datetime(2026, 9, d))
    async with async_session_maker() as db:
        rec = await notes.recurring(db, WS, o, date(2026, 9, 12))
        asks = await notes.asks(db, WS, o, date(2026, 9, 12))
    assert sorted(r["area"] for r in rec) == ["food", "sleep-energy"] and all(r["sittings"] == 3 for r in rec)       # both recur: a count says nothing about worth
    assert [a["area"] for a in asks if a["kind"] == "recurring"] == ["sleep-energy"]                                   # only a strain area is worth asking about


@pytest.mark.asyncio
async def test_a_light_wish_that_comes_back_is_something_worth_asking_but_one_remark_is_not():
    o = owner()
    await write(o, {"notes": [note(area="aspiration", certainty="hypothetical", text="They daydream about a riso press by the canal.")]}, datetime(2026, 9, 15))
    async with async_session_maker() as db:
        assert not [a for a in await notes.asks(db, WS, o, date(2026, 9, 16)) if a["kind"] == "returning"]
    await write(o, {"notes": [note(area="reading-culture", text="A print shop made them think of the riso press again.")]}, datetime(2026, 9, 28))
    async with async_session_maker() as db:
        got = [a for a in await notes.asks(db, WS, o, date(2026, 9, 29)) if a["kind"] == "returning"]
    assert len(got) == 1 and "riso" in got[0]["text"] and "Tue 15 Sep" in got[0]["text"]


@pytest.mark.asyncio
async def test_people_group_a_first_name_with_the_one_longer_name_and_skip_the_person():
    o = owner()
    await write(o, {"notes": [note(subject="Morgan Ellis", area="friends", text="Morgan Ellis left the firm."), note(subject="Morgan", area="friends", text="Morgan is advising on the pilot."),
                              note(subject="Jo", area="work-people", text="Jo helped with the spec.")]}, datetime(2026, 9, 25))
    async with async_session_maker() as db:
        ppl = await notes.people(db, WS, o)
    assert sorted(p["name"] for p in ppl) == ["Jo", "Morgan Ellis"]
    assert next(p for p in ppl if p["name"] == "Morgan Ellis")["notes"] == 2


@pytest.mark.asyncio
async def test_consolidation_writes_notes_only_when_enabled_and_never_for_independent_sittings(async_client, monkeypatch):
    fn, _ = fake_notes({"notes": [note(text="They have not slept well this week.", quote="not slept")]})
    base = {"workspace_id": WS, "owner": owner(), "conversation_id": "c1", "session_id": "s1", "companion_id": "sophie", "session_time": "2026-09-17T18:00:00+01:00", "time_zone": "Europe/London"}
    msgs = [{"id": f"m{i}", "speaker": "user" if i % 2 == 0 else "assistant", "text": t} for i, t in enumerate(
        ["i have not slept well this week", "that sounds hard, what is keeping you up", "work mostly and the presentation", "i hope it goes well"])]

    async def run(extra=None):
        memory_pipeline.set_model_fn(lambda kind, prompt, mt, models: fn(kind, prompt, mt, models) if kind.startswith("notes") else
                                     {"text": '{"new": []}' if kind == "ledger" else "ok", "model": "fake", "provider": "fake", "usage": {}, "ms": 1})
        try:
            r = await async_client.post("/v1/memory/consolidate", json={**base, "messages": msgs, **(extra or {})})
            assert r.status_code == 202, r.text
            for _ in range(80):
                st = (await async_client.get(f"/v1/memory/run/{r.json()['run_id']}")).json()
                if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
                    return st
                await asyncio.sleep(0.1)
        finally:
            memory_pipeline.set_model_fn(None)

    monkeypatch.setattr(settings, "NOTES_ENABLED", False)
    await run()
    assert await rows(base["owner"]) == []
    monkeypatch.setattr(settings, "NOTES_ENABLED", True)
    base["conversation_id"], base["session_id"] = "c2", "s2"
    msgs2 = [{**m, "id": "b" + m["id"], "text": m["text"] + " today"} for m in msgs]
    msgs[:] = msgs2
    await run()
    got = await rows(base["owner"])
    assert len(got) == 1 and got[0].area == "sleep-energy" and got[0].certainty == "stated" and got[0].sitting_on == datetime(2026, 9, 17)


@pytest.mark.asyncio
async def test_what_keeps_coming_up_reaches_the_packet_as_dated_facts_under_its_own_heading():
    from src.services import known_world as kw, opportunities as op
    o = owner()
    for d in (7, 8, 10):
        await write(o, {"notes": [note(text=f"They barely slept (night of {d} Sep).")]}, datetime(2026, 9, d))
    ctx = kw.Ctx(datetime(2026, 9, 12, 9, 0), "Europe/London")
    async with async_session_maker() as db:
        out = await op.read(db, WS, o, ctx, world_on=False, ledger_rows=[], notes_on=True)
    packet = op.build_packet(out, stage="survey")
    assert op.NOTICED_HEAD in packet["text"] and "3 conversations" in packet["text"] and "Mon 7 Sep" in packet["text"]
    assert "should" not in packet["text"].lower() and "ask" not in packet["text"].lower().replace("asked", "")    # facts, never an instruction


@pytest.mark.asyncio
async def test_a_short_check_in_that_says_something_is_not_accepted_as_nothing_until_asked_twice():
    o = owner()
    calls = {"n": 0}

    def fn(kind, prompt, max_tokens, models):
        calls["n"] += kind == "notes"
        payload = {"notes": []} if calls["n"] == 1 else {"notes": [note(area="mood-low", text="They felt flat, stuck at the desk with the accounts.", quote="stuck at my desk all day")]}
        return {"text": json.dumps(payload), "model": "fake", "provider": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "ms": 1}
    memory_pipeline.set_model_fn(fn)
    try:
        async with async_session_maker() as db:
            out = await notes.write(db, workspace_id=WS, owner=o, product="sophie", session_id="s", run_id=None, session_day=datetime(2026, 10, 11), weekday="Sunday", person_label="Person",
                                    companion_name="Bloom", transcript="Person: oh, bit flat really, been stuck at my desk all day with the accounts, one of those days\nBloom: that sounds like a heavy slog")
    finally:
        memory_pipeline.set_model_fn(None)
    assert calls["n"] == 2 and out["notes"] == 1 and out["empty_retry"] == 1 and out["tokens"] == {"in": 20, "out": 10}


@pytest.mark.asyncio
async def test_a_plan_from_the_morning_is_a_thing_to_ask_about_until_it_is_closed():
    o = owner()
    await write(o, {"notes": [note(area="friends", certainty="intention", when="2026-10-13", text="They plan to catch up with Morgan this evening, 2026-10-13.", quote="barely slept")]}, datetime(2026, 10, 13))
    async with async_session_maker() as db:
        got = [a for a in await notes.asks(db, WS, o, date(2026, 10, 13)) if a["kind"] == "plan"]
        later = [a for a in await notes.asks(db, WS, o, date(2026, 10, 25)) if a["kind"] == "plan"]
    assert len(got) == 1 and "Morgan" in got[0]["text"] and "Tue 13 Oct" in got[0]["text"] and later == []       # old plans fall away; they are not nagged about for ever


@pytest.mark.asyncio
async def test_a_light_product_reads_the_sitting_once_into_notes_and_runs_nothing_else(monkeypatch):
    from src.models.world import NotebookPage
    from src.services import bloom_memory
    monkeypatch.setattr(settings, "NOTES_ENABLED", True)
    monkeypatch.setattr(settings, "NOTES_ONLY_PRODUCTS", "bloom")
    o = owner()
    kinds = []

    def fn(kind, prompt, max_tokens, models):
        kinds.append(kind)
        if kind != "notes":
            raise AssertionError(f"a light product must not run {kind}")
        return {"text": json.dumps({"notes": [note(area="nature-outdoors", text="They saw deer on the hill at sunset.", quote="deer on the hill")]}), "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    memory_pipeline.set_model_fn(fn)
    try:
        async with async_session_maker() as db:
            out = await memory_pipeline._consolidate(db, workspace_id=WS, owner=o, conversation_id="c", session_id="s", cfg=bloom_memory.BLOOM, companion_id="bloom",
                                                     session_time="2026-10-15T20:30:00+01:00", time_zone="Europe/London", sitting_kind="user",
                                                     messages=[{"id": "m1", "speaker": "user", "text": "i watched the deer on the hill at sunset, best bit of my week"},
                                                               {"id": "m2", "speaker": "assistant", "text": "that sounds lovely"}])
        async with async_session_maker() as db:
            pages = (await db.execute(select(NotebookPage).where(NotebookPage.owner_peer_id == o))).scalars().all()
    finally:
        memory_pipeline.set_model_fn(None)
    assert out["status"] == "consolidated" and kinds == ["notes"] and pages == []
    assert [r.text for r in await rows(o)] == ["They saw deer on the hill at sunset."]


@pytest.mark.asyncio
async def test_an_ask_is_offered_twice_then_stays_quiet_until_there_is_new_evidence():
    from src.models.known_world import CueExposure
    from src.services import known_world as kw
    o = owner()
    for d in (7, 8, 10):
        await write(o, {"notes": [note(text=f"They barely slept (night of {d} Sep).")]}, datetime(2026, 9, d))
    today = date(2026, 9, 12)
    async with async_session_maker() as db:
        first = await notes.ask_candidates(db, WS, o, today)
        ref = first[0]["ref"]
        for _ in range(2):                                           # offered at two openings (a new sitting-sized window each time)
            x = (await db.execute(select(CueExposure).where(CueExposure.owner_peer_id == o, CueExposure.ref == ref))).scalars().first()
            if x is None:
                db.add(CueExposure(honcho_workspace_id=WS, owner_peer_id=o, source="notes", ref=ref, shown_count=1))
            else:
                x.shown_count += 1
            await db.commit()
        assert await notes.ask_candidates(db, WS, o, today) == []
    await write(o, {"notes": [note(text="They barely slept again (night of 11 Sep).")]}, datetime(2026, 9, 11))
    async with async_session_maker() as db:
        again = await notes.ask_candidates(db, WS, o, today)
    assert len(again) == 1 and again[0]["ref"] != ref                 # a fourth sitting is new evidence: a new ask


@pytest.mark.asyncio
async def test_saying_they_are_tired_meets_the_sleep_pattern_in_the_moment_even_though_the_word_is_not_in_it():
    from src.services import known_world as kw, opportunities as op
    o = owner()
    for d in (7, 8, 10):
        await write(o, {"notes": [note(text=f"They barely slept (night of {d} Sep).")]}, datetime(2026, 9, d))
    ctx = kw.Ctx(datetime(2026, 9, 12, 9, 0), "Europe/London")
    async with async_session_maker() as db:
        out = await op.read(db, WS, o, ctx, world_on=False, ledger_rows=[], notes_on=True)
    assert op.build_packet(out, stage="moment", user_text="not much, bit tired again today")["items"][0]["source"]["system"] == "notes"
    assert op.build_packet(out, stage="moment", user_text="the weather is nice")["items"] == []


@pytest.mark.asyncio
async def test_a_plan_they_asked_us_not_to_raise_keeps_their_words_and_the_day():
    from src.services import known_world as kw, opportunities as op
    o = owner()
    await write(o, {"notes": [note(area="preferences", text="The person asked the companion not to bring up Callie's wedding.", quote="barely slept")]}, datetime(2026, 9, 19),
                transcript="Him: don't bring the callie thing up, i'm not ready, i barely slept")
    async with async_session_maker() as db:
        # the quote must be in their words for a stated note; reuse a verified phrase and the boundary words in the text
        pass
    await write(o, {"notes": [note(area="friends", certainty="intention", when="2026-10-04", text="The person is reconsidering going to Callie's wedding.", quote="barely slept")]}, datetime(2026, 10, 4))
    async with async_session_maker() as db:
        got = [a for a in await notes.ask_candidates(db, WS, o, date(2026, 10, 4)) if "wedding" in a["text"]]
    assert len(got) == 1 and got[0]["asked"].startswith("They asked me on Sat 19 Sep not to bring this up")
    packet = op.build_packet({"candidates": got, "background_items": [], "now": "2026-10-04T09:00:00+01:00", "people_notes": {}}, stage="survey")
    assert "What they have asked of me:" in packet["text"] and "Sat 19 Sep" in packet["text"]


@pytest.mark.asyncio
async def test_retired_layers_do_not_run_and_the_rest_of_the_consolidation_is_unchanged(monkeypatch):
    from src.models.world import NotebookPage, SittingPreparation
    from tests.test_memory_pipeline import _fake_model
    monkeypatch.setattr(settings, "NOTES_ENABLED", True)
    monkeypatch.setattr(settings, "RETIRED_LAYERS", "attention,preparation,pages")
    o = owner()
    kinds = []

    def fn(kind, prompt, max_tokens, models):
        kinds.append(kind)
        if kind.startswith("edit:") or kind == "preparation" or "attention" in kind:
            raise AssertionError(f"a retired layer must not run: {kind}")
        if kind == "notes":
            return {"text": json.dumps({"notes": [note(area="exercise", text="They walk about five miles most evenings.", quote="five miles")]}), "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
        return _fake_model(kind, prompt, max_tokens, models)
    memory_pipeline.set_model_fn(fn)
    try:
        async with async_session_maker() as db:
            out = await memory_pipeline._consolidate(db, workspace_id=WS, owner=o, conversation_id="c", session_id="s", cfg=memory_pipeline.SOPHIE, companion_id="sophie",
                                                     session_time="2026-10-15T20:30:00+01:00", time_zone="Europe/London", sitting_kind="user",
                                                     messages=[{"id": "m1", "speaker": "user", "text": "i walk about five miles most evenings and it keeps me steady"},
                                                               {"id": "m2", "speaker": "assistant", "text": "that sounds like a good habit to keep"}])
        async with async_session_maker() as db:
            preps = (await db.execute(select(SittingPreparation).where(SittingPreparation.owner_peer_id == o))).scalars().all()
    finally:
        memory_pipeline.set_model_fn(None)
    assert out["status"] == "consolidated" and preps == []
    assert {"discovery", "handoff", "notes", "arc"} <= set(kinds) and not any(k.startswith("edit:") for k in kinds)
    assert len(await rows(o)) == 1


@pytest.mark.asyncio
async def test_where_we_left_off_is_the_last_two_sittings_dated_with_their_certainty_and_no_carried_mood():
    o = owner()
    await write(o, {"notes": [note(area="mood-low", text="The person felt low and flat.")]}, datetime(2026, 9, 10))
    await write(o, {"notes": [note(area="sleep-energy", text="The person slept badly.")]}, datetime(2026, 9, 12))
    await write(o, {"notes": [note(area="goals-plans", certainty="intention", text="The person means to register for the half in November."),
                              note(area="aspiration", certainty="hypothetical", text="The person daydreams about a boat."),
                              note(subject="Dad", area="family-parents", certainty="hearsay", text="Nell says Dad may sell the house.")]}, datetime(2026, 9, 14))
    async with async_session_maker() as db:
        text = await notes.where_we_left_off(db, WS, o, date(2026, 9, 15))
    assert text.startswith("Mon 14 Sep (yesterday):") and "Sat 12 Sep (3 days ago):" in text and "Thu 10 Sep" not in text
    assert "(a plan)" in text and "(said lightly)" in text and "(relayed by someone else)" in text and "the user" in text.lower() and "the person" not in text.lower()


@pytest.mark.asyncio
async def test_with_the_arc_retired_the_state_serves_the_last_sittings_as_dated_notes_and_falls_back_to_the_stored_arc(monkeypatch):
    monkeypatch.setattr(settings, "NOTES_ENABLED", True)
    monkeypatch.setattr(settings, "RETIRED_LAYERS", "arc")
    o = owner()
    async with async_session_maker() as db:
        before = await memory_pipeline.read_state(db, workspace_id=WS, owner=o)
    assert before["arc"]["text"] == memory_pipeline.SOPHIE.arc_seed                      # no notes yet: the stored arc
    await write(o, {"notes": [note(area="exercise", text="The person ran eight miles.")]}, datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
    async with async_session_maker() as db:
        after = await memory_pipeline.read_state(db, workspace_id=WS, owner=o)
    assert "(that day):" in after["arc"]["text"] and "ran eight miles" in after["arc"]["text"]


@pytest.mark.asyncio
async def test_the_brief_is_the_days_page_from_dates_and_changes_with_the_part_of_the_day():
    from src.models.world import LedgerItem
    o = owner()
    await write(o, {"notes": [note(subject="Mara", area="identity", key="birthday", when="2026-10-30", text="Mara's birthday is 30 October.", quote="barely slept"),
                              note(area="goals-plans", certainty="intention", when="2026-10-27", text="They plan to ring the plumber today.", quote="barely slept")]}, datetime(2026, 10, 27))
    await write(o, {"notes": [note(area="goals-plans", certainty="intention", when="2026-10-28", text="They plan to send the invoice today.", quote="barely slept")]}, datetime(2026, 10, 28))
    async with async_session_maker() as db:
        db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="appointment", title="Physio", status="open", situation_key="physio", expected_date=datetime(2026, 10, 28), expected_time="16:00"))
        await db.commit()
        from src.services import memory_pipeline as mp
        rows_ = await mp.open_ledger(db, WS, o)
        morning = await notes.brief(db, WS, o, datetime(2026, 10, 28, 8, 30), rows_)
        evening = await notes.brief(db, WS, o, datetime(2026, 10, 28, 19, 0), rows_)
    assert morning["part"] == "morning" and "Physio (16:00)" in morning["text"] and "Fri 30 Oct: Mara's birthday is 30 October" in morning["text"]
    assert evening["part"] == "evening" and "They plan to send the invoice today" in evening["text"] and "Coming up this week" not in evening["text"]


@pytest.mark.asyncio
async def test_the_prepared_brief_is_served_from_the_cache_and_rebuilt_the_moment_a_note_or_the_ledger_changes():
    from src.models.world import LedgerItem
    from src.services import brief_cache, memory_pipeline as mp
    o = owner()
    now = datetime(2026, 10, 28, 8, 30)
    async with async_session_maker() as db:
        first = await brief_cache.get(db, WS, o, now, [])
        again = await brief_cache.get(db, WS, o, now, [])
    assert first["cached"] is False and first["version"] == 1 and again["cached"] is True and again["version"] == 1
    async with async_session_maker() as db:                       # the person (or a tool) adds a ledger row: the page is stale at once
        db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="appointment", title="Dentist", status="open", situation_key="dentist",
                          expected_date=datetime(2026, 10, 28), expected_time="15:30"))
        await db.commit()
    async with async_session_maker() as db:
        rows_ = await mp.open_ledger(db, WS, o)
        changed = await brief_cache.get(db, WS, o, now, rows_)
    assert changed["cached"] is False and changed["version"] == 2 and changed["reason"] == "changed" and "Dentist (15:30)" in changed["text"]
    await write(o, {"notes": [note(area="goals-plans", certainty="intention", when="2026-10-28", text="They plan to send the invoice today.", quote="barely slept")]}, datetime(2026, 10, 28))
    async with async_session_maker() as db:
        rows_ = await mp.open_ledger(db, WS, o)
        after_note = await brief_cache.get(db, WS, o, now, rows_)
        steady = await brief_cache.get(db, WS, o, now, rows_)
    assert after_note["version"] == 3 and "send the invoice" in after_note["text"] and steady["cached"] is True and steady["version"] == 3
    assert (await brief_cache.get(db, WS, o, now, rows_, force=True))["version"] == 4                       # a forced rebuild is always possible


@pytest.mark.asyncio
async def test_a_life_aim_with_no_day_is_not_a_plan_awaiting_follow_up_and_the_profile_serves_who_they_are():
    o = owner()
    await write(o, {"notes": [note(subject="the person", area="identity", key="name", text="The person's name is Mukesh.", quote="barely slept"),
                              note(subject="the person", area="identity", key="residence", text="The person lives in Burwell.", quote="barely slept"),
                              note(subject="the person", area="preferences", key="interaction_style", text="The person wants a companion with opinions, not an agreeable one.", quote="barely slept"),
                              note(subject="the person", area="aspiration", certainty="intention", text="The person wants to travel more around Latin America.", quote="barely slept"),
                              note(subject="Ashley", area="partner", key="relationship_to_the_person", text="Ashley is the person's long-distance girlfriend.", quote="barely slept")]}, datetime(2026, 10, 28))
    async with async_session_maker() as db:
        plans = [a for a in await notes.asks(db, WS, o, date(2026, 10, 28)) if a["kind"] == "plan"]
        prof = await notes.profile(db, WS, o)
    assert plans == []
    assert "Who they are:" in prof["text"] and "Mukesh" in prof["text"] and "Burwell" in prof["text"] and "opinions" in prof["text"]
    assert "People who matter to them:" in prof["text"] and "Ashley: Ashley is the user's long-distance girlfriend" in prof["text"]


@pytest.mark.asyncio
async def test_the_state_carries_a_small_user_block_a_version_stamp_and_what_she_is_still_holding(monkeypatch):
    monkeypatch.setattr(settings, "NOTES_ENABLED", True)
    o = owner()
    await write(o, {"notes": [note(area="identity", key="name", text="The person's name is Mukesh.", quote="barely slept"), note(area="identity", key="age", text="The person is 43 years old.", quote="barely slept"),
                              note(area="preferences", key="interaction_style", text="The person wants a companion with opinions, not an agreeable one.", quote="barely slept"),
                              note(subject="Ashley", area="partner", key="relationship_to_the_person", text="Ashley is the person's long-distance girlfriend.", quote="barely slept"),
                              note(area="exercise", text="The person boxed two or three days a week.", quote="barely slept")]}, datetime(2026, 10, 28))
    async with async_session_maker() as db:
        before = await memory_pipeline.read_state(db, workspace_id=WS, owner=o)
        # her exploring page: one closed thread, one open one
        from src.models.world import NotebookPage
        db.add(NotebookPage(honcho_workspace_id=WS, owner_peer_id=o, page_key="exploring", product="sophie", version=99,
                            text="# Things\n\n**Old metaphor**\n*   It is resolved and retired.\n\n**Why running feels different on wet pavement**\n*   Still turning it over: the sound changes."))
        await db.commit()
    async with async_session_maker() as db:
        after = await memory_pipeline.read_state(db, workspace_id=WS, owner=o)
    u = before["user"]
    assert "[USER]" in u and "Mukesh" in u and "43" in u and "Ashley (the user's long-distance girlfriend)" in u and "opinions" in u and "know(" in u and "Ashley" in u.split("know(")[1]
    assert after["version"] != before["version"] and after["holding"] == "- Why running feels different on wet pavement: Still turning it over: the sound changes."


@pytest.mark.asyncio
async def test_a_name_or_a_topic_finds_what_is_noted_and_a_dateless_aim_stays_out_of_the_operational_picture(monkeypatch):
    from src.models.world import LedgerItem
    o = owner()
    await write(o, {"notes": [note(subject="Ashley", area="partner", key="relationship_to_the_person", text="Ashley is the person's long-distance girlfriend.", quote="barely slept"),
                              note(area="exercise", text="The person boxed two or three days a week and loved it.", quote="barely slept")]}, datetime(2026, 10, 28))
    async with async_session_maker() as db:
        assert "long-distance girlfriend" in await notes.know_text(db, WS, o, "Ashley")
        assert "boxed" in await notes.know_text(db, WS, o, "boxing")
        assert (await notes.mentions_text(db, WS, o, "Ashley called me today")).startswith("[WHO OR WHAT THEY MEAN")
        assert await notes.mentions_text(db, WS, o, "I went for a walk") == ""
        db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="aspiration", title="Travel more", status="open", situation_key="travel"))
        db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="commitment", title="Send the invoice", status="open", situation_key="inv"))
        await db.commit()
    from httpx import ASGITransport, AsyncClient
    from src.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/memory/ledger", params={"workspace_id": WS, "owner": o, "view": "awareness", "now": "2026-10-28T09:00:00+00:00", "time_zone": "Europe/London"})
    assert r.status_code == 200 and "Send the invoice" in r.json()["text"] and "Travel more" not in r.json()["text"]
