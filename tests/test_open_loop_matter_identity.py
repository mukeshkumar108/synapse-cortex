"""Regression coverage for OpenLoop matter-identity / cross-message reuse.

Blinded Scenario 1 showed one real-world matter (Carlos's outstanding
payment) producing multiple OpenLoop rows, one per mention, because
`create_open_loop_if_needed` only deduped an exact same-message replay — it
had no query for an already-OPEN loop about the same matter from an earlier
message. This is NOT title dedupe: title overlap alone is explicitly not
trusted (see `_find_reusable_open_loop`'s docstring). Reuse requires BOTH a
confidently-resolved shared subject entity (via the existing entity_service/
EntityLink infrastructure, extended to the open_loop lane for parity with
commitments/facts/expectations, which already have it) AND sufficient
content overlap (the same `_significant_tokens` primitive already used by
`close_answered_loops`/`reconcile_new_expectation`).
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate

UTC = timezone.utc


def _loop_candidate(*, key: str, hint: str, title: str, refs: list) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key,
        observation=hint,
        canonical_title=title,
        operational_kind="open_loop",
        open_loop_hint=hint,
        subject_refs=refs,
        confidence=0.9,
        formation="explicit",
        extractor_version="matter-identity-regression",
    )


async def _send_turn(async_client, monkeypatch, *, workspace_id: str, sender: str,
                     message_id: str, candidate: ExtractionCandidate, text: str):
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": workspace_id,
            "session_id": "session-1",
            "honcho_message_id": message_id,
            "peer_id": sender,
            "text": text,
            "now": "2026-09-27T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text


async def _open_loops(workspace_id: str):
    async with async_session_maker() as db:
        return (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
        ).order_by(OpenLoop.created_at))).scalars().all()


# ── Case A: same matter across messages -> one live loop ───────────────────

@pytest.mark.asyncio
async def test_case_a_same_matter_across_messages_reuses_one_loop(async_client, monkeypatch):
    ws = "ws-matter-carlos-same"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos still owes the rest of the payment",
            title="Carlos still owes the rest of the payment", refs=["Carlos"]),
        text="Carlos still owes the rest of the payment.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m2",
        candidate=_loop_candidate(
            key="c2", hint="Carlos says the bank delayed it",
            title="Carlos says the bank delayed the payment", refs=["Carlos"]),
        text="Carlos says the bank delayed it.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m3",
        candidate=_loop_candidate(
            key="c3", hint="Any news on Carlos's payment",
            title="Any news on Carlos's payment", refs=["Carlos"]),
        text="Any news on Carlos's payment?",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 1, [l.title for l in loops]
    assert loops[0].status == OpenLoopStatus.OPEN
    assert loops[0].honcho_message_id == "m1"  # original row, updated not replaced


# ── Case B: same actor, genuinely different matters -> stay distinct ───────

@pytest.mark.asyncio
async def test_case_b_same_actor_different_matters_stay_distinct(async_client, monkeypatch):
    ws = "ws-matter-carlos-distinct"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos owes the rest of the payment",
            title="Carlos owes the rest of the payment", refs=["Carlos"]),
        text="Carlos owes the rest of the payment.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m2",
        candidate=_loop_candidate(
            key="c2", hint="Carlos needs to send the venue details",
            title="Carlos needs to send the venue details", refs=["Carlos"]),
        text="Carlos needs to send the venue details.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 2, [l.title for l in loops]
    assert {l.status for l in loops} == {OpenLoopStatus.OPEN}


# ── Case C: different actors, similar wording -> never merge ───────────────

@pytest.mark.asyncio
async def test_case_c_different_actors_similar_wording_never_merge(async_client, monkeypatch):
    ws = "ws-matter-cross-actor"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos owes the outstanding payment",
            title="Carlos owes the outstanding payment", refs=["Carlos"]),
        text="Carlos owes the outstanding payment.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m2",
        candidate=_loop_candidate(
            key="c2", hint="Studio Sam owes the outstanding payment",
            title="Studio Sam owes the outstanding payment", refs=["Sam"]),
        text="Studio Sam owes the outstanding payment.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 2, [l.title for l in loops]


# ── Case D: resolved matter + retrospective question ────────────────────────

@pytest.mark.asyncio
async def test_case_d_resolved_matter_not_silently_reopened(async_client, monkeypatch):
    """A RESOLVED loop must never be mutated/reopened by the reuse path — it
    is excluded from the reuse lookup by construction (status == OPEN only).
    This test pins that guarantee; whether the extractor would even emit a
    fresh open_loop_hint for a retrospective question is outside this
    module's control (documented as a remaining gap, not asserted here)."""
    ws = "ws-matter-resolved"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos owes the outstanding payment",
            title="Carlos owes the outstanding payment", refs=["Carlos"]),
        text="Carlos owes the outstanding payment.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 1
    async with async_session_maker() as db:
        loop = await db.get(OpenLoop, loops[0].id)
        loop.status = OpenLoopStatus.RESOLVED
        loop.resolution_evidence = "test-fixture:carlos-paid"
        db.add(loop)
        await db.commit()

    # A later message about the same actor/content must not touch the
    # resolved row: the reuse lookup only considers status == OPEN.
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m2",
        candidate=_loop_candidate(
            key="c2", hint="Did Carlos ever send that payment",
            title="Did Carlos ever send that payment", refs=["Carlos"]),
        text="Did Carlos ever send that payment?",
    )
    async with async_session_maker() as db:
        original = await db.get(OpenLoop, loops[0].id)
        assert original.status == OpenLoopStatus.RESOLVED
        assert original.resolution_evidence == "test-fixture:carlos-paid"


