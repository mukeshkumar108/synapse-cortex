"""Consolidation writes canonical state through the existing primitives; the
SessionEpisode only records and REFERENCES those writes."""
import json

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.consolidation import ConsolidationRun
from src.models.expectation import Expectation, OutcomeState
from src.models.identity import ModelEntry
from src.models.matter import Matter, MatterLink
from src.models.world_model import KnowledgeCoverage, SessionEpisode
from src.services import consolidation_world as cw
from src.services import session_episode_service as ses
from src.services.session_apply import apply_reconstruction
from src.services.session_consolidation import SessionTurn, StartSnapshot, ValidatedOp
from src.services.session_reconstruction import translate_to_ops, validate_reconstruction
from tests.cortex_fixtures import NOW, USER, WS, ago, exp, naive, save, loop

TURNS = [
    SessionTurn("m1", USER, "Ashley keeps saying she did nothing wrong and I just feel unheard"),
    SessionTurn("m2", USER, "Please check back on me after the interview on Thursday"),
    SessionTurn("m3", USER, "I think I will take the Leeds job"),
    SessionTurn("m4", "sophie", "I'll check in Thursday evening"),
]


def raw(**sections):
    return {"session_summary": "A hard talk with Ashley; interview Thursday; leaning towards Leeds.",
            "matters": [], **sections}


def validate(raw_, snapshot=None):
    validated, rejected = validate_reconstruction(
        raw_, snapshot=snapshot or StartSnapshot(), transcript=TURNS, provisional_ids=set(),
        user_peer_ids={USER})
    return validated, rejected


def claim(**kw):
    base = {"claim": "Kai reports feeling unheard when Ashley says she did nothing wrong",
            "claim_kind": "relationship_development", "formation": "reported", "subjects": ["Ashley"],
            "evidence": {"message_ids": ["m1"], "spans": [{"message_id": "m1", "span": "I just feel unheard"}]},
            "confidence": 0.85, "rationale": "stated"}
    base.update(kw)
    return base


# ------------------------------------------------------------------ validation
def test_firm_claims_need_verbatim_spans_and_interpretations_stay_labelled():
    v, rej = validate(raw(claims=[
        claim(),
        claim(claim="Ashley is defensive", formation="explicit", evidence={"message_ids": ["m1"], "spans": []}),
        claim(claim="Kai may be avoiding the real issue", claim_kind="observation", formation="hypothesis",
              evidence={"message_ids": ["m1"], "spans": []}),
        claim(claim="made up", evidence={"message_ids": ["nope"], "spans": []}),
        claim(claim="no provenance", formation="inferred", evidence={"message_ids": [], "spans": []}),
        claim(claim="low", confidence=0.3),
    ]))
    assert [c["claim"] for c in v["claims"]] == [
        "Kai reports feeling unheard when Ashley says she did nothing wrong",
        "Kai may be avoiding the real issue"]
    reasons = {r["reason"] for r in rej}
    assert {"firm_claim_needs_verbatim_spans", "bad_evidence", "claim_needs_provenance",
            "confidence_below_floor"} <= reasons


def test_perspective_is_forced_system_directed_and_never_testimony():
    v, _ = validate(raw(claims=[claim(claim="Sophie wonders whether Kai is overextended", claim_kind="perspective",
                                      formation="explicit")]))
    c = v["claims"][0]
    assert c["formation"] == "inferred" and c["direction"] == "system_to_user"


def test_directed_and_gap_shapes_are_validated():
    v, rej = validate(raw(
        directed=[{"direction": "system_to_user", "title": "Check in after Thursday's interview",
                   "formation": "explicit", "confidence": 0.8, "rationale": "asked",
                   "evidence": {"message_ids": ["m2"], "spans": [{"message_id": "m2", "span": "check back on me"}]}},
                  {"direction": "sideways", "title": "x", "formation": "explicit", "confidence": 0.8,
                   "rationale": "", "evidence": {"message_ids": ["m2"], "spans": []}},
                  {"direction": "user_to_system", "title": "needs spans", "formation": "explicit",
                   "confidence": 0.8, "rationale": "", "evidence": {"message_ids": ["m2"], "spans": []}}],
        gaps=[{"subject_key": "routines/weekday_morning", "why_useful": "to time check-ins"},
              {"subject_key": "Not A Path", "why_useful": "x"}, {"subject_key": "a/b", "why_useful": ""}]))
    assert [d["direction"] for d in v["directed"]] == ["system_to_user"]
    assert [g["subject_key"] for g in v["gaps"]] == ["routines/weekday_morning"]
    assert {r["reason"] for r in rej} >= {"bad_directed_shape", "explicit_needs_verbatim_spans", "bad_gap"}


