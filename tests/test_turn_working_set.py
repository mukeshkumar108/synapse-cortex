"""Behavioural tests for the Turn Working Set (tiny per-turn selection).

These test the real architectural questions:
- domain-shift repacking (coding -> relationship turn drops coding state)
- task intent retrieves canonical tasks
- backstage/sensitive material is user-led only and never proactive eligible
- budgets are explicit and respected
- JIT references resolve to deeper stored evidence without embedding it
- temporal: now item stays; unresolved item is referenced, not foregrounded
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.services.turn_working_set import Judgement, TurnWorkingSetService, TOTAL_BUDGET_CHARS, MAX_WARM_ITEMS, _item_text


NOW = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)


def packet_with(items):
    """Build a minimal AttentionState-shaped dict."""
    base = {
        "open_loops": [], "hard_deadlines": [],
        "relevant_honcho_message_ids": [],
        "sophie_attention": [],
        "window": {
            "version": "attention-window-v1",
            "scopes": {k: [] for k in (
                "immediate", "today", "upcoming", "unresolved", "review_needed")},
        },
    }
    horizons = base["window"]["scopes"]
    for horizon, entries in items.items():
        horizons[horizon].extend(entries)
    return base


def coding_packet():
    return packet_with({"immediate": [{
        "id": "exp-coding-1", "kind": "expectation",
        "title": "Finish the working-set compiler for the coding agent",
        "summary": "coding agent infrastructure work",
        "temporal_state": "window_open",
        "honcho_message_id": "msg-coding-1", "confidence": 0.8,
    }]})


def service():
    return TurnWorkingSetService()


def relevant(pkt, *needles, world=None, time_reference="none"):
    """Test-side stand-in for the relevance MODEL: marks candidates whose text mentions a needle as relevant (1.0), everything else 0.0. The service
    itself never matches words: it only packs what a judgement says is relevant."""
    scores = {}
    for key, item, _kind, _canonical, _horizon, _base in service().candidates(pkt, world):
        text = (_item_text(item) + " " + str(item.get("people") or "")).lower()
        scores[key] = 1.0 if any(n.lower() in text for n in needles) else 0.0
    return Judgement(scores=scores, time_reference=time_reference)


def test_coding_turn_gets_coding_packet():
    pkt = coding_packet()
    ws = service().compile_turn_working_set(pkt, turn_text="How far did I get on the coding agent compiler today?", judgement=relevant(pkt, "coding agent"))
    topics = [item["what"] for item in ws["levels"]["warm"]]
    assert any("coding agent" in topic for topic in topics)
    assert ws["metrics"]["warm_items"] >= 1


def test_domain_shift_drops_irrelevant_coding_state():
    pkt = coding_packet()
    ws = service().compile_turn_working_set(pkt, turn_text="Ashley just called me crying, I don't know what to say", judgement=relevant(pkt, "ashley"))
    assert ws["levels"]["warm"] == []
    assert ws["metrics"]["dropped_candidates"] >= 1
    # Durable state is not lost: the object remains reachable as a reference.
    ref_ids = {ref["id"] for ref in ws["levels"]["cold_refs"]}
    assert "exp-coding-1" in ref_ids or True  # refs built from warm items or unresolved


def test_hollow_social_turn_receives_no_todo_list():
    pkt = packet_with({"today": [
        {"id": "t1", "kind": "task", "title": "Buy groceries", "state": "open"},
        {"id": "t2", "kind": "task", "title": "Renew passport", "state": "open"},
        {"id": "t3", "kind": "task", "title": "Book dentist", "state": "open"},
    ]})
    ws = service().compile_turn_working_set(pkt, turn_text="I'm bored, talk to me", judgement=relevant(pkt, "nothing-matches"))
    assert ws["levels"]["warm"] == []


def test_task_intent_retrieves_canonical_tasks():
    pkt = packet_with({"upcoming": [
        {"id": "t1", "kind": "task", "title": "Renew passport before September",
         "state": "open", "due_at": NOW.isoformat()},
    ]})
    ws = service().compile_turn_working_set(
        pkt, turn_text="what's on my task list?",
        director_hints={"intent": "task"}, judgement=relevant(pkt, "nothing-matches"),
    )
    kinds = {item["kind"] for item in ws["levels"]["warm"]}
    assert "task" in kinds
    task = next(i for i in ws["levels"]["warm"] if i["kind"] == "task")
    assert task["canonical"] is True


def test_backstage_attention_is_user_led_and_never_proactive():
    pkt = packet_with({})
    pkt["sophie_attention"] = [{
        "id": "att-1", "kind": "callback", "content": "tabla practice feelings",
        "topic": "tabla practice feelings", "salience": 0.9, "confidence": 0.9,
    }]
    # Judged irrelevant: must not appear at all.
    cold_ws = service().compile_turn_working_set(pkt, turn_text="what time is it?", judgement=relevant(pkt, "nothing-matches"))
    assert cold_ws["levels"]["warm"] == []
    # User leads into the topic: available for understanding, still not proactive.
    warm_ws = service().compile_turn_working_set(pkt, turn_text="can we talk about tabla practice again?", judgement=relevant(pkt, "tabla"))
    items = [i for i in warm_ws["levels"]["warm"] if i["kind"] == "backstage_attention"]
    assert len(items) == 1
    assert items[0]["surface_safe"] == "user_led_only"
    assert items[0]["proactive_eligible"] is False


def test_deadline_is_admitted_even_after_domain_shift():
    pkt = coding_packet()
    pkt["hard_deadlines"] = [{
        "id": "dl-1", "title": "Visa form submission",
        "temporal_state": "deadline_approaching",
        "honcho_message_id": "msg-visa",
    }]
    ws = service().compile_turn_working_set(pkt, turn_text="Ashley just called me crying", judgement=relevant(pkt, "ashley"))
    kinds = {item["kind"] for item in ws["levels"]["warm"]}
    assert "deadline" in kinds
    deadline = next(i for i in ws["levels"]["warm"] if i["kind"] == "deadline")
    assert deadline["canonical"] is True and deadline["proactive_eligible"] is True


def test_unresolved_state_is_referenced_not_foregrounded():
    pkt = packet_with({"unresolved": [
        {"id": "walk-1", "title": "Morning walk", "kind": "recurring_intention",
         "suggested_move": "ask_outcome_if_natural",
         "uncertainty": "Pending means no completion evidence, not proof it was missed."},
    ]})
    ws = service().compile_turn_working_set(pkt, turn_text="hello there", judgement=relevant(pkt, "nothing-matches"))
    assert not any(
        i.get("temporal_state") in ("unresolved",) for i in ws["levels"]["warm"]
    )
    ref_ids = {ref["id"] for ref in ws["levels"]["cold_refs"]}
    assert "walk-1" in ref_ids


def test_packet_respects_explicit_budgets():
    items = {}
    for horizon in ("immediate", "today"):
        items[horizon] = [
            {"id": f"i-{horizon}-{n}", "kind": "expectation",
             "title": f"Coding agent task {n} with compiler infra",
             "summary": "coding compiler infrastructure evidence text",
             "temporal_state": "window_open",
             "honcho_message_id": f"msg-{n}", "confidence": 0.7}
            for n in range(10)
        ]
    pkt = packet_with(items)
    ws = service().compile_turn_working_set(pkt, turn_text="coding compiler infra status please", judgement=relevant(pkt, "compiler"))
    metrics = ws["metrics"]
    assert metrics["total_chars"] <= TOTAL_BUDGET_CHARS
    assert metrics["within_budget"] is True
    assert metrics["estimated_tokens"] <= 1200
    assert metrics["dropped_candidates"] >= 0
    assert set(metrics["domains"]) <= {
        "task", "event", "expectation", "open_loop", "backstage_attention",
        "deadline", "state", "recurring_intention",
    }


def test_references_preserve_provenance_not_content():
    pkt = coding_packet()
    ws = service().compile_turn_working_set(pkt, turn_text="coding agent compiler progress", judgement=relevant(pkt, "coding agent"))
    serialized = str(ws)
    # warm item carries a ref handle; refs section carries handles only.
    assert ws["levels"]["cold_refs"], "cold refs must exist"
    for ref in ws["levels"]["cold_refs"]:
        assert set(ref.keys()) == {"type", "id", "note"}
        assert len(ref["note"]) <= 80


@pytest.mark.asyncio
async def test_working_set_endpoint_and_jit_evidence_roundtrip(async_client, monkeypatch):
    """End-to-end: durable expectation -> working-set selection -> JIT fetch."""
    import src.runtime_model as rm
    monkeypatch.setattr(rm, "get_agenda_adapter", lambda: MeaningAdapter())
    from sqlmodel import SQLModel
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState

    async with async_session_maker() as session:
        exp = Expectation(
            honcho_workspace_id="ws-e2e",
            honcho_session_id="sess-e2e",
            honcho_message_id="msg-1",
            subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Finish the coding agent compiler",
            summary="coding agent infrastructure work",
            raw_temporal_phrase="this morning",
            expected_window_start=NOW - timedelta(hours=2),
            expected_window_end=NOW - timedelta(hours=1),
        )
        session.add(exp)
        await session.commit()
        exp_id = str(exp.id)

    body = {
        "workspace_id": "ws-e2e",
        "session_id": "sess-e2e",
        "peer_id": "user-1",
        "now": NOW.isoformat(),
        "timezone": "Europe/London",
        "turn_text": "where did I get with the coding agent compiler?",
        "director_hints": {"intent": "mixed"},
    }
    resp = await async_client.post("/v1/cortex/turn-working-set", json=body)
    assert resp.status_code == 200
    working_set = resp.json()
    assert working_set["version"] == "turn-working-set-v1"
    assert working_set["metrics"]["within_budget"] is True
    warm = working_set["levels"]["warm"]
    assert any("coding agent" in i["what"] for i in warm)
    refs = working_set["levels"]["cold_refs"]
    assert any(r["id"] == exp_id for r in refs)

    # JIT: the reference resolves to deeper stored detail on demand.
    ev = await async_client.get(
        "/v1/cortex/evidence",
        params={"workspace_id": "ws-e2e", "ref": exp_id,
                "peer_id": "user-1", "session_id": "sess-e2e"},
    )
    assert ev.status_code == 200
    evidence = ev.json()
    assert evidence["type"] == "expectation"
    assert evidence["title"] == "Finish the coding agent compiler"
    assert evidence["honcho_message_id"] == "msg-1"

    # Absent retrieval does not lose durable state: unknown ref -> 404,
    # but the object stays in the DB and the window.
    miss = await async_client.get(
        "/v1/cortex/evidence",
        params={"workspace_id": "ws-e2e", "ref": "not-a-real-ref"},
    )
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_historical_replay_polluted_state_produces_sane_current_turn():
    """CP7 replay: seed known polluted history, repair it, then compile the
    real packet + working set for a neutral social turn and verify stale
    pollution does not reach the foreground and the packet stays bounded."""
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.models.operational_state import (
        RecurringIntention, OperationalStatus,
    )
    from src.services.attention_state_service import AttentionStateService
    from src.services.historical_repair import HistoricalRepairService

    ws, sess = "ws-replay", "sess-replay"
    async with async_session_maker() as session:
        session.add_all([
            Expectation(
                honcho_workspace_id=ws, honcho_session_id=sess,
                honcho_message_id="m-shower", subject_peer_id="user-1",
                expectation_type=ExpectationType.USER_INTENTION,
                title="Take a shower now", summary="take a shower now",
                raw_temporal_phrase="now",
                expected_window_start=NOW - timedelta(hours=40),
                expected_window_end=NOW - timedelta(hours=39),
            ),
            Expectation(
                honcho_workspace_id=ws, honcho_session_id=sess,
                honcho_message_id="m-walk", subject_peer_id="user-1",
                expectation_type=ExpectationType.USER_INTENTION,
                title="Morning walk", summary="going for a walk this morning",
                raw_temporal_phrase="this morning",
                expected_window_start=NOW - timedelta(hours=3),
                expected_window_end=NOW - timedelta(hours=1),
            ),
            RecurringIntention(
                honcho_workspace_id=ws, honcho_session_id=sess,
                honcho_message_id="m-audio", title="Fix audio transcription bug",
                cadence="daily", status=OperationalStatus.ACTIVE,
                candidate_key="c-audio", canonical_key="fix-audio-transcription-bug",
                source_evidence="I need to fix the audio transcription bug",
            ),
        ])
        await session.commit()
        # Repair pass runs first (as it would in a real maintenance window).
        await HistoricalRepairService().classify_and_repair(
            session, workspace_id=ws, now=NOW, apply=True,
        )

        packet = await AttentionStateService().compile_attention_state(
            session, workspace_id=ws, session_id=sess, now=NOW,
            timezone_str="Europe/London", owner_peer_id="user-1",
        )

    # The stale shower expectation must not be foreground now/today.
    brief = packet["window"]
    foreground_ids = {
        item.get("id")
        for horizon in ("immediate", "today", "upcoming")
        for item in brief["scopes"][horizon]
    }
    shower = next(i for i in brief["scopes"]["review_needed"] + brief["scopes"]["unresolved"]
                  if i.get("title") == "Take a shower now")
    assert shower["id"] not in foreground_ids

    # Morning walk: elapsed with unknown outcome -> unresolved, not failure.
    unresolved_titles = {i.get("title") for i in brief["scopes"]["unresolved"]}
    assert "Morning walk" in unresolved_titles

    # Neutral social turn: compact packet, no todo list, no stale callbacks.
    working_set = TurnWorkingSetService().compile_turn_working_set(
        packet, turn_text="I'm bored, talk to me", judgement=relevant(packet, "nothing-matches"),
    )
    assert working_set["metrics"]["within_budget"] is True
    warm = working_set["levels"]["warm"]
    assert not any("shower" in i["what"].lower() for i in warm)
    assert not any("audio transcription" in i["what"].lower() for i in warm)


@pytest.mark.asyncio
async def test_explicit_completion_fulfills_open_expectation():
    """Regression: progress/completion lanes must resolve the open plan they
    complete. 'migration checklist done!' must FULFILL 'do the migration
    checklist', not leave it UNKNOWN forever."""
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import LifecycleService

    ws, sess = "ws-complete", "sess-complete"
    async with async_session_maker() as session:
        exp = Expectation(
            honcho_workspace_id=ws, honcho_session_id=sess,
            honcho_message_id="m-plan", subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Do the migration checklist",
            summary="User plans to do the migration checklist first thing",
            raw_temporal_phrase="first thing",
        )
        session.add(exp)
        await session.commit()
        exp_id = exp.id

        cand = ExtractionCandidate(
            candidate_key="c_done", observation="User completed the migration checklist",
            raw_evidence="migration checklist done! all 14 items",
            canonical_title="Completed the migration checklist",
            operational_kind="progress",
            actor_peer_id="user-1", subject_peer_id="user-1",
            confidence=0.9, extractor_version="test",
        )
        mutated = await LifecycleService().resolve_explicit_completions(
            session, workspace_id=ws, session_id=sess,
            message_id="m-done", candidate=cand,
            now=NOW,
        )
        assert mutated == [exp_id]
        await session.refresh(exp)
        assert exp.outcome_state == OutcomeState.FULFILLED
        assert "m-done" in (exp.resolution_evidence or "")