# ── Case E: unresolved control — matter remains open ────────────────────────

@pytest.mark.asyncio
async def test_case_e_unresolved_matter_remains_open(async_client, monkeypatch):
    ws = "ws-matter-unresolved"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos owes the outstanding payment",
            title="Carlos owes the outstanding payment", refs=["Carlos"]),
        text="Carlos owes the outstanding payment.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 1
    assert loops[0].status == OpenLoopStatus.OPEN


# ── Direct reproduction of the blinded Scenario 1 evidence ──────────────────

@pytest.mark.asyncio
async def test_blinded_scenario_1_carlos_sequence_collapses_to_one_loop(async_client, monkeypatch):
    """Reproduces the exact loop-sprawl evidence from
    evals/sophie_longitudinal/raw_outputs/model/scenario_1_raw_checkpoints.md:
    4 separate OPEN rows (`6d75bd6e`, `49ff0ebd`, `3b941ffa`, `189bd9e5`) were
    minted for msg-s1_e07/e09/e11/e14, one per mention of the identical
    Carlos-debt matter, using the model's own historical title wording
    (including its inconsistent "Carlos'"/"Carlos's"/"Carlos" spellings —
    this must not depend on exact apostrophe matching)."""
    ws = "ws-matter-s1-reproduction"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="s1_e07",
        candidate=_loop_candidate(
            key="e07", hint="Carlos' debt payment", title="Carlos' debt payment",
            refs=["Carlos"]),
        text="Still waiting on Carlos to pay me back.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="s1_e09",
        candidate=_loop_candidate(
            key="e09", hint="Follow up on the remaining debt from Carlos",
            title="Carlos' debt", refs=["Carlos"]),
        text="Follow up on the remaining 2,100 debt from Carlos.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="s1_e11",
        candidate=_loop_candidate(
            key="e11", hint="Follow up on Carlos's payment",
            title="Follow up on Carlos's payment", refs=["Carlos"]),
        text="Any update from Carlos?",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="s1_e14",
        candidate=_loop_candidate(
            key="e14", hint="Carlos payment", title="Carlos payment",
            refs=["Carlos"]),
        text="Carlos still hasn't paid.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 1, [(l.honcho_message_id, l.title) for l in loops]
    assert loops[0].honcho_message_id == "s1_e07"
    assert loops[0].status == OpenLoopStatus.OPEN


# ── No actor signal: never reuse via content alone ──────────────────────────

@pytest.mark.asyncio
async def test_no_subject_refs_never_reuses_via_title_alone(async_client, monkeypatch):
    """Title overlap alone is explicitly not semantic authority: a candidate
    with no resolvable subject_refs must fall back to safe existing
    behavior (create its own row) rather than guess a match."""
    ws = "ws-matter-no-actor"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m1",
        candidate=_loop_candidate(
            key="c1", hint="Carlos owes the outstanding payment",
            title="Carlos owes the outstanding payment", refs=["Carlos"]),
        text="Carlos owes the outstanding payment.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="kai", message_id="m2",
        candidate=_loop_candidate(
            key="c2", hint="Outstanding payment still owed",
            title="Outstanding payment still owed", refs=[]),
        text="Outstanding payment still owed.",
    )
    loops = await _open_loops(ws)
    assert len(loops) == 2, [l.title for l in loops]
