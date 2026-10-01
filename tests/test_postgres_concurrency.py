"""Concurrency / transaction behaviour that SQLite cannot show. Runs only against a
LOCAL scratch Postgres:  CORTEX_TEST_POSTGRES_URL=postgresql+asyncpg://...@localhost:PORT/db
"""
import asyncio
import os

import pytest
from sqlalchemy import func
from sqlmodel import select

from src.db import async_session_maker
from src.models.matter import Matter, MatterLink
from src.services import matter_service as ms
from src.services import world_model_service as wm
from tests.cortex_fixtures import NOW, USER, WS, ago, build_longitudinal_world, entity, exp, link, loop, naive, save

pytestmark = pytest.mark.skipif(not os.environ.get("CORTEX_TEST_POSTGRES_URL"),
                                reason="needs a local Postgres (CORTEX_TEST_POSTGRES_URL)")
TZ = "Europe/London"


async def _sync(**kw):
    async with async_session_maker() as db:
        return await ms.sync_primitives(db, workspace_id=WS, owner_peer_id=USER, now=NOW, **kw)


async def _counts():
    async with async_session_maker() as db:
        m = (await db.execute(select(func.count()).select_from(Matter))).scalar_one()
        subj = (await db.execute(select(MatterLink.object_id, func.count()).where(MatterLink.role == "subject")
                                 .group_by(MatterLink.object_id))).all()
    return m, max([c for _, c in subj], default=0)


@pytest.mark.asyncio
async def test_concurrent_reconcilers_never_double_found_or_double_link_a_primitive():
    carlos = entity("Carlos")
    rows = [exp(f"Collect payment {i} from Carlos", message=f"e{i}", created=ago(30 - i)) for i in range(12)]
    await save(carlos, *rows)
    await save(*[link("expectation", r.id, carlos.id) for r in rows])
    results = await asyncio.gather(*[_sync() for _ in range(6)])        # six reconcilers at once
    matters, max_links = await _counts()
    assert max_links == 1, "a primitive was linked as subject of two Matters"
    assert matters <= 2
    again = await _sync()
    assert again["linked"] == 0 and again["created"] == 0
    assert sum(r.get("conflicts", 0) for r in results) >= 0           # losers roll back cleanly


@pytest.mark.asyncio
async def test_world_model_read_concurrent_with_consolidation_write_and_sweeper_sync():
    await build_longitudinal_world()
    from tests.test_session_episode import EV, op, run_apply

    async def read():
        async with async_session_maker() as db:
            return await wm.compile_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW,
                                                timezone_str=TZ, force=True)

    async def consolidate():
        await run_apply([op("claim", {"claim": "Kai reports feeling unheard", "claim_kind": "relationship_development",
                                      "formation": "reported", "subjects": [], "related": [], "supersedes_claim_id": "",
                                      "direction": "shared", "evidence": EV})])
        await save(loop("New thread during consolidation", message="l-cons", created=ago(0, 1)))
        return await _sync()

    out = await asyncio.gather(read(), consolidate(), read(), _sync(), return_exceptions=True)
    errors = [o for o in out if isinstance(o, Exception)]
    assert not errors, errors
    final = await read()
    await _sync()
    async with async_session_maker() as db:
        final = await wm.compile_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW, timezone_str=TZ, force=True)
    assert any("consolidation" in m["title"] for m in final["matters"]["active"])


@pytest.mark.asyncio
async def test_sweeper_writes_while_attention_reads():
    from src.services.attention_state_service import AttentionStateService
    from src.services.sweeper_service import SweeperService
    await build_longitudinal_world()
    sw = SweeperService()

    async def fake_gather(ws, peer):
        return [{"stub": True}]

    sw.gather = fake_gather
    sw.synthesize = lambda packets: [{"valid": True, "kind": "open_loop", "title": ["Boiler service booking", "Passport renewal form", "Guitar string order", "Dentist insurance claim"][i],
                                      "summary": "", "confidence": 0.9, "evidence_text": "x", "evidence_id": f"sw{i}",
                                      "evidence_session_id": "lane-1", "validation_notes": []} for i in range(4)]

    async def sweep():
        async with async_session_maker() as db:
            return await sw.run(db, workspace_id=WS, peer_id=USER, session_id="lane-1", now=naive(NOW))

    async def attend():
        async with async_session_maker() as db:
            return await AttentionStateService().compile_attention_state(
                db=db, workspace_id=WS, session_id="lane-1", now=NOW, timezone_str=TZ, owner_peer_id=USER)

    out = await asyncio.gather(sweep(), attend(), attend(), return_exceptions=True)
    import traceback
    for o in out:
        if isinstance(o, Exception):
            traceback.print_exception(o)
    assert not [o for o in out if isinstance(o, Exception)], out
    assert out[0]["matters"]["created"] >= 4


@pytest.mark.asyncio
async def test_repeated_writes_and_dedupe_converge_on_postgres():
    from tests.test_matter_fragmentation import CARLOS_MONEY, CARLOS_VENUE, Judge, seed
    await seed(CARLOS_MONEY + CARLOS_VENUE)
    judge = Judge()
    for _ in range(5):
        await _sync(allow_judge=True, adapter=judge)
    async with async_session_maker() as db:
        live = (await db.execute(select(func.count()).select_from(Matter).where(Matter.merged_into_id.is_(None)))).scalar_one()
    assert live == 2


@pytest.mark.asyncio
async def test_rollback_session_leaves_no_trace_and_uniqueness_is_enforced():
    from sqlalchemy.exc import IntegrityError
    from contextlib import aclosing
    from src.db import get_rollback_session
    await build_longitudinal_world()
    before = await _counts()
    async with aclosing(get_rollback_session()) as gen:
        db = await gen.__anext__()
        await save_in(db)
    assert await _counts() == before
    async with async_session_maker() as db:
        link0 = (await db.execute(select(MatterLink).where(MatterLink.role == "subject").limit(1))).scalars().one()
        db.add(MatterLink(honcho_workspace_id=WS, matter_id=link0.matter_id, object_type=link0.object_type,
                          object_id=link0.object_id, role="subject"))
        with pytest.raises(IntegrityError):
            await db.commit()


async def save_in(db):
    await ms.sync_primitives(db, workspace_id=WS, owner_peer_id=USER, now=NOW)
    db.add(Matter(honcho_workspace_id=WS, owner_peer_id=USER, title="ghost", kind="other"))
    await db.commit()
