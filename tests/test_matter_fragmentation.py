"""One real-world concern must not become 15 Matters; distinct concerns must not merge.

Deterministic identity handles the obvious (links, lineage, relations, keys,
entity+content overlap); the bounded semantic judge resolves what wording alone
cannot ("pay" vs "payment", "balance" vs "invoice") — and a dedupe pass repairs
fragments that already exist. The judge in these tests is a test double that
stands in for model judgement; production code contains no keyword lists.
"""
import re

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.matter import Matter, MatterLink, MatterRelation
from src.services import matter_service as ms
from tests.cortex_fixtures import NOW, USER, WS, ago, entity, exp, link, loop, save

CARLOS_MONEY = [
    ("exp", "Collect £2,100 from Carlos for the event"), ("loop", "Carlos payment for the event still outstanding"),
    ("loop", "Any news on the payment from Carlos"), ("exp", "Chase Carlos about the balance"),
    ("loop", "Carlos says he will pay on Friday"), ("loop", "Carlos did not pay on Friday"),
    ("exp", "Send Carlos a payment reminder"), ("loop", "Carlos paid half of the event money"),
    ("loop", "Remaining payment from Carlos"), ("exp", "Decide whether to involve a solicitor about Carlos"),
    ("loop", "Carlos ghosted my messages about the money"), ("exp", "Call Carlos about the unpaid event fee"),
    ("loop", "Carlos event invoice dispute"), ("loop", "Still waiting for Carlos to settle up"),
    ("exp", "Write off the Carlos balance?"),
]
CARLOS_VENUE = [
    ("loop", "Venue booking details for Saturday"), ("exp", "Confirm the venue capacity with Carlos"),
    ("loop", "Carlos needs the stage plan for the venue"),
]
MONEY = re.compile(r"pay|paid|balance|owe|money|invoice|£|settle|collect|solicitor|fee|unpaid", re.I)


class Judge:
    """Model-judgement test double: 'same matter' iff both texts are about the money and neither about the venue."""

    def __init__(self):
        self.calls = 0

    async def generate_structured(self, **kw):
        self.calls += 1
        prompt = kw["prompt"]
        earlier = prompt.split("EARLIER:\n", 1)[1].split("\n\nLATER:", 1)[0]
        later = prompt.split("LATER:\n", 1)[1].split("\n", 1)[0]
        same = all(MONEY.search(t) and "venue" not in t.lower() for t in (earlier, later))
        return {"verdict": "yes" if same else "no", "confidence": 0.9,
                "evidence_span": later[:25] if same else "", "rationale": "stub"}


async def seed(items, start_day=40):
    carlos = (await _carlos())
    rows = []
    for i, (kind, text) in enumerate(items):
        r = (exp if kind == "exp" else loop)(text, message=f"{kind}{i}-{abs(hash(text)) % 9999}", created=ago(start_day - i * 2))
        rows.append((kind, r))
    await save(*[r for _, r in rows])
    await save(*[link("expectation" if k == "exp" else "open_loop", r.id, carlos.id) for k, r in rows])


async def _carlos():
    async with async_session_maker() as db:
        from src.models.identity import Entity
        found = (await db.execute(select(Entity).where(Entity.display_name == "Carlos"))).scalars().first()
    if found:
        return found
    e = entity("Carlos")
    await save(e)
    return e


async def sync(**kw):
    async with async_session_maker() as db:
        return await ms.sync_primitives(db, workspace_id=WS, owner_peer_id=USER, now=NOW, **kw)


async def matters():
    async with async_session_maker() as db:
        return [m for m in (await db.execute(select(Matter))).scalars().all() if m.merged_into_id is None]


@pytest.mark.asyncio
async def test_deterministic_identity_alone_collapses_fifteen_mentions_to_few_matters():
    await seed(CARLOS_MONEY)
    stats = await sync()
    ms_ = await matters()
    assert stats["scanned"] == 15 and stats["by"]["entity"] >= 10
    assert len(ms_) <= 4, [m.title for m in ms_]           # measured: 4 (was 10 before chronological identity order)
    sizes = [len(await _links(m.id)) for m in ms_]
    assert max(sizes) >= 10                                 # one dominant Matter holds the bulk


async def _links(mid):
    async with async_session_maker() as db:
        return (await db.execute(select(MatterLink).where(MatterLink.matter_id == mid))).scalars().all()


@pytest.mark.asyncio
async def test_judge_assisted_identity_reaches_one_matter_and_keeps_the_venue_concern_separate():
    await seed(CARLOS_MONEY + CARLOS_VENUE)
    judge = Judge()
    await sync(allow_judge=True, adapter=judge)
    ms_ = await matters()
    titles = sorted(m.title for m in ms_)
    assert len(ms_) == 2, titles
    sizes = sorted([len(await _links(m.id)) for m in ms_])
    assert sizes == [3, 15]                                 # 15 money mentions in ONE matter; 3 venue mentions in another
    venue = [m for m in ms_ if len(await _links(m.id)) == 3][0]
    assert "venue" in (await _titles_of(venue.id)).lower() and "pay" not in (await _titles_of(venue.id)).lower()


async def _titles_of(mid):
    ids = [l.object_id for l in await _links(mid)]
    async with async_session_maker() as db:
        from src.models.expectation import Expectation
        from src.models.open_loop import OpenLoop
        out = []
        for model in (Expectation, OpenLoop):
            out += [r.title for r in (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()]
    return " | ".join(out)


@pytest.mark.asyncio
async def test_dedupe_repairs_existing_fragmentation_and_never_rejudges_a_settled_pair():
    await seed(CARLOS_MONEY + CARLOS_VENUE)
    await sync()                                            # deterministic only: leaves fragments
    before = len(await matters())
    assert before >= 4
    judge = Judge()
    s1 = await sync(allow_judge=True, adapter=judge)       # bounded: JUDGE_BUDGET_PER_SYNC verdicts per run
    assert s1["dedupe"]["judged"] <= ms.JUDGE_BUDGET_PER_SYNC and s1["dedupe"]["merged"] >= 1
    assert len(await matters()) < before
    for _ in range(3):                                      # converges across runs; settled pairs are never re-judged
        await sync(allow_judge=True, adapter=judge)
    assert len(await matters()) == 2
    calls = judge.calls
    s2 = await sync(allow_judge=True, adapter=judge)
    assert judge.calls == calls and s2["dedupe"]["judged"] == 0
    async with async_session_maker() as db:
        rels = (await db.execute(select(MatterRelation))).scalars().all()
        archived = [m for m in (await db.execute(select(Matter))).scalars().all() if m.merged_into_id]
    assert any("judged:distinct" in r.evidence_refs_json for r in rels)      # the money/venue verdict is remembered
    assert archived and all(m.status == "archived" for m in archived)         # history kept, never deleted


@pytest.mark.asyncio
async def test_without_an_adapter_the_judge_path_is_fail_closed():
    await seed(CARLOS_MONEY[:6])
    n = len(await matters())
    stats = await sync(allow_judge=True, adapter=None)
    assert "dedupe" not in stats
    assert len(await matters()) >= 1 and n == 0


async def _dump():
    out = []
    for m in await matters():
        out.append((len(await _links(m.id)), m.title, await _titles_of(m.id)))
    return out
