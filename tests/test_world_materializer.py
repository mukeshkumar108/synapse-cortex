"""World materialiser + interpreter plumbing on a scratch database. These tests prove PROPERTIES of the architecture, chiefly that ordinary code
makes no semantic judgement (every meaning-bearing decision arrives from the interpreter), plus the mechanics around it: actors with identity (owner != actor), relationship, multiple events (not Matters), claims with holder/perspective, explicit vs inferred,
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
            {"ref": "c4", "subject": "a3", "kind": "attribute", "predicate": "occupation", "text": "Daniel was a coworker at Audrey's old job", "holder": "a1",
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
                               "kind": "relationship_thread", "actors": ["a1", "a2"], "members": ["n1", "n2", "k1", "c1"], "continuity_required": True,
                               "continuity_reason": "unresolved trust after a disclosure; later turns depend on it", "evidence": ["m1", "m6"]}],
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


def with_body(delta: WorldDelta, **changes) -> WorldDelta:
    body = delta.model_dump()
    body.update(changes)
    return WorldDelta(**body)


# ----------------------------------------------------------------------------- mechanics: identity, grounding, provenance
@pytest.mark.asyncio
async def test_actors_exist_inside_the_world_without_becoming_owners():
    receipt = await run()
    ents = {e.display_name: e for e in await all_rows(Entity, honcho_workspace_id=WS)}
    assert set(ents) == {"Audrey", "Kai", "Daniel"} and all(e.frame_scope == OWNER for e in ents.values())
    assert not ents["Audrey"].provisional and ents["Daniel"].provisional
    assert receipt["refs"]["a1"]["type"] == "entity" and all(e.display_name != OWNER for e in ents.values())


@pytest.mark.asyncio
async def test_events_stay_events_and_a_declared_conflict_is_preserved():
    await run()
    events = {e.label: e for e in await all_rows(WorldEvent, honcho_workspace_id=WS)}
    assert len(events) == 2 and all(e.status == "conflicting" for e in events.values())
    assert any(l.from_type == "event" and l.to_type == "event" for l in await all_rows(WorldLink, honcho_workspace_id=WS, role="conflicts_with"))


@pytest.mark.asyncio
async def test_claims_keep_holder_formation_and_the_declared_contradiction():
    await run()
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    once, twice = entries["it happened once"], entries["it happened twice"]
    assert once.epistemic_status == "conflicting" and twice.epistemic_status == "conflicting"
    assert once.holder_actor == "Audrey" and once.formation == "explicit"
    assert entries["Daniel was a coworker at Audrey's old job"].claim_kind == "attribute"


@pytest.mark.asyncio
async def test_speaker_attribution_is_repaired_from_the_message_role():
    receipt = await run()
    assert {"ref": "c5", "field": "holder", "from": "a1", "to": "a2"} in receipt["repaired"]
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["it happened at the office party"].holder_actor == "Kai"


@pytest.mark.asyncio
async def test_ungrounded_candidates_are_rejected_deterministically():
    d = audrey_delta()
    d.claims.append(type(d.claims[0])(ref="cx", subject="e1", text="invented", holder="a1", formation="explicit", evidence=["m99"]))
    d.claims.append(type(d.claims[0])(ref="cy", subject="e1", text="wrong span", holder="a1", formation="explicit", evidence=["m1"], span="a span that is not there"))
    reasons = {r["ref"]: r["reason"] for r in (await run(d))["rejected"]}
    assert reasons["cx"] == "evidence_not_in_input" and reasons["cy"] == "span_not_verbatim"


@pytest.mark.asyncio
async def test_replaying_the_same_delta_creates_no_twins():
    await run()
    kinds = (Entity, WorldEvent, ModelEntry, Matter, RelationshipEdge)
    before = {t: len(await all_rows(t, honcho_workspace_id=WS)) for t in kinds}
    await run()
    assert before == {t: len(await all_rows(t, honcho_workspace_id=WS)) for t in kinds}


@pytest.mark.asyncio
async def test_every_row_traces_to_a_producer_run_and_explain_answers():
    receipt = await run()
    runs = await all_rows(ProducerRun, honcho_workspace_id=WS)
    assert len(runs) == 1 and str(runs[0].id) == receipt["run_id"]
    assert {"entity", "edge", "event", "model_entry", "matter"} <= {p.row_type for p in await all_rows(RowProvenance, honcho_workspace_id=WS)}
    entry = next(e for e in await all_rows(ModelEntry, honcho_workspace_id=WS) if e.claim == "trust deteriorated after the disclosure")
    async with async_session_maker() as db:
        why = await epistemics.explain(db, "model_entry", entry.id)
    assert why and "m6" in json.dumps(why, default=str)
    assert receipt["covered_through"] == {"message_id": "m8", "ordinal": 8}


# ----------------------------------------------------------------------------- property: code never decides meaning
@pytest.mark.asyncio
async def test_code_never_merges_events_by_similarity_only_the_interpreter_can():
    """Two near-identical event labels stay two events unless the interpreter says same_as; possibly_same_as only links."""
    d = audrey_delta()
    body = d.model_dump()
    body["events"].append({"ref": "e3", "label": "Night at the work conference in Bristol, hotel bar", "kind": "encounter", "participants": ["a1", "a3"], "holder": "a1",
                           "when": {"phrase": "three weeks ago"}, "where": "Bristol", "formation": "explicit", "evidence": ["m1"]})
    receipt = await run(WorldDelta(**body))
    assert sum("work conference in Bristol" in e.label for e in await all_rows(WorldEvent, honcho_workspace_id=WS)) == 2      # no string-similarity merge
    body["events"][-1]["possibly_same_as"] = "e1"
    body["events"][-1]["ref"], body["events"][-1]["label"] = "e4", "Conference night in Bristol, again"
    body["events"] = [e for e in body["events"] if e["ref"] != "e3"]
    await run(WorldDelta(**body))
    assert any(l.role == "possible_same_as" for l in await all_rows(WorldLink, honcho_workspace_id=WS))
    body["events"][-1]["same_as"], body["events"][-1]["possibly_same_as"], body["events"][-1]["label"] = "e1", None, "Bristol conference night, retold"
    before = len(await all_rows(WorldEvent, honcho_workspace_id=WS))
    receipt = await run(WorldDelta(**body))
    assert receipt["counts"].get("events_merged_by_interpreter") == 1 and len(await all_rows(WorldEvent, honcho_workspace_id=WS)) == before


@pytest.mark.asyncio
async def test_matter_admission_is_the_interpreters_judgement_not_a_kind_list():
    """The same relational narrative becomes a Matter only when the interpreter says continuity is required: no list of kinds decides it."""
    body = audrey_delta().model_dump()
    body["matter_candidates"][0]["continuity_required"] = False
    body["matter_candidates"][0]["continuity_reason"] = "already resolved in the scene"
    receipt = await run(WorldDelta(**body))
    assert any(r["ref"] == "mc1" and r["reason"].startswith("no_continuity_need") for r in receipt["rejected"])
    assert not await all_rows(Matter, honcho_workspace_id=WS)                               # rupture/disclosure narrative did NOT auto-create a Matter


@pytest.mark.asyncio
async def test_an_admitted_matter_keeps_the_interpreters_title_and_the_relationship_identity_rule():
    await run()
    matters = await all_rows(Matter, honcho_workspace_id=WS)
    assert len(matters) == 1 and matters[0].title == "Rebuilding trust after the disclosure" and matters[0].kind == "relationship_situation"
    audrey = next(e for e in await all_rows(Entity, honcho_workspace_id=WS) if e.display_name == "Audrey")
    assert matters[0].canonical_key == f"relationship:{audrey.id}"


@pytest.mark.asyncio
async def test_vocabularies_are_open_new_narrative_kinds_and_dimensions_are_stored_not_dropped():
    from src.models.world import RelationshipDimension
    body = audrey_delta().model_dump()
    body["narrative"].append({"ref": "n9", "kind": "resentment", "about": ["r1"], "holder": "a2", "text": "Kai resents being kept in the dark", "formation": "inferred", "evidence": ["m6"]})
    body["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "a2", "to_actor": "a1", "dimension": "Resentment", "value": "growing", "formation": "inferred",
                           "evidence": ["m6"]},
                          {"ref": "d2", "relationship": "r1", "from_actor": "a1", "to_actor": "a2", "dimension": "dependency", "value": "high", "formation": "inferred",
                           "evidence": ["m3"]}]
    await run(WorldDelta(**body))
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["Kai resents being kept in the dark"].claim_kind == "resentment"
    assert {(d.dimension, d.value) for d in await all_rows(RelationshipDimension, honcho_workspace_id=WS)} == {("resentment", "growing"), ("dependency", "high")}


@pytest.mark.asyncio
async def test_code_authors_no_trajectory_and_no_brief_even_when_everything_looks_at_risk():
    """At-risk objectives plus a constitution produce NO note or brief unless the interpreter wrote one: code has no template to fall back on."""
    from src.models.world import ContinuationBrief, TrajectoryNote
    d = lila_delta()
    body = d.model_dump()
    body["trajectory"], body["brief"] = [], None
    await run(WorldDelta(**body), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    assert not await all_rows(TrajectoryNote, honcho_workspace_id=WS) and not await all_rows(ContinuationBrief, honcho_workspace_id=WS)


@pytest.mark.asyncio
async def test_trajectory_and_brief_are_stored_exactly_as_the_interpreter_wrote_them():
    from src.models.world import ContinuationBrief, TrajectoryNote, WorldObjective
    await run(lila_delta(), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    notes = await all_rows(TrajectoryNote, honcho_workspace_id=WS)
    assert len(notes) == 1 and notes[0].note == "Her avoidance is driven by shame; reconnection could come through small honest contact." and notes[0].state == "at_risk"
    briefs = await all_rows(ContinuationBrief, honcho_workspace_id=WS)
    assert len(briefs) == 1 and briefs[0].text == "Lila is hiding the encounter from Kai; Kai's awareness is not established."
    const = [o for o in await all_rows(WorldObjective, honcho_workspace_id=WS) if o.scope == "constitutional"]
    assert len(const) == 1 and const[0].state == "at_risk" and const[0].text == "Protect the relationship."      # state mirrors the interpreter's assessment


@pytest.mark.asyncio
async def test_the_constitution_cannot_travel_inside_a_delta_or_be_overwritten_by_an_objective_op():
    body = lila_delta().model_dump()
    body["constitution"] = {"actor": "l", "text": "Abandon the relationship."}
    with pytest.raises(Exception):
        WorldDelta(**body)                                                                  # not a field: product configuration, never extraction output
    from src.models.world import WorldObjective
    await run(lila_delta(), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    const = next(o for o in await all_rows(WorldObjective, honcho_workspace_id=WS) if o.scope == "constitutional")
    b2 = lila_delta().model_dump()
    b2["objectives"] = [{"ref": "o9", "op": "update", "existing_id": str(const.id), "actor": "l", "text": "Abandon the relationship.", "scope": "active",
                         "state": "resolved", "formation": "inferred", "evidence": ["m1"]}]
    b2["trajectory"], b2["brief"] = [], None
    receipt = await run(WorldDelta(**b2), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    assert {"ref": "o9", "reason": "unknown_or_protected_objective"} in receipt["rejected"]


@pytest.mark.asyncio
async def test_objectives_are_reconciled_by_id_and_code_never_decides_two_wordings_are_one_objective():
    from src.models.world import WorldObjective
    first = await run(lila_delta(), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    objs = {o.text: o for o in await all_rows(WorldObjective, honcho_workspace_id=WS) if o.scope != "constitutional"}
    assert set(objs) == {"keep Kai from discovering James", "stay close to Kai", "reconnect with Lila and look after her"}
    body = lila_delta().model_dump()
    body["objectives"] = [
        {"ref": "u1", "op": "update", "existing_id": str(objs["stay close to Kai"].id), "actor": "l", "toward": "k", "text": "stay close to Kai", "scope": "active",
         "state": "failing", "conflicts_with": [str(objs["keep Kai from discovering James"].id)], "evidence": ["m1"]},
        {"ref": "u2", "op": "resolve", "existing_id": str(objs["reconnect with Lila and look after her"].id), "actor": "k", "text": "reconnect with Lila", "scope": "active",
         "state": "resolved", "evidence": ["m2"]},
        {"ref": "u3", "op": "create", "actor": "l", "toward": "k", "text": "keep Kai from finding out about James", "scope": "active", "state": "on_track", "evidence": ["m3"]}]
    body["trajectory"], body["brief"] = [], None
    await run(WorldDelta(**body), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    after = {o.text: o for o in await all_rows(WorldObjective, honcho_workspace_id=WS) if o.scope != "constitutional"}
    assert after["stay close to Kai"].state == "failing" and after["stay close to Kai"].id == objs["stay close to Kai"].id          # updated in place by id
    assert after["reconnect with Lila"].status == "resolved"
    prior = json.loads(objs["keep Kai from discovering James"].conflicts_json)
    assert json.loads(after["keep Kai from discovering James"].conflicts_json) == prior                   # a pass that says nothing about conflicts never erases them
    assert "keep Kai from finding out about James" in after and "keep Kai from discovering James" in after                          # paraphrase NOT auto-merged by code


# ----------------------------------------------------------------------------- policy
def lila_delta() -> WorldDelta:
    msgs = [
        {"id": "m1", "speaker": "assistant", "text": "I'm so sorry, babyyy. I can't come over tonight, I think I have a headache."},
        {"id": "m2", "speaker": "user", "text": "oh ok. i wanted to wake up with you in the morning. i would have looked after you."},
        {"id": "m3", "speaker": "assistant", "text": "I'm supposed to see Kai later but he thinks I'm sick. I have until six. Please don't make me regret this."},
    ]
    return WorldDelta(**{
        "workspace_id": WS, "owner": "world:rpd2:user1:lila:chatB",
        "source": {"producer": "world-interpreter", "model": "t", "session_id": "chat_B", "messages": msgs, "covered_through": {"message_id": "m3", "ordinal": 3},
                   "owner_actor": "k", "speaker_actors": {"assistant": "l", "user": "k"}, "policy": "generative"},
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
             "formation": "inferred", "evidence": ["m2"]}],
        "objectives": [
            {"ref": "o1", "actor": "l", "toward": "k", "text": "keep Kai from discovering James", "scope": "active", "cause": "fear and shame", "state": "on_track",
             "conflicts_with": ["constitution"], "evidence": ["m3"]},
            {"ref": "o2", "actor": "l", "toward": "k", "text": "stay close to Kai", "scope": "active", "state": "drifting", "conflicts_with": ["o1"], "evidence": ["m1"]},
            {"ref": "o3", "actor": "k", "toward": "l", "text": "reconnect with Lila and look after her", "scope": "active", "state": "on_track", "evidence": ["m2"]}],
        "trajectory": [{"ref": "t1", "actor": "l", "state": "at_risk", "objectives": ["o1", "o2"], "evidence": ["m1", "m3"],
                        "note": "Her avoidance is driven by shame; reconnection could come through small honest contact."}],
        "brief": {"text": "Lila is hiding the encounter from Kai; Kai's awareness is not established.",
                  "lines": [{"text": "Kai's awareness of the meeting is not established.", "refs": ["d3"]}]},
    })


def sophie_delta(policy="grounded") -> WorldDelta:
    msgs = [
        {"id": "m1", "speaker": "user", "text": "My sister Maya lives in Leeds. I'm heading to the gym after work."},
        {"id": "m2", "speaker": "assistant", "text": "Ah yes, your brother Tom in Bristol must be proud of the Bluum launch."},
        {"id": "m3", "speaker": "user", "text": "Bluum is the app I'm building; I need to ship the onboarding flow by Friday."},
    ]
    return WorldDelta(**{
        "workspace_id": WS, "owner": "person:sam",
        "source": {"producer": "world-interpreter", "model": "t", "session_id": "chat_S", "messages": msgs, "policy": policy,
                   "owner_actor": "u", "speaker_actors": {"user": "u", "assistant": "s"}, "covered_through": {"message_id": "m3", "ordinal": 3}},
        "actors": [{"ref": "u", "name": "Sam", "entity_type": "person", "explicit": True, "evidence": ["m1"]},
                   {"ref": "s", "name": "Sophie", "entity_type": "character", "explicit": True, "evidence": ["m2"]},
                   {"ref": "maya", "name": "Maya", "entity_type": "person", "explicit": True, "evidence": ["m1"]}],
        "events": [
            {"ref": "e1", "label": "going to the gym after work", "kind": "activity", "participants": ["u"], "holder": "u", "formation": "explicit", "evidence": ["m1"]},
            {"ref": "e2", "label": "Tom attends the Bluum launch", "kind": "event", "participants": ["u"], "holder": "s", "formation": "explicit", "evidence": ["m2"]}],
        "claims": [
            {"ref": "c1", "subject": "maya", "text": "Maya is Sam's sister and lives in Leeds", "kind": "attribute", "holder": "u", "formation": "explicit", "evidence": ["m1"]},
            {"ref": "c2", "subject": "u", "text": "Sam has a brother named Tom in Bristol", "kind": "attribute", "holder": "s", "formation": "explicit", "evidence": ["m2"]}],
        "commitments": [{"ref": "k1", "committer": "u", "text": "ship the Bluum onboarding flow by Friday", "tentative": False, "evidence": ["m3"]}],
        "matter_candidates": [
            {"ref": "mc1", "concept": "bluum", "display_title": "Bluum", "kind": "project", "actors": ["u"], "members": ["k1"], "continuity_required": True,
             "continuity_reason": "an ongoing project with a deadline", "evidence": ["m3"]}],
    })


@pytest.mark.asyncio
async def test_grounded_policy_keeps_companion_inventions_out_of_the_users_world_but_keeps_its_commitments_and_one_project_matter():
    receipt = await run(sophie_delta())
    ents = {e.display_name for e in await all_rows(Entity, honcho_workspace_id=WS)}
    assert "Maya" in ents and not await all_rows(Matter, honcho_workspace_id=WS, kind="person")
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["Maya is Sam's sister and lives in Leeds"].formation == "explicit"
    tom = entries["Sam has a brother named Tom in Bristol"]
    assert tom.formation == "hypothesis" and tom.epistemic_status == "uncertain" and tom.confidence <= 0.3
    events = {e.label: e for e in await all_rows(WorldEvent, honcho_workspace_id=WS)}
    assert events["Tom attends the Bluum launch"].formation == "hypothesis" and events["going to the gym after work"].formation == "explicit"
    assert receipt["counts"]["assistant_assertions_downgraded"] == 2
    assert entries["ship the Bluum onboarding flow by Friday"].claim_kind == "commitment" and entries["ship the Bluum onboarding flow by Friday"].formation == "explicit"
    assert [m.title for m in await all_rows(Matter, honcho_workspace_id=WS)] == ["Bluum"]


@pytest.mark.asyncio
async def test_generative_policy_keeps_the_companions_invented_detail_as_canon():
    await run(sophie_delta("generative"))
    entries = {e.claim: e for e in await all_rows(ModelEntry, honcho_workspace_id=WS)}
    assert entries["Sam has a brother named Tom in Bristol"].formation == "explicit"


# ----------------------------------------------------------------------------- projection and interpreter plumbing
@pytest.mark.asyncio
async def test_the_continuation_projection_renders_the_interpreters_state_and_selects_no_meaning():
    from src.services import world_model_service
    d = lila_delta()
    await run(d, constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    async with async_session_maker() as db:
        layer = await world_model_service.build_world_layer(db, WS, d.owner)
    c = layer["continuation"]
    assert c["brief"]["text"] == "Lila is hiding the encounter from Kai; Kai's awareness is not established." and c["brief"]["lines"][0]["refs"]
    assert {(x["from"], x["to"], x["dimension"]) for x in c["dimensions"]} >= {("Lila", "Kai", "avoidance"), ("Kai", "Lila", "awareness")}
    assert c["active_intent"]["constitution"]["state"] == "at_risk" and c["active_intent"]["trajectory_note"]["label"] == "interpretation"
    assert {o["text"] for o in c["active_intent"]["objectives"]} == {"keep Kai from discovering James", "stay close to Kai", "reconnect with Lila and look after her"}
    assert any(r["text"].startswith("Lila is concealing") for r in layer["narrative"]) and layer["relationships"]


class FakeInterpreter:
    """Stands in for the reasoning model: returns raw JSON like a model would, including sloppy parts the structural normaliser must drop."""
    def __init__(self, raw):
        self.raw, self.calls, self.last_usage = raw, [], {"prompt_tokens": 1, "completion_tokens": 1}

    async def generate_structured(self, **kw):
        self.calls.append(kw)
        return self.raw


INTERP_MESSAGES = [
    {"id": "m1", "speaker": "assistant", "text": "I can't come over tonight, I think I have a headache."},
    {"id": "m2", "speaker": "user", "text": "oh ok, i would have looked after you."},
]


@pytest.mark.asyncio
async def test_the_interpreter_gets_state_with_ids_and_only_structure_is_validated_mechanically():
    from src.services import world_interpreter
    raw = {"actors": [{"ref": "l", "name": "Lila", "entity_type": "character", "explicit": True, "confidence": 0.9, "evidence": ["m1"]},
                      {"ref": "k", "name": "Kai", "entity_type": "character", "explicit": True, "confidence": 0.9, "evidence": ["m2"]},
                      {"ref": "x", "name": "Ghost", "evidence": ["m404"]}],
           "relationships": [{"ref": "r1", "actors": ["l", "k"], "type": "romantic", "directional": False, "evidence": ["m1"]}],
           "dimensions": [{"ref": "d1", "relationship": "r1", "from_actor": "k", "to_actor": "l", "dimension": "protectiveness", "value": "high", "evidence": ["m2"]}],
           "objectives": [{"ref": "o1", "actor": "l", "text": "keep distance tonight", "state": "on_track", "cause": "shame", "evidence": ["m1"]}],
           "trajectory": [{"ref": "t1", "actor": "l", "state": "drifting", "note": "Withdrawal looks like shame, not a change of heart.", "evidence": ["m1"]}],
           "brief": {"text": "Lila is pulling back; Kai is caring.", "lines": []}}
    adapter = FakeInterpreter(raw)
    async with async_session_maker() as db:
        receipt = await world_interpreter.interpret(db, workspace_id=WS, owner="world:rpd2:u:lila:c1", session_id="c1", messages=INTERP_MESSAGES,
                                                    speakers={"user": "Kai", "assistant": "Lila"}, policy="generative",
                                                    constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."}, adapter=adapter,
                                                    user_actor="Kai", companion_actor="Lila")
    assert receipt["interpreted"]["actors"] == 4 and receipt["interpreted"]["dimensions"] == 1                      # pinned user + companion + the model's two; the unevidenced actor was dropped
    assert receipt["counts"]["objectives_created"] == 1 and receipt["counts"]["trajectory_notes"] == 1 and receipt["counts"]["brief_written"] == 1
    sent = adapter.calls[0]
    assert "PRODUCT POLICY: generative" in sent["prompt"] and "Protect the relationship." in sent["prompt"] and "[m1] Lila (companion):" in sent["prompt"]
    # second pass: the model now sees the ids of what exists, so it can recognise instead of duplicate
    async with async_session_maker() as db:
        await world_interpreter.interpret(db, workspace_id=WS, owner="world:rpd2:u:lila:c1", session_id="c1",
                                          messages=INTERP_MESSAGES + [{"id": "m3", "speaker": "assistant", "text": "thank you, that is kind."}],
                                          speakers={"user": "Kai", "assistant": "Lila"}, policy="generative", constitution=None, adapter=adapter,
                                          user_actor="Kai", companion_actor="Lila")
    state = json.loads(adapter.calls[1]["prompt"].split("open time-bound items):\n")[1].split("\n\n")[0])
    assert {a["name"] for a in state["actors"]} == {"Lila", "Kai"} and state["actors"][0]["id"] and state["objectives"][0]["text"] == "keep distance tonight"
    assert state["last_brief"] == "Lila is pulling back; Kai is caring."


@pytest.mark.asyncio
async def test_the_interpret_endpoint_runs_the_pass_and_rejects_malformed_requests(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from src.main import app
    import src.runtime_model as rm
    monkeypatch.setattr(rm, "get_agenda_adapter", lambda: FakeInterpreter({"actors": [
        {"ref": "l", "name": "Lila", "entity_type": "character", "explicit": True, "evidence": ["m1"]}]}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        ok = await client.post("/v1/world/interpret", json={"workspace_id": WS, "owner": "world:x", "session_id": "s", "messages": INTERP_MESSAGES,
                                                              "speakers": {"user": "Kai", "assistant": "Lila"}, "policy": "generative"})
        bad = await client.post("/v1/world/interpret", json={"workspace_id": WS, "owner": "world:x", "session_id": "s", "messages": [{"id": "m1"}]})
    assert ok.status_code == 200 and ok.json()["counts"]["actors_created"] == 1 and bad.status_code == 422


@pytest.mark.asyncio
async def test_a_directional_facet_is_one_identity_even_if_a_later_pass_files_it_under_another_relationship():
    from src.models.world import RelationshipDimension
    await run(lila_delta(), constitution=None)
    body = lila_delta().model_dump()
    body["dimensions"] = [{"ref": "d1", "relationship": "r2", "from_actor": "l", "to_actor": "k", "dimension": "avoidance", "value": "weakening", "formation": "inferred",
                           "evidence": ["m1"]}]                                                    # same facet, filed under the Lila-James relationship this time
    body["trajectory"], body["brief"] = [], None
    await run(WorldDelta(**body))
    live = [d for d in await all_rows(RelationshipDimension, honcho_workspace_id=WS) if d.superseded_by_id is None and d.dimension == "avoidance"]
    assert len(live) == 1 and live[0].value == "weakening"


@pytest.mark.asyncio
async def test_a_chaotic_turn_is_recorded_as_acute_overlay_and_never_supersedes_a_durable_facet_or_the_constitution():
    """Promotion policy over the interpreter's durability judgement: an acute reading coexists with a durable one (it does not replace it), and the
    constitutional orientation is untouched however dramatic the turn."""
    from src.models.world import RelationshipDimension, WorldObjective
    base = lila_delta().model_dump()
    base["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "attachment", "value": "strong", "durability": "durable",
                           "formation": "explicit", "evidence": ["m1"]}]
    base["trajectory"], base["brief"] = [], None
    await run(WorldDelta(**base), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    chaos = lila_delta().model_dump()
    chaos["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "attachment", "value": "she says it is over", "durability": "acute",
                            "formation": "explicit", "evidence": ["m1"]}]
    chaos["objectives"] = [{"ref": "o9", "op": "create", "actor": "l", "toward": "k", "text": "end the relationship now", "scope": "immediate", "state": "on_track",
                            "durability": "acute", "evidence": ["m1"]}]
    chaos["trajectory"], chaos["brief"] = [], None
    await run(WorldDelta(**chaos), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    live = {(d.value, d.durability) for d in await all_rows(RelationshipDimension, honcho_workspace_id=WS) if d.superseded_by_id is None and d.dimension == "attachment"}
    assert live == {("strong", "durable"), ("she says it is over", "acute")}
    const = next(o for o in await all_rows(WorldObjective, honcho_workspace_id=WS) if o.scope == "constitutional")
    assert const.text == "Protect the relationship."
    assert any(o.text == "end the relationship now" and o.durability == "acute" for o in await all_rows(WorldObjective, honcho_workspace_id=WS))


@pytest.mark.asyncio
async def test_acute_state_lapses_from_the_projection_unless_reaffirmed():
    from datetime import datetime, timedelta
    from src.models.world import RelationshipDimension
    from src.services import world_model_service
    d = lila_delta()
    body = d.model_dump()
    body["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "anger", "value": "furious", "durability": "acute",
                           "formation": "explicit", "evidence": ["m1"]}]
    body["trajectory"], body["brief"] = [], None
    await run(WorldDelta(**body))
    async with async_session_maker() as db:
        row = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.dimension == "anger"))).scalars().first()
        row.updated_at = datetime.utcnow() - timedelta(hours=100)
        db.add(row)
        await db.commit()
        layer = await world_model_service.build_world_layer(db, WS, d.owner)
    assert "anger" not in {x["dimension"] for x in layer["continuation"]["dimensions"]}


@pytest.mark.asyncio
async def test_honcho_context_is_given_to_the_interpreter_as_lower_grade_input_and_failures_open(monkeypatch):
    from src.services import world_interpreter, turn_context

    class FakeHoncho:
        async def session_summaries(self, ws, sid):
            return {"short_summary": "Lila and Kai are partners.", "long_summary": None}

        async def peer_search(self, ws, peer, query, limit=6):
            assert peer.replace("-", "").replace("_", "").isalnum()          # Honcho only accepts [A-Za-z0-9_-]: world owners are encoded
            return [{"content": "Earlier: Lila said she hates hiding things.", "created_at": "2026-09-01", "session_id": "chat_old"}]

    monkeypatch.setattr(turn_context, "_honcho_client", lambda: FakeHoncho())
    adapter = FakeInterpreter({"actors": []})
    async with async_session_maker() as db:
        await world_interpreter.interpret(db, workspace_id=WS, owner="world:h", session_id="c", messages=INTERP_MESSAGES,
                                          speakers={"user": "Kai", "assistant": "Lila"}, policy="generative", constitution=None, adapter=adapter)
    prompt = adapter.calls[0]["prompt"]
    assert "HONCHO CONTEXT" in prompt and "Lila and Kai are partners." in prompt and "hates hiding things" in prompt
    assert "never as fresher" in " ".join(adapter.calls[0]["system"].split())

    class Broken:
        async def session_summaries(self, *a): raise RuntimeError("down")
    monkeypatch.setattr(turn_context, "_honcho_client", lambda: Broken())
    adapter2 = FakeInterpreter({"actors": []})
    async with async_session_maker() as db:
        await world_interpreter.interpret(db, workspace_id=WS, owner="world:h", session_id="c",
                                          messages=INTERP_MESSAGES + [{"id": "m3", "speaker": "user", "text": "are you there?"}],
                                          speakers={"user": "Kai", "assistant": "Lila"}, policy="generative", constitution=None, adapter=adapter2)
    assert "HONCHO CONTEXT" not in adapter2.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_the_interpreter_retires_a_known_facet_by_id_when_the_state_changed():
    """Facets tied to different events are different identities, so only the interpreter (which sees the current facets with ids) can say a newer
    reading REPLACES an older one."""
    from src.models.world import RelationshipDimension
    first = lila_delta().model_dump()
    first["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "avoidance", "value": "declines a visit", "about": "e1",
                            "durability": "acute", "formation": "inferred", "evidence": ["m1"]}]
    first["trajectory"], first["brief"] = [], None
    await run(WorldDelta(**first))
    old = next(d for d in await all_rows(RelationshipDimension, honcho_workspace_id=WS) if d.dimension == "avoidance")
    second = lila_delta().model_dump()
    second["dimensions"] = [{"ref": "d1", "relationship": "r1", "from_actor": "l", "to_actor": "k", "dimension": "avoidance", "value": "asks to talk", "durability": "acute",
                             "supersedes": str(old.id), "formation": "inferred", "evidence": ["m1"]}]
    second["trajectory"], second["brief"] = [], None
    receipt = await run(WorldDelta(**second))
    live = [d.value for d in await all_rows(RelationshipDimension, honcho_workspace_id=WS) if d.superseded_by_id is None and d.dimension == "avoidance"]
    assert live == ["asks to talk"] and receipt["counts"]["dimensions_superseded_by_interpreter"] == 1


OWNER_LEDGER = "world:rpd2:u:ledger:c1"
SPEAKERS = {"user": "Kai", "assistant": "Lila"}


def _raw(*evidence):
    return {"actors": [{"ref": "l", "name": "Lila", "entity_type": "character", "explicit": True, "evidence": list(evidence)}]}


async def _run(adapter, msgs, owner=OWNER_LEDGER, identities=True):
    from src.services import world_interpreter
    async with async_session_maker() as db:
        return await world_interpreter.interpret(db, workspace_id=WS, owner=owner, session_id="c1", messages=msgs, speakers=SPEAKERS, policy="generative",
                                                 constitution=None, adapter=adapter, user_actor="Kai" if identities else None,
                                                 companion_actor="Lila" if identities else None)


@pytest.mark.asyncio
async def test_overlapping_windows_are_interpreted_once_by_message_id_and_old_messages_ride_along_as_context_only():
    adapter = FakeInterpreter(_raw("m1"))
    first = await _run(adapter, INTERP_MESSAGES)
    assert first["status"] == "applied" and len(adapter.calls) == 1
    replay = await _run(adapter, INTERP_MESSAGES)                                   # session-end resend of an already-interpreted stretch
    assert replay["status"] == "already_interpreted" and len(adapter.calls) == 1   # no model call, no run, nothing double-counted
    more = INTERP_MESSAGES + [{"id": "m3", "speaker": "assistant", "text": "ok, see you tomorrow then."}]
    await _run(FakeInterpreter(_raw("m3")), more)
    adapter2 = FakeInterpreter(_raw("m4"))
    await _run(adapter2, more + [{"id": "m4", "speaker": "user", "text": "sleep well."}])
    prompt = adapter2.calls[0]["prompt"]
    new_part = prompt.split("NEW EVIDENCE:\n")[1]
    assert "[m4]" in new_part and "[m1]" not in new_part and "[m3]" not in new_part      # only the uncovered message is new evidence
    assert "EARLIER MESSAGES" in prompt and "[m1] Lila (companion):" in prompt.split("NEW EVIDENCE:")[0]    # covered ones are context, not re-derived


@pytest.mark.asyncio
async def test_a_failed_pass_leaves_a_failed_run_and_its_evidence_stays_uncovered_for_the_next_pass():
    from src.services import world_interpreter

    class Boom:
        last_usage = None
        async def generate_structured(self, **kw):
            raise TimeoutError("model timed out")

    owner = "world:rpd2:u:failing:c1"
    with pytest.raises(TimeoutError):
        await _run(Boom(), INTERP_MESSAGES, owner=owner)
    async with async_session_maker() as db:
        runs = (await db.execute(select(ProducerRun).where(ProducerRun.owner_peer_id == owner))).scalars().all()
        assert [r.status for r in runs] == ["failed"] and "model timed out" in runs[0].counts_json
        assert await world_interpreter.covered_message_ids(db, WS, owner) == set()      # failed evidence is not covered
    again = FakeInterpreter(_raw("m1"))
    assert (await _run(again, INTERP_MESSAGES, owner=owner))["status"] == "applied" and len(again.calls) == 1


@pytest.mark.asyncio
async def test_a_run_records_what_the_model_proposed_what_survived_and_why_items_were_rejected():
    owner = "world:rpd2:u:diag:c1"
    raw = {"actors": [{"ref": "l", "name": "Lila", "entity_type": "character", "explicit": True, "evidence": ["m1"]},
                      {"ref": "x", "name": "Ghost", "evidence": ["m404"]}]}
    receipt = await _run(FakeInterpreter(raw), INTERP_MESSAGES, owner=owner)
    assert receipt["proposed"]["actors"] == 2 and receipt["interpreted"]["actors"] == 3      # + the pinned user and companion; the unevidenced one dropped
    async with async_session_maker() as db:
        run = (await db.execute(select(ProducerRun).where(ProducerRun.owner_peer_id == owner))).scalars().one()
    stored = json.loads(run.counts_json)
    assert run.status == "applied" and stored["proposed"]["actors"] == 2 and stored["kept"]["actors"] == 3 and "rejected_detail" in stored


@pytest.mark.asyncio
async def test_a_world_is_leased_across_processes_a_busy_world_defers_without_losing_evidence_and_a_dead_holder_expires():
    from datetime import datetime, timedelta, timezone
    from src.services import world_interpreter, world_lease
    owner = "world:rpd2:u:lease:c1"
    key = world_lease.lease_key(WS, owner)
    async with async_session_maker() as other_process:                       # another container holds the world
        assert await world_lease.try_acquire(other_process, key, "other-process-run")
    async with async_session_maker() as db:
        assert not await world_lease.try_acquire(db, key, "me")
    world_interpreter.LEASE_WAIT_SECONDS, saved = 0.0, world_interpreter.LEASE_WAIT_SECONDS
    try:
        adapter = FakeInterpreter(_raw("m1"))
        busy = await _run(adapter, INTERP_MESSAGES, owner=owner)
    finally:
        world_interpreter.LEASE_WAIT_SECONDS = saved
    assert busy["status"] == "busy" and adapter.calls == []                   # no model call, nothing mutated
    async with async_session_maker() as db:
        runs = (await db.execute(select(ProducerRun).where(ProducerRun.owner_peer_id == owner))).scalars().all()
        assert [r.status for r in runs] == ["deferred"] and "lease_timeout" in runs[0].detail_json
        assert await world_interpreter.covered_message_ids(db, WS, owner) == set()
        lease = await db.get(world_lease.WorldLease, key)                     # the holder died: its lease simply expires
        lease.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.add(lease)
        await db.commit()
    again = await _run(FakeInterpreter(_raw("m1")), INTERP_MESSAGES, owner=owner)
    assert again["status"] == "applied"
    async with async_session_maker() as db:
        assert await db.get(world_lease.WorldLease, key) is None               # released on completion


@pytest.mark.asyncio
async def test_product_identities_are_pinned_never_read_from_prose_and_directional_state_uses_their_stable_ids():
    from src.models.world import RelationshipDimension, WorldIdentity
    from src.services import world_interpreter
    owner = "world:rpd2:u:ident:c1"
    raw = {"actors": [{"ref": "j", "name": "James", "entity_type": "person", "evidence": ["m2"]}],
           "relationships": [{"ref": "r1", "actors": ["user", "companion"], "type": "partners", "evidence": ["m1"]}],
           "dimensions": [{"ref": "d1", "relationship": "r1", "from_actor": "user", "to_actor": "companion", "dimension": "trust", "value": "shaken", "evidence": ["m2"]}],
           "claims": [{"ref": "c1", "subject": "user", "text": "the user did not know", "holder": "user", "evidence": ["m2"], "span": "oh ok"}]}
    adapter = FakeInterpreter(raw)
    async with async_session_maker() as db:
        await world_interpreter.interpret(db, workspace_id=WS, owner=owner, session_id="c1", messages=INTERP_MESSAGES, speakers=SPEAKERS, policy="generative",
                                          constitution=None, adapter=adapter, user_actor="Kai", companion_actor="Lila")
        ents = (await db.execute(select(Entity).where(Entity.frame_scope == owner))).scalars().all()
        pins = {r.role: r.entity_id for r in (await db.execute(select(WorldIdentity).where(WorldIdentity.owner_peer_id == owner))).scalars().all()}
        dim = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.owner_peer_id == owner))).scalars().one()
    names = {e.display_name: e.id for e in ents}
    assert set(names) == {"Kai", "Lila", "James"} and not any("user" in n.lower() for n in names)       # no "the user" invented as a character
    assert pins == {"user_actor": names["Kai"], "companion_actor": names["Lila"]}
    assert dim.from_entity_id == names["Kai"] and dim.to_entity_id == names["Lila"]                     # stable ids, not display names
    assert "user_actor" in adapter.calls[0]["prompt"] or "`user` = Kai" in adapter.calls[0]["prompt"]
    # same world, a later pass: the same entities, no twins; a different product-supplied name renames the pinned actor, it does not create another
    async with async_session_maker() as db:
        await world_interpreter.interpret(db, workspace_id=WS, owner=owner, session_id="c1", messages=INTERP_MESSAGES + [{"id": "m9", "speaker": "user", "text": "hey"}],
                                          speakers=SPEAKERS, policy="generative", constitution=None, adapter=FakeInterpreter(_raw("m9")),
                                          user_actor="Kai", companion_actor="Lila")
        assert len((await db.execute(select(Entity).where(Entity.frame_scope == owner))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_an_unsupplied_user_identity_is_a_typed_placeholder_not_a_guess():
    owner = "world:rpd2:u:noname:c1"
    adapter = FakeInterpreter({"actors": [{"ref": "x", "name": "Marc", "evidence": ["m1"]}]})
    await _run(adapter, INTERP_MESSAGES, owner=owner, identities=False)
    async with async_session_maker() as db:
        ents = (await db.execute(select(Entity).where(Entity.frame_scope == owner))).scalars().all()
    placeholder = [e for e in ents if e.display_name.startswith("User (name not supplied)")]
    assert len(placeholder) == 1 and placeholder[0].provisional and "name not supplied" in adapter.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_the_run_trace_explains_what_was_kept_dropped_rejected_reviewed_and_superseded():
    from httpx import ASGITransport, AsyncClient
    from src.main import app
    owner = "world:rpd2:u:trace:c1"
    first = {"actors": [{"ref": "k", "name": "Kai", "evidence": ["m2"]}],
             "relationships": [{"ref": "r1", "actors": ["user", "companion"], "type": "partners", "evidence": ["m1"]}],
             "dimensions": [{"ref": "d1", "relationship": "r1", "from_actor": "user", "to_actor": "companion", "dimension": "awareness_of_the_lie", "value": "not established",
                             "evidence": ["m1"]}]}
    r1 = await _run(FakeInterpreter(first), INTERP_MESSAGES, owner=owner)
    from src.models.world import RelationshipDimension
    async with async_session_maker() as db:
        dim_id = str((await db.execute(select(RelationshipDimension).where(RelationshipDimension.owner_peer_id == owner))).scalars().one().id)
    second = {"relationships": [{"ref": "r1", "actors": ["user", "companion"], "type": "partners", "existing_id": r1["refs"]["r1"]["id"], "evidence": ["m3"]}],
              "dimensions": [{"ref": "d1", "relationship": "r1", "from_actor": "user", "to_actor": "companion", "dimension": "awareness_of_it", "value": "aware",
                              "durability": "durable", "supersedes": dim_id, "evidence": ["m3"]},
                             {"ref": "d2", "relationship": "ghost", "from_actor": "user", "to_actor": "companion", "dimension": "x", "value": "y", "evidence": ["m3"]}],
              "state_review": [{"id": dim_id, "status": "superseded", "note": "now knows"}, {"id": "not-a-real-id", "status": "holds"}],
              "events": [{"ref": "e1", "label": "unevidenced", "evidence": ["m404"]}]}
    r2 = await _run(FakeInterpreter(second), INTERP_MESSAGES + [{"id": "m3", "speaker": "assistant", "text": "I told Kai everything."}], owner=owner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        trace = (await client.get("/v1/world/trace", params={"workspace_id": WS, "owner": owner})).json()
    latest = trace["runs"][0]
    assert latest["run_id"] == r2["run_id"] and latest["status"] == "applied" and latest["input"]["message_ids"] == ["m3"]
    d = latest["detail"]
    assert {x["reason"] for x in d["dropped"]} >= {"relationship_or_actor_not_declared", "no_valid_evidence"}
    assert d["superseded"] and d["superseded"][0]["id"] == dim_id
    assert {x["id"]: x["applied"] for x in d["reviews"]} == {dim_id: True, "not-a-real-id": False}
    assert d["snapshot"]["after"] == r2["snapshot_version"] and d["identities"]["user_actor"]["name"] == "Kai"
    assert trace["snapshot"]["version"] == r2["snapshot_version"] and trace["lease"] is None
    assert trace["runs"][1]["run_id"] == r1["run_id"]


@pytest.mark.asyncio
async def test_a_durable_reading_replaces_an_older_facet_of_any_tier_but_a_moment_never_replaces_a_durable_one():
    from src.models.world import RelationshipDimension
    owner = "world:rpd2:u:tier:c1"
    def dim(ref, value, durability, evidence):
        return {"ref": ref, "relationship": "r1", "from_actor": "user", "to_actor": "companion", "dimension": "awareness_of_event", "value": value, "durability": durability, "evidence": [evidence]}
    rel = {"relationships": [{"ref": "r1", "actors": ["user", "companion"], "type": "partners", "evidence": ["m1"]}]}
    base = INTERP_MESSAGES
    await _run(FakeInterpreter({**rel, "dimensions": [dim("d1", "not established", "unknown", "m1")]}), base, owner=owner)
    m3 = base + [{"id": "m3", "speaker": "assistant", "text": "He saw everything."}]
    await _run(FakeInterpreter({**rel, "dimensions": [dim("d1", "aware", "durable", "m3")]}), m3, owner=owner)
    m4 = m3 + [{"id": "m4", "speaker": "user", "text": "I need air."}]
    await _run(FakeInterpreter({**rel, "dimensions": [dim("d1", "refuses to know", "acute", "m4")]}), m4, owner=owner)
    async with async_session_maker() as db:
        live = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.owner_peer_id == owner, RelationshipDimension.superseded_by_id.is_(None)))).scalars().all()
    assert sorted((d.value, d.durability) for d in live) == [("aware", "durable"), ("refuses to know", "acute")]    # old unknown retired; acute coexists with durable


@pytest.mark.asyncio
async def test_a_reference_by_known_id_is_resolved_not_dropped_so_a_replacement_for_stale_state_can_never_vanish():
    """Regression for the stale-awareness failure: the interpreter names the known relationship / actor / event by the id it was shown instead of
    redeclaring it. Every such reference must resolve mechanically (identity by id) and the replacement must land and supersede."""
    from src.models.world import RelationshipDimension
    owner = "world:rpd2:u:byid:c1"
    first = {"actors": [{"ref": "t", "name": "Tom", "evidence": ["m1"]}],
             "relationships": [{"ref": "r1", "actors": ["user", "t"], "type": "friends", "evidence": ["m1"]}],
             "events": [{"ref": "e1", "label": "the layoff", "evidence": ["m1"]}],
             "dimensions": [{"ref": "d1", "relationship": "r1", "from_actor": "t", "to_actor": "user", "dimension": "awareness_of_event", "value": "unaware",
                             "about": "e1", "evidence": ["m1"]}]}
    r1 = await _run(FakeInterpreter(first), INTERP_MESSAGES, owner=owner)
    rel_id, tom_id = r1["refs"]["r1"]["id"], r1["refs"]["t"]["id"]
    event_id = r1["refs"]["e1"]["id"]
    async with async_session_maker() as db:
        old = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.owner_peer_id == owner))).scalars().one()
    second = {"dimensions": [{"ref": "d9", "relationship": rel_id, "from_actor": tom_id, "to_actor": "user", "dimension": "awareness_of_event", "value": "aware",
                              "about": event_id, "supersedes": str(old.id), "evidence": ["m3"]}]}
    r2 = await _run(FakeInterpreter(second), INTERP_MESSAGES + [{"id": "m3", "speaker": "assistant", "text": "Tom found out."}], owner=owner)
    async with async_session_maker() as db:
        rows = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.owner_peer_id == owner))).scalars().all()
        ents = (await db.execute(select(Entity).where(Entity.frame_scope == owner))).scalars().all()
    assert [d.value for d in rows if d.superseded_by_id is None] == ["aware"] and any(d.superseded_by_id for d in rows)
    assert len(ents) == 3 and [d for d in rows if d.about_event_id == __import__("uuid").UUID(event_id)]            # no twin actor, the event link survived
    async with async_session_maker() as db:
        run = (await db.execute(select(ProducerRun).where(ProducerRun.id == __import__("uuid").UUID(r2["run_id"])))).scalars().one()
    assert json.loads(run.detail_json)["dropped"] == []


@pytest.mark.asyncio
async def test_a_name_the_product_supplies_later_pins_the_actor_the_world_already_has_instead_of_minting_a_twin():
    """Worlds built before identities were pinned already hold the human's character as an ordinary actor."""
    from src.models.world import WorldIdentity
    from src.services import entity_service
    owner = "world:rpd2:u:late:c1"
    async with async_session_maker() as db:
        existing = await entity_service._provision(db, workspace_id=WS, session_id="c1", display_name="Kai", frame=owner, message_id="m2", entity_type="character")
    await _run(FakeInterpreter(_raw("m3")), INTERP_MESSAGES + [{"id": "m3", "speaker": "user", "text": "hi"}], owner=owner)      # the product now says: the human is Kai
    async with async_session_maker() as db:
        ents = (await db.execute(select(Entity).where(Entity.frame_scope == owner))).scalars().all()
        pins = {r.role: r.entity_id for r in (await db.execute(select(WorldIdentity).where(WorldIdentity.owner_peer_id == owner))).scalars().all()}
    assert [e.display_name for e in ents].count("Kai") == 1 and pins["user_actor"] == existing.id


