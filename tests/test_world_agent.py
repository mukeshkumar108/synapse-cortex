"""The connect pass: interface guarantees (what code refuses or enforces), the pipeline hook, and the flag. Models are scripted."""
import json
import uuid
from datetime import datetime

import pytest
from sqlmodel import select

from src.config import settings
from src.db import async_session_maker
from src.models.known_world import KnownEntity, KnownLink
from src.models.world import AttentionAction, LedgerItem, MemoryRun
from src.services import attention_cycle as ac, known_world as kw, maintenance_agent as ma, memory_pipeline as mp, world_agent as wa

WS = "wsW"
TRANSCRIPT = ('Person: Morgan is advising me on Bloom, and we decided to test it with the missionaries next month.\n'
              'Person: My niece has her medical tests on Thursday and I am worried.')


def _tc(i, name, args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


def _script(steps, seen=None):
    st = {"n": 0}

    async def chat(model, messages):
        if seen is not None:
            seen.append(list(messages))
        step = steps[min(st["n"], len(steps) - 1)]
        st["n"] += 1
        return {"content": "", "tool_calls": step.get("calls", []), "finish_reason": step.get("finish_reason", "tool_calls"),
                "model": model, "provider": "fake", "usage": {}}
    return chat


def owner():
    return f"u-{uuid.uuid4().hex[:8]}"


async def run(o, steps, transcript=TRANSCRIPT, seen=None, ledger_ctx="", person_label=""):
    wa.set_chat_fn(_script(steps, seen))
    try:
        async with async_session_maker() as db:
            return await wa.run(db, workspace_id=WS, owner=o, session_id="s1", run_id=None, transcript=transcript,
                                ledger_context=ledger_ctx, date_reference="Today is Monday 2026-10-19", time_zone="Europe/London",
                                person_label=person_label)
    finally:
        wa.set_chat_fn(None)


async def rows(o, model):
    async with async_session_maker() as db:
        return (await db.execute(select(model).where(model.owner_peer_id == o))).scalars().all()


FIN = lambda i: {"calls": [_tc(i, "finish", {"summary": "ok", "considered": "nothing notable"})]}


@pytest.mark.asyncio
async def test_a_stated_claim_needs_a_real_quote_otherwise_it_is_stored_as_inferred():
    o = owner()
    steps = [{"calls": [_tc(1, "list_entities", {}),
                        _tc(2, "create_entity", {"name": "Morgan", "kind": "person", "summary": "Advising on Bloom", "basis": "stated", "evidence": "Morgan is advising me on Bloom"}),
                        _tc(3, "create_entity", {"name": "Bloom", "kind": "project", "summary": "A reflection companion", "basis": "stated", "evidence": "Bloom is a cult"})]},
             {"calls": [_tc(4, "list_entities", {})]}, FIN(5)]
    out = await run(o, steps)
    ents = {e.name: e for e in await rows(o, KnownEntity)}
    assert ents["Morgan"].basis == "stated" and ents["Bloom"].basis == "inferred"        # the invented quote was not in the transcript
    assert out["status"] == "verified" and out["changes"]["created"] == 2


@pytest.mark.asyncio
async def test_links_point_at_real_records_and_inferred_is_never_promoted_without_a_quote():
    o = owner()
    async with async_session_maker() as db:
        db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="event", title="Pilot kickoff", status="open", situation_key="pilot-kickoff",
                          expected_date=datetime(2026, 11, 3)))
        await db.commit()
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Morgan", "kind": "person"}), _tc(3, "create_entity", {"name": "Bloom", "kind": "project"})]},
             {"calls": [_tc(4, "list_entities", {})]}]
    await run(o, steps)
    ids = {e.name: str(e.id) for e in await rows(o, KnownEntity)}
    steps2 = [{"calls": [_tc(1, "list_entities", {}),
                         _tc(2, "link_entity", {"from_id": ids["Morgan"], "relation": "adviser on", "to_entity_id": ids["Bloom"], "basis": "stated", "evidence": "Morgan is advising me on Bloom"}),
                         _tc(3, "link_entity", {"from_id": ids["Morgan"], "relation": "may become co-founder of", "to_entity_id": ids["Bloom"], "basis": "stated"}),
                         _tc(4, "link_entity", {"from_id": ids["Morgan"], "relation": "involved in", "ledger_key": "pilot-kickoff", "basis": "inferred"}),
                         _tc(5, "link_entity", {"from_id": ids["Morgan"], "relation": "involved in", "ledger_key": "does-not-exist", "basis": "inferred"}),
                         _tc(6, "link_entity", {"from_id": ids["Morgan"], "relation": "x", "basis": "inferred"}),
                         _tc(7, "link_entity", {"from_id": ids["Morgan"], "relation": "x", "to_entity_id": ids["Bloom"], "ledger_key": "pilot-kickoff", "basis": "inferred"}),
                         _tc(8, "link_entity", {"from_id": ids["Bloom"], "relation": "self", "to_entity_id": ids["Bloom"], "basis": "inferred"})]},
              {"calls": [_tc(9, "list_entities", {})]}, FIN(10)]
    seen = []
    out = await run(o, steps2, seen=seen)
    links = {l.relation: l for l in await rows(o, KnownLink)}
    assert links["adviser on"].basis == "stated" and links["adviser on"].evidence.startswith("Morgan is advising")
    assert links["may become co-founder of"].basis == "inferred" and links["may become co-founder of"].evidence == ""       # no quote -> not stated
    assert links["involved in"].target_kind == "ledger" and links["involved in"].target_ref == "pilot-kickoff"
    results = [m["content"] for m in seen[-1] if m.get("role") == "tool"]
    assert any("no ledger record with key 'does-not-exist'" in r for r in results)
    assert any("exactly one target" in r for r in results)
    assert any("cannot be linked to itself" in r for r in results)
    assert any("recorded as inferred" in r for r in results)
    assert out["status"] == "verified"


