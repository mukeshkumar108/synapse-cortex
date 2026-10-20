"""The per-owner consolidation lock on real Postgres: a session advisory lock on a
dedicated connection holds across commits and across processes. Runs only against a
LOCAL scratch Postgres (CORTEX_TEST_POSTGRES_URL); skipped otherwise."""
import os
import uuid

import pytest

from src.services import memory_pipeline as mp

pytestmark = pytest.mark.skipif(not os.environ.get("CORTEX_TEST_POSTGRES_URL"), reason="needs a local scratch Postgres")


@pytest.mark.asyncio
async def test_advisory_lock_blocks_a_second_holder_on_another_connection(monkeypatch):
    ws, owner = "wsLock", f"u-{uuid.uuid4().hex[:6]}"
    async with mp.owner_lock(ws, owner, timeout=5):
        # simulate a second PROCESS: it has its own in-process lock table, so only the DB lock can stop it
        monkeypatch.setattr(mp, "_OWNER_LOCKS", {})
        with pytest.raises(mp.ConsolidationBusy):
            async with mp.owner_lock(ws, owner, timeout=0.5):
                pytest.fail("second holder entered while the first held the advisory lock")
        # a different owner is unaffected
        async with mp.owner_lock(ws, owner + "-other", timeout=2):
            pass
    monkeypatch.setattr(mp, "_OWNER_LOCKS", {})
    async with mp.owner_lock(ws, owner, timeout=5):      # released cleanly: reacquirable
        pass
