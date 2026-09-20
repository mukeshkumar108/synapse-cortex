"""Release-path authority semantics at the Cortex endpoint (deterministic).

Drives POST /v1/cortex/current-meaning/revise-sync through
T1 revised/active → T2 unchanged/backgrounded → T3 unchanged/active with a
scripted interpreter (monkeypatched adapter — test-only; production resolves
its own model adapter). Asserts: authority steps down and back with ZERO new
rows, identical id/version throughout, supersession untouched.

The live-interpreter question (does softening actually emit backgrounded?)
is probe D, MEASURED not gated:
synapse-cortex/scripts/probe_authority_matrix.py.
"""

from datetime import datetime, timezone

import pytest


class ScriptedMeaningAdapter:
    """Test-only interpreter stand-in: yields scripted raw outputs in order."""

    def __init__(self, raws: list):
        self._raws = list(raws)
        self.calls = 0

    async def generate_structured(self, **kwargs):
        idx = min(self.calls, len(self._raws) - 1)
        self.calls += 1
        return self._raws[idx]


def _scope(n: str):
    return {
        "workspace_id": "ws-auth",
        "session_id": f"sess-{n}",
        "peer_id": "user_1",
        "message_id": f"m-{n}-t1",
        "turn_text": "you cancelled our walk and I am still hurt about it",
        "recent_conversation": [],
    }


def _raw(revision: str, authority: str, no_change: bool, means=("Y-MEANS",), unresolved=("Z-OPEN",)):
    return {
        "means": list(means),
        "unresolved": list(unresolved),
        "foreground_authority": authority,
        "evidence_span": "cancelled our walk",
        "confidence": 0.9,
        "no_change": no_change,
    }


def _count_rows():
    from src.db import async_session_maker
    from src.models.current_meaning import CurrentMeaning
    from sqlmodel import select, func

    async def _run():
        async with async_session_maker() as db:
            return (await db.execute(select(func.count()).select_from(CurrentMeaning))).scalar()
    return _run()


async def test_release_and_reactivation_without_version_churn(async_client, monkeypatch):
    import src.routers.v1_cortex as cortex_router

    raws = [
        _raw("revised", "active", False),       # T1: establish v1
        _raw("unchanged", "backgrounded", True, means=(), unresolved=()),  # T2: release
        _raw("unchanged", "active", True, means=(), unresolved=()),        # T3: reactivate
    ]
    scripted = ScriptedMeaningAdapter(raws)
    monkeypatch.setattr(cortex_router, "get_agenda_adapter", lambda: scripted)

    base = _scope("churn")
    r1 = await async_client.post("/v1/cortex/current-meaning/revise-sync", json=base)
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["meaning_revision"] == "revised" and b1["foreground_authority"] == "active"
    v1_id, v1_version = b1["active"]["id"], b1["active"]["version"]

    t2 = dict(base, message_id="m-churn-t2",
              turn_text="hey, that was kind of you to just own it — I feel a lot lighter",
              expected_prior_id=v1_id, expected_prior_version=v1_version)
    r2 = await async_client.post("/v1/cortex/current-meaning/revise-sync", json=t2)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["meaning_revision"] == "unchanged"
    assert b2["foreground_authority"] == "backgrounded"
    assert b2["active"]["id"] == v1_id and b2["active"]["version"] == v1_version
    assert b2["revision"] is None  # authority-only transition: zero rows

    t3 = dict(base, message_id="m-churn-t3",
              turn_text="do you even remember what you cancelled?",
              expected_prior_id=v1_id, expected_prior_version=v1_version)
    r3 = await async_client.post("/v1/cortex/current-meaning/revise-sync", json=t3)
    assert r3.status_code == 200
    b3 = r3.json()
    assert b3["meaning_revision"] == "unchanged"
    assert b3["foreground_authority"] == "active"
    assert b3["active"]["id"] == v1_id and b3["active"]["version"] == v1_version
    assert b3["revision"] is None

    # Exactly one row exists in the whole table for this scope: v1.
    from src.db import async_session_maker
    from src.models.current_meaning import CurrentMeaning, scope_key_for
    from sqlmodel import select

    async with async_session_maker() as db:
        rows = (await db.execute(select(CurrentMeaning).where(
            CurrentMeaning.scope_key == scope_key_for("ws-auth", "sophie", "sess-churn", "user_1"),
        ))).scalars().all()
    assert len(rows) == 1
    assert rows[0].superseded_by_id is None
