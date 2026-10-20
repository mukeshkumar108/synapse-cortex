"""Maintenance-agent interface guarantees (no network; the model is a script).

These test PROPERTIES of the interface — what the code refuses or enforces —
not what a model happens to decide: unknown/malformed/truncated tool calls are
rejected, create carries full state, finish needs a re-read and a complete
accounting against records touched in this run.
"""
import json
import uuid

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.world import LedgerItem
from src.services import maintenance_agent as ma
from src.services import memory_pipeline as mp


def _tc(i, name, args):
    return {"id": f"c{i}", "type": "function",
            "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


def _owner():
    return f"u-{uuid.uuid4().hex[:8]}"


def _scripted(steps, seen=None):
    state = {"n": 0}

    async def chat(model, messages):
        if seen is not None:
            seen.append(list(messages))
        step = steps[min(state["n"], len(steps) - 1)]
        state["n"] += 1
        return {"content": "", "tool_calls": step.get("calls", []), "finish_reason": step.get("finish_reason", "tool_calls"),
                "model": model, "provider": "fake", "usage": {}}
    return chat


async def _run(owner, steps, n_obs=0, today="2026-10-19", transcript="", seen=None):
    async with async_session_maker() as db:
        ma.set_chat_fn(_scripted(steps, seen))
        try:
            out = await ma.run_maintenance(db, workspace_id="wsC", owner=owner, session_id="s", observations="obs",
                                           n_observations=n_obs, today=today, weekday="Monday", transcript=transcript)
        finally:
            ma.set_chat_fn(None)
    return out


async def _rows(owner):
    async with async_session_maker() as db:
        return (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == "wsC", LedgerItem.owner_peer_id == owner))).scalars().all()


@pytest.mark.asyncio
async def test_create_item_carries_complete_state():
    o = _owner()
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {
        "title": "Dentist appointment", "kind": "event", "timing": "Thursday", "expected_date": "2026-10-22",
        "status": "waiting", "waiting_on": "Mum's text with the time", "question_text": "What time?",
        "confidence": "reported", "detail": "Thursday, time unknown"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"summary": "created", "accounting": [
                 {"obs": 1, "treatment": "applied", "key": "dentist-appointment"}]})]}]
    out = await _run(o, steps, n_obs=1)
    assert out["status"] == "verified"
    (r,) = await _rows(o)
    assert r.status == "waiting" and r.expected_date.strftime("%Y-%m-%d") == "2026-10-22"
    assert r.waiting_on.startswith("Mum") and r.question_text == "What time?" and r.confidence == "reported"
    assert out["accounting"][0]["key"] == "dentist-appointment"


@pytest.mark.asyncio
async def test_unknown_arguments_are_rejected_not_ignored():
    o = _owner()
    async with async_session_maker() as db:
        bad = await ma._tools(db, "wsC", o, "create_item", {"title": "X thing", "due_date": "2026-10-22"})
        assert "unsupported argument" in bad["error"] and "due_date" in bad["error"]
        assert await _rows(o) == []
        await ma._tools(db, "wsC", o, "create_item", {"title": "Real thing"})
        bad2 = await ma._tools(db, "wsC", o, "update_item", {"key": "real-thing", "expectedDate": "2026-10-22"})
        assert "unsupported argument" in bad2["error"]
        bad3 = await ma._tools(db, "wsC", o, "create_item", {"title": "Other", "expected_date": "2026-13-45"})
        assert "calendar" in bad3["error"] or "YYYY" in bad3["error"]


@pytest.mark.asyncio
async def test_malformed_and_truncated_calls_never_run():
    o = _owner()
    seen = []
    steps = [{"calls": [_tc(1, "create_item", '{"title": "Half written", "detail": "cut of')]},
             {"calls": [_tc(2, "create_item", {"title": "Truncated one"})], "finish_reason": "length"},
             {"calls": [_tc(3, "finish", '{"summary":')]}]
    out = await _run(o, steps, seen=seen)
    assert await _rows(o) == []
    tool_msgs = [m["content"] for m in seen[-1] if m.get("role") == "tool"]
    assert any("not a valid JSON object" in c for c in tool_msgs)
    assert any("cut off" in c for c in tool_msgs)
    assert out["status"] != "verified" and out["summary"] is None   # a broken finish is not a finish