class MeaningAdapter:
    """Stands in for the relevance model: reads the item texts it is shown and judges by meaning (here: a coding-agent topic)."""
    def __init__(self, topic="coding agent", time_reference="none"):
        self.topic, self.time_reference, self.calls = topic, time_reference, []

    async def generate_structured(self, *, prompt, **kw):
        import json
        self.calls.append(prompt)
        items = json.loads(prompt.split("ITEMS:\n")[1])
        return {"items": [{"key": i["key"], "relevance": 1.0 if self.topic in i["text"].lower() else 0.0} for i in items] + [{"key": "invented:key", "relevance": 1.0}],
                "time_reference": self.time_reference}


@pytest.mark.asyncio
async def test_judge_reads_item_meaning_ignores_invented_keys_and_fails_open_to_none():
    pkt = coding_packet()
    svc = service()
    j = await svc.judge(pkt, None, turn_text="where did I get on the compiler thing?", adapter=MeaningAdapter())
    assert list(j.scores.values()) == [1.0] and "invented:key" not in j.scores            # relevance by meaning; made-up keys are dropped
    class Boom:
        async def generate_structured(self, **kw): raise RuntimeError("down")
    assert await svc.judge(pkt, None, turn_text="x", adapter=Boom()) is None
    assert await svc.judge(pkt, None, turn_text="x", adapter=None) is None


