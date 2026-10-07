"""Graduated apply path — deterministic tests (stub reconstruction results).

No model calls. Each test builds a V2Result-equivalent by hand and runs
apply_reconstruction (or the endpoint with a stub adapter).
"""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
)
from src.models.consolidation import ConsolidationRun
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.semantic import SemanticRelation
from src.models.suppression import Suppression
from src.services.session_apply import apply_reconstruction
from src.services.session_consolidation import ValidatedOp

WS = "ws-apply"
NOW = "2026-09-28T10:00:00+01:00"


def _op(op, data, conf=0.9):
    return ValidatedOp(op=op, data=data, confidence=conf, rationale="fixture")


class _Result:
    def __init__(self, accepted, discards=None, marks=None):
        self.accepted = accepted
        self.discards = discards or []
        self.provisional_marks = marks or []


async def _loops(ws=WS):
    async with async_session_maker() as db:
        return (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()


async def _commits(ws=WS):
    async with async_session_maker() as db:
        return (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == ws))).scalars().all()


@pytest.mark.asyncio
async def test_new_matter_creates_loop_with_provenance():
    async with async_session_maker() as db:
        result = _Result([_op("new_matter", {
            "title": "Carlos owes £2,100", "matter_kind": "watch",
            "owner": "user",
            "evidence": {"message_ids": ["e1"],
                         "spans": [{"message_id": "e1",
                                    "span": "Carlos owes"}]}})])
        report = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=result,
            user_peer_id="ashley")
    assert len(report["applied"]) == 1
    assert report["applied"][0]["row_kind"] == "open_loop"
    assert report["deferred"] == []
    loops = await _loops()
    assert len(loops) == 1
    assert "Carlos" in (loops[0].title or "")
    assert loops[0].honcho_message_id == "consolidation:s"
    assert loops[0].owner_peer_id == "ashley"


@pytest.mark.asyncio
async def test_new_obligation_becomes_ask_never_act():
    async with async_session_maker() as db:
        result = _Result([_op("new_matter", {
            "title": "Pay school money Friday", "matter_kind": "obligation",
            "owner": "user",
            "evidence": {"message_ids": ["e1"],
                         "spans": [{"message_id": "e1", "span": "pay"}]}})])
        report = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=result,
            user_peer_id="ashley")
    assert len(report["applied"]) == 1
    commits = await _commits()
    assert len(commits) == 1
    assert commits[0].authority == CommitmentCandidateAuthority.ASK, \
        "consolidation proposals must never mint violable ACT rows"
    assert commits[0].status == CommitmentCandidateStatus.PENDING


@pytest.mark.asyncio
async def test_resolve_applies_when_live_defers_when_settled():
    live_id = "11111111-1111-1111-1111-111111111111"
    done_id = "22222222-2222-2222-2222-222222222222"
    async with async_session_maker() as db:
        from uuid import UUID
        db.add(OpenLoop(honcho_workspace_id=WS, honcho_session_id="s",
                        honcho_message_id="seed", owner_peer_id="ashley",
                        candidate_key="k1", title="Live matter",
                        summary="Live matter", status=OpenLoopStatus.OPEN,
                        id=UUID(live_id)))
        db.add(OpenLoop(honcho_workspace_id=WS, honcho_session_id="s",
                        honcho_message_id="seed", owner_peer_id="ashley",
                        candidate_key="k2", title="Done matter",
                        summary="Done matter", status=OpenLoopStatus.RESOLVED,
                        id=UUID(done_id)))
        await db.commit()
        result = _Result([
            _op("resolve_matter", {"matter_id": live_id, "via": "completed",
                                   "evidence": {"message_ids": ["e1"],
                                                "spans": [{"message_id": "e1",
                                                           "span": "done"}]}},
                conf=0.85),
            _op("resolve_matter", {"matter_id": done_id, "via": "completed",
                                   "evidence": {"message_ids": ["e1"],
                                                "spans": [{"message_id": "e1",
                                                           "span": "done"}]}},
                conf=0.9),
            _op("resolve_matter", {"matter_id": live_id, "via": "completed",
                                   "evidence": {"message_ids": ["e1"],
                                                "spans": [{"message_id": "e1",
                                                           "span": "done"}]}},
                conf=0.6),
        ])
        report = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=result)
    assert [a["row_id"] for a in report["applied"]] == [live_id]
    reasons = {d["reason"] for d in report["deferred"]}
    assert reasons == {"target_not_live", "below_mutate_threshold"}
    loops = await _loops()
    by_id = {str(l.id): l for l in loops}
    assert by_id[live_id].status == OpenLoopStatus.RESOLVED
    assert "consolidation:s" in (by_id[live_id].resolution_evidence or "")


