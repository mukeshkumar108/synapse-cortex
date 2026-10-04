"""World interpreter: THE semantic owner for the world model (docs/SEMANTIC_BOUNDARY_INVENTORY.md).

One reasoning-model call per checkpoint reads the new evidence (verbatim messages) together with the CURRENT world state (with ids) and the
product policy, and returns a typed interpretation: actors (recognising known ones), relationships and their directional dimensions (open
vocabulary), events (including which known event an account is the same as), propositions, narrative state, commitments, objective
reconciliation (create / update / resolve against known objectives), Matter continuity judgements, a trajectory assessment per actor, and a
compact brief. Ordinary code only validates, grounds and stores that result (`world_materializer`); it decides no meaning.

The constitutional orientation and epistemic policy are product configuration supplied by the trusted caller. They are shown to the model as
context and are never extracted from dialogue."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.schemas.world_delta import WorldDelta
from src.services import world_materializer

logger = logging.getLogger(__name__)

INTERPRETER_MODEL = os.getenv("WORLD_INTERPRETER_MODEL", "openai/gpt-5.6-luna-pro")
INTERPRETER_TIMEOUT = float(os.getenv("WORLD_INTERPRETER_TIMEOUT_SECONDS", "150"))
STATE_ITEMS = 30

SYSTEM = """You maintain the WORLD MODEL for a long-running companion product (a grounded real-life companion, or a roleplay/fiction companion).
You are given NEW EVIDENCE (verbatim messages, each with an id), the CURRENT WORLD STATE (with ids), the PRODUCT POLICY and the character's
CONSTITUTIONAL ORIENTATION. Return a typed interpretation of what the new evidence adds or changes. The material may be fiction, explicit or
painful: analyse it neutrally and never produce or continue it; describe explicit content only as far as needed to classify what happened.

PRINCIPLES
- Canonicalise identity, never perspective. One relationship between two people can carry different state in each direction; people can
  disagree about the same event; conflicting accounts coexist until evidence resolves them. Never pick a winner the evidence does not pick.
- Distinguish how things are known: explicit (the speaker states it), reported (relayed), observed, inferred (your interpretation), hypothesis.
  Do not turn inference into fact. Rhetoric, performance and hyperbole are `self_expression`, not claims about the world.
- Recognise known actors, relationships, events and objectives by their ids (existing_id / same_as / op update|resolve) instead of creating
  duplicates; use possibly_same_as when unsure. Two descriptions are the same event only if they are plausibly the same real occurrence.
- Claims are propositions about the world restated neutrally in the third person, not quotes. A quote or outburst is evidence, not a claim,
  unless it establishes lasting relational state (then say that state).
- Dimensions are directional facets of a relationship (from_actor toward to_actor) with an open vocabulary: affection, trust, resentment,
  dependency, avoidance, respect, awareness of a specific event, expectation, intent, and so on. For awareness use: "aware" only when the
  evidence shows they know; "not established" when there is NO evidence either way (the default for anyone absent from a concealed matter); and
  "unaware" ONLY when the evidence positively shows they do not know (they say they had no idea, or are plainly misled in a way they act on).
  Absence of evidence is never evidence of absence: never write "unaware" just because the text does not show them knowing.
- DURABILITY (objectives and dimensions carry `durability`): acute = a reaction in the moment; provisional = supported but not yet confirmed over
  time; durable = sustained across the evidence; unknown. A single dramatic turn (a furious "we're done", an abrupt reversal, a theatrical line
  from the character) HAPPENED and is recorded as an event and as acute state, but it does not by itself become a durable objective or end a
  relationship: say what it most plausibly is (acute rupture, withdrawal, performance) and what would confirm it. If similar behaviour is sustained
  across later evidence, mark it durable then. The foreground is a less constrained model whose turns can be erratic or self-contradictory;
  treat what the character says as evidence of what occurred, never as authority about what is true or what the character durably wants.
- Objectives: each actor can have several, they may compete, and short-term behaviour may conflict with long-term orientation: keep both sides.
  scope = enduring | active | immediate. state = on_track | drifting | at_risk | failing | resolved | unknown, judged against what the actor
  wants. Reconcile against the known objectives: update or resolve them by id when the evidence changes them; create only genuinely new ones.
- A MATTER is a continuity container. Set continuity_required=true only when FUTURE behaviour depends on this unresolved state (and say why in
  continuity_reason). A topic that was merely discussed, or a one-off event, is not a Matter.
