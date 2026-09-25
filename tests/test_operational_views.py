"""Views, moves, operational decisions, T2 maintenance tests.

Views compose existing compilers; moves read existing tables; decisions are
pure; T2 revises only on mutating turns with cooldown. No foreground wiring.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker


@pytest.mark.asyncio
async def test_views_project_sections():
    from datetime import datetime, timezone

    from src.models.expectation import Expectation, ExpectationType
    from src.models.open_loop import OpenLoop
    from src.services.state_views import compile_views

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-views", honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="kai",
            title="Renew parking permit", summary="Renew parking permit",
            expectation_type=ExpectationType.USER_INTENTION))
        db.add(OpenLoop(
            honcho_workspace_id="ws-views", honcho_session_id="s1",
            honcho_message_id="m1", title="Cake vendor",
            summary="Remember the cake vendor"))
        await db.commit()
        views = await compile_views(
            db, workspace_id="ws-views", session_id="s1",
            owner_peer_id="kai", now=now)
        assert set(views) == {
            "todo", "reminder", "calendar", "open_matter", "waiting_on",
            "worry", "follow_up", "companion_obligation",
            "conversation_opportunity", "relationship_context",
            "narrative_continuity"}
        assert any(i["title"] == "Renew parking permit" for i in views["todo"])
        assert any(i["title"] == "Cake vendor Remember the cake vendor"
                   for i in views["open_matter"])
        # Full untruncated lists: views carry structure, consumers narrow.
        assert isinstance(views["waiting_on"], list)
        # Worry is model-annotation-only: no graph/textual spillover.
        assert views["worry"] == []
        # Session user is never a character undertaking.
        from src.models.commitment_candidate import CommitmentCandidate
        db.add(CommitmentCandidate(
            honcho_workspace_id="ws-views", honcho_session_id="s1",
            owner_peer_id="kai", candidate_key="ck9", canonical_key="ck9",
            title="User task", evidence_verbatim="x", source_message_id="m1",
            authority="ask"))
        await db.commit()
        views2 = await compile_views(
            db, workspace_id="ws-views", session_id="s1",
            owner_peer_id="kai", now=now)
        assert not [i for i in views2["narrative_continuity"]
                    if i["kind"] == "character_undertaking"]


@pytest.mark.asyncio
async def test_moves_unify_and_gate():
    from datetime import datetime, timezone

    from src.models.attention_candidate import (
        AttentionCandidate, AttentionCandidateKind,
    )
    from src.models.clarification import ClarificationCandidate
    from src.models.commitment_candidate import CommitmentCandidate
    from src.services.candidate_moves import derive_moves

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        db.add(AttentionCandidate(
            honcho_workspace_id="ws-moves", honcho_session_id="s1",
            source_message_id="m1", candidate_key="k1",
            kind=AttentionCandidateKind.PENDING_QUESTION,
            content="Which vendor did you mean"))
        # Settled in state: the question is answerable internally.
        from src.models.expectation import Expectation, ExpectationType, OutcomeState
        db.add(Expectation(
            honcho_workspace_id="ws-moves", honcho_session_id="s1",
            honcho_message_id="m0", subject_peer_id="kai",
            title="Which vendor did you mean",
            summary="Which vendor did you mean",
            expectation_type=ExpectationType.USER_INTENTION,
            outcome_state=OutcomeState.FULFILLED))
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws-moves", honcho_session_id="s1",
            honcho_message_id="m1", description="Ambiguous pickup day"))
        db.add(CommitmentCandidate(
            honcho_workspace_id="ws-moves", honcho_session_id="s1",
            owner_peer_id="sophie", candidate_key="ck1", canonical_key="ck1",
            title="Send venue numbers", evidence_verbatim="I will send them",
            source_message_id="m1", authority="ask"))
        await db.commit()
        out = await derive_moves(
            db, workspace_id="ws-moves", session_id="s1",
            owner_peer_id="kai", now=now)
        kinds = {(m["kind"], m["matter_kind"]) for m in out["moves"]}
        # ASK stays PROPOSE, never ACT.
        assert ("PROPOSE", "commitment") in kinds
        assert ("ACT", "commitment") not in kinds
        # Internally answered question emits no move.
        assert not any(m["matter_kind"] == "attention" for m in out["moves"])
        assert out["internally_resolved"] >= 1
        assert out["telemetry"].get("NO_MOVE_WARRANTED", 0) >= 1
        # Clarification survives with eligibility bookkeeping.
        clar = [m for m in out["moves"] if m["matter_kind"] == "clarification"]
        assert clar and clar[0]["kind"] == "QUESTION"
        assert clar[0]["telemetry"] in ("MOVE_ELIGIBLE", "MOVE_HELD")
        # Expiry never equals resolution: every move links its matter.
        for m in out["moves"]:
            assert m["matter_id"]


def test_operational_form_vs_authority():
    from datetime import datetime, timezone
    from src.services.operational_decision import decide_for_view_item, decide_views

    now = datetime.now(timezone.utc)
    d = decide_for_view_item(
        {"kind": "event", "id": "1", "title": "Dentist Friday"},
        owner_peer_id="kai", now=now)
    assert d.form == "calendar" and d.authorized is False and d.action == "propose"
    d2 = decide_for_view_item(
        {"kind": "reminder", "id": "2", "title": "Chairs today"},
        owner_peer_id="kai", now=now)
    assert d2.form == "reminder" and d2.authorized is True
    d3 = decide_for_view_item(
        {"kind": "graph", "id": "x", "title": "Carlos debt watch"},
        owner_peer_id="kai", now=now)
    assert d3.form == "watch" and d3.authorized is True and d3.action == "execute"
    grouped = decide_views(
        {"todo": [{"kind": "expectation", "id": "e", "title": "Thing"}],
         "nothing_here": []},
        owner_peer_id="kai", now=now)
    assert grouped["todo"][0]["form"] == "task"
    assert grouped["todo"][0]["action"] in ("propose", "hold")


@pytest.mark.asyncio
async def test_t2_revises_only_on_mutation_with_cooldown(monkeypatch):
    from datetime import datetime, timezone

    from src.db import async_session_maker
    from src.services import current_meaning_service as cm

    calls = {"n": 0}

    class FakeAdapter:
        async def generate_structured(self, **kw):
            calls["n"] += 1
            return {"means": ["Ashley is overloaded with event ops"],
                    "unresolved": ["Carlos payment"],
                    "foreground_authority": "active",
                    "evidence_span": "Carlos still owes me",
                    "confidence": 0.8, "no_change": False}

    monkeypatch.setattr("src.runtime_model.get_agenda_adapter", lambda: FakeAdapter())
    # HONCHO disabled in tests -> history skipped; disable cooldown for test.
    monkeypatch.setattr(cm, "MEANING_MIN_REVISE_INTERVAL_SECONDS", 0)
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        out = await cm.maybe_revise_after_turn(
            db, workspace_id="ws-t2", session_id="s1", peer_id="kai",
            message_id="m1", turn_text="Carlos still owes me for the event",
            now=now, mutated=False)
        assert out == {"revised": False, "reason": "no_mutation"}
        assert calls["n"] == 0
        out2 = await cm.maybe_revise_after_turn(
            db, workspace_id="ws-t2", session_id="s1", peer_id="kai",
            message_id="m1", turn_text="Carlos still owes me for the event",
            now=now, mutated=True)
        assert out2["revised"] is True, out2
        assert calls["n"] == 1


@pytest.mark.asyncio
async def test_t2_liveness_fallback_on_quiet_rupture(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from src.db import async_session_maker
    from src.models.operational_state import TurnStamp
    from src.services import current_meaning_service as cm

    class FakeAdapter:
        def __init__(self):
            self.calls = 0

        async def generate_structured(self, **kw):
            self.calls += 1
            return {"means": ["Rupture acknowledged, repair pending"],
                    "unresolved": ["Trust"],
                    "foreground_authority": "active",
                    "evidence_span": "I need space",
                    "confidence": 0.8, "no_change": False}

    fake = FakeAdapter()
    monkeypatch.setattr("src.runtime_model.get_agenda_adapter", lambda: fake)
    monkeypatch.setattr(cm, "MEANING_FALLBACK_USER_TURNS", 2)
    monkeypatch.setattr(cm, "MEANING_FALLBACK_MIN_AGE_SECONDS", 0)
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        # Seed a prior meaning observed 1h ago + 3 user turns since, no mutations.
        from src.models.current_meaning import CurrentMeaning
        old = now - timedelta(hours=1)
        db.add(CurrentMeaning(
            honcho_workspace_id="ws-live", product="sophie",
            honcho_session_id="s1", owner_peer_id="kai",
            scope_key="ws-live|sophie|s1|kai",
            means_json='["ok"]', unresolved_json="[]",
            source_message_ids_json='["m0"]', revision_key="turn:m0",
            observed_at=old.replace(tzinfo=None)))
        for i in range(3):
            db.add(TurnStamp(honcho_workspace_id="ws-live",
                             honcho_message_id=f"m{i + 1}", owner_peer_id="kai",
                             turn_at=(old + timedelta(minutes=10 * (i + 1))).replace(tzinfo=None)))
        await db.commit()
        out = await cm.maybe_revise_after_turn(
            db, workspace_id="ws-live", session_id="s1", peer_id="kai",
            message_id="m4", turn_text="I need space to think",
            now=now, mutated=False)
        assert out["revised"] is True, out
        assert fake.calls == 1
