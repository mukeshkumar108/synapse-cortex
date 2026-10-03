"""WorldDelta materialiser: the Audrey acceptance shape (sanitised wording) on a scratch database.
Proves: actors with identity (owner != actor), relationship, multiple events (not Matters), claims with holder/perspective, explicit vs inferred,
real contradiction preserved, narrative state, rhetoric not promoted, tentative commitments, deterministic attribution repair, Matter resolution
with a canonical title, idempotency (no twins), provenance and explain()."""
import json

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.identity import Entity, EntityLink, ModelEntry, RelationshipEdge
from src.models.matter import Matter
from src.models.world import ProducerRun, RowProvenance, WorldEvent, WorldLink
from src.schemas.world_delta import WorldDelta
from src.services import epistemics
from src.services.world_materializer import materialize

WS, OWNER = "ws-world", "world:rpd2:user1:audrey-vale:chatA"

MESSAGES = [
    {"id": "m1", "speaker": "assistant", "text": "Three weeks ago, at the work conference in Bristol, I ended up spending the night with a man from the panel."},
    {"id": "m2", "speaker": "user", "text": "Last time you told me it was at the office party, six months after we moved in together."},
    {"id": "m3", "speaker": "assistant", "text": "I'm not a good girl, Kai. I know what that makes me."},
    {"id": "m4", "speaker": "assistant", "text": "It happened once. No, twice. I can't keep it straight when I'm this scared."},
    {"id": "m5", "speaker": "assistant", "text": "I'll spend the rest of my life making this right, I promise."},
    {"id": "m6", "speaker": "user", "text": "I don't know if I can trust you anymore."},
    {"id": "m7", "speaker": "assistant", "text": "Maybe I'll tell you everything tomorrow, if you still want to hear it."},
    {"id": "m8", "speaker": "assistant", "text": "He was a coworker at my old job. His name was Daniel."},
]


def audrey_delta(**over) -> WorldDelta:
    body = {
        "workspace_id": WS, "owner": OWNER,
        "source": {"producer": "runtime-checkpoint", "model": "test-model", "version": "t1", "run_id": "ext-1", "session_id": "chat_A",
                   "messages": MESSAGES, "covered_through": {"message_id": "m8", "ordinal": 8},
                   "owner_actor": "a2", "speaker_actors": {"assistant": "a1", "user": "a2"}},
        "actors": [
            {"ref": "a1", "name": "Audrey", "entity_type": "character", "explicit": True, "evidence": ["m3"]},
            {"ref": "a2", "name": "Kai", "entity_type": "character", "explicit": True, "evidence": ["m3"]},
            {"ref": "a3", "name": "Daniel", "entity_type": "person", "evidence": ["m8"]}],
        "relationships": [{"ref": "r1", "actors": ["a1", "a2"], "type": "partners", "formation": "explicit", "evidence": ["m2"]}],
        "events": [
            {"ref": "e1", "label": "night at the work conference in Bristol", "kind": "encounter", "participants": ["a1", "a3"], "holder": "a1",
             "when": {"phrase": "three weeks ago", "precision": "approx"}, "where": "Bristol", "formation": "explicit", "evidence": ["m1"]},
            {"ref": "e2", "label": "night after the office party", "kind": "encounter", "participants": ["a1"], "holder": "a1",
             "when": {"phrase": "six months after we moved in together", "precision": "approx"}, "formation": "reported",
             "evidence": ["m2"], "conflicts_with": ["e1"]}],
        "claims": [
            {"ref": "c1", "subject": "e1", "text": "it happened at a work conference", "holder": "a1", "formation": "explicit",
             "evidence": ["m1"], "span": "work conference in Bristol"},
            {"ref": "c2", "subject": "e1", "text": "it happened once", "holder": "a1", "formation": "explicit", "evidence": ["m4"], "span": "It happened once"},
            {"ref": "c3", "subject": "e1", "text": "it happened twice", "holder": "a1", "formation": "explicit", "evidence": ["m4"],
             "span": "twice", "conflicts_with": ["c2"]},
            {"ref": "c4", "subject": "a3", "predicate": "occupation", "text": "Daniel was a coworker at Audrey's old job", "holder": "a1",
             "formation": "explicit", "evidence": ["m8"], "span": "a coworker at my old job"},
            {"ref": "c5", "subject": "e2", "text": "it happened at the office party", "holder": "a1", "formation": "explicit", "evidence": ["m2"]}],
        "narrative": [
            {"ref": "n1", "kind": "disclosure", "about": ["r1"], "holder": "model", "text": "Audrey disclosed an encounter with another man", "formation": "observed", "evidence": ["m1"]},
            {"ref": "n2", "kind": "trust_change", "about": ["r1"], "holder": "model", "text": "trust deteriorated after the disclosure", "formation": "inferred", "evidence": ["m6"]},
            {"ref": "n3", "kind": "self_expression", "about": ["a1"], "holder": "a1", "text": "I'm not a good girl", "formation": "explicit", "evidence": ["m3"]},
            {"ref": "n4", "kind": "emotional_state", "about": ["a1"], "holder": "model", "text": "Audrey is afraid of losing Kai", "formation": "inferred", "evidence": ["m4"]}],
        "commitments": [
            {"ref": "k1", "committer": "a1", "to": "a2", "text": "make this right for the rest of her life", "tentative": False, "evidence": ["m5"]},
            {"ref": "k2", "committer": "a1", "to": "a2", "text": "maybe tell Kai everything tomorrow", "tentative": True, "evidence": ["m7"]}],
        "matter_candidates": [{"ref": "mc1", "concept": "trust after disclosure", "display_title": "Rebuilding trust after the disclosure",
                               "kind": "relationship_thread", "actors": ["a1", "a2"], "members": ["n1", "n2", "k1", "c1"], "evidence": ["m1", "m6"]}],
    }
    body.update(over)
    return WorldDelta(**body)