@pytest.mark.asyncio
async def test_finish_needs_reread_and_full_accounting():
    o = _owner()
    seen = []
    steps = [
        {"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Call Mum", "expected_date": "2026-10-20"})]},
        # no re-list, partial accounting -> refused
        {"calls": [_tc(3, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
        {"calls": [_tc(4, "list_open", {})]},
        # O2 unaccounted -> refused
        {"calls": [_tc(5, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
        # names a record never touched -> refused
        {"calls": [_tc(6, "finish", {"summary": "x", "accounting": [
            {"obs": 1, "treatment": "applied", "key": "call-mum"}, {"obs": 2, "treatment": "applied", "key": "ghost"}]})]},
    ]
    out = await _run(o, steps, n_obs=2, seen=seen)
    refusals = [m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"]]
    joined = " ".join(refusals)
    assert "Re-list" in joined and "unaccounted observations: O2" in joined
    assert out["status"] == "finished_unchecked"          # accepted only after MAX bounces, flagged, never "verified"
    assert out["gate_failures"]


@pytest.mark.asyncio
async def test_two_observations_about_one_matter_fold_without_duplicates():
    o = _owner()
    steps = [
        {"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Dentist appointment", "timing": "Thursday 2pm",
                                                                    "expected_date": "2026-10-22", "detail": "Thursday at 2pm"})]},
        {"calls": [_tc(3, "list_open", {})]},
        {"calls": [_tc(4, "finish", {"summary": "ok", "accounting": [
            {"obs": 1, "treatment": "applied", "key": "dentist-appointment"},
            {"obs": 2, "treatment": "merged", "key": "dentist-appointment", "note": "same appointment"}]})]},
    ]
    out = await _run(o, steps, n_obs=2)
    assert out["status"] == "verified"
    assert len(await _rows(o)) == 1


@pytest.mark.asyncio
async def test_no_change_must_name_an_existing_record_and_skipped_a_reason():
    o = _owner()
    async with async_session_maker() as db:
        await ma._tools(db, "wsC", o, "create_item", {"title": "Dentist appointment"})
    steps = [{"calls": [_tc(1, "list_open", {})]},
             {"calls": [_tc(2, "finish", {"summary": "x", "accounting": [
                 {"obs": 1, "treatment": "no_change", "key": "dentist-appointment", "note": "already says Thursday 2pm"},
                 {"obs": 2, "treatment": "skipped", "note": "a metaphor, not an operational matter"}]})]}]
    assert (await _run(o, steps, n_obs=2))["status"] == "verified"
    steps2 = [{"calls": [_tc(1, "list_open", {})]},
              {"calls": [_tc(2, "finish", {"summary": "x", "accounting": [
                  {"obs": 1, "treatment": "no_change", "note": "trust me"}]})]}]
    assert (await _run(_owner(), steps2, n_obs=1))["status"] == "finished_unchecked"


@pytest.mark.asyncio
async def test_update_clears_answered_wait_and_keeps_prior_detail():
    o = _owner()
    async with async_session_maker() as db:
        await ma._tools(db, "wsC", o, "create_item", {
            "title": "Dentist appointment", "status": "waiting", "waiting_on": "Mum's text", "question_text": "What time?",
            "detail": "Thursday, time unknown", "timing": "Thursday"})
        res = await ma._tools(db, "wsC", o, "update_item", {
            "key": "dentist-appointment", "status": "open", "waiting_on": "", "question_text": "",
            "detail": "Thursday at 2pm (Mum texted)", "timing_text": "Thursday 2pm", "expected_date": "2026-10-22"})
        assert res["ok"] and res["changed"]["status"]["to"] == "open" and res["record"]["waiting_on"] == ""
        (row,) = await _rows(o)
        assert row.status == "open" and row.expected_date.strftime("%Y-%m-%d") == "2026-10-22"
        refs = json.loads(row.source_refs_json)
        assert "time unknown" in refs["detail_history"][0]       # the superseded detail is kept, not lost


@pytest.mark.asyncio
async def test_missing_date_advisory_is_advice_not_a_write():
    o = _owner()
    token = ma._TODAY_CTX.set("2026-10-19")
    try:
        async with async_session_maker() as db:
            res = await ma._tools(db, "wsC", o, "create_item", {"title": "Send the deck", "timing": "by Friday"})
            assert any("resolves to 2026-10-23" in a for a in res["advisories"])
            (row,) = await _rows(o)
            assert row.expected_date is None                       # the check never forces a value
    finally:
        ma._TODAY_CTX.reset(token)
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Ship thing", "timing": "by Friday"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "ship-thing"}]})]},
             {"calls": [_tc(5, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "ship-thing"}]})]}]
    o2 = _owner()
    out = await _run(o2, steps, n_obs=1, today="2026-10-19")
    # first finish bounced with the advisory; second (agent disagrees) is accepted: advice, not a veto
    assert out["status"] == "verified"
    (r,) = await _rows(o2)
    assert r.expected_date is None