def test_unknown_supersedes_claim_id_is_rejected_known_one_accepted():
    snap = StartSnapshot(claims=[cw.SnapshotClaim("c-1", "pattern", "observed", "walks most mornings")])
    v, rej = validate(raw(claims=[claim(supersedes_claim_id="c-1"), claim(claim="other", supersedes_claim_id="zzz")]), snap)
    assert len(v["claims"]) == 1 and v["claims"][0]["supersedes_claim_id"] == "c-1"
    assert any(r["reason"] == "unknown_claim_id" for r in rej)
    ops, _ = translate_to_ops(v, start_by_id={}, pid_to_uuid={})
    assert [o.op for o in ops] == ["claim"]


# ----------------------------------------------------------------------- apply
class _Result:
    def __init__(self, accepted):
        self.accepted, self.discards, self.provisional_marks = accepted, [], []


def op(name, data, conf=0.85):
    return ValidatedOp(op=name, data=data, confidence=conf, rationale="fixture")


EV = {"message_ids": ["m1"], "spans": [{"message_id": "m1", "span": "I just feel unheard"}]}


async def run_apply(ops, session="lane-1", temporal="t-1"):
    async with async_session_maker() as db:
        return await apply_reconstruction(db, workspace_id=WS, session_id=session, result=_Result(ops),
                                          user_peer_id=USER, temporal_session_id=temporal, now=NOW)