@pytest.mark.asyncio
async def test_unknown_malformed_and_truncated_calls_never_run_and_duplicates_are_refused():
    o = owner()
    seen = []
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Morgan", "kind": "person", "age": 40}),
                        _tc(3, "create_entity", '{"name": "Half'), _tc(4, "create_entity", {"name": "Morgan", "kind": "person"})]},
             {"calls": [_tc(5, "create_entity", {"name": "Cut", "kind": "person"})], "finish_reason": "length"},
             {"calls": [_tc(6, "create_entity", {"name": "Morgan", "kind": "person"}), _tc(7, "create_entity", {"name": "Morgan", "kind": "person"})]},
             {"calls": [_tc(8, "list_entities", {})]}, FIN(9)]
    await run(o, steps, seen=seen)
    names = [e.name for e in await rows(o, KnownEntity) if e.kind != "self"]
    assert names == ["Morgan"]                                                      # one real create; the rest refused
    tool_msgs = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool")
    assert "unsupported argument(s) for create_entity: age" in tool_msgs and "not a valid JSON object" in tool_msgs and "cut off" in tool_msgs
    assert "already exists" in tool_msgs


@pytest.mark.asyncio
async def test_exact_names_do_not_collide_but_similar_names_may_coexist():
    o = owner()
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Morgan Lee", "kind": "person", "aliases": ["Morgan"]}),
                        _tc(3, "create_entity", {"name": "Morgan Ellis", "kind": "person"})]}, {"calls": [_tc(4, "list_entities", {})]}, FIN(5)]
    out = await run(o, steps)
    assert sorted(e.name for e in await rows(o, KnownEntity) if e.kind != "self") == ["Morgan Ellis", "Morgan Lee"] and out["status"] == "verified"


