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
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "created", "accounting": [
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
        {"calls": [_tc(3, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
        {"calls": [_tc(4, "list_open", {})]},
        # O2 unaccounted -> refused
        {"calls": [_tc(5, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
        # names a record never touched -> refused
        {"calls": [_tc(6, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [
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
        {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "ok", "accounting": [
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
             {"calls": [_tc(2, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [
                 {"obs": 1, "treatment": "no_change", "key": "dentist-appointment", "note": "already says Thursday 2pm"},
                 {"obs": 2, "treatment": "skipped", "note": "a metaphor, not an operational matter"}]})]}]
    assert (await _run(o, steps, n_obs=2))["status"] == "verified"
    steps2 = [{"calls": [_tc(1, "list_open", {})]},
              {"calls": [_tc(2, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [
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
            assert any("names a day" in a and "upcoming one is 2026-10-23" in a and "most recent is 2026-10-16" in a for a in res["advisories"])
            (row,) = await _rows(o)
            assert row.expected_date is None                       # the check never forces a value
    finally:
        ma._TODAY_CTX.reset(token)
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Ship thing", "timing": "by Friday"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "ship-thing"}]})]},
             {"calls": [_tc(5, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "ship-thing"}]})]}]
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
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
             {"calls": [_tc(5, "update_item", {"key": "call-mum", "timing_text": "tomorrow at 6"}), _tc(6, "list_open", {})]},
             {"calls": [_tc(7, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]}]
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
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [
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
              {"calls": [_tc(2, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [
                  {"obs": 1, "treatment": "skipped", "note": "n/a"}, {"obs": 0, "treatment": "applied", "key": "ghost"}]})]}]
    out2 = await _run(_owner(), steps2, n_obs=1)
    assert out2["status"] == "finished_unchecked"


def test_contracts_let_the_model_reason_but_require_the_basis_to_be_recorded():
    from src.services import attention_cycle as ac
    for must in ("Reason freely, record uncertainty faithfully", "Never present an assumption as something they said",
                 'time_basis "stated"', '"assumed"', "keep their exact words in timing_text"):
        assert must in ma.CONTRACT, must
    assert "never guess am/pm" not in ma.CONTRACT and "do not turn it into" not in ma.CONTRACT        # no blanket prohibition on interpreting
    assert 'Only a time marked "stated" may trigger a timed follow-up' in ac.CONTRACT and "do not guess a clock time" not in ac.CONTRACT


@pytest.mark.asyncio
async def test_structured_time_is_validated_stamped_with_the_persons_zone_and_clearable():
    o = _owner()
    tz_t = ma._TZ_CTX.set("America/Los_Angeles")
    try:
        async with async_session_maker() as db:
            r = await ma._tools(db, "wsC", o, "create_item", {"title": "Call with Vinesh", "expected_date": "2026-10-20", "expected_time": "15:00",
                                                              "time_basis": "stated", "time_role": "happens", "importance": 3})
            assert r["ok"] and r["record"]["expected_time"] == "15:00" and r["record"]["time_role"] == "happens" and r["record"]["importance"] == 3
            assert r["record"]["time_basis"] == "stated"
            (row,) = await _rows(o)
            assert row.time_zone == "America/Los_Angeles"                        # code stamps the zone; the model never supplies it
            for bad, msg in (({"expected_time": "3pm"}, "HH:MM"), ({"expected_time": "25:00"}, "HH:MM"), ({"time_role": "sometime"}, "time_role"),
                             ({"importance": 5}, "importance"), ({"importance": "high"}, "importance"), ({"time_basis": "probably"}, "time_basis")):
                e = await ma._tools(db, "wsC", o, "update_item", {"key": "call-with-vinesh", **bad})
                assert "error" in e and msg in e["error"], (bad, e)
            # the date moves and the time is not known: it is cleared, never left stale
            u = await ma._tools(db, "wsC", o, "update_item", {"key": "call-with-vinesh", "expected_date": "2026-10-21", "expected_time": ""})
            assert u["ok"] and u["record"]["expected_time"] == "" and u["record"]["expected_date"] == "2026-10-21"
            assert u["record"]["time_basis"] == ""                                 # clearing the time clears its basis too
            # a time cannot be set without saying what it rests on
            nb = await ma._tools(db, "wsC", o, "update_item", {"key": "call-with-vinesh", "expected_time": "16:00"})
            assert "also set time_basis" in nb["error"]
            ok = await ma._tools(db, "wsC", o, "update_item", {"key": "call-with-vinesh", "expected_time": "18:00", "time_basis": "assumed"})
            assert ok["ok"] and ok["record"]["time_basis"] == "assumed"
        # a time without a date is refused on create and on update
        async with async_session_maker() as db:
            assert "needs an expected_date" in (await ma._tools(db, "wsC", o, "create_item", {"title": "Floating time", "expected_time": "10:00", "time_basis": "stated"}))["error"]
            await ma._tools(db, "wsC", o, "create_item", {"title": "No date yet"})
            assert "needs an expected_date" in (await ma._tools(db, "wsC", o, "update_item", {"key": "no-date-yet", "expected_time": "10:00", "time_basis": "stated"}))["error"]
    finally:
        ma._TZ_CTX.reset(tz_t)


def test_contract_teaches_structured_time_and_missing_details():
    c = ma.CONTRACT
    for must in ('time_role: set "happens"', '"deadline"', 'clear the old time with expected_time ""',
                 "An appointment with an unknown time or place is still an appointment", "put what is missing in question_text",
                 "The person's own words, what you inferred, and what is still unresolved must all stay visible"):
        assert must in c, must



def test_past_tense_days_have_a_past_reference_and_the_agent_is_told_to_use_it():
    from datetime import date
    text, _ = mp.build_observations([{"title": "Electricity bill", "timing": "Sunday", "detail": "it was due on Sunday", "people": [], "evidence": []}], date(2026, 10, 20))
    assert "Past days: Monday 2026-10-19, Sunday 2026-10-18" in text and "point FORWARD" in text
    assert "was due on Sunday" in text and "(2026-10-25)" in text.split("[O1]")[1]          # the forward annotation is still there for the model to weigh
    assert "A weekday the person speaks of in the past tense" in ma.CONTRACT


@pytest.mark.asyncio
async def test_a_dated_record_without_a_role_is_advised_once_never_forced():
    o = _owner()
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Dentist", "expected_date": "2026-10-22"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "dentist"}]})]},
             {"calls": [_tc(5, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "dentist"}]})]}]
    seen = []
    out = await _run(o, steps, n_obs=1, seen=seen)
    refusals = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"])
    assert "no time_role" in refusals and out["status"] == "verified"        # shown once; the agent may decline
    (r,) = await _rows(o)
    assert r.time_role == ""                                                  # code never fills it in


def test_an_extractor_that_drops_the_ITEM_prefix_loses_nothing():
    # Observed in a real run: bare title lines opened each block, so the whole session was discarded as 'unparsed'.
    raw = """James invoice approval
KIND: situation
DETAIL: pending
TIMING: pending

Marathon aspiration
KIND: aspiration
DETAIL: vague
a continuation line of the detail
TIMING: "someday"

**Call Mum reminder**
KIND: reminder
TIMING: "tomorrow at 6"
"""
    items, unparsed = mp.parse_tagged_lines(raw)
    assert [i["title"] for i in items] == ["James invoice approval", "Marathon aspiration", "Call Mum reminder"] and not unparsed
    assert items[1]["detail"] == "vague a continuation line of the detail"          # continuation lines still belong to their tag
    again, _ = mp.parse_tagged_lines("ITEM: A\nKIND: x\nDETAIL: one\nsecond line\nTIMING: Thu\n")
    assert [(i["title"], i["detail"]) for i in again] == [("A", "one second line")]


@pytest.mark.asyncio
async def test_a_stated_time_of_day_is_nominated_to_the_agent_never_set_by_code():
    o = _owner()
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Submit proposal", "expected_date": "2026-10-20", "time_role": "deadline", "timing": "by 5pm today"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "submit-proposal"}]})]},
             {"calls": [_tc(5, "update_item", {"key": "submit-proposal", "expected_time": "17:00", "time_basis": "stated"}), _tc(6, "list_open", {})]},
             {"calls": [_tc(7, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "submit-proposal"}]})]}]
    seen = []
    async with async_session_maker() as db:
        ma.set_chat_fn(_scripted(steps, seen))
        try:
            out = await ma.run_maintenance(db, workspace_id="wsC", owner=o, session_id="s", observations="obs", n_observations=1, today="2026-10-20",
                                           weekday="Tuesday", obs_timing={1: '"by 5pm"'})
        finally:
            ma.set_chat_fn(None)
    refusals = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"])
    assert "states a time of day" in refusals and out["status"] == "verified"
    (r,) = await _rows(o)
    assert r.expected_time == "17:00"                                          # set by the agent after the nomination, not by code
    assert "ENDED outranks STATUS-HINT" in ma.CONTRACT


@pytest.mark.asyncio
async def test_a_reasonable_assumption_is_welcome_but_must_be_labelled_as_one():
    """'tomorrow at 6' may be read as 18:00. What may not happen is the reading being stored as if the person had said it."""
    o = _owner()
    steps = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Call Mum", "expected_date": "2026-10-21", "expected_time": "18:00",
                                                                          "time_basis": "stated", "time_role": "happens"})]},
             {"calls": [_tc(3, "list_open", {})]},
             {"calls": [_tc(4, "finish", {"transcript_sweep": "none", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]},
             {"calls": [_tc(5, "update_item", {"key": "call-mum", "time_basis": "assumed", "question_text": "6 am or 6 pm?", "timing_text": "tomorrow at 6"}), _tc(6, "list_open", {})]},
             {"calls": [_tc(7, "finish", {"transcript_sweep": "none", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]}]
    seen = []
    async with async_session_maker() as db:
        ma.set_chat_fn(_scripted(steps, seen))
        try:
            out = await ma.run_maintenance(db, workspace_id="wsC", owner=o, session_id="s", observations="obs", n_observations=1, today="2026-10-20",
                                           weekday="Tuesday", obs_timing={1: '"tomorrow at 6"'})
        finally:
            ma.set_chat_fn(None)
    refusals = " ".join(m["content"] for msgs in seen for m in msgs if m.get("role") == "tool" and "finish refused" in m["content"])
    assert "is your reading" in refusals and "assumed" in refusals and out["status"] == "verified"
    (r,) = await _rows(o)
    assert r.expected_time == "18:00" and r.time_basis == "assumed"            # the best reading is KEPT, honestly labelled
    assert r.timing_text == "tomorrow at 6" and "6 am or 6 pm" in r.question_text   # the person's words and the open question survive

    # an explicitly stated time never triggers the "this is your reading" nudge
    o2 = _owner()
    ok = [{"calls": [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Call Mum", "expected_date": "2026-10-21", "expected_time": "18:00",
                                                                      "time_basis": "stated", "time_role": "happens", "timing": "tomorrow at 6pm"})]},
          {"calls": [_tc(3, "list_open", {})]},
          {"calls": [_tc(4, "finish", {"transcript_sweep": "none", "summary": "x", "accounting": [{"obs": 1, "treatment": "applied", "key": "call-mum"}]})]}]
    seen2 = []
    async with async_session_maker() as db:
        ma.set_chat_fn(_scripted(ok, seen2))
        try:
            quiet = await ma.run_maintenance(db, workspace_id="wsC", owner=o2, session_id="s", observations="obs", n_observations=1, today="2026-10-20",
                                             weekday="Tuesday", obs_timing={1: '"tomorrow at 6pm"'})
        finally:
            ma.set_chat_fn(None)
    assert quiet["status"] == "verified" and len(quiet["calls"]) == 3
    assert not any("is your reading" in m["content"] for msgs in seen2 for m in msgs if m.get("role") == "tool")


def test_the_witness_keeps_timing_verbatim_as_evidence_but_may_record_its_reading_elsewhere():
    pr = mp.SITUATIONS_PROMPT
    assert "VERBATIM" in pr and "it is evidence" in pr
    assert 'put it in DETAIL as your inference ("likely 6pm — am/pm not stated")' in pr            # interpretation is welcome, in the right place


@pytest.mark.asyncio
async def test_a_close_is_not_a_reschedule():
    o = _owner()
    tok = ma._TRANSCRIPT_CTX.set("Sent the Vinesh proposal this morning, all done.")
    try:
        async with async_session_maker() as db:
            await ma._tools(db, "wsC", o, "create_item", {"title": "Send proposal", "expected_date": "2026-10-22"})
            bad = await ma._tools(db, "wsC", o, "update_item", {"key": "send-proposal", "status": "done", "expected_date": "2026-10-19",
                                                                "evidence": "Sent the Vinesh proposal this morning, all done."})
            assert "a close does not change when the thing was due" in bad["error"]
            ok = await ma._tools(db, "wsC", o, "update_item", {"key": "send-proposal", "status": "done", "expected_date": "2026-10-22",
                                                               "evidence": "Sent the Vinesh proposal this morning, all done."})
            assert ok["ok"] and ok["record"]["expected_date"] == "2026-10-22"
            (r,) = await _rows(o)
            assert r.status == "done" and r.expected_date.strftime("%Y-%m-%d") == "2026-10-22"
    finally:
        ma._TRANSCRIPT_CTX.reset(tok)


def test_placeholders_in_parentheses_are_never_proof_of_an_end():
    for junk in ("(none)", "(leave out — not ended)", "[n/a]", "(not ended)"):
        items, _ = mp.parse_tagged_lines(f"ITEM: Proposal\nENDED: {junk}\nCHANGED: {junk}\n")
        assert not items[0].get("ended") and not items[0].get("resolved") and not items[0].get("changed"), junk
    real, _ = mp.parse_tagged_lines('ITEM: Proposal\nENDED: sent this morning ("Sent the Vinesh proposal this morning")\n')
    assert real[0]["ended"] is True                                              # a real quote that merely contains parentheses still counts


def test_contract_says_an_input_arriving_does_not_end_the_dependent_matter():
    assert "An input arriving" in ma.CONTRACT and "does not end the matter that depends on it" in ma.CONTRACT
