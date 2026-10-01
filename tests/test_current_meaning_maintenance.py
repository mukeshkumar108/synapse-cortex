"""T2 current-meaning maintenance tests (the state-views / candidate-moves /
operational-decision layers were retired by the Cortex cutover; their roles
are now AttentionState + projections, see tests/test_attention_state.py and
tests/test_projections.py).

T2 revises only on mutating turns with cooldown. No foreground wiring.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker


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