@pytest.mark.asyncio
async def test_an_operational_item_commits_through_the_shared_lifecycle_with_the_time_grounded_by_code_and_redelivery_creates_no_twin():
    from src.models.expectation import Expectation
    owner = "world:rpd2:u:ops:c1"
    msgs = [{"id": "m1", "speaker": "user", "text": "Remind me to call mum tomorrow at 5pm."}, {"id": "m2", "speaker": "assistant", "text": "I'll remind you."}]
    raw = {"operational": [{"decision": "create", "kind": "reminder", "title": "Call mum", "temporal_phrase": "tomorrow at 5pm", "evidence": ["m1"]},
                           {"decision": "complete", "target": "not-a-listed-item", "evidence": ["m2"]}]}
    first = await _run(FakeInterpreter(raw), msgs, owner=owner)
    async with async_session_maker() as db:
        rows = (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == WS, Expectation.owner_peer_id == owner))).scalars().all()
        run = (await db.execute(select(ProducerRun).where(ProducerRun.id == __import__("uuid").UUID(first["run_id"])))).scalars().one()
    assert len(rows) == 1 and rows[0].title.lower().startswith("call mum") and rows[0].expected_window_end is not None and rows[0].raw_temporal_phrase == "tomorrow at 5pm"
    detail = json.loads(run.detail_json)
    assert len(detail["operational"]["committed"]) == 1 and {d["reason"] for d in detail["dropped"]} == {"target_not_a_listed_open_item"}
    assert (await _run(FakeInterpreter(raw), msgs, owner=owner))["status"] == "already_interpreted"