@pytest.mark.asyncio
async def test_finish_needs_a_reread_and_a_considered_line_and_is_never_trapped():
    o = owner()
    seen = []
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Bloom", "kind": "project"})]},
             {"calls": [_tc(3, "finish", {"summary": "x"})]},                       # no re-read, no considered
             {"calls": [_tc(4, "finish", {"summary": "x", "considered": ""})]},      # still missing
             {"calls": [_tc(5, "finish", {"summary": "x", "considered": "n/a"})]}]   # third try is accepted but flagged
    out = await run(o, steps, seen=seen)
    assert out["status"] == "finished_unchecked" and out["gate_failures"]
    refusals = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"])
    assert "Re-read" in refusals and "considered is required" in refusals


@pytest.mark.asyncio
async def test_updates_follow_the_rules_status_boundaries_aliases_and_renames_keep_resolving():
    o = owner()
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Niece's medical tests", "kind": "health", "summary": "Tests on Thursday", "sensitive": True})]},
             {"calls": [_tc(3, "list_entities", {})]}]
    await run(o, steps)
    (e,) = [x for x in await rows(o, KnownEntity) if x.kind != "self"]
    steps2 = [{"calls": [_tc(1, "list_entities", {}),
                         _tc(2, "update_entity", {"id": str(e.id), "status": "merged"}),
                         _tc(3, "update_entity", {"id": str(e.id), "suppressed": True, "add_aliases": ["Anna's tests"], "summary": "Tests were on Thursday; no result recorded"}),
                         _tc(4, "update_entity", {"id": str(e.id), "name": "Anna's medical tests"})]},
              {"calls": [_tc(5, "get_entity", {"id": str(e.id)})]}, FIN(6)]
    seen = []
    await run(o, steps2, seen=seen)
    (e2,) = [x for x in await rows(o, KnownEntity) if x.kind != "self"]
    assert e2.suppressed and e2.sensitive and e2.name == "Anna's medical tests" and "no result recorded" in e2.summary and e2.status == "active"
    async with async_session_maker() as db:
        assert [x.name for x in await kw.find(db, WS, o, "Niece's medical tests")] == ["Anna's medical tests"]      # the old name still resolves
        assert [x.name for x in await kw.find(db, WS, o, "Anna's tests")] == ["Anna's medical tests"]
    assert any("status must be active, dormant or resolved" in m["content"] for msgs in seen for m in msgs if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_a_corrected_relationship_is_superseded_with_history_and_a_merge_keeps_one_survivor():
    o = owner()
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Morgan", "kind": "person"}), _tc(3, "create_entity", {"name": "Bloom", "kind": "project"}),
                        _tc(4, "create_entity", {"name": "Mo", "kind": "person"})]}, {"calls": [_tc(5, "list_entities", {})]}]
    await run(o, steps)
    ids = {e.name: str(e.id) for e in await rows(o, KnownEntity)}
    steps2 = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "link_entity", {"from_id": ids["Morgan"], "relation": "adviser on", "to_entity_id": ids["Bloom"], "basis": "inferred"})]},
              {"calls": [_tc(3, "get_entity", {"id": ids["Morgan"]})]}]
    await run(o, steps2)
    (lk,) = await rows(o, KnownLink)
    steps3 = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "supersede_link", {"link_id": str(lk.id), "reason": "he is a co-founder, not an adviser"}),
                         _tc(3, "link_entity", {"from_id": ids["Morgan"], "relation": "co-founder of", "to_entity_id": ids["Bloom"], "basis": "stated", "evidence": "Morgan is advising me on Bloom"}),
                         _tc(4, "merge_entities", {"keep_id": ids["Morgan"], "absorb_id": ids["Mo"]})]},
              {"calls": [_tc(5, "list_entities", {})]}, FIN(6)]
    out = await run(owner_o := o, steps3)
    links = await rows(o, KnownLink)
    assert sorted((l.relation, l.status) for l in links) == [("adviser on", "superseded"), ("co-founder of", "current")]
    ents = {e.name: e for e in await rows(o, KnownEntity)}
    assert ents["Mo"].status == "merged" and ents["Mo"].merged_into_id == ents["Morgan"].id and out["changes"]["superseded"] == 1 and out["changes"]["merged"] == 1