def test_witness_tags_ended_changed_and_legacy_resolved():
    raw = """ITEM: Dentist appointment
KIND: event
TIMING: Thursday
CHANGED: time confirmed as 2pm by Mum's text
EVIDENCE: "Mum just texted, dentist is at 2pm."
ITEM: Send proposal to Vinesh
ENDED: sent this morning | "Sent the Vinesh proposal this morning"
ITEM: Old thing
RESOLVED: something unclassified
"""
    items, unparsed = mp.parse_tagged_lines(raw)
    d, v, o = items
    assert d["changed"].startswith("time confirmed") and not d.get("ended") and not d.get("resolved")
    assert v["ended"] is True and v["resolved"].startswith("sent this morning")
    assert o["resolved"] and not o.get("ended")
    standalone, _ = mp.parse_tagged_lines("CHANGED: Vinesh review | moved to Friday morning")
    assert standalone[0]["title"] == "Vinesh review" and standalone[0]["changed"] == "moved to Friday morning"


def test_observations_are_numbered_complete_and_weekdays_annotated_once():
    from datetime import date
    items, _ = mp.parse_tagged_lines("""ITEM: Dentist appointment
KIND: event
DETAIL: time unknown
TIMING: Tuesday or Thursday
WAITING-ON: Mum
QUESTION: What time?
PERSON: Mum (will text the time)
CONFIDENCE: reported
EVIDENCE: "Dentist on Thursday, not sure what time yet."
STATUS-HINT: waiting
CHANGED: moved from Tuesday to Thursday
ITEM: Call Mum
REMINDER-AUTHORISED: asked to be reminded
""")
    text, n = mp.build_observations(items, date(2026, 10, 20))     # a Tuesday
    assert n == 2 and "[O1]" in text and "[O2]" in text
    for must in ("waiting-on: Mum", "question: What time?", "people: Mum", "confidence: reported",
                 "STATUS-HINT: waiting", "CHANGED:", 'evidence: "Dentist on Thursday', "REMINDER-AUTHORISED"):
        assert must in text, must
    assert "Tuesday (2026-10-20)" in text and "Thursday (2026-10-22)" in text
    assert "(2026-10-27)" not in text.split("[O1]", 1)[1]           # same weekday as today is annotated once


def test_resolve_clock_uses_where_and_when_the_person_spoke():
    c = mp.resolve_clock("2026-10-19T21:30:00-07:00", "America/Los_Angeles")   # 04:30 UTC on the 20th
    assert c["today"] == "2026-10-19" and c["weekday"] == "Monday"
    assert mp.resolve_clock("2026-10-20T04:30:00Z", "America/Los_Angeles")["today"] == "2026-10-19"
    assert mp.resolve_clock("2026-10-19T21:30:00", "America/Los_Angeles")["today"] == "2026-10-19"   # naive = their wall time
    assert mp.resolve_clock("2026-10-19T12:00:00+00:00", "Not/AZone")["tz"] == "UTC"
    tomorrow = mp.resolve_date("tomorrow", c["today"])
    assert tomorrow.strftime("%Y-%m-%d") == "2026-10-20"