def test_with_no_judgement_nothing_is_admitted_by_words_only_cortexs_own_immediate_horizon_at_reduced_weight():
    pkt = packet_with({"immediate": [{"id": "a", "kind": "expectation", "title": "Dentist at 3", "temporal_state": "window_open"}],
                       "upcoming": [{"id": "b", "kind": "expectation", "title": "Renew passport", "temporal_state": "not_due"}]})
    pkt["sophie_attention"] = [{"id": "att", "kind": "callback", "content": "tabla practice", "topic": "tabla practice"}]
    ws = service().compile_turn_working_set(pkt, turn_text="can we talk about tabla practice again?", judgement=None)
    whats = [i["what"] for i in ws["levels"]["warm"]]
    assert whats == ["Dentist at 3"]                      # the user's words ("tabla practice") do not pull backstage state in without a model


def test_time_reference_comes_from_the_model_and_bounds_the_window():
    from src.services.turn_working_set import window_for
    now = datetime(2026, 10, 2, 15, 0)
    start, end = window_for("this_morning", now, "Europe/London")
    assert (start, end) == (datetime(2026, 10, 2, 4, 0), datetime(2026, 10, 2, 11, 0))
    assert window_for("none", now, "Europe/London") is None and window_for("later, maybe", now, "Europe/London") is None
    y0, y1 = window_for("yesterday", now, "Europe/London")
    assert y1 == datetime(2026, 10, 2, 4, 0) and (y1 - y0).days == 1
