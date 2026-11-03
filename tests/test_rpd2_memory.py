"""RPD2 story-world memory: its own notes profile; every other product is untouched. The model is an injected fake; no network."""
import json
import uuid
from datetime import datetime

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.note import Note
from src.services import memory_pipeline, notes, product_memory, rpd2_memory

WS = "wsR"
TRANSCRIPT = (
    "Player: ** isa is at the club with the girls. a muscly man flirts with her **\n"
    "Character: (I laugh and show him my engagement ring.) This is my fiance. The only one I want.\n"
    "Player: ** marcus the security guard: \"take me back to yours?\" **\n"
    "Character: Back to mine.\n"
    "Player: ** back at home marcus kisses her on kai's bed **\n"
    "Character: (I shove him back.) No. Not on that bed. Get out.\n"
)


def owner():
    return f"world:rpd2:{uuid.uuid4().hex[:8]}"


def fake(payload):
    def fn(kind, prompt, max_tokens, models):
        if kind == "notes":
            return {"text": json.dumps(payload), "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
        return {"text": "ok", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    return fn


def story_note(**kw):
    base = {"subject": "the story", "area": "event", "certainty": "stated", "when": "", "key": "", "text": "x", "quote": "", "resolves": ""}
    base.update(kw)
    return base


def test_rpd2_is_a_registered_product_with_a_story_profile_and_others_are_unchanged():
    assert "rpd2" in product_memory.known()
    cfg = product_memory.get("rpd2")
    assert cfg.notes_profile is rpd2_memory.PROFILE and cfg.notes_profile.evidence == "all" and not cfg.ledger_enabled
    assert product_memory.get("sophie").notes_profile is None and product_memory.get("bloom").notes_profile is None


def test_the_profile_prompt_renders_its_areas_and_cap():
    text = rpd2_memory.PROFILE.system % ("\n".join(f"  - {k}: {v}" for k, v in rpd2_memory.PROFILE.areas.items()), rpd2_memory.PROFILE.max_notes)
    assert "  - event:" in text and "Up to 40 notes" in text and "NEVER use the names of the two main characters" in text


def test_story_notes_are_verified_against_both_sides_and_use_story_areas():
    p = rpd2_memory.PROFILE
    out, stats = notes.clean([
        story_note(text="Marcus asked Isa to take him home.", quote="take me back to yours"),            # the player's narration: verified under evidence=all
        story_note(text="Isa agreed.", quote="Back to mine."),                                          # the character's line: verified
        story_note(text="Marcus kissed Isa on Kai's bed.", area="not-an-area", quote="made up quote"),   # unknown area -> other; quote not in transcript -> stated downgraded
    ], TRANSCRIPT, p.areas, p.max_notes)
    by = {n["text"]: n for n in out}
    assert by["Marcus asked Isa to take him home."]["quote_verified"] and by["Marcus asked Isa to take him home."]["certainty"] == "stated"
    assert by["Isa agreed."]["quote_verified"]
    assert by["Marcus kissed Isa on Kai's bed."]["area"] == "other" and by["Marcus kissed Isa on Kai's bed."]["certainty"] == "unclear"
    assert stats["downgraded"] == 1


@pytest.mark.asyncio
async def test_a_story_sitting_is_kept_event_by_event_and_naming_marcus_brings_the_events_back():
    o = owner()
    payload = {"notes": [
        story_note(subject="Marcus", area="cast", key="role", text="Marcus is a security guard at the club who walked Isa home.", quote="marcus the security guard"),
        story_note(text="Isa told Marcus she was engaged and showed him the ring at the club.", quote="engagement ring"),
        story_note(text="Isa agreed to take Marcus back to her house.", quote="Back to mine."),
        story_note(text="Marcus kissed Isa on Kai's bed at the house; she shoved him away and told him to get out.", quote="Not on that bed"),
    ]}
    memory_pipeline.set_model_fn(fake(payload))
    try:
        async with async_session_maker() as db:
            out = await notes.write(db, workspace_id=WS, owner=o, product="rpd2", session_id="s1", run_id=None, transcript=TRANSCRIPT, person_label="Player",
                                    companion_name="Character", session_day=datetime(2026, 11, 2), weekday="Monday", profile=rpd2_memory.PROFILE)
    finally:
        memory_pipeline.set_model_fn(None)
    assert out["status"] == "ok" and out["notes"] == 4 and out.get("still_relative") == 0
    async with async_session_maker() as db:
        stored = list((await db.execute(select(Note).where(Note.owner_peer_id == o))).scalars().all())
        text, named = await notes.mentions_text(db, WS, o, "what did you do with marcus?")
    assert all(r.certainty == "stated" and r.quote_verified for r in stored)
    assert named == ["Marcus"]
    assert "kissed Isa on Kai's bed" in text and "took Marcus back" not in text and "back to her house" in text


def test_a_cast_note_filed_under_the_story_is_refiled_under_the_person_it_describes():
    p = rpd2_memory.PROFILE
    out, _ = notes.clean([story_note(subject="the story", area="cast", key="role", text="Marcus is a security guard at the club who walked Isa home.", quote="marcus the security guard"),
                          story_note(subject="the story", area="event", text="Marcus is mentioned in an event note and stays under the story.")], TRANSCRIPT, p.areas, p.max_notes, p)
    assert [n["subject"] for n in out] == ["Marcus", "the story"]


def test_an_event_whose_quote_is_not_word_for_word_is_still_stated_in_a_story_but_not_in_personal_notes():
    p = rpd2_memory.PROFILE
    raw = [story_note(text="Isa took the ring off.", quote="she took the ring off, he thought")]
    assert notes.clean(raw, TRANSCRIPT, p.areas, p.max_notes, p)[0][0]["certainty"] == "stated"
    assert notes.clean(raw, TRANSCRIPT)[0][0]["certainty"] == "unclear"        # the default path is unchanged


@pytest.mark.asyncio
async def test_the_story_and_the_relationship_are_never_looked_up_as_people_and_a_cast_gets_a_long_mention_list():
    o = owner()
    ev = [story_note(text=f"Marcus did thing number {i} with Isa.", quote="Back to mine.") for i in range(12)]
    payload = {"notes": [story_note(subject="Marcus", area="cast", key="role", text="Marcus is a security guard at the club.", quote="marcus the security guard"), *ev,
                         story_note(subject="the relationship", area="bond", text="Kai and Isa are engaged.", quote="engagement ring")]}
    memory_pipeline.set_model_fn(fake(payload))
    try:
        async with async_session_maker() as db:
            await notes.write(db, workspace_id=WS, owner=o, product="rpd2", session_id="s1", run_id=None, transcript=TRANSCRIPT, person_label="Player",
                              companion_name="Character", session_day=datetime(2026, 11, 2), weekday="Monday", profile=rpd2_memory.PROFILE)
    finally:
        memory_pipeline.set_model_fn(None)
    async with async_session_maker() as db:
        names = [p["name"] for p in await notes.people(db, WS, o)]
        text, named = await notes.mentions_text(db, WS, o, "the story so far, what did marcus do")
    assert names == ["Marcus"] and named == ["Marcus"] and "could mean" not in text
    assert text.count("Marcus did thing number") == 12             # not cut to the standard six


@pytest.mark.asyncio
async def test_a_rewind_retracts_the_story_memory_a_discarded_message_fed_and_leaves_the_rest():
    import json
    from datetime import datetime, timedelta
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.note import Note
    from src.models.world import ContinuingArc, MemoryRun
    from src.services import world_rewind
    WS, OWNER, t0 = "rpd2::w-rw-mem", "world:rpd2:u1:isa:c9", datetime.utcnow() - timedelta(hours=2)
    async with async_session_maker() as db:
        r1 = MemoryRun(honcho_workspace_id=WS, owner_peer_id=OWNER, conversation_id="c9", session_id="s1", status="consolidated", created_at=t0,
                       covered_ids_json=json.dumps(["t1-u", "t1-a"]), bundle_json=json.dumps({"arc_before": ""}))
        r2 = MemoryRun(honcho_workspace_id=WS, owner_peer_id=OWNER, conversation_id="c9", session_id="s2", status="consolidated", created_at=t0 + timedelta(hours=1),
                       covered_ids_json=json.dumps(["t2-u", "t2-a"]), bundle_json=json.dumps({"arc_before": "They made a pact."}))
        db.add_all([r1, r2]); await db.commit()
        kept = Note(honcho_workspace_id=WS, owner_peer_id=OWNER, product="rpd2", run_id=r1.id, sitting_on=t0, subject="the story", text="They made a pact.")
        ghost = Note(honcho_workspace_id=WS, owner_peer_id=OWNER, product="rpd2", run_id=r2.id, sitting_on=t0, subject="Marco", text="Marco came over.")
        db.add_all([kept, ghost, ContinuingArc(honcho_workspace_id=WS, owner_peer_id=OWNER, product="rpd2", text="They made a pact. Marco came over.")]); await db.commit()

        none = await world_rewind.rewind(db, workspace_id="w-rw-mem", owner=OWNER, session_ids=[], since=t0, deleted=[{"id": "t9-u", "speaker": "user", "text": "x"}], product="rpd2")
        assert none["memory_runs_retracted"] == 0                                             # nothing consolidated has read it: a regenerated last reply costs nothing

        out = await world_rewind.rewind(db, workspace_id="w-rw-mem", owner=OWNER, session_ids=[], since=t0, deleted=[{"id": "t2-u", "speaker": "user", "text": "x"}], product="rpd2")
        assert out["memory_runs_retracted"] == 1 and out["notes_removed"] == 1
        texts = [n.text for n in (await db.execute(select(Note).where(Note.honcho_workspace_id == WS))).scalars().all()]
        assert texts == ["They made a pact."]
        arc = (await db.execute(select(ContinuingArc).where(ContinuingArc.honcho_workspace_id == WS))).scalars().one()
        assert arc.text == "They made a pact."                                               # back to before the run that read the ghost
        assert (await db.get(MemoryRun, r2.id)).status == "retracted" and (await db.get(MemoryRun, r1.id)).status == "consolidated"

        other = await world_rewind.rewind(db, workspace_id="w-rw-mem", owner=OWNER, session_ids=[], since=t0, deleted=[{"id": "t1-u", "speaker": "user", "text": "x"}])
        assert "memory_runs_retracted" not in other                                           # callers that do not say they run the pipeline are exactly as before
