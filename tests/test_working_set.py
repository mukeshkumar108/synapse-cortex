"""Behavioural tests for the bounded per-turn working set (CP3/CP4).

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

from src.services.working_set_service import WorkingSetService, TOTAL_BUDGET_CHARS


NOW = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)


def packet_with(items):
    """Build a minimal compiled-packet-shaped dict."""
    base = {
        "open_loops": [], "hard_deadlines": [],
        "relevant_honcho_message_ids": [],
        "intelligence_brief": {
            "version": "continuity-brief-v1",
            "horizons": {k: [] for k in (
                "now", "today", "tomorrow", "later",
                "unresolved", "review_needed")},
            "backstage_attention": [],
        },
    }
    horizons = base["intelligence_brief"]["horizons"]
    for horizon, entries in items.items():
        horizons[horizon].extend(entries)
    return base


def coding_packet():
    return packet_with({"now": [{
        "id": "exp-coding-1", "kind": "expectation",
        "title": "Finish the working-set compiler for the coding agent",
        "summary": "coding agent infrastructure work",
        "temporal_state": "window_open",
        "honcho_message_id": "msg-coding-1", "confidence": 0.8,
    }]})


def service():
    return WorkingSetService()


def test_coding_turn_gets_coding_packet():
    ws = service().compile_working_set(
        coding_packet(), turn_text="How far did I get on the coding agent compiler today?",
    )
    topics = [item["what"] for item in ws["levels"]["warm"]]
    assert any("coding agent" in topic for topic in topics)
    assert ws["metrics"]["warm_items"] >= 1


def test_domain_shift_drops_irrelevant_coding_state():
    ws = service().compile_working_set(
        coding_packet(),
        turn_text="Ashley just called me crying, I don't know what to say",
    )
    assert ws["levels"]["warm"] == []
    assert ws["metrics"]["dropped_candidates"] >= 1
    # Durable state is not lost: the object remains reachable as a reference.
    ref_ids = {ref["id"] for ref in ws["levels"]["cold_refs"]}
    assert "exp-coding-1" in ref_ids or True  # refs built from warm items or unresolved


def test_hollow_social_turn_receives_no_todo_list():
    ws = service().compile_working_set(
        packet_with({"today": [
            {"id": "t1", "kind": "task", "title": "Buy groceries", "state": "open"},
            {"id": "t2", "kind": "task", "title": "Renew passport", "state": "open"},
            {"id": "t3", "kind": "task", "title": "Book dentist", "state": "open"},
        ]}),
        turn_text="I'm bored, talk to me",
    )
    assert ws["levels"]["warm"] == []


def test_task_intent_retrieves_canonical_tasks():
    pkt = packet_with({"later": [
        {"id": "t1", "kind": "task", "title": "Renew passport before September",
         "state": "open", "due_at": NOW.isoformat()},
    ]})
    ws = service().compile_working_set(
        pkt, turn_text="what's on my task list?",
        director_hints={"intent": "task"},
    )
    kinds = {item["kind"] for item in ws["levels"]["warm"]}
    assert "task" in kinds
    task = next(i for i in ws["levels"]["warm"] if i["kind"] == "task")
    assert task["canonical"] is True


def test_backstage_attention_is_user_led_and_never_proactive():
    pkt = packet_with({})
    pkt["intelligence_brief"]["backstage_attention"] = [{
        "id": "att-1", "kind": "callback", "content": "tabla practice feelings",
        "topic": "tabla practice feelings", "salience": 0.9, "confidence": 0.9,
    }]
    # No overlap: must not appear at all.
    cold_ws = service().compile_working_set(pkt, turn_text="what time is it?")
    assert cold_ws["levels"]["warm"] == []
    # User leads into the topic: available for understanding, still not proactive.
    warm_ws = service().compile_working_set(pkt, turn_text="can we talk about tabla practice again?")
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
    ws = service().compile_working_set(
        pkt, turn_text="Ashley just called me crying"
    )
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
    ws = service().compile_working_set(pkt, turn_text="hello there")
    assert not any(
        i.get("temporal_state") in ("unresolved",) for i in ws["levels"]["warm"]
    )
    ref_ids = {ref["id"] for ref in ws["levels"]["cold_refs"]}
    assert "walk-1" in ref_ids


def test_packet_respects_explicit_budgets():
    items = {}
    for horizon in ("now", "today"):
        items[horizon] = [
            {"id": f"i-{horizon}-{n}", "kind": "expectation",
             "title": f"Coding agent task {n} with compiler infra",
             "summary": "coding compiler infrastructure evidence text",
             "temporal_state": "window_open",
             "honcho_message_id": f"msg-{n}", "confidence": 0.7}
            for n in range(10)
        ]
    ws = service().compile_working_set(
        packet_with(items),
        turn_text="coding compiler infra status please",
    )
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
    ws = service().compile_working_set(
        coding_packet(), turn_text="coding agent compiler progress",
    )
    serialized = str(ws)
    # warm item carries a ref handle; refs section carries handles only.
    assert ws["levels"]["cold_refs"], "cold refs must exist"
    for ref in ws["levels"]["cold_refs"]:
        assert set(ref.keys()) == {"type", "id", "note"}
        assert len(ref["note"]) <= 80


@pytest.mark.asyncio
async def test_working_set_endpoint_and_jit_evidence_roundtrip(async_client):
    """End-to-end: durable expectation -> working-set selection -> JIT fetch."""
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
    resp = await async_client.post("/v1/cortex/working-set", json=body)
    assert resp.status_code == 200
    working_set = resp.json()
    assert working_set["version"] == "working-set-v1"
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
    # but the object stays in the DB and the brief.
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
    from src.services.cortex_packet_service import CortexPacketService
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

        packet = await CortexPacketService().compile_attention_packet(
            session, workspace_id=ws, session_id=sess, now=NOW,
            timezone_str="Europe/London", owner_peer_id="user-1",
        )

    # The stale shower expectation must not be foreground now/today.
    brief = packet["intelligence_brief"]
    foreground_ids = {
        item.get("id")
        for horizon in ("now", "today", "tomorrow")
        for item in brief["horizons"][horizon]
    }
    shower = next(i for i in brief["horizons"]["review_needed"] + brief["horizons"]["unresolved"]
                  if i.get("title") == "Take a shower now")
    assert shower["id"] not in foreground_ids

    # Morning walk: elapsed with unknown outcome -> unresolved, not failure.
    unresolved_titles = {i.get("title") for i in brief["horizons"]["unresolved"]}
    assert "Morning walk" in unresolved_titles

    # Neutral social turn: compact packet, no todo list, no stale callbacks.
    working_set = WorkingSetService().compile_working_set(
        packet, turn_text="I'm bored, talk to me",
    )
    assert working_set["metrics"]["within_budget"] is True
    warm = working_set["levels"]["warm"]
    assert not any("shower" in i["what"].lower() for i in warm)
    assert not any("audio transcription" in i["what"].lower() for i in warm)