# ------------------------------------------------------------- pipeline ----

class Models:
    async def __call__(self, kind, prompt, max_tokens, models):
        text = {"discovery": "They discussed Bloom with Morgan and a worry about a niece. Enough findings for notes here.", "handoff": "Bloom and Morgan.",
                "arc": "They discussed Bloom.", "preparation": "Notes.",
                "ledger": 'ITEM: Meeting with Morgan\nKIND: event\nTIMING: Thursday\nEVIDENCE: "Morgan is advising me on Bloom"\n'}.get(kind)
        if kind.startswith("edit:"):
            text = f"# {kind.split(':', 1)[1]}\n\ntext"
        return {"text": text, "model": "fake", "provider": "fake", "usage": {}, "ms": 1}


def _ledger_agent():
    steps = [[_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Meeting with Morgan", "expected_date": "2026-10-22", "time_role": "happens"})],
             [_tc(3, "list_open", {})],
             [_tc(4, "finish", {"transcript_sweep": "none", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "meeting-with-morgan"}]})]]
    st = {"n": 0}

    async def chat(model, messages):
        step = steps[min(st["n"], len(steps) - 1)]
        st["n"] += 1
        return {"content": "", "tool_calls": step, "finish_reason": "tool_calls", "model": model, "provider": "fake", "usage": {}}
    return chat


MSGS = [{"id": "m0", "speaker": "user", "text": "Morgan is advising me on Bloom, and we decided to test it with the missionaries next month. Meeting Morgan Thursday."},
        {"id": "m1", "speaker": "assistant", "text": "Great."}]


async def _consolidate(o, sitting_kind="user", companion="sophie"):
    async with async_session_maker() as db:
        return await mp.consolidate(db, workspace_id=mp.product_scope.scoped_workspace(companion, WS), owner=o, conversation_id="c", session_id="s",
                                    messages=MSGS, companion_id=companion, sitting_kind=sitting_kind, session_time="2026-10-19T20:00:00+01:00", time_zone="Europe/London")


async def _bundle(rid):
    async with async_session_maker() as db:
        return json.loads((await mp.get_run(db, rid)).bundle_json)


@pytest.fixture(autouse=True)
def _reset():
    yield
    mp.set_model_fn(None)
    ma.set_chat_fn(None)
    wa.set_chat_fn(None)


@pytest.mark.asyncio
async def test_the_connect_pass_runs_after_the_ledger_links_its_records_and_is_off_by_default(monkeypatch):
    o = owner()
    mp.set_model_fn(Models())
    ma.set_chat_fn(_ledger_agent())
    off = await _consolidate(o)
    assert (await _bundle(off["run_id"]))["world_agent"]["status"] == "skipped"
    assert await rows(o, KnownEntity) == []                                             # flag off: nothing written, nothing called

    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", True, raising=False)
    o2 = owner()
    ma.set_chat_fn(_ledger_agent())
    seen = []
    wa.set_chat_fn(_script([{"calls": [_tc(1, "list_entities", {}),
                                       _tc(2, "create_entity", {"name": "Morgan", "kind": "person", "summary": "Adviser on Bloom", "basis": "stated", "evidence": "Morgan is advising me on Bloom"}),
                                       _tc(3, "create_entity", {"name": "Bloom", "kind": "project", "summary": "Reflection companion app"})]},
                            {"calls": [_tc(4, "list_entities", {})]}], seen))
    ids = {}
    on = await _consolidate(o2)                                                         # step 2 needs ids: run the pass in two sittings
    b = await _bundle(on["run_id"])
    assert b["world_agent"]["status"] in ("unfinished", "finished_unchecked", "verified") and b["world_agent"]["changes"]["created"] == 2
    ctx_msg = seen[0][1]["content"]
    assert "key=meeting-with-morgan" in ctx_msg and "touched this session" in ctx_msg and "session transcript (ground truth)" in ctx_msg   # it sees what the ledger just did
    assert {e.name for e in await rows(o2, KnownEntity) if e.kind != "self"} == {"Morgan", "Bloom"}