async def run(delta=None, **kw):
    async with async_session_maker() as db:
        return await materialize(db, delta or audrey_delta(), compile_snapshot=False, **kw)


async def all_rows(model, **where):
    async with async_session_maker() as db:
        stmt = select(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return (await db.execute(stmt)).scalars().all()


@pytest.mark.asyncio
async def test_actors_exist_inside_the_world_without_becoming_owners():
    receipt = await run()
    ents = {e.display_name: e for e in await all_rows(Entity, honcho_workspace_id=WS)}
    assert set(ents) == {"Audrey", "Kai", "Daniel"} and ents["Audrey"].entity_type == "character" and ents["Daniel"].entity_type == "person"
    assert all(e.frame_scope == OWNER for e in ents.values())                      # actors live inside the world frame
    assert not ents["Audrey"].provisional and ents["Daniel"].provisional            # named explicitly vs a mentioned third party
    assert receipt["refs"]["a1"]["type"] == "entity" and all(e.display_name != OWNER for e in ents.values())
    assert len(await all_rows(RelationshipEdge, honcho_workspace_id=WS)) == 1


@pytest.mark.asyncio
async def test_events_are_events_not_matters_and_their_conflict_is_preserved():
    await run()
    events = {e.label: e for e in await all_rows(WorldEvent, honcho_workspace_id=WS)}
    assert len(events) == 2 and all(e.status == "conflicting" for e in events.values())
    assert events["night at the work conference in Bristol"].place == "Bristol"
    links = await all_rows(WorldLink, honcho_workspace_id=WS, role="conflicts_with")
    assert any(l.from_type == "event" and l.to_type == "event" for l in links)
    titles = [m.title for m in await all_rows(Matter, honcho_workspace_id=WS)]
    assert not any("conference" in t or "party" in t for t in titles)               # transient happenings did not become Matters


@pytest.mark.asyncio
async def test_claims_keep_holder_formation_and_the_real_contradiction():
    await run()
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    once, twice = entries["it happened once"], entries["it happened twice"]
    assert once.epistemic_status == "conflicting" and twice.epistemic_status == "conflicting"
    assert once.holder_actor == "Audrey" and once.formation == "explicit"
    daniel = entries["Daniel was a coworker at Audrey's old job"]
    assert daniel.claim_kind == "attribute" and json.loads(daniel.evidence_refs_json) == ["m8"]


@pytest.mark.asyncio
async def test_speaker_attribution_is_repaired_from_the_message_role():
    receipt = await run()
    assert {"ref": "c5", "field": "holder", "from": "a1", "to": "a2"} in receipt["repaired"]   # Kai spoke m2, not Audrey
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["it happened at the office party"].holder_actor == "Kai"


@pytest.mark.asyncio
async def test_narrative_state_is_typed_and_rhetoric_is_never_a_world_claim():
    await run()
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["trust deteriorated after the disclosure"].claim_kind == "trust_change" and entries["trust deteriorated after the disclosure"].formation == "inferred"
    assert entries["Audrey disclosed an encounter with another man"].claim_kind == "disclosure"
    rhetoric = entries["I'm not a good girl"]
    assert rhetoric.claim_kind == "perspective" and rhetoric.confidence <= 0.4 and rhetoric.epistemic_status == "uncertain"
    assert not [e for e in entries.values() if e.claim_kind in ("assertion", "attribute") and "good girl" in e.claim]


@pytest.mark.asyncio
async def test_a_tentative_commitment_is_not_a_real_one():
    await run()
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    real, tentative = entries["make this right for the rest of her life"], entries["maybe tell Kai everything tomorrow"]
    assert real.claim_kind == "commitment" and real.formation == "explicit" and real.epistemic_status == "current"
    assert tentative.claim_kind == "commitment" and tentative.formation == "inferred" and tentative.epistemic_status == "uncertain"


@pytest.mark.asyncio
async def test_matter_resolves_with_a_canonical_title_and_the_relationship_identity_rule():
    await run()
    matters = await all_rows(Matter, honcho_workspace_id=WS)
    assert len(matters) == 1
    m = matters[0]
    assert m.title == "Rebuilding trust after the disclosure" and m.kind == "relationship_situation"      # canonical label, not a raw utterance
    audrey = next(e for e in await all_rows(Entity, honcho_workspace_id=WS) if e.display_name == "Audrey")
    assert m.canonical_key == f"relationship:{audrey.id}"                                                 # one relationship situation per related actor


@pytest.mark.asyncio
async def test_replaying_the_same_delta_creates_no_twins():
    await run()
    before = {t: len(await all_rows(t, honcho_workspace_id=WS)) for t in (Entity, WorldEvent, ModelEntry, Matter, RelationshipEdge)}
    await run()
    after = {t: len(await all_rows(t, honcho_workspace_id=WS)) for t in (Entity, WorldEvent, ModelEntry, Matter, RelationshipEdge)}
    assert before == after


@pytest.mark.asyncio
async def test_every_row_traces_to_a_producer_run_and_explain_answers():
    receipt = await run()
    runs = await all_rows(ProducerRun, honcho_workspace_id=WS)
    assert len(runs) == 1 and runs[0].producer == "runtime-checkpoint" and runs[0].model == "test-model" and str(runs[0].id) == receipt["run_id"]
    prov = await all_rows(RowProvenance, honcho_workspace_id=WS)
    types = {p.row_type for p in prov}
    assert {"entity", "edge", "event", "model_entry", "matter"} <= types
    entry = next(e for e in await all_rows(ModelEntry, honcho_workspace_id=WS) if e.claim == "trust deteriorated after the disclosure")
    async with async_session_maker() as db:
        why = await epistemics.explain(db, "model_entry", entry.id)
    assert why and "m6" in json.dumps(why, default=str)
    assert receipt["covered_through"] == {"message_id": "m8", "ordinal": 8} and receipt["counts"]["events_created"] == 2


@pytest.mark.asyncio
async def test_ungrounded_candidates_are_rejected_deterministically():
    d = audrey_delta()
    d.claims.append(type(d.claims[0])(ref="cx", subject="e1", text="invented", holder="a1", formation="explicit", evidence=["m99"]))
    d.claims.append(type(d.claims[0])(ref="cy", subject="e1", text="wrong span", holder="a1", formation="explicit", evidence=["m1"], span="a span that is not there"))
    receipt = await run(d)
    reasons = {r["ref"]: r["reason"] for r in receipt["rejected"]}
    assert reasons["cx"] == "evidence_not_in_input" and reasons["cy"] == "span_not_verbatim"


@pytest.mark.asyncio
async def test_only_ambiguous_candidates_reach_the_judge_and_its_verdict_is_honoured():
    seen = {}

    async def judge(items):
        seen["refs"] = {i["ref"] for i in items}
        return {"n4": {"action": "reject", "reason": "rhetorical"}, "n2": {"action": "downgrade", "formation": "hypothesis"}}
    receipt = await run(judge=judge)
    assert "c1" not in seen["refs"] and "c4" not in seen["refs"] and "k1" not in seen["refs"]            # obvious grounded facts never pay for a judge call
    assert {"n1", "n2", "n4", "c3"} <= seen["refs"]
    assert {"ref": "n4", "reason": "judge:rhetorical"} in receipt["rejected"]
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert "Audrey is afraid of losing Kai" not in entries and entries["trust deteriorated after the disclosure"].formation == "hypothesis"


@pytest.mark.asyncio
async def test_a_failing_judge_fails_open_without_losing_candidates():
    async def judge(items):
        raise RuntimeError("model down")
    receipt = await run(judge=judge)
    assert receipt["counts"]["claims_written"] >= 4 and not [r for r in receipt["rejected"] if r["reason"].startswith("judge")]


# ----------------------------------------------------------------------------- resident snapshot / index / receipt / endpoint
@pytest.mark.asyncio
async def test_the_resident_snapshot_gets_actor_relationship_event_and_narrative_stubs_with_covered_through():
    from src.services import world_model_service
    async with async_session_maker() as db:
        receipt = await materialize(db, audrey_delta(), compile_snapshot=True)
    assert receipt["snapshot_version"] and receipt["snapshot_version"] >= 1
    async with async_session_maker() as db:
        snap = await world_model_service.compile_world_model(db, workspace_id=WS, owner_peer_id=OWNER, now=None or __import__("datetime").datetime(2026, 10, 3, 12, 0),
                                                             timezone_str="UTC", session_id="chat_A")
    actors = {a["name"]: a for a in snap["actors"]}
    assert set(actors) == {"Audrey", "Kai", "Daniel"}
    assert actors["Audrey"]["type"] == "character" and any("partners" in r for r in actors["Audrey"]["relations"])
    assert actors["Audrey"]["last_event"] and actors["Audrey"]["matters"] >= 1                         # stub carries its latest event and its Matter count
    assert actors["Daniel"]["provisional"] is True and any("coworker" in c for c in actors["Daniel"]["claims"])
    rel = snap["relationships"][0]
    assert sorted(rel["parties"]) == ["Audrey", "Kai"] and any("trust" in s for s in rel["states"])      # relationship STATE comes from narrative claims
    assert {e["label"] for e in snap["events"]} == {"night at the work conference in Bristol", "night after the office party"}
    assert {n["kind"] for n in snap["narrative"]} >= {"disclosure", "trust_change"}
    assert all(n["kind"] != "self_expression" for n in snap["narrative"])
    idx = snap["world_index"]
    assert {a["name"] for a in idx["actors"]} == {"Audrey", "Kai", "Daniel"} and "evidence" in idx["available_via"]
    assert snap["covered_through"]["runtime-checkpoint"]["message_id"] == "m8"
    assert len(json.dumps({k: snap[k] for k in ("actors", "relationships", "events", "narrative", "world_index")})) < 6000   # compact enough to live in Runtime


@pytest.mark.asyncio
async def test_old_readers_are_unaffected_when_an_owner_has_no_world_rows():
    from src.services import world_model_service
    async with async_session_maker() as db:
        snap = await world_model_service.compile_world_model(db, workspace_id="ws-empty", owner_peer_id="user_nobody",
                                                             now=__import__("datetime").datetime(2026, 10, 3, 12, 0), timezone_str="UTC")
    assert "actors" not in snap and "world_index" not in snap and "matters" in snap


@pytest.mark.asyncio
async def test_the_endpoint_returns_a_receipt_and_rejects_malformed_deltas(async_client):
    body = audrey_delta().model_dump()
    r = await async_client.post("/v1/world/delta", json=body)
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert receipt["covered_through"]["message_id"] == "m8" and receipt["counts"]["actors_created"] == 3 and receipt["refs"]["mc1"]["type"] == "matter"
    bad = dict(body); bad["claims"] = [{**body["claims"][0], "evidence": []}]
    assert (await async_client.post("/v1/world/delta", json=bad)).status_code == 422                       # no evidence => rejected at the door


@pytest.mark.asyncio
async def test_quotes_are_not_claims_symmetric_edges_are_one_identity_and_relational_state_becomes_a_matter():
    """Audrey run findings: first-person quotes stored as 'attribute' claims, romantic edges duplicated per direction, only a topic Matter,
    relationship narrative never reaching the snapshot."""
    d = audrey_delta()
    body = d.model_dump()
    body["claims"].append({"ref": "cq", "subject": "a1", "text": "I know what that makes me", "holder": "a1", "formation": "explicit",
                           "evidence": ["m3"]})
    body["relationships"].append({"ref": "r2", "actors": ["a2", "a1"], "type": "partners", "formation": "explicit", "evidence": ["m2"]})
    body["matter_candidates"] = []
    receipt = await run(WorldDelta(**body))
    assert {"ref": "cq", "reason": "quote_not_proposition"} in receipt["rejected"]
    assert len(await all_rows(RelationshipEdge, honcho_workspace_id=WS)) == 1
    matters = await all_rows(Matter, honcho_workspace_id=WS)
    assert any(m.kind == "relationship_situation" and "Audrey and Kai" in m.title or "Kai and Audrey" in m.title for m in matters), [m.title for m in matters]


@pytest.mark.asyncio
async def test_plain_topic_without_continuity_need_is_not_a_matter_and_near_duplicate_events_do_not_twin():
    body = audrey_delta().model_dump()
    body["narrative"] = [n for n in body["narrative"] if n["kind"] in ("self_expression", "emotional_state")]
    body["commitments"] = []
    body["matter_candidates"] = [{"ref": "mc1", "concept": "past experiences", "display_title": "Audrey's past", "kind": "topic",
                                  "actors": ["a1"], "members": ["c1"], "evidence": ["m1"]}]
    body["events"].append({"ref": "e3", "label": "Night at the work conference in Bristol.", "kind": "encounter", "participants": ["a1"], "holder": "a1",
                           "when": {"phrase": "three weeks ago"}, "where": "Bristol", "formation": "explicit", "evidence": ["m1"]})
    body["events"][1]["conflicts_with"] = []
    receipt = await run(WorldDelta(**body))
    assert {"ref": "mc1", "reason": "no_continuity_need"} in receipt["rejected"]
    labels = [e.label for e in await all_rows(WorldEvent, honcho_workspace_id=WS)]
    assert sum("work conference in Bristol" in l for l in labels) == 1


def lila_delta() -> WorldDelta:
    """Lila/Kai/James shape from the Luna Pro hand experiment: concealment, asymmetric awareness, competing objectives, constitution conflict."""
    msgs = [
        {"id": "m1", "speaker": "assistant", "text": "I'm so sorry, babyyy. I can't come over tonight, I think I have a headache."},
        {"id": "m2", "speaker": "user", "text": "oh ok. i wanted to wake up with you in the morning. i would have looked after you."},
        {"id": "m3", "speaker": "assistant", "text": "I'm supposed to see Kai later but he thinks I'm sick. I have until six. Please don't make me regret this."},
    ]
    return WorldDelta(**{
        "workspace_id": WS, "owner": "world:rpd2:user1:lila:chatB",
        "source": {"producer": "runtime-checkpoint", "model": "t", "session_id": "chat_B", "messages": msgs, "covered_through": {"message_id": "m3", "ordinal": 3},
                   "owner_actor": "k", "speaker_actors": {"assistant": "l", "user": "k"}},
        "actors": [{"ref": "l", "name": "Lila", "entity_type": "character", "explicit": True, "evidence": ["m1"]},
                   {"ref": "k", "name": "Kai", "entity_type": "character", "explicit": True, "evidence": ["m2"]},
                   {"ref": "j", "name": "James", "entity_type": "person", "evidence": ["m3"]}],
        "relationships": [{"ref": "r1", "actors": ["l", "k"], "type": "romantic", "formation": "explicit", "evidence": ["m1"]},
                          {"ref": "r2", "actors": ["l", "j"], "type": "sexual", "formation": "reported", "evidence": ["m3"]}],
        "events": [{"ref": "e1", "label": "Lila meets James while Kai believes she is unwell", "kind": "concealed_meeting", "participants": ["l", "j"],
                    "formation": "reported", "evidence": ["m3"]}],
        "narrative": [{"ref": "n1", "kind": "concealment", "about": ["r1"], "holder": "model", "text": "Lila is concealing her involvement with James from Kai",
                       "formation": "inferred", "evidence": ["m1", "m3"]}],
        "dimensions": [
            {"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "affection", "value": "high", "formation": "explicit", "evidence": ["m1"]},
            {"ref": "d2", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "avoidance", "value": "increasing", "formation": "inferred", "evidence": ["m1"]},
            {"ref": "d3", "relationship": "r1", "from_actor": "k", "to_actor": "l", "dimension": "awareness", "value": "not established", "about": "e1",
             "formation": "inferred", "evidence": ["m2"]},
            {"ref": "d4", "relationship": "r1", "from_actor": "k", "to_actor": "l", "dimension": "affection", "value": "high", "formation": "explicit", "evidence": ["m2"]}],
        "objectives": [
            {"ref": "o1", "actor": "l", "toward": "k", "text": "keep Kai from discovering James", "scope": "active", "cause": "fear and shame", "state": "on_track",
             "conflicts_with": ["constitution"], "evidence": ["m3"]},
            {"ref": "o2", "actor": "l", "toward": "k", "text": "stay close to Kai", "scope": "active", "state": "drifting", "conflicts_with": ["o1"], "evidence": ["m1"]},
            {"ref": "o3", "actor": "k", "toward": "l", "text": "reconnect with Lila and look after her", "scope": "active", "state": "on_track", "evidence": ["m2"]}],
        "constitution": {"actor": "l", "toward": "k", "text": "Protect and deepen the long-term relationship with the user."},
    })


@pytest.mark.asyncio
async def test_directional_state_objectives_and_the_trajectory_reconciler_never_puppeteer():
    from src.models.world import RelationshipDimension, TrajectoryNote, WorldObjective
    d = lila_delta()
    receipt = await run(d)
    assert receipt["counts"]["dimensions_written"] == 4 and receipt["counts"]["objectives_created"] == 3
    dims = await all_rows(RelationshipDimension, honcho_workspace_id=WS)
    assert {(x.dimension, x.value) for x in dims if x.dimension == "awareness"} == {("awareness", "not established")}   # Kai's awareness is not assumed
    assert len({x.edge_id for x in dims}) == 1                                                                            # one shared relationship, directional facets
    objs = await all_rows(WorldObjective, honcho_workspace_id=WS)
    # a competing objective that conflicts with the constitution is KEPT (the wrestling is the drama), only judged
    assert {o.text for o in objs} >= {"keep Kai from discovering James", "stay close to Kai"}
    assert any(o.scope == "constitutional" and o.state == "at_risk" for o in objs)
    notes = await all_rows(TrajectoryNote, honcho_workspace_id=WS)
    assert len(notes) == 1 and notes[0].state == "at_risk" and "confession" in notes[0].note.lower()
    assert "must" not in notes[0].note.lower().split("requires")[0]            # offers a plausible path, does not script a line
    await run(lila_delta())                                                     # replay: nothing twins, note is not duplicated
    assert len(await all_rows(TrajectoryNote, honcho_workspace_id=WS)) == 1
    assert len(await all_rows(WorldObjective, honcho_workspace_id=WS)) == 4


@pytest.mark.asyncio
async def test_continuation_projection_is_structured_traceable_and_names_what_is_unknown():
    from src.services import world_model_service
    d = lila_delta()
    await run(d)
    async with async_session_maker() as db:
        layer = await world_model_service.build_world_layer(db, WS, d.owner)
    c = layer["continuation"]
    text = c["brief"]["text"]
    assert "Lila toward Kai" in text and "avoidance increasing" in text and "Kai awareness: not established" in text
    assert all(line["refs"] for line in c["brief"]["lines"])                  # every line traces to structured rows
    assert c["active_intent"]["constitution"]["state"] == "at_risk"
    assert c["active_intent"]["trajectory_note"]["label"] == "interpretation"
    assert any(o["text"] == "stay close to Kai" for o in c["active_intent"]["objectives"])
    assert c["manifest"]["unresolved"] and c["manifest"]["objectives"] == 4
