"""H1 experiment: the one-call delta ledger writer. No network: the model is a canned JSON reply; the tools, validation and finish gate are the real ones."""
import pytest

from src.db import async_session_maker
from src.services import ledger_light, memory_pipeline, nano_adapter


async def _seed(db):
    db.add(memory_pipeline.LedgerItem(honcho_workspace_id="wl", owner_peer_id="u1", kind="commitment", title="Vinesh review Thursday", detail="d",
                                      status="open", situation_key="vinesh-review", timing_text="Thursday"))
    db.add(memory_pipeline.LedgerItem(honcho_workspace_id="wl", owner_peer_id="u1", kind="commitment", title="Ashley renders", detail="d",
                                      status="open", situation_key="ashley-renders", timing_text="Tuesday"))
    await db.commit()


def _script(monkeypatch, replies):
    seen = []

    async def fake(*, system, prompt, models=None, max_tokens=0, temperature=0, title=""):
        seen.append({"system": system, "prompt": prompt, "models": models})
        return dict(replies[min(len(seen) - 1, len(replies) - 1)], _model="fake")
    monkeypatch.setattr(nano_adapter, "generate_json", fake)
    return seen


GOOD = {"ops": [
    {"tool": "update_item", "args": {"key": "ashley-renders", "status": "done", "evidence": "loved the renders, done"}},
    {"tool": "update_item", "args": {"key": "vinesh-review", "timing_text": "Friday morning", "expected_date": "2026-10-23", "time_role": "happens",
                                     "evidence": "moved to Friday morning"}}],
    "accounting": [{"obs": 1, "treatment": "applied", "key": "ashley-renders"}, {"obs": 2, "treatment": "applied", "key": "vinesh-review"}],
    "transcript_sweep": "nothing beyond the observations", "summary": "closed Ashley, moved Vinesh"}


@pytest.mark.asyncio
async def test_one_call_does_what_the_agent_needed_four_for(monkeypatch):
    seen = _script(monkeypatch, [GOOD])
    async with async_session_maker() as db:
        await _seed(db)
        out = await ledger_light.run(db, workspace_id="wl", owner="u1", session_id="s2", n_observations=2, today="2026-10-19",
                                     observations="[O1] Ashley loved the renders, done\n[O2] Vinesh moved to Friday morning",
                                     transcript="Person: Ashley loved the renders, done. Vinesh moved to Friday morning.")
    assert out["status"] == "verified" and len(out["calls"]) == 1 and len(seen) == 1
    async with async_session_maker() as db:
        rows = {r.situation_key: r for r in await memory_pipeline.open_ledger(db, "wl", "u1", limit=50)}
    assert "ashley-renders" not in rows and rows["vinesh-review"].expected_date.strftime("%Y-%m-%d") == "2026-10-23"


@pytest.mark.asyncio
async def test_a_failed_gate_gets_one_repair_round_and_then_stops(monkeypatch):
    bad = dict(GOOD, accounting=[{"obs": 1, "treatment": "applied", "key": "ashley-renders"}])      # observation 2 unaccounted
    repair = dict(GOOD, ops=[])          # what is applied stays applied: the repair round only completes the accounting
    seen = _script(monkeypatch, [bad, repair])
    async with async_session_maker() as db:
        await _seed(db)
        out = await ledger_light.run(db, workspace_id="wl", owner="u1", session_id="s3", n_observations=2, today="2026-10-19",
                                     observations="[O1] Ashley loved the renders, done\n[O2] Vinesh moved to Friday morning",
                                     transcript="Person: Ashley loved the renders, done. Vinesh moved to Friday morning.")
    assert len(seen) == 2 and "unaccounted" in seen[1]["prompt"], out
    assert out["status"] == "verified", out["gate_failures"]


@pytest.mark.asyncio
async def test_no_json_is_reported_not_papered_over(monkeypatch):
    async def none(**kw):
        return None
    monkeypatch.setattr(nano_adapter, "generate_json", none)
    async with async_session_maker() as db:
        await _seed(db)
        out = await ledger_light.run(db, workspace_id="wl", owner="u1", session_id="s4", n_observations=1, today="2026-10-19", observations="[O1] x")
    assert out["status"] != "verified" and out["wrote"] is False