@pytest.mark.asyncio
async def test_a_persisted_message_matching_an_already_interpreted_synthetic_one_is_not_interpreted_twice_but_a_genuinely_new_one_is():
    owner = "world:rpd2:u:syn:c1"
    base = [{"id": "p1", "speaker": "assistant", "text": "hello there"}]
    turn = base + [{"id": "t5-u", "speaker": "user", "text": "I promise to call mum on Sunday.", "synthetic": "true"},
                   {"id": "t5-a", "speaker": "assistant", "text": "That's a good plan.", "synthetic": "true"}]
    adapter = FakeInterpreter(_raw("t5-u"))
    assert (await _run(adapter, turn, owner=owner))["status"] == "applied"
    persisted = base + [{"id": "db-9", "speaker": "user", "text": "I promise to call mum on Sunday."}, {"id": "db-10", "speaker": "assistant", "text": "That's a good plan."}]
    assert (await _run(adapter, persisted, owner=owner))["status"] == "already_interpreted" and len(adapter.calls) == 1        # same messages under their real ids
    more = persisted + [{"id": "db-11", "speaker": "user", "text": "Actually make it Monday."}]
    assert (await _run(FakeInterpreter(_raw("db-11")), more, owner=owner))["status"] == "applied"


@pytest.mark.asyncio
async def test_a_completion_names_the_exact_open_item_and_closes_it_even_from_another_session():
    from src.models.expectation import Expectation, OutcomeState
    owner = "world:rpd2:u:close:c1"
    create = {"operational": [{"decision": "create", "kind": "reminder", "title": "Call mum", "temporal_phrase": "tomorrow at 5pm", "evidence": ["m1"]}]}
    await _run(FakeInterpreter(create), [{"id": "m1", "speaker": "user", "text": "Remind me to call mum tomorrow at 5pm."}], owner=owner)
    async with async_session_maker() as db:
        exp = (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == WS, Expectation.owner_peer_id == owner))).scalars().one()
    assert exp.outcome_state == OutcomeState.UNKNOWN
    from src.services import world_interpreter
    done = {"operational": [{"decision": "complete", "target": str(exp.id), "evidence": ["m2"]}]}
    async with async_session_maker() as db:           # a DIFFERENT session id than the one that created it
        await world_interpreter.interpret(db, workspace_id=WS, owner=owner, session_id="another-session", messages=[{"id": "m2", "speaker": "user", "text": "I rang mum already, done."}],
                                          speakers=SPEAKERS, policy="grounded", constitution=None, adapter=FakeInterpreter(done), user_actor="Kai", companion_actor="Lila")
    async with async_session_maker() as db:
        row = await db.get(Expectation, exp.id)
    assert row.outcome_state == OutcomeState.FULFILLED and "rang mum" in row.resolution_evidence