@pytest.mark.asyncio
async def test_apply_writes_canonical_primitives_with_formation_holder_and_direction():
    report = await run_apply([
        op("claim", {"claim": "Kai reports feeling unheard", "claim_kind": "relationship_development",
                     "formation": "reported", "subjects": ["Ashley"], "related": [], "supersedes_claim_id": "",
                     "direction": "shared", "evidence": EV}),
        op("claim", {"claim": "Sophie wonders whether Kai is overextended", "claim_kind": "perspective",
                     "formation": "hypothesis", "subjects": [], "related": [], "supersedes_claim_id": "",
                     "direction": "system_to_user", "evidence": EV}, 0.7),
        op("claim", {"claim": "Kai decided to take the Leeds job", "claim_kind": "decision", "formation": "explicit",
                     "subjects": [], "related": [], "supersedes_claim_id": "", "direction": None,
                     "evidence": {"message_ids": ["m3"], "spans": [{"message_id": "m3", "span": "I will take the Leeds job"}]}}),
        op("directed_expectation", {"direction": "system_to_user", "title": "Check in after Thursday's interview",
                                    "formation": "explicit", "subjects": [],
                                    "evidence": {"message_ids": ["m2"], "spans": [{"message_id": "m2", "span": "check back"}]}}),
        op("directed_expectation", {"direction": "user_to_system", "title": "Keep me honest about the gym",
                                    "formation": "inferred", "subjects": [], "evidence": {"message_ids": ["m2"], "spans": []}}),
        op("knowledge_gap", {"subject_key": "routines/weekday_morning", "why_useful": "to time check-ins"}, 0.7),
    ])
    assert len(report["applied"]) == 6 and report["deferred"] == []
    async with async_session_maker() as db:
        entries = {e.claim_kind: e for e in (await db.execute(select(ModelEntry))).scalars().all()}
        exps = {e.direction: e for e in (await db.execute(select(Expectation))).scalars().all()}
        gap = (await db.execute(select(KnowledgeCoverage))).scalars().one()
    assert entries["relationship_development"].formation == "reported"
    assert entries["relationship_development"].honcho_message_id == "consolidation:t-1"
    persp = entries["perspective"]
    assert persp.holder_actor == "system" and persp.formation == "hypothesis"   # stays a system-owned hypothesis
    assert entries["decision"].formation == "explicit"
    assert exps["system_to_user"].owner_peer_id == USER and exps["system_to_user"].formation == "explicit"
    assert exps["user_to_system"].formation == "inferred"                      # a prediction is not a statement
    assert gap.status == "unknown" and gap.source == "registered"
    # idempotent: re-applying the same run duplicates nothing
    await run_apply([op("claim", {"claim": "Kai reports feeling unheard", "claim_kind": "relationship_development",
                                  "formation": "reported", "subjects": [], "related": [], "supersedes_claim_id": "",
                                  "direction": "shared", "evidence": EV})])
    async with async_session_maker() as db:
        assert len((await db.execute(select(ModelEntry))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_revise_expectation_violated_maps_to_not_fulfilled_not_an_apply_error():
    e = exp("Gym on Tuesday", message="e-gym")
    await save(e)
    report = await run_apply([op("revise_expectation", {
        "expectation_id": str(e.id), "outcome": "violated", "note": "skipped it",
        "evidence": {"message_ids": ["m1"], "spans": [{"message_id": "m1", "span": "x"}]}})])
    assert [a["op"] for a in report["applied"]] == ["revise_expectation"], report
    async with async_session_maker() as db:
        row = await db.get(Expectation, e.id)
    assert row.outcome_state == OutcomeState.NOT_FULFILLED


# ---------------------------------------------------------------------- episode
async def episode_for(applied, deferred=()):
    async with async_session_maker() as db:
        run = ConsolidationRun(honcho_workspace_id=WS, honcho_session_id="lane-1", temporal_session_id="t-1",
                               mode="apply", model="m", summary="A hard talk; interview Thursday.",
                               owner_peer_id=USER)
        db.add(run)
        await db.commit()
        ep = await ses.record_episode(db, workspace_id=WS, session_id="lane-1", temporal_session_id="t-1",
                                      run=run, aggregate={"applied": applied, "deferred": list(deferred),
                                                          "summaries": ["x"]},
                                      user_peer_id=USER, now=naive(NOW), allow_judge=False)
        again = await ses.record_episode(db, workspace_id=WS, session_id="lane-1", temporal_session_id="t-1",
                                         run=run, aggregate={"applied": applied, "deferred": []},
                                         user_peer_id=USER, now=naive(NOW), allow_judge=False)
        assert again.id == ep.id                                            # idempotent per run
        return ses.episode_view(ep)


@pytest.mark.asyncio
async def test_episode_references_writes_and_does_not_store_truth():
    lp = loop("Ashley conversation about feeling unheard", message="l-ash")
    await save(lp)
    report = await run_apply([
        op("claim", {"claim": "Kai reports feeling unheard", "claim_kind": "relationship_development",
                     "formation": "reported", "subjects": [], "related": [str(lp.id)], "supersedes_claim_id": "",
                     "direction": "shared", "evidence": EV}),
        op("claim", {"claim": "Kai decided to take the Leeds job", "claim_kind": "decision", "formation": "explicit",
                     "subjects": [], "related": [], "supersedes_claim_id": "", "direction": None,
                     "evidence": {"message_ids": ["m3"], "spans": [{"message_id": "m3", "span": "I will take the Leeds job"}]}}),
        op("directed_expectation", {"direction": "system_to_user", "title": "Check in after Thursday's interview",
                                    "formation": "explicit", "subjects": [],
                                    "evidence": {"message_ids": ["m2"], "spans": [{"message_id": "m2", "span": "check back"}]}}),
        op("knowledge_gap", {"subject_key": "routines/weekday_morning", "why_useful": "to time check-ins"}, 0.7),
    ])
    ep = await episode_for(report["applied"], [{"op": "suppress", "reason": "suppression_needs_review"}])
    roles = sorted(w["role"] for w in ep["writes"])
    assert roles == ["decision", "knowledge_gap", "relationship_development", "system_to_user_expectation"]
    assert all(w["object_id"] and w["object_type"] for w in ep["writes"])
    assert ep["detected"][0] == {"op": "suppress", "reason": "suppression_needs_review", "applied": False}
    # the claim landed in the Matter of the loop it was about; entity/matter touch lists come from canonical links
    async with async_session_maker() as db:
        rd = (await db.execute(select(ModelEntry).where(ModelEntry.claim_kind == "relationship_development"))).scalars().one()
        matter = await db.get(Matter, rd.subject_matter_id)
    assert matter.title == "Ashley conversation about feeling unheard"
    assert str(matter.id) in ep["matters_touched"]
    # structural guarantee: the episode table has NO columns for repair/decision/expectation/relationship truth
    cols = {c.name for c in SessionEpisode.__table__.columns}
    assert not {"repair_state", "decisions", "corrections", "system_expectations",
                "relationship_developments", "expectations"} & cols
    # and the canonical rows are the source: delete the episode, nothing is lost
    async with async_session_maker() as db:
        for e in (await db.execute(select(SessionEpisode))).scalars().all():
            await db.delete(e)
        await db.commit()
        assert len((await db.execute(select(ModelEntry))).scalars().all()) == 2
        assert len((await db.execute(select(Expectation))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_consolidation_endpoint_applies_world_sections_and_records_the_episode(async_client, monkeypatch):
    from src.services import semantic_judge

    class Stub:
        async def generate_structured(self, **kw):
            if "json_schema" in kw and "claims" in (kw["json_schema"].get("properties") or {}):
                return raw(
                    matters=[{"pid": "m1", "kind": "watch", "title": "Ashley conversation about feeling unheard",
                              "status": "open", "owner": "user", "basis": "new", "confidence": 0.85,
                              "rationale": "stated", "subjects": ["Ashley"], "evidence": EV}],
                    claims=[claim()],
                    directed=[{"direction": "system_to_user", "title": "Check in after Thursday's interview",
                               "formation": "explicit", "confidence": 0.8, "rationale": "asked",
                               "evidence": {"message_ids": ["m2"], "spans": [{"message_id": "m2", "span": "check back on me"}]}}],
                    gaps=[{"subject_key": "routines/weekday_morning", "why_useful": "to time check-ins"}])
            return {"verdict": "no", "confidence": 0.5, "evidence_span": "", "rationale": ""}

    monkeypatch.setattr(semantic_judge, "_adapter", lambda: Stub())
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    r = await async_client.post("/v1/sessions/consolidate", json={
        "workspace_id": WS, "session_id": "lane-1", "mode": "apply", "user_peer_id": USER,
        "temporal_session_id": "t-9", "transcript": [t.__dict__ for t in TURNS[:3]]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["episode_id"]
    ops = {a["op"] for a in body["applied"]}
    assert {"new_matter", "claim", "directed_expectation", "knowledge_gap"} <= ops, body
    eps = await async_client.post("/v1/cortex/episodes/list", json={"workspace_id": WS, "peer_id": USER})
    ep = eps.json()["episodes"][0]
    assert ep["id"] == body["episode_id"] and ep["temporal_session_id"] == "t-9" and ep["session_id"] == "lane-1"
    assert {"matter_created", "relationship_development", "system_to_user_expectation", "knowledge_gap"} <= {
        w["role"] for w in ep["writes"]}
    assert ep["matters_touched"]                       # new matter resolved + linked by the shared write path
    # the matter is session-independent: it survives a different lane and is owned by the user
    async with async_session_maker() as db:
        ms_ = (await db.execute(select(Matter))).scalars().all()
    assert ms_ and all(m.owner_peer_id == USER for m in ms_)
    # shadow mode records no episode (proposal only)
    monkeypatch.delenv("SESSION_CONSOLIDATION_APPLY")
    r2 = await async_client.post("/v1/sessions/consolidate", json={
        "workspace_id": WS, "session_id": "lane-1", "mode": "apply", "user_peer_id": USER,
        "temporal_session_id": "t-10", "transcript": [t.__dict__ for t in TURNS[:3]]})
    assert r2.json()["status"] == "shadow" and "episode_id" not in r2.json()


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
