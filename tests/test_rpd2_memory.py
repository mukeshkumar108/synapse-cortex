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