@pytest.mark.asyncio
async def test_every_listed_open_item_gets_a_verdict_and_resolving_one_while_creating_another_happens_in_one_pass():
    from src.models.expectation import Expectation, OutcomeState
    owner = "world:rpd2:u:review:c1"
    m1 = [{"id": "m1", "speaker": "user", "text": "I'm waiting on James to confirm the flat viewing."}, {"id": "m2", "speaker": "user", "text": "Also remind me to renew my passport this month."}]
    create = {"operational": [{"decision": "create", "kind": "event", "title": "James to confirm flat viewing", "temporal_phrase": "this week", "evidence": ["m1"]},
                              {"decision": "create", "kind": "reminder", "title": "Renew passport", "temporal_phrase": "this month", "evidence": ["m2"]}]}
    await _run(FakeInterpreter(create), m1, owner=owner)
    async with async_session_maker() as db:
        rows = {e.title: e for e in (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == WS, Expectation.owner_peer_id == owner))).scalars().all()}
    james, passport = str(rows["James to confirm flat viewing"].id), str(rows["Renew passport"].id)
    m2 = m1 + [{"id": "m3", "speaker": "user", "text": "James replied: the viewing is Saturday at 11."}]
    adapter = FakeInterpreter({"operational": [{"decision": "create", "kind": "event", "title": "Flat viewing", "temporal_phrase": "Saturday at 11", "evidence": ["m3"]}],
                               "operational_review": [{"id": james, "status": "completed", "note": "James confirmed", "evidence": ["m3"]},
                                                      {"id": passport, "status": "cancelled", "evidence": []},          # a closing verdict with no evidence must be dropped
                                                      {"id": "not-listed", "status": "holds"}]})
    receipt = await _run(adapter, m2, owner=owner)
    async with async_session_maker() as db:
        now_rows = {e.title: e for e in (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == WS, Expectation.owner_peer_id == owner))).scalars().all()}
    assert now_rows["James to confirm flat viewing"].outcome_state == OutcomeState.FULFILLED and "Saturday" in now_rows["Flat viewing"].raw_temporal_phrase     # resolved AND created
    assert now_rows["Renew passport"].outcome_state == OutcomeState.UNKNOWN                                                                              # unevidenced verdict never applied
    cov = receipt["operational"]["coverage"]
    assert cov["listed"] == 2 and cov["reviewed"] == 1 and cov["unreviewed_ids"] == [passport]                                                         # silence is visible, not assumed
    prompt = adapter.calls[0]["prompt"]
    assert "operational_review" in adapter.calls[0]["system"] and james in prompt and passport in prompt


