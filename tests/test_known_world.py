"""Connected understanding: deterministic views over stored entities, links and the records they point to.
No model anywhere: a state change in a source record is reflected in the next read."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.known_world import CueExposure, KnownEntity, KnownLink
from src.models.world import AttentionAction, LedgerItem
from src.services import known_world as kw

WS = "wsK"
NOW = datetime(2026, 10, 20, 14, 0)           # naive -> read in the zone given to Ctx


def ctx():
    return kw.Ctx(NOW, "Europe/London")


def owner():
    return f"u-{uuid.uuid4().hex[:8]}"


async def seed(o):
    """Morgan (adviser on Bloom, stated), Bloom (project), Church pilot (situation), a worry; ledger items linked by key."""
    async with async_session_maker() as db:
        morgan = await kw.create(db, WS, o, name="Morgan", kind="person", summary="Adviser who is helping shape Bloom's first pilot", aliases=["Morgan Lee"])
        bloom = await kw.create(db, WS, o, name="Bloom", kind="project", summary="A daily reflection companion app", aliases=["the Bloom app"])
        pilot = await kw.create(db, WS, o, name="Missionary pilot", kind="situation", summary="Testing Bloom with missionaries next month; scope not yet decided",
                                aliases=["the pilot"], basis="inferred")
        worry = await kw.create(db, WS, o, name="Niece's medical tests", kind="situation", summary="Niece had tests last Thursday; no result recorded", sensitive=True)
        await kw.link(db, WS, o, from_id=morgan.id, relation="adviser on", target_kind="entity", target_ref=str(bloom.id), basis="stated", evidence="Morgan is advising on Bloom")
        await kw.link(db, WS, o, from_id=morgan.id, relation="possibly a future co-founder of", target_kind="entity", target_ref=str(bloom.id), basis="inferred")
        await kw.link(db, WS, o, from_id=pilot.id, relation="a pilot of", target_kind="entity", target_ref=str(bloom.id), basis="inferred")
        for key, title, d, t, role, st in (("morgan-meeting", "Meeting with Morgan", "2026-10-22", "15:00", "happens", "open"),
                                           ("pilot-scope", "Decide the pilot scope", "2026-10-25", "", "deadline", "waiting"),
                                           ("bloom-demo", "Send the Bloom demo", "2026-10-18", "", "deadline", "done")):
            db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="event", title=title, status=st, situation_key=key,
                              expected_date=datetime.strptime(d, "%Y-%m-%d"), expected_time=t, time_role=role, time_basis="stated" if t else "",
                              time_zone="Europe/London", waiting_on="Morgan" if key == "pilot-scope" else "", updated_at=datetime(2026, 10, 19)))
            await kw.link(db, WS, o, from_id=morgan.id, relation="involved in", target_kind="ledger", target_ref=key, basis="stated", evidence="x")
        await db.commit()
        return morgan.id, bloom.id, pilot.id, worry.id


@pytest.mark.asyncio
async def test_a_mention_resolves_to_a_self_contained_snapshot_with_connections_read_from_their_sources():
    o = owner()
    await seed(o)
    async with async_session_maker() as db:
        pk = await kw.packet(db, WS, o, "I spoke to Morgan again", ctx())
    t = pk["mentions"]
    assert t.startswith("[WHO OR WHAT THEY MEAN") and "Morgan (person)" in t
    assert "Morgan: adviser on Bloom" in t                                           # stated: plain
    assert "possibly a future co-founder of Bloom (inferred, not confirmed)" in t   # inferred: always labelled, never plain fact
    assert "Meeting with Morgan: Thu 22 Oct, 3:00pm" in t                            # the operational matter is READ from the ledger
    assert "Decide the pilot scope" in t and "waiting on Morgan" in t
    assert "Send the Bloom demo" not in t.split("Open matters:")[1]                  # closed items are not open matters
    for banned in ("consider", "perhaps", "you could", "should ask", "if relevant"):
        assert banned not in t.lower()
    assert {"source": "entity", "ref": str((await _id(o, "Morgan")))} in pk["shown"]


async def _id(o, name):
    async with async_session_maker() as db:
        return (await db.execute(select(KnownEntity).where(KnownEntity.owner_peer_id == o, KnownEntity.name == name))).scalars().one().id


@pytest.mark.asyncio
async def test_a_state_change_in_a_source_record_shows_up_with_no_model_and_no_copying():
    o = owner()
    await seed(o)
    async with async_session_maker() as db:
        before = (await kw.entity_view(db, WS, o, "Morgan", ctx(), "snapshot"))["text"]
        row = (await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == o, LedgerItem.situation_key == "morgan-meeting"))).scalars().one()
        row.status, row.expected_date, row.expected_time = "done", datetime(2026, 10, 22), "15:00"
        pilot = (await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == o, LedgerItem.situation_key == "pilot-scope"))).scalars().one()
        pilot.expected_date, pilot.status, pilot.waiting_on = datetime(2026, 10, 27), "open", ""
        await db.commit()
        after = (await kw.entity_view(db, WS, o, "Morgan", ctx(), "snapshot"))["text"]
    assert "Meeting with Morgan: Thu 22 Oct, 3:00pm" in before and "Meeting with Morgan: Thu 22 Oct" not in after.split("Open matters:")[1]
    assert "Tue 27 Oct" in after and "waiting on Morgan" not in after.split("Decide the pilot scope")[1].split("\n")[0]


@pytest.mark.asyncio
async def test_deeper_views_add_history_and_evidence_on_demand_only():
    o = owner()
    await seed(o)
    async with async_session_maker() as db:
        snap = (await kw.entity_view(db, WS, o, "Morgan", ctx(), "snapshot"))["text"]
        deep = (await kw.entity_view(db, WS, o, "Morgan", ctx(), "deep"))["text"]
        conn = (await kw.entity_view(db, WS, o, "Morgan Lee", ctx(), "connected"))["text"]      # an alias resolves
    assert "Supporting evidence" not in snap and "Supporting evidence" in deep and "Morgan is advising on Bloom" in deep
    assert "Recently closed" in conn and "Send the Bloom demo: done" in conn and "Also known as: Morgan Lee" in conn
    assert len(snap) < len(conn) <= len(deep) + 400


@pytest.mark.asyncio
async def test_overview_is_selective_current_and_respects_boundaries():
    o = owner()
    mid, bid, pid, wid = await seed(o)
    async with async_session_maker() as db:
        text, shown = await kw.overview_text(db, WS, o, ctx())
    assert text.startswith("[THEIR WORLD RIGHT NOW") and "Morgan (person)" in text and "Bloom (project)" in text
    assert "Niece's medical tests (sensitive): Niece had tests last Thursday; no result recorded. Last update today." in text
    assert "possibly" not in text or "(inferred, not confirmed)" in text                # an inferred entity is labelled
    # boundary: the person said not to raise the worry -> it leaves the overview, the memory stays and a mention still resolves
    async with async_session_maker() as db:
        w = await kw.get(db, WS, o, wid)
        w.suppressed = True
        await db.commit()
        text2, _ = await kw.overview_text(db, WS, o, ctx())
        mention, _ = await kw.mentions_text(db, WS, o, "any news on my niece's medical tests?", ctx())
    assert "Niece's medical tests" not in text2 and "Niece's medical tests" in mention
    assert "Not to be raised unprompted" in mention
    # a product that holds back sensitive detail
    async with async_session_maker() as db:
        w = await kw.get(db, WS, o, wid)
        w.suppressed = False
        await db.commit()
        minimal, _ = await kw.overview_text(db, WS, o, ctx(), sensitive="minimal")
    assert "Niece had tests last Thursday" not in minimal and "details available if they raise it" in minimal


@pytest.mark.asyncio
async def test_exposure_is_counted_per_sitting_not_per_turn_and_wears_out_unengaged_situations():
    o = owner()
    mid, bid, pid, wid = await seed(o)
    async with async_session_maker() as db:
        w = await kw.get(db, WS, o, wid)
        w.last_touched_at = datetime(2026, 10, 10)                                     # 10 days old
        await db.commit()
        t0 = datetime(2026, 10, 20, 9, 0)
        for turn in range(5):                                                          # five turns of ONE sitting
            await kw.record_exposure(db, WS, o, [{"source": "entity", "ref": str(wid)}], now=t0 + timedelta(minutes=turn))
        x = (await db.execute(select(CueExposure).where(CueExposure.owner_peer_id == o))).scalars().one()
        assert x.shown_count == 1
        for sitting in (1, 2):                                                         # two more sittings
            await kw.record_exposure(db, WS, o, [{"source": "entity", "ref": str(wid)}], now=t0 + timedelta(hours=3 * sitting))
        await db.commit()
        again = (await db.execute(select(CueExposure).where(CueExposure.owner_peer_id == o))).scalars().one()
        assert again.shown_count == 3
        text, _ = await kw.overview_text(db, WS, o, ctx())
        assert "Niece's medical tests" not in text                                     # shown 3 sittings, never engaged, stale: stops occupying the overview
        await kw.record_engagement(db, WS, o, "entity", str(wid), now=datetime(2026, 10, 20, 13, 0))
        await db.commit()
        text2, _ = await kw.overview_text(db, WS, o, ctx())
        assert "Niece's medical tests" in text2                                        # engagement resets it
        people = await kw.entity_view(db, WS, o, "Morgan", ctx())
        assert people["found"]                                                         # entity views are never worn out, only the overview selection


@pytest.mark.asyncio
async def test_ambiguous_names_are_reported_not_guessed_and_merges_keep_resolving():
    o = owner()
    async with async_session_maker() as db:
        a = await kw.create(db, WS, o, name="Morgan Lee", kind="person", summary="Adviser on Bloom", aliases=["Morgan"])
        b = await kw.create(db, WS, o, name="Morgan Ellis", kind="person", summary="A nephew", aliases=["Morgan"])
        await db.commit()
        txt, shown = await kw.mentions_text(db, WS, o, "Morgan called", ctx())
        assert "\"morgan\" could mean" in txt and "Morgan Lee (person: Adviser on Bloom)" in txt and "Morgan Ellis (person: A nephew)" in txt
        assert "has not been established" in txt and shown == []
        txt2, _ = await kw.mentions_text(db, WS, o, "Morgan Ellis called", ctx())
        assert "Morgan Ellis (person)" in txt2 and "could mean" not in txt2          # the more specific name resolves it
        dup = await kw.create(db, WS, o, name="Mo Lee", kind="person", summary="")
        kept = await kw.merge(db, WS, o, a.id, dup.id)
        await db.commit()
        assert kept.id == a.id and (await kw.get(db, WS, o, dup.id)).id == a.id      # the absorbed id still resolves to the survivor
        assert [e.name for e in await kw.find(db, WS, o, "Mo Lee")] == ["Morgan Lee"]


@pytest.mark.asyncio
async def test_a_new_relation_between_the_same_pair_supersedes_the_old_one_and_history_is_kept():
    o = owner()
    async with async_session_maker() as db:
        m = await kw.create(db, WS, o, name="Morgan", kind="person")
        b = await kw.create(db, WS, o, name="Bloom", kind="project")
        l1, c1 = await kw.link(db, WS, o, from_id=m.id, relation="adviser on", target_kind="entity", target_ref=str(b.id), basis="inferred")
        l1b, c1b = await kw.link(db, WS, o, from_id=m.id, relation="adviser on", target_kind="entity", target_ref=str(b.id), basis="stated", evidence="he advises")
        assert c1 and not c1b and l1b.id == l1.id and l1b.basis == "stated"          # confirmed inference is upgraded, not duplicated
        l2, c2 = await kw.link(db, WS, o, from_id=m.id, relation="co-founder of", target_kind="entity", target_ref=str(b.id), basis="stated", evidence="he joined as co-founder")
        assert c2 and l1.status == "current"                                           # a different relation COEXISTS until the connect pass supersedes the old one
        await kw.supersede(db, WS, o, l1.id, "he is now a co-founder, not just an adviser")
        await db.commit()
        cur = await kw.entity_view(db, WS, o, "Morgan", ctx(), "snapshot")
        hist = await kw.entity_view(db, WS, o, "Morgan", ctx(), "connected")
    assert "co-founder of Bloom" in cur["text"] and "adviser on" not in cur["text"]
    assert "Earlier understanding (superseded)" in hist["text"] and "adviser on" in hist["text"].split("Earlier understanding")[1]


@pytest.mark.asyncio
async def test_inspect_exposes_everything_with_provenance():
    o = owner()
    await seed(o)
    async with async_session_maker() as db:
        dump = await kw.inspect(db, WS, o)
    names = {e["name"] for e in dump["entities"]}
    assert {"Morgan", "Bloom", "Missionary pilot", "Niece's medical tests"} <= names
    assert any(l["relation"] == "adviser on" and l["basis"] == "stated" and l["target"] == "Bloom" and l["evidence"] for l in dump["links"])
    assert any(l["relation"].startswith("possibly") and l["basis"] == "inferred" for l in dump["links"])


@pytest.mark.asyncio
async def test_people_are_nominated_by_first_name_and_an_ambiguous_first_name_is_reported_not_guessed():
    o = owner()
    async with async_session_maker() as db:
        await kw.create(db, WS, o, name="Morgan Ellis", kind="person", summary="Adviser on Bloom")
        await kw.create(db, WS, o, name="Priya Nair", kind="person", summary="New manager")
        await kw.create(db, WS, o, name="Taking the lead", kind="decision", summary="x")
        await db.commit()
        txt, shown = await kw.mentions_text(db, WS, o, "Morgan texted me again about the pilot", ctx())
        assert "Morgan Ellis (person)" in txt and len(shown) == 1
        txt, _ = await kw.mentions_text(db, WS, o, "Priya wants an update", ctx())
        assert "Priya Nair (person)" in txt
        txt, shown = await kw.mentions_text(db, WS, o, "the lead is weighing on me", ctx())
        assert shown == []                      # first names are for people; a situation's first word is not a name
        await kw.create(db, WS, o, name="Morgan Lee", kind="person", summary="A friend")
        await db.commit()
        txt, shown = await kw.mentions_text(db, WS, o, "Morgan texted", ctx())
        assert "could mean" in txt and shown == []


@pytest.mark.asyncio
async def test_the_person_anchor_is_never_nominated_or_listed_among_their_people():
    o = owner()
    async with async_session_maker() as db:
        s = await kw.ensure_self(db, WS, o)
        assert (await kw.ensure_self(db, WS, o)).id == s.id                            # idempotent
        await kw.create(db, WS, o, name="Ashley", kind="person", summary="Partner")
        await db.commit()
        txt, shown = await kw.mentions_text(db, WS, o, "the person said hello to Ashley", ctx())
        assert "Ashley (person)" in txt and "the person (self)" not in txt and len(shown) == 1
        ov, _ = await kw.overview_text(db, WS, o, ctx())
        assert "the person (self)" not in ov