@pytest.mark.asyncio
async def test_a_failure_in_the_connect_pass_never_costs_the_session_its_other_results(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", True, raising=False)
    o = owner()
    mp.set_model_fn(Models())
    ma.set_chat_fn(_ledger_agent())

    async def boom(*a, **k):
        raise RuntimeError("world model exploded")
    monkeypatch.setattr(wa, "run", boom)
    res = await _consolidate(o)
    b = await _bundle(res["run_id"])
    assert res["status"] == "consolidated" and b["world_agent"]["status"] == "failed"
    async with async_session_maker() as db:
        assert [r.title for r in await mp.open_ledger(db, mp.product_scope.scoped_workspace("sophie", WS), o)] == ["Meeting with Morgan"]


@pytest.mark.asyncio
async def test_independent_sittings_and_unwilling_products_do_not_run_it(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", True, raising=False)
    mp.set_model_fn(Models())
    ma.set_chat_fn(_ledger_agent())

    async def must_not_run(*a, **k):
        raise AssertionError("connect pass must not run")
    monkeypatch.setattr(wa, "run", must_not_run)
    res = await _consolidate(owner(), sitting_kind="independent")
    assert (await _bundle(res["run_id"]))["world_agent"]["status"] == "skipped"


TALK = ("Person: Ashley, my partner, thinks I should take the lead. She\u2019s got a chest infection that won't clear, they're waiting on results.\n"
        "Sophie: You said your partner Priya is a doctor and Morgan manages you.")


@pytest.mark.asyncio
async def test_the_person_has_their_own_anchor_so_nothing_stands_in_for_them_and_it_cannot_be_edited_or_duplicated():
    o = owner()
    steps = [{"calls": [_tc(1, "list_entities", {})]}]
    await run(o, steps + [FIN(2)])
    selves = [e for e in await rows(o, KnownEntity) if e.kind == "self"]
    assert len(selves) == 1 and selves[0].name == "the person"
    sid = str(selves[0].id)
    seen = []
    steps = [{"calls": [_tc(1, "list_entities", {}), _tc(2, "create_entity", {"name": "Ashley", "kind": "person"}),
                        _tc(3, "create_entity", {"name": "The person", "kind": "person"}), _tc(4, "create_entity", {"name": "Me", "kind": "self"}),
                        _tc(5, "update_entity", {"id": sid, "summary": "he is a man"})]},
             {"calls": [_tc(6, "list_entities", {})]}, FIN(7)]
    await run(o, steps, seen=seen)
    msgs = " ".join(m["content"] for ms in seen for m in ms if m.get("role") == "tool")
    assert "already has their own entity" in msgs and "is not edited" in msgs
    assert len([e for e in await rows(o, KnownEntity) if e.kind == "self"]) == 1 and (await rows(o, KnownEntity))
    async with async_session_maker() as db:
        ash = (await kw.find(db, WS, o, "Ashley"))[0]
        await wa._tool(db, wa.State(WS, o, "s1", None, TALK, "Person"), "link_entity", {"from_id": str(ash.id), "relation": "partner of", "to_entity_id": sid, "basis": "stated",
                                                                                          "evidence": "Ashley, my partner, thinks I should take the lead"})
        await db.commit()
        txt, _ = await kw.overview_text(db, WS, o, kw.Ctx(datetime(2026, 10, 19, 20), "Europe/London"))
    assert "Ashley (person)" in txt and "User's partner" in txt and "the person (self)" not in txt


@pytest.mark.asyncio
async def test_a_stated_quote_must_be_the_persons_own_words_exactly_apostrophes_and_all():
    o = owner()
    st = wa.State(WS, o, "s1", None, TALK, "Person")
    assert wa._quote("She's got a chest infection that won't clear", st) == "She's got a chest infection that won't clear"      # curly vs straight apostrophe
    assert wa._quote("Ashley, my partner, thinks I should take the lead ... they're waiting on results", st).count("\u2026") == 1
    assert wa._quote("Priya is a doctor and Morgan manages you", st) == ""                  # the assistant said it, the person did not
    assert wa._quote("She has a chest infection that will not clear", st) == ""             # a paraphrase is not a quote
    assert wa._quote("chest", st) == ""                                                      # too short to prove anything
    async with async_session_maker() as db:
        out = await wa._tool(db, st, "create_entity", {"name": "Priya", "kind": "person", "basis": "stated", "evidence": "Priya is a doctor"})
        assert out["entity"]["basis"] == "inferred" and "copy it exactly" in out["note"]
        out = await wa._tool(db, st, "create_entity", {"name": "Ashley", "kind": "person", "basis": "stated", "evidence": "Ashley, my partner, thinks I should take the lead"})
        assert out["entity"]["basis"] == "stated"
        e = await kw.get(db, WS, o, out["entity"]["id"])
        e.basis = "inferred"
        await wa._tool(db, st, "update_entity", {"id": str(e.id), "basis": "stated", "evidence": "Ashley, my partner"})
        assert e.basis == "stated"                  # later said by the person themself: no longer a bare inference
        e.basis = "inferred"
        await wa._tool(db, st, "update_entity", {"id": str(e.id), "basis": "stated", "evidence": "Ashley is a doctor"})
        assert e.basis == "inferred"                # an unverified quote upgrades nothing


@pytest.mark.asyncio
async def test_a_wrongly_retired_link_is_shown_when_it_happens_and_can_be_restored():
    o = owner()
    async with async_session_maker() as db:
        a = await kw.create(db, WS, o, name="Ashley", kind="person")
        b = await kw.create(db, WS, o, name="Ruth", kind="person")
        lk, _ = await kw.link(db, WS, o, from_id=a.id, relation="niece of", target_kind="entity", target_ref=str(b.id), basis="stated", evidence="x")
        await db.commit()
        st = wa.State(WS, o, "s1", None, TALK, "Person")
        res = await wa._tool(db, st, "supersede_link", {"link_id": str(lk.id), "reason": "oops"})
        assert res["link"]["retired"] == "Ashley \u2014 niece of \u2014 Ruth" and st.changes["superseded"] == 1
        res = await wa._tool(db, st, "restore_link", {"link_id": str(lk.id)})
        assert res["link"]["status"] == "current" and st.changes["superseded"] == 0
        assert (await wa._tool(db, st, "restore_link", {"link_id": "nope"}))["error"] == "no such link"


@pytest.mark.asyncio
async def test_happenings_dispositions_and_patterns_are_validated_not_guessed():
    o = owner()
    st = wa.State(WS, o, "s1", None, TALK, "Person")
    async with async_session_maker() as db:
        bad = await wa._tool(db, st, "create_entity", {"name": "X", "kind": "incident", "form": "memory-thing"})
        assert "form must be" in bad["error"]
        assert "YYYY-MM-DD" in (await wa._tool(db, st, "create_entity", {"name": "Y", "kind": "incident", "form": "happening", "occurred_on": "last night"}))["error"]
        ok = await wa._tool(db, st, "create_entity", {"name": "Kissed Rebecca", "kind": "incident", "form": "happening", "occurred_on": "2026-10-19",
                                                      "significance": 9, "tags": ["Relationships/Romantic", "relationships/romantic", "!!"]})
        assert ok["ok"]
        e = await kw.get(db, WS, o, ok["entity"]["id"])
        assert (e.form, e.tags, e.significance, e.occurred_on.date().isoformat()) == ("happening", "relationships/romantic", 3, "2026-10-19")
        up = await wa._tool(db, st, "update_entity", {"id": str(e.id), "significance": "x"})
        assert "significance" in up["error"] and e.significance == 3          # a refused update changes nothing
        await wa._tool(db, st, "update_entity", {"id": str(e.id), "form": "pattern", "tags": ["sleep"]})
        assert (e.form, e.tags) == ("pattern", "sleep")