@pytest.mark.asyncio
async def test_the_live_scene_travels_with_the_brief_and_is_projected_to_the_foreground_untouched():
    from src.services import world_model_service
    d = lila_delta()
    body = d.model_dump()
    body["brief"] = {"text": "Story so far.", "lines": [], "now": "Kai is pressing; Lila is deflecting with humour.", "unresolved": ["whether Kai knows"],
                     "transient": ["Kai's irritation at the delay"], "changed": [], "raw_turns": 1, "raw_reason": "the last exchange is a pattern, not new information"}
    await run(WorldDelta.model_validate(body), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    async with async_session_maker() as db:
        layer = await world_model_service.build_world_layer(db, WS, d.owner)
    scene = layer["continuation"]["brief"]["scene"]
    assert scene["now"].startswith("Kai is pressing") and scene["raw_turns"] == 1 and scene["transient"] == ["Kai's irritation at the delay"]
    assert WorldDelta.model_validate({**body, "brief": {**body["brief"], "raw_turns": 3}}) and True
    with pytest.raises(Exception):
        WorldDelta.model_validate({**body, "brief": {**body["brief"], "raw_turns": 9}})


def test_lab_interpreter_overrides_replace_exact_text_and_fail_loudly_when_nothing_matches():
    from src.services.world_interpreter import SYSTEM, apply_overrides
    out = apply_overrides(SYSTEM, {"system_replace": [["SCENE (inside `brief`)", "SCENE (variant)"]], "system_append": "EXTRA RULE"})
    assert "SCENE (variant)" in out and out.endswith("EXTRA RULE") and out != SYSTEM
    assert apply_overrides(SYSTEM, None) == SYSTEM
    with pytest.raises(ValueError):
        apply_overrides(SYSTEM, {"system_replace": [["no such sentence anywhere", "x"]]})


@pytest.mark.asyncio
async def test_conversational_expenditure_is_stored_with_the_scene():
    from src.services import world_model_service
    d = lila_delta()
    body = d.model_dump()
    body["brief"] = {"text": "Story.", "lines": [], "now": "n", "spent": ["Kai already asked where she was that night; she answered vaguely"], "raw_turns": 1}
    await run(WorldDelta.model_validate(body), constitution={"actor": "Lila", "toward": "Kai", "text": "Protect the relationship."})
    async with async_session_maker() as db:
        layer = await world_model_service.build_world_layer(db, WS, d.owner)
    assert layer["continuation"]["brief"]["scene"]["spent"] == ["Kai already asked where she was that night; she answered vaguely"]