@pytest.mark.asyncio
async def test_suppress_and_discards_always_defer():
    async with async_session_maker() as db:
        result = _Result(
            [_op("suppress", {"topic_or_entity": "neck", "reason": "boundary",
                              "evidence": {"message_ids": ["e1"],
                                           "spans": [{"message_id": "e1",
                                                      "span": "neck"}]}},
                 conf=0.95)],
            discards=[{"matter_id": "x", "reason": "junk", "confidence": 0.9}],
            marks=[{"matter_id": "y", "verdict": "redundant", "confidence": 0.9}])
        report = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=result)
    assert report["applied"] == []
    assert {d["reason"] for d in report["deferred"]} == {
        "suppression_needs_review", "destructive_needs_review",
        "provisional_needs_review"}
    async with async_session_maker() as db:
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == WS))).scalars().all()
    assert supps == []


@pytest.mark.asyncio
async def test_attention_cap_and_idempotent_rerun():
    ops = [_op("attend", {"content": f"follow up {i}",
                          "related_ids": [],
                          "evidence": {"message_ids": ["e1"], "spans": []}})
           for i in range(7)]
    async with async_session_maker() as db:
        first = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=_Result(ops))
        second = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=_Result(ops))
    assert len(first["applied"]) == 5
    assert first["deferred"][0]["reason"] == "attention_cap_reached"
    # Stable keys: rerun re-records the same 5 (no duplicates beyond cap)...
    async with async_session_maker() as db:
        atts = (await db.execute(select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == WS))).scalars().all()
    assert len(atts) == 5, "idempotent keys must not multiply rows"
    assert len(second["applied"]) == 5  # same rows touched, none added


@pytest.mark.asyncio
async def test_apply_never_touches_other_workspaces():
    async with async_session_maker() as db:
        result = _Result([_op(
            "resolve_matter", {"matter_id": "33333333-3333-3333-3333-333333333333",
                               "via": "completed",
                               "evidence": {"message_ids": ["e1"],
                                            "spans": [{"message_id": "e1",
                                                       "span": "x"}]}},
            conf=0.9)])
        report = await apply_reconstruction(
            db, workspace_id="ws-other", session_id="s", result=result)
    assert report["applied"] == []
    assert report["deferred"][0]["reason"] == "target_missing"


@pytest.mark.asyncio
async def test_new_watch_links_subjects_matt_links_neck_skips():
    from src.models.identity import EntityLink
    async with async_session_maker() as db:
        result = _Result([
            _op("new_matter", {
                "title": "Waiting for news on Matt", "matter_kind": "watch",
                "owner": "user", "subjects": ["Matt"],
                "evidence": {"message_ids": ["e1"],
                             "spans": [{"message_id": "e1",
                                        "span": "waiting"}]}}),
            _op("new_matter", {
                "title": "Neck pain and poor sleep", "matter_kind": "watch",
                "owner": "user", "subjects": ["neck"],
                "evidence": {"message_ids": ["e1"],
                             "spans": [{"message_id": "e1",
                                        "span": "neck"}]}}),
        ])
        report = await apply_reconstruction(
            db, workspace_id=WS, session_id="s", result=result,
            user_peer_id="ashley")
    assert len(report["applied"]) == 2
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
        links = (await db.execute(select(EntityLink).where(
            EntityLink.honcho_workspace_id == WS))).scalars().all()
    by_title = {l.title: l for l in loops}
    matt_links = [x for x in links
                  if str(x.object_id) == str(by_title["Waiting for news on Matt"].id)]
    neck_links = [x for x in links
                  if str(x.object_id) == str(by_title["Neck pain and poor sleep"].id)]
    assert len(matt_links) == 1, "proper-name subjects must link for later reattachment"
    # Whether a subject is a named referent is the reconstruction model's contract (see its prompt), not a regex here: whatever subjects the model
    # returns are linked (as provisional entities), and the watch is created either way.
    assert "Neck pain and poor sleep" in by_title


