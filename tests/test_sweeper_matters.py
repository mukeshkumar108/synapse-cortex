"""The sweeper reconciles what it finds into Matters through the same write path as everything else."""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.matter import Matter
from tests.cortex_fixtures import NOW, USER, WS, naive


@pytest.mark.asyncio
async def test_sweeper_run_reconciles_into_matters_through_the_same_write_path(monkeypatch):
    from src.services.sweeper_service import SweeperService
    svc = SweeperService()

    async def fake_gather(ws, peer):
        return [{"stub": True}]

    monkeypatch.setattr(svc, "gather", fake_gather)
    monkeypatch.setattr(svc, "synthesize", lambda packets: [{
        "valid": True, "kind": "open_loop", "title": "Carlos invoice outstanding", "summary": "",
        "confidence": 0.9, "evidence_text": "Carlos still owes me", "evidence_id": "e1",
        "evidence_session_id": "lane-1", "validation_notes": []}])
    async with async_session_maker() as db:
        out = await svc.run(db, workspace_id=WS, peer_id=USER, session_id="lane-1", now=naive(NOW))
        ms_ = (await db.execute(select(Matter))).scalars().all()
    assert out["matters"]["created"] == 1 and [m.title for m in ms_] == ["Carlos invoice outstanding"]