def test_marker_ahead_of_item_on_one_line_is_honoured_not_dropped():
    # Observed in a real extractor reply: the whole item was discarded as 'unparsed'.
    raw = ('REMINDER-AUTHORISED: ITEM: Call Mum tomorrow at 6\nKIND: reminder\nTIMING: "tomorrow at 6"\n'
           'EVIDENCE: "Remind me to call Mum tomorrow at 6."\n\nITEM: Marathon\nKIND: aspiration\n')
    items, unparsed = mp.parse_tagged_lines(raw)
    assert [i["title"] for i in items] == ["Call Mum tomorrow at 6", "Marathon"] and not unparsed
    assert items[0]["reminder_authorised"] is True and not items[1].get("reminder_authorised")


def test_empty_ended_or_changed_never_closes_or_updates():
    items, _ = mp.parse_tagged_lines("ITEM: Proposal\nENDED: (none)\nCHANGED: none stated\nRESOLVED: -\nTIMING: Thursday\n")
    (p,) = items
    assert not p.get("ended") and not p.get("resolved") and not p.get("changed")


@pytest.mark.asyncio
async def test_persons_own_timing_words_must_survive_the_handoff():
    o = _owner()
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Call Mum", "expected_date": "2026-10-20"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
             {"calls": [_tc(5, "update_item", {"key": "call-mum", "timing_text": "tomorrow at 6"}), _tc(6, "list_open", {})]},
             {"calls": [_tc(7, "finish", {"summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]}]
    seen = []
    async with async_session_maker() as db:
        ma.set_chat_fn(_scripted(steps, seen))
        try:
            out = await ma.run_maintenance(db, workspace_id="wsC", owner=o, session_id="s", observations="obs", n_observations=1,
                                           today="2026-10-19", weekday="Monday", obs_timing={1: "tomorrow at 6"})
        finally:
            ma.set_chat_fn(None)
    refusals = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"])
    assert "tomorrow at 6" in refusals and out["status"] == "verified"
    (row,) = await _rows(o)
    assert row.timing_text == "tomorrow at 6"


def test_contract_defines_status_hint_and_delivery_semantics():
    assert "STATUS-HINT is the witness's reading" in ma.CONTRACT and "never rewrite it as an action" in ma.CONTRACT
    assert "a promised thing that has been done is over" in ma.CONTRACT


@pytest.mark.asyncio
async def test_agent_sees_the_transcript_and_may_add_what_the_witness_missed():
    o = _owner()
    seen = []
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Pete SSH pings", "status": "suppressed", "kind": "situation"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"summary": "x", "accounting": [
                 {"obs": 1, "treatment": "skipped", "note": "witness garbled this; not supported by the transcript"},
                 {"obs": 0, "treatment": "applied", "key": "pete-ssh-pings", "note": "stand-down the witness missed"}]})]}]
    out = await _run(o, steps, n_obs=1, transcript="Person: Pete keeps pinging about SSH; ignore him tonight.", seen=seen)
    first_user = seen[0][1]["content"]
    assert "session transcript (ground truth" in first_user and "ignore him tonight" in first_user
    assert out["status"] == "verified" and any(a["obs"] == 0 and a["key"] == "pete-ssh-pings" for a in out["accounting"])
    (r,) = await _rows(o)
    assert r.status == "suppressed"
    # obs 0 must name a record actually touched in this run
    steps2 = [{"calls": [_tc(1, "list_open", {})]},
              {"calls": [_tc(2, "finish", {"summary": "x", "accounting": [
                  {"obs": 1, "treatment": "skipped", "note": "n/a"}, {"obs": 0, "treatment": "applied", "key": "ghost"}]})]}]
    out2 = await _run(_owner(), steps2, n_obs=1)
    assert out2["status"] == "finished_unchecked"


def test_contracts_forbid_inventing_am_pm():
    from src.services import attention_cycle as ac
    assert "am/pm not stated" in ma.CONTRACT and "do not turn it into 06:00 or 18:00" in ma.CONTRACT
    assert "do not guess a clock time" in ac.CONTRACT
