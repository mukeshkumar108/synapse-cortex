"""GET /v1/memory/ledger: the deterministic views over HTTP, product-scoped like every other memory route."""
import uuid

import pytest

from src.config import settings
from src.db import async_session_maker
from src.models.world import LedgerItem
from src.services import memory_pipeline as mp


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    monkeypatch.setattr(settings, "SYNAPSE_CORTEX_API_TOKEN", "legacy", raising=False)
    monkeypatch.setattr(settings, "SYNAPSE_PRODUCT_TOKENS", "sophie=ts,bloom=tb", raising=False)


def H(t): return {"Authorization": f"Bearer {t}"}


async def _seed(ws, owner, rows):
    from datetime import datetime
    async with async_session_maker() as db:
        for key, title, d, t, role, status, q in rows:
            db.add(LedgerItem(honcho_workspace_id=ws, owner_peer_id=owner, kind="event", title=title, status=status, situation_key=key,
                              expected_date=datetime.strptime(d, "%Y-%m-%d") if d else None, expected_time=t, time_role=role,
                              time_zone="Europe/London", question_text=q))
        await db.commit()


ROWS = [("call", "Call with Vinesh", "2026-10-20", "15:00", "happens", "open", ""),
        ("prop", "Submit the proposal", "2026-10-20", "17:00", "deadline", "open", ""),
        ("dent", "Dentist", "2026-10-22", "", "happens", "open", "what time?"),
        ("old", "Pay invoice", "2026-10-18", "", "deadline", "open", "")]


@pytest.mark.asyncio
async def test_awareness_range_and_needs_detail(async_client):
    o = f"u-{uuid.uuid4().hex[:6]}"
    await _seed("wsL", o, ROWS)
    q = {"workspace_id": "wsL", "owner": o, "time_zone": "Europe/London"}
    r = (await async_client.get("/v1/memory/ledger", params={**q, "now": "2026-10-20T13:30:00+00:00"}, headers=H("legacy"))).json()       # 14:30 BST
    assert "Right now (next 3 hours):" in r["text"] and "Call with Vinesh" in r["text"] and "Overdue:" in r["text"] and "Pay invoice" in r["text"]
    assert {c["band"] for c in r["cues"]} >= {"imminent", "overdue", "week"} and r["time_zone"] == "Europe/London"
    wk = (await async_client.get("/v1/memory/ledger", params={**q, "view": "range", "period": "week", "now": "2026-10-20T08:00:00+01:00"}, headers=H("legacy"))).json()
    assert wk["from"] == "2026-10-20" and wk["to"] == "2026-10-26" and "Thursday 22 October:" in wk["text"] and "time not recorded" in wk["text"]
    span = (await async_client.get("/v1/memory/ledger", params={**q, "view": "range", "date_from": "2026-10-22", "date_to": "2026-10-22", "now": "2026-10-20T08:00:00+01:00"}, headers=H("legacy"))).json()
    assert "Dentist" in span["text"] and "Call with Vinesh" not in span["text"]
    nd = (await async_client.get("/v1/memory/ledger", params={**q, "view": "needs_detail", "now": "2026-10-20T08:00:00+01:00"}, headers=H("legacy"))).json()
    assert [c["key"] for c in nd["cues"]] == ["dent"]
    for bad in ({"view": "range", "period": "fortnight"}, {"view": "nope"}, {"now": "tuesday"}, {"view": "range", "date_from": "2026-10-22", "date_to": "2026-10-01"}):
        assert (await async_client.get("/v1/memory/ledger", params={**q, **bad}, headers=H("legacy"))).status_code == 422


@pytest.mark.asyncio
async def test_each_product_reads_only_its_own_ledger_with_the_same_ids(async_client):
    o = f"u-{uuid.uuid4().hex[:6]}"
    await _seed("wsL", o, [("s1", "SOPHIE meeting", "2026-10-20", "15:00", "happens", "open", "")])
    await _seed("bloom::wsL", o, [("b1", "BLOOM experiment", "2026-10-20", "18:00", "deadline", "open", "")])
    q = {"workspace_id": "wsL", "owner": o, "now": "2026-10-20T10:00:00+01:00", "time_zone": "Europe/London"}
    s = (await async_client.get("/v1/memory/ledger", params=q, headers=H("ts"))).json()
    b = (await async_client.get("/v1/memory/ledger", params=q, headers=H("tb"))).json()
    assert "SOPHIE" in s["text"] and "BLOOM" not in s["text"] and s["product"] == "sophie"
    assert "BLOOM" in b["text"] and "SOPHIE" not in b["text"] and b["product"] == "bloom"
    rng = (await async_client.get("/v1/memory/ledger", params={**q, "view": "range", "period": "today"}, headers=H("tb"))).json()
    assert "BLOOM" in rng["text"] and "SOPHIE" not in rng["text"]
    assert (await async_client.get("/v1/memory/ledger", params={**q, "companion_id": "sophie"}, headers=H("tb"))).status_code == 403
    assert (await async_client.get("/v1/memory/ledger", params={**{**q, "workspace_id": "bloom::wsL"}}, headers=H("tb"))).status_code == 422


@pytest.mark.asyncio
async def test_prepared_notes_never_see_dates_or_details_they_could_restate():
    seen = {}

    async def fake(kind, prompt, max_tokens, models):
        seen[kind] = prompt
        return {"text": "notes", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}

    o = f"u-{uuid.uuid4().hex[:6]}"
    await _seed("wsP2", o, [("call", "Call with Vinesh", "2026-10-20", "15:00", "happens", "open", "what room?")])
    mp.set_model_fn(fake)
    try:
        async with async_session_maker() as db:
            await mp.prepare(db, workspace_id="wsP2", owner=o, now_iso="2026-10-20T09:00:00+01:00", time_zone="Europe/London")
    finally:
        mp.set_model_fn(None)
    p = seen["preparation"]
    assert "Call with Vinesh" in p and "15:00" not in p and "what room?" not in p and "2026-10-20T" not in p.split("--- operational ledger")[1].split("--- needs attention")[0]