- TRAJECTORY: only for the companion character named in the CONSTITUTIONAL ORIENTATION (not for the user's own character or other people), assess how its current behaviour relates to its constitutional orientation (do not copy the
  constitution; judge the situation). If there is tension, explain what is driving the behaviour (hurt, fear, shame...) and describe what
  psychologically plausible movement could restore coherence. This is an interpretation, not an instruction: never script a line, never require
  a confession or reconciliation, never rewrite or soften what happened. If behaviour is coherent, say so with state on_track.
- HONCHO CONTEXT (when present) is earlier evidence and summaries retrieved from the long-term store: use it to recognise continuity, never as
  fresher than the NEW EVIDENCE and never to invent ids.
- BRIEF: 80-150 neutral words, what has happened and where each person stands now, including what is unknown and any contradictions left unresolved. The text is plain prose with NO refs or ids in it; the refs go only in `lines[].refs`.
- Epistemic policy 'grounded' (a real person's life): facts that only the companion asserted about the user's life or other people are
  hypotheses, not facts. Policy 'generative' (collaborative fiction): story events and invented detail are canon, still attributed.
- Use short local refs (a1, r1, e1, c1, n1, k1, o1, d1, mc1, t1). Every item needs evidence: message ids from the NEW EVIDENCE. Omit anything unsure.

OUTPUT: ONE JSON object with these arrays (empty when nothing applies): actors, relationships, events, claims, narrative, commitments,
dimensions, objectives, matter_candidates, trajectory, and an optional brief. Shapes:
actors:[{ref,name,aliases[],entity_type(person|character|organisation|team),explicit(bool),existing_id|null,confidence,evidence[]}]
relationships:[{ref,actors[a,b],type,directional(bool),existing_id|null,formation,confidence,evidence[]}]
events:[{ref,label,kind,when_phrase|null,where|null,participants[],holder|null,formation,confidence,evidence[],conflicts_with[],same_as|null,possibly_same_as|null}]
claims:[{ref,subject(ref of actor/event/relationship),text,kind(assertion|attribute),holder(actor ref|null),formation,confidence,evidence[],span|null(verbatim),conflicts_with[]}]
narrative:[{ref,kind(open: rupture, concealment, resentment, self_expression, ...),about[refs],holder(actor ref|null),text,formation,confidence,evidence[]}]
commitments:[{ref,committer,to|null,text,tentative(bool),confidence,evidence[]}]
dimensions:[{ref,relationship(ref),from_actor,to_actor,dimension,value,about(event ref)|null,durability(acute|provisional|durable|unknown),formation,confidence,evidence[]}]
objectives:[{ref,op(create|update|resolve),existing_id|null,actor,toward|null,text,scope,cause|null,state,durability(acute|provisional|durable|unknown),strength(0-1),conflicts_with[objective refs|known ids|"constitution"; omit the field to leave recorded conflicts unchanged],formation,confidence,evidence[]}]
matter_candidates:[{ref,concept,display_title,kind(project|topic|concern|relationship_situation|goal|life_situation|routine|other),actors[],members[refs],continuity_required(bool),continuity_reason,attach_to_existing_matter_id|null,evidence[]}]
trajectory:[{ref,actor,state(on_track|drifting|at_risk|failing|unknown),note,objectives[],evidence[]}]
brief:{text,lines:[{text,refs[]}]}"""


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text if text and text.lower() != "null" else None


def _num(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _durability(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in ("acute", "provisional", "durable") else "unknown"


def _formation(value: Any, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in ("explicit", "reported", "source_linked", "observed", "inferred", "hypothesis") else default


def normalize(raw: Dict[str, Any], *, messages: List[Dict[str, str]], speakers: Dict[str, str], workspace_id: str, owner: str, session_id: str,
              model: str, run_id: str, policy: str, covered_ordinal: int = 0) -> Dict[str, Any]:
    """Tolerant structural cleanup of the model's JSON into a valid WorldDelta dict (mechanics only): drop items with no usable evidence or
    broken local references, keep refs unique, map speaker names to actor refs. Nothing is invented or reinterpreted here."""
    ids = {m["id"] for m in messages}
    seen: set = set()

    def fresh(ref: Any) -> bool:
        if not isinstance(ref, str) or not ref.strip() or ref in seen:
            return False
        seen.add(ref)
        return True

    def ev(item: Dict[str, Any]) -> List[str]:
        return [e for e in _list(item.get("evidence")) if isinstance(e, str) and e in ids]

    actors = []
    for a in _list(raw.get("actors")):
        if isinstance(a, dict) and _str(a.get("name")) and ev(a) and fresh(a.get("ref")):
            et = str(a.get("entity_type") or "person").lower()
            actors.append({"ref": a["ref"], "name": a["name"].strip(), "aliases": [x for x in _list(a.get("aliases")) if isinstance(x, str) and x.strip()],
                           "entity_type": et if et in ("person", "character", "organisation", "team") else "person", "explicit": bool(a.get("explicit")),
                           "existing_id": _str(a.get("existing_id")), "confidence": _num(a.get("confidence"), 0.7), "evidence": ev(a)})
    actor_refs = {a["ref"] for a in actors}
    norm = lambda t: "".join(ch for ch in str(t).lower() if ch.isalpha())
    by_name = {norm(a["name"]): a["ref"] for a in actors}
    for a in actors:
        for al in a["aliases"]:
            by_name.setdefault(norm(al), a["ref"])
    speaker_actors = {role: by_name[norm(name)] for role, name in speakers.items() if norm(name) in by_name}
    rels = [{"ref": r["ref"], "actors": r["actors"], "type": _str(r.get("type")) or "related", "directional": bool(r.get("directional")),
             "existing_id": _str(r.get("existing_id")), "formation": _formation(r.get("formation"), "inferred"), "confidence": _num(r.get("confidence"), 0.7),
             "evidence": ev(r)}
            for r in _list(raw.get("relationships")) if isinstance(r, dict) and len(_list(r.get("actors"))) == 2 and all(x in actor_refs for x in r["actors"])
            and ev(r) and fresh(r.get("ref"))]
    rel_refs = {r["ref"] for r in rels}
    events = []
    for e in _list(raw.get("events")):
        if isinstance(e, dict) and _str(e.get("label")) and ev(e) and fresh(e.get("ref")):
            events.append({"ref": e["ref"], "label": e["label"].strip(), "kind": _str(e.get("kind")) or "event",
                           "when": {"phrase": _str(e.get("when_phrase")), "precision": "approx" if _str(e.get("when_phrase")) else "unknown"},
                           "where": _str(e.get("where")), "participants": [p for p in _list(e.get("participants")) if p in actor_refs],
                           "holder": e.get("holder") if e.get("holder") in actor_refs else None, "formation": _formation(e.get("formation"), "reported"),
                           "confidence": _num(e.get("confidence"), 0.7), "evidence": ev(e), "conflicts_with": [x for x in _list(e.get("conflicts_with")) if isinstance(x, str)],
                           "same_as": _str(e.get("same_as")), "possibly_same_as": _str(e.get("possibly_same_as"))})
    event_refs = {e["ref"] for e in events}
    for e in events:
        e["conflicts_with"] = [x for x in e["conflicts_with"] if x in event_refs and x != e["ref"]]
    subjects = actor_refs | event_refs | rel_refs
    claims = []
    for c in _list(raw.get("claims")):
        if isinstance(c, dict) and _str(c.get("text")) and c.get("subject") in subjects and ev(c) and fresh(c.get("ref")):
            claims.append({"ref": c["ref"], "subject": c["subject"], "text": c["text"].strip(), "kind": "attribute" if c.get("kind") == "attribute" else "assertion",
                           "holder": c.get("holder") if c.get("holder") in actor_refs else "narrator", "formation": _formation(c.get("formation"), "reported"),
                           "conflicts_with": [x for x in _list(c.get("conflicts_with")) if isinstance(x, str)], "confidence": _num(c.get("confidence"), 0.7),
                           "evidence": ev(c), "span": _str(c.get("span"))})
    claim_refs = {c["ref"] for c in claims}
    for c in claims:
        c["conflicts_with"] = [x for x in c["conflicts_with"] if x in claim_refs and x != c["ref"]]
    known = subjects | claim_refs
    narrative = []
    for n in _list(raw.get("narrative")):
        about = [x for x in _list(n.get("about")) if x in known] if isinstance(n, dict) else []
        if isinstance(n, dict) and _str(n.get("text")) and _str(n.get("kind")) and about and ev(n) and fresh(n.get("ref")):
            narrative.append({"ref": n["ref"], "kind": n["kind"].strip(), "about": about, "holder": n.get("holder") if n.get("holder") in actor_refs else "model",
                              "text": n["text"].strip(), "formation": _formation(n.get("formation"), "inferred"), "confidence": _num(n.get("confidence"), 0.6),
                              "evidence": ev(n)})
    commitments = [{"ref": k["ref"], "committer": k["committer"], "to": k.get("to") if k.get("to") in actor_refs else None, "text": k["text"].strip(),
                    "tentative": bool(k.get("tentative")), "confidence": _num(k.get("confidence"), 0.7), "evidence": ev(k)}
                   for k in _list(raw.get("commitments")) if isinstance(k, dict) and _str(k.get("text")) and k.get("committer") in actor_refs and ev(k)
                   and fresh(k.get("ref"))]
    dims = [{"ref": d["ref"], "relationship": d["relationship"], "from_actor": d["from_actor"], "to_actor": d["to_actor"], "dimension": d["dimension"].strip(),
             "value": d["value"].strip(), "about": d.get("about") if d.get("about") in event_refs else None,
             "durability": _durability(d.get("durability")), "formation": _formation(d.get("formation"), "inferred"),
             "confidence": _num(d.get("confidence"), 0.6), "evidence": ev(d)}
            for d in _list(raw.get("dimensions")) if isinstance(d, dict) and d.get("relationship") in rel_refs and d.get("from_actor") in actor_refs
            and d.get("to_actor") in actor_refs and _str(d.get("dimension")) and _str(d.get("value")) and ev(d) and fresh(d.get("ref"))]
    objectives = []
    for o in _list(raw.get("objectives")):
        if isinstance(o, dict) and o.get("actor") in actor_refs and _str(o.get("text")) and ev(o) and fresh(o.get("ref")):
            op = o.get("op") if o.get("op") in ("create", "update", "resolve") else "create"
            existing = _str(o.get("existing_id"))
            if op != "create" and not existing:
                op = "create"
            scope = str(o.get("scope") or "active").lower()
            state = str(o.get("state") or "unknown").lower()
            objectives.append({"ref": o["ref"], "op": op, "existing_id": existing if op != "create" else None, "actor": o["actor"],
                               "toward": o.get("toward") if o.get("toward") in actor_refs else None, "text": o["text"].strip(),
                               "scope": scope if scope in ("enduring", "active", "immediate") else "active", "cause": _str(o.get("cause")),
                               "state": state if state in ("on_track", "drifting", "at_risk", "failing", "resolved", "unknown") else "unknown",
                               "durability": _durability(o.get("durability")),
                               "strength": _num(o.get("strength"), 0.6), "conflicts_with": ([x for x in _list(o.get("conflicts_with")) if isinstance(x, str)] if isinstance(o.get("conflicts_with"), list) else None),
                               "formation": _formation(o.get("formation"), "inferred"), "confidence": _num(o.get("confidence"), 0.6), "evidence": ev(o)})
    all_refs = known | {n["ref"] for n in narrative} | {k["ref"] for k in commitments}
    matters = []
    for m in _list(raw.get("matter_candidates")):
        members = [x for x in _list(m.get("members")) if x in all_refs] if isinstance(m, dict) else []
        if isinstance(m, dict) and _str(m.get("display_title")) and _str(m.get("concept")) and members and ev(m) and fresh(m.get("ref")):
            kind = str(m.get("kind") or "topic")
            matters.append({"ref": m["ref"], "concept": m["concept"].strip(), "display_title": m["display_title"].strip(),
                            "kind": kind if kind in ("project", "topic", "concern", "relationship_situation", "relationship_thread", "goal", "life_situation", "routine", "other") else "topic",
                            "actors": [a for a in _list(m.get("actors")) if a in actor_refs], "members": members, "continuity_required": bool(m.get("continuity_required")),
                            "continuity_reason": _str(m.get("continuity_reason")), "attach_to_existing_matter_id": _str(m.get("attach_to_existing_matter_id")),
                            "evidence": ev(m)})
    trajectory = [{"ref": t["ref"], "actor": t["actor"], "state": t.get("state") if t.get("state") in ("on_track", "drifting", "at_risk", "failing") else "unknown",
                   "note": t["note"].strip(), "objectives": [x for x in _list(t.get("objectives")) if isinstance(x, str)], "evidence": ev(t)}
                  for t in _list(raw.get("trajectory")) if isinstance(t, dict) and t.get("actor") in actor_refs and _str(t.get("note")) and ev(t) and fresh(t.get("ref"))]
    brief = None
    b = raw.get("brief")
    if isinstance(b, dict) and _str(b.get("text")):
        brief = {"text": b["text"].strip(), "lines": [{"text": str(l.get("text")).strip(), "refs": [r for r in _list(l.get("refs")) if isinstance(r, str)]}
                                                      for l in _list(b.get("lines")) if isinstance(l, dict) and _str(l.get("text"))]}
    return {
        "contract_version": "world-delta-v1", "workspace_id": workspace_id, "owner": owner,
        "source": {"producer": "world-interpreter", "model": model, "version": "wi-1", "run_id": run_id, "session_id": session_id,
                   "messages": [{"id": m["id"], "speaker": m["speaker"], "text": m["text"]} for m in messages], "policy": policy if policy in ("grounded", "generative") else "grounded",
                   "covered_through": {"message_id": messages[-1]["id"], "ordinal": covered_ordinal} if messages else None,
                   "owner_actor": speaker_actors.get("user"), "speaker_actors": speaker_actors},
        "actors": actors, "relationships": rels, "events": events, "claims": claims, "narrative": narrative, "commitments": commitments,
        "dimensions": dims, "objectives": objectives, "matter_candidates": matters, "trajectory": trajectory, "brief": brief,
    }


async def world_state_for_prompt(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, Any]:
    """The current world as the interpreter should see it: ids included so it can recognise instead of duplicate. Selection is by recency only."""
    from src.models.identity import Entity, ModelEntry, RelationshipEdge
    from src.models.matter import Matter
    from src.models.world import ContinuationBrief, RelationshipDimension, TrajectoryNote, WorldEvent, WorldObjective
    ents = (await db.execute(select(Entity).where(Entity.honcho_workspace_id == workspace_id, Entity.frame_scope == owner))).scalars().all()
    names = {e.id: e.display_name for e in ents}
    ids = list(names)
    edges = (await db.execute(select(RelationshipEdge).where(RelationshipEdge.honcho_workspace_id == workspace_id,
                                                              RelationshipEdge.from_entity_id.in_(ids)))).scalars().all() if ids else []
    events = (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
                                                         WorldEvent.superseded_by_id.is_(None)).order_by(WorldEvent.updated_at.desc()).limit(STATE_ITEMS))).scalars().all()
    objs = (await db.execute(select(WorldObjective).where(WorldObjective.honcho_workspace_id == workspace_id, WorldObjective.owner_peer_id == owner,
                                                           WorldObjective.status == "current").order_by(WorldObjective.updated_at.desc()).limit(STATE_ITEMS))).scalars().all()
    dims = (await db.execute(select(RelationshipDimension).where(RelationshipDimension.honcho_workspace_id == workspace_id,
                                                                  RelationshipDimension.owner_peer_id == owner, RelationshipDimension.superseded_by_id.is_(None)
                                                                  ).order_by(RelationshipDimension.updated_at.desc()).limit(STATE_ITEMS))).scalars().all()
    entries = (await db.execute(select(ModelEntry).where(ModelEntry.honcho_workspace_id == workspace_id, ModelEntry.owner_peer_id == owner,
                                                          ModelEntry.superseded_by_id.is_(None)).order_by(ModelEntry.updated_at.desc()).limit(STATE_ITEMS))).scalars().all()
    matters = (await db.execute(select(Matter).where(Matter.honcho_workspace_id == workspace_id, Matter.owner_peer_id == owner,
                                                      Matter.status == "active").limit(15))).scalars().all()
    brief = (await db.execute(select(ContinuationBrief).where(ContinuationBrief.honcho_workspace_id == workspace_id, ContinuationBrief.owner_peer_id == owner,
                                                               ContinuationBrief.superseded_by_id.is_(None)).limit(1))).scalars().first()
    note = (await db.execute(select(TrajectoryNote).where(TrajectoryNote.honcho_workspace_id == workspace_id, TrajectoryNote.owner_peer_id == owner,
                                                           TrajectoryNote.superseded_by_id.is_(None)).order_by(TrajectoryNote.created_at.desc()).limit(1))).scalars().first()
    return {
        "actors": [{"id": str(e.id), "name": e.display_name, "type": e.entity_type} for e in ents],
        "relationships": [{"id": str(r.id), "between": [names.get(r.from_entity_id), names.get(r.to_entity_id)], "type": r.role} for r in edges],
        "events": [{"id": str(e.id), "label": e.label, "kind": e.kind, "when": e.when_phrase, "where": e.place, "status": e.status} for e in events],
        "objectives": [{"id": str(o.id), "actor": names.get(o.actor_entity_id), "toward": names.get(o.toward_entity_id), "text": o.text, "scope": o.scope,
                        "state": o.state, "cause": o.cause} for o in objs],
        "dimensions": [{"from": names.get(d.from_entity_id), "to": names.get(d.to_entity_id), "dimension": d.dimension, "value": d.value} for d in dims],
        "recent_entries": [{"kind": e.claim_kind, "text": e.claim[:160], "holder": e.holder_actor, "formation": e.formation, "status": e.epistemic_status} for e in entries],
        "matters": [{"id": str(m.id), "title": m.title, "kind": m.kind} for m in matters],
        "last_brief": brief.text if brief else None, "last_trajectory_note": note.note if note else None,
    }


async def honcho_context(workspace_id: str, owner: str, session_id: str, evidence_text: str) -> Optional[Dict[str, Any]]:
    """Long-horizon input from Honcho (derived summaries + semantic search over the stored raw evidence). Honcho is evidence storage and retrieval
    for these worlds; this interpreter remains the single semantic author. Bounded, fail-open."""
    try:
        from src.services.turn_context import _honcho_client
        client = _honcho_client()
        if client is None:
            return None
        summaries = await client.session_summaries(workspace_id, session_id)
        hits = await client.peer_search(workspace_id, owner, evidence_text[-450:], limit=6)
        earlier = [{"text": str(h.get("content") or "")[:300], "when": h.get("created_at"), "session": h.get("session_id")} for h in (hits or [])]
        out = {"summary": {k: (v or "")[:900] for k, v in (summaries or {}).items() if v}, "earlier_evidence": earlier}
        return out if out["summary"] or earlier else None
    except Exception as exc:
        logger.warning("honcho context failed open: %s", exc)
        return None


async def interpret(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str, messages: List[Dict[str, str]], speakers: Dict[str, str],
                    policy: str, constitution: Optional[Dict[str, str]], adapter: Any, covered_ordinal: int = 0, model: Optional[str] = None,
                    now: Optional[datetime] = None, matter_adapter: Any = None) -> Dict[str, Any]:
    """One interpretation pass: read state, ask the model, validate structurally, materialise, return the receipt (with usage telemetry)."""
    model_id = model or INTERPRETER_MODEL
    state = await world_state_for_prompt(db, workspace_id, owner)
    evidence = "\n".join(f"[{m['id']}] {speakers.get(m['speaker'], m['speaker'])}: {m['text']}" for m in messages)
    honcho = await honcho_context(workspace_id, owner, session_id, evidence)
    prompt = (f"PRODUCT POLICY: {policy}\n"
              f"CHARACTER CONSTITUTIONAL ORIENTATION (product-authored; {constitution.get('actor') if constitution else 'the companion'} toward "
              f"{constitution.get('toward') if constitution else 'the user'}): {constitution.get('text') if constitution else 'none'}\n"
              f"SPEAKERS: user = {speakers.get('user', 'the user')}; assistant = {speakers.get('assistant', 'the companion')}\n\n"
              f"CURRENT WORLD STATE (ids are real):\n{json.dumps(state, ensure_ascii=False, default=str)}\n\n"
              + (f"HONCHO CONTEXT (long-term store):\n{json.dumps(honcho, ensure_ascii=False)}\n\n" if honcho else "")
              + f"NEW EVIDENCE:\n{evidence}")
    raw = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"type": "object"}, model_id=model_id, max_tokens=9000,
                                            temperature=0.1, strict=False, timeout=INTERPRETER_TIMEOUT)
    delta_dict = normalize(raw if isinstance(raw, dict) else {}, messages=messages, speakers=speakers, workspace_id=workspace_id, owner=owner,
                           session_id=session_id, model=model_id, run_id=str(uuid.uuid4()), policy=policy, covered_ordinal=covered_ordinal)
    delta = WorldDelta(**delta_dict)
    receipt = await world_materializer.materialize(db, delta, now=now, adapter=matter_adapter, constitution=constitution)
    receipt["usage"] = getattr(adapter, "last_usage", None)
    receipt["model"] = model_id
    receipt["interpreted"] = {k: len(delta_dict[k]) for k in ("actors", "relationships", "events", "claims", "narrative", "commitments", "dimensions",
                                                              "objectives", "matter_candidates", "trajectory")} | {"brief": bool(delta_dict["brief"])}
    return receipt
