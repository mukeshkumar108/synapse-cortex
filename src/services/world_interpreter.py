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

# Plain Luna, not the "-pro" variant: measured 2026-10-06 on identical input, Pro billed ~46k prompt tokens for an ~8.4k-token prompt (internal ensembling), took 44s and cost
# $0.020 a pass; plain Luna took 20-24s at ~$0.004 with equal-or-better extraction. Cheaper/faster alternatives tried and rejected (thin reviews, invalid JSON, or no scene): see
# docs/INTERPRETER_MODEL_BAKEOFF.md.
INTERPRETER_MODEL = os.getenv("WORLD_INTERPRETER_MODEL", "openai/gpt-5.6-luna")
INTERPRETER_TIMEOUT = float(os.getenv("WORLD_INTERPRETER_TIMEOUT_SECONDS", "150"))
STATE_ITEMS = 30
LEASE_WAIT_SECONDS = float(os.getenv("WORLD_LEASE_WAIT_SECONDS", "45"))
CONTEXT_MESSAGES = 6          # already-interpreted messages shown as context only (a budget, not a judgement)

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
  dependency, avoidance, respect, awareness of a specific event, expectation, intent, and so on. When the state of a known facet has CHANGED
  (the CURRENT WORLD STATE lists facets with ids), set `supersedes` to its id so the old reading is retired; if both readings still hold, omit it. For awareness use: "aware" only when the
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
- PROVENANCE OF THE COMPANION'S OWN WORDS: what the companion character says about its own OFF-SCREEN past or secret acts, offered under questioning, or anything that contradicts events already established in the evidence or the CURRENT WORLD STATE, is a CLAIM held by that actor (list the established event in `conflicts_with`), never an event. It becomes an event only if the evidence independently shows it happened (it is shown happening in the scene, or the person confirms it). What the companion does and says in the present scene is evidence of what occurred there as usual.
- FACTS ABOUT THE PERSON THAT ONLY THE COMPANION SUPPLIED: when the person asks the companion to remind them of, or recall, something about the person's own life (their name, pets, work, family, history, what they said before) and the companion answers with detail the person has not stated anywhere in the evidence or the CURRENT WORLD STATE, that detail is a hypothesis held by the companion (formation hypothesis), never an event or a fact about the person. It is promoted only if the person later states or confirms it. This holds in every policy, fiction included: invented story world is canon, invented knowledge of the person's own side is not.
- Epistemic policy 'grounded' (a real person's life): facts that only the companion asserted about the user's life or other people are
  hypotheses, not facts. Policy 'generative' (collaborative fiction): story events and invented detail are canon, still attributed.
- IDENTITIES are product-supplied, never inferred from prose: the actor refs `user` (the human's actor) and `companion` (the character) already exist in
  every response; use them wherever those two appear (from_actor, to_actor, holder, committer, actor, participants, relationships). Never create an actor
  for the human or the companion, and never call anyone "the user" as a character. Messages marked as the user's are spoken by `user`; the assistant's by
  `companion`. If the human's name was not supplied, do not guess it; a person the dialogue names is a separate actor unless the evidence plainly says
  the human is that person.
- REFERENCES (he/she/they, him/her, "my boyfriend", "the guy from the panel", a repeated first name, a new nickname): resolve a reference only when the
  evidence supports it, by the known actor's id (existing_id). Same name can be different people and one person can have several names. If a reference
  is probable but not established, keep it low-confidence (hypothesis / possibly_same_as). If two or more known actors fit and the evidence does not
  choose, do NOT choose: add a narrative item of kind `ambiguous_reference` whose `about` lists the candidates and whose text says what is unresolved.
  If nothing known fits, either create a new actor or leave it out. Ambiguity is a valid, stored outcome.
- STATE REVIEW: for EVERY objective and dimension listed in CURRENT WORLD STATE, return one `state_review` entry {id, status, note}: holds (still true
  given everything so far), superseded (the new evidence changed it: also write the replacement in `dimensions` with `supersedes` = this id),
  resolved (an objective that is over: also an objectives entry with op resolve), or unclear (evidence is mixed, unresolved contradiction stays).
  Silence is not a verdict. Absence of new evidence about a facet means holds or unclear, never superseded. A facet about whether someone knows
  something changes when the evidence shows they now do, however it happened.
- Anywhere a reference is expected (actor, relationship, event), you may use either a short local ref declared in this response or the id of a known
  item from CURRENT WORLD STATE. Prefer the known id when the thing already exists.
- OPERATIONAL: things someone will be held to or must remember (a reminder the user asked for, a plan with a time, a promise, an appointment, a routine) and
  what happens to those already listed under OPERATIONAL STATE (done, called off, postponed, progressing). Emit `operational` items only for those, not
  for every idea or topic. `temporal_phrase` is the speaker's own words about when (never compute a timestamp: code grounds it). To act on a listed open
  item use its id in `target`. In a grounded world, something only the companion asserts about the user's life is not the user's commitment; the companion's
  own promises are its own. An item that merely repeats one already listed is not new. When new evidence RESOLVES a listed item (including something someone was waiting on), complete or cancel THAT item by its id in addition to recording anything new; do not leave it open and create a replacement.
- OPERATIONAL REVIEW: for EVERY item listed under OPERATIONAL STATE return one `operational_review` verdict {id, status, note, evidence}: holds (still open as
  is), updated (its timing or substance changed: also emit the change in `operational`), completed (it happened / was resolved, including something someone was
  waiting on), cancelled (called off), superseded (replaced by a newer item you create), unclear. completed / cancelled / superseded / updated need `evidence`
  (message ids). Resolving an item and creating a new one are separate acts and can both happen in one response. Silence is not a verdict.
- STANDING REQUESTS: anything the person has asked of the companion about how to talk or behave (a name not to use, a topic to avoid, less of something, a correction to what the companion got wrong) is listed under STANDING REQUESTS in CURRENT WORLD STATE. Return the full list that should be active after the NEW EVIDENCE as `standing_requests` (strings in the person's own terms): keep each one that still stands, add new ones, and leave out any the person has withdrawn or changed. Omit the field entirely if you have no view.
- BRIEF carries the durable story only. The live scene (what is happening right now, what has just been used up) is written by a separate fast pass; do not describe it here.
- Use short local refs (a1, r1, e1, c1, n1, k1, o1, d1, mc1, t1). Every item needs evidence: message ids from the NEW EVIDENCE. Omit anything unsure.

OUTPUT: ONE JSON object with these arrays (empty when nothing applies): actors, relationships, events, claims, narrative, commitments,
dimensions, objectives, matter_candidates, trajectory, state_review, operational, operational_review, and an optional brief. Shapes:
actors:[{ref,name,aliases[],entity_type(person|character|organisation|team),explicit(bool),existing_id|null,confidence,evidence[]}]
relationships:[{ref,actors[a,b],type,directional(bool),existing_id|null,formation,confidence,evidence[]}]
events:[{ref,label,kind,when_phrase|null,where|null,participants[],holder|null,formation,confidence,evidence[],conflicts_with[],same_as|null,possibly_same_as|null}]
claims:[{ref,subject(ref of actor/event/relationship),text,kind(assertion|attribute),holder(actor ref|null),formation,confidence,evidence[],span|null(verbatim),conflicts_with[]}]
narrative:[{ref,kind(open: rupture, concealment, resentment, self_expression, ...),about[refs],holder(actor ref|null),text,formation,confidence,evidence[]}]
commitments:[{ref,committer,to|null,text,tentative(bool),confidence,evidence[]}]
dimensions:[{ref,relationship(ref),from_actor,to_actor,dimension,value,about(event ref)|null,durability(acute|provisional|durable|unknown),supersedes(known facet id)|null,formation,confidence,evidence[]}]
objectives:[{ref,op(create|update|resolve),existing_id|null,actor,toward|null,text,scope,cause|null,state,durability(acute|provisional|durable|unknown),strength(0-1),conflicts_with[objective refs|known ids|"constitution"; omit the field to leave recorded conflicts unchanged],formation,confidence,evidence[]}]
matter_candidates:[{ref,concept,display_title,kind(project|topic|concern|relationship_situation|goal|life_situation|routine|other),actors[],members[refs],continuity_required(bool),continuity_reason,attach_to_existing_matter_id|null,evidence[]}]
trajectory:[{ref,actor,state(on_track|drifting|at_risk|failing|unknown),note,objectives[],evidence[]}]
state_review:[{id(of a listed objective or dimension),status(holds|superseded|resolved|unclear),note}]
operational_review:[{id(of a listed open item),status(holds|updated|completed|cancelled|superseded|unclear),note,evidence[]}]
operational:[{decision(create|complete|cancel|progress|reschedule),kind(reminder|event|deadline|commitment),title,temporal_phrase|null,target(id of a listed open item)|null,canonical_title|null,new_temporal_phrase|null,progress_amount|null,progress_unit|null,confidence,evidence[]}]
brief:{text,lines:[{text,refs[]}]}
standing_requests:["<request>", ...]  (optional; the full active list)"""


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


class _Drops:
    """Every candidate the structural cleanup removes is recorded with its reason: nothing disappears silently."""
    def __init__(self) -> None:
        self.items: List[Dict[str, str]] = []

    def __call__(self, kind: str, item: Any, reason: str) -> None:
        ref = item.get("ref") if isinstance(item, dict) else None
        self.items.append({"kind": kind, "ref": str(ref) if ref is not None else "?", "reason": reason})


def normalize(raw: Dict[str, Any], *, messages: List[Dict[str, str]], speakers: Dict[str, str], workspace_id: str, owner: str, session_id: str,
              model: str, run_id: str, policy: str, covered_ordinal: int = 0, pinned: Optional[Dict[str, Any]] = None,
              drops: Optional[_Drops] = None, known: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
    """Tolerant structural cleanup of the model's JSON into a valid WorldDelta dict (mechanics only): drop items with no usable evidence or
    broken local references (each drop recorded with its reason), keep refs unique. Nothing is invented or reinterpreted here. `pinned` maps the
    product-supplied roles (user_actor / companion_actor) to their stable entities; they enter every delta as the fixed refs `user` / `companion`.
    `known` is the id registry of the world state the interpreter was shown ({actors|relationships|events: {id: label}}): a reference may be a local
    ref OR a known id; a known id is resolved mechanically by declaring a link-by-id stub (identity is by id, nothing is inferred)."""
    drops = drops if drops is not None else _Drops()
    ids = {m["id"] for m in messages}
    seen: set = set()

    def fresh(kind: str, item: Any) -> bool:
        ref = item.get("ref") if isinstance(item, dict) else None
        if not isinstance(ref, str) or not ref.strip():
            drops(kind, item, "missing_ref")
            return False
        if ref in seen:
            drops(kind, item, "duplicate_ref")
            return False
        seen.add(ref)
        return True

    def ev(item: Dict[str, Any]) -> List[str]:
        return [e for e in _list(item.get("evidence")) if isinstance(e, str) and e in ids]

    def dict_items(kind: str, key: str) -> List[Dict[str, Any]]:
        out = []
        for it in _list(raw.get(key)):
            if isinstance(it, dict):
                out.append(it)
            else:
                drops(kind, {}, "not_an_object")
        return out

    first_id = messages[0]["id"] if messages else ""
    actors: List[Dict[str, Any]] = []
    speaker_actors: Dict[str, str] = {}
    for role, ref, speaker_key in (("user_actor", "user", "user"), ("companion_actor", "companion", "assistant")):
        ent = (pinned or {}).get(role)
        if ent is not None and messages:
            seen.add(ref)
            actors.append({"ref": ref, "name": ent.display_name, "aliases": [], "entity_type": ent.entity_type if ent.entity_type in ("person", "character", "organisation", "team") else "person",
                           "explicit": not ent.provisional, "existing_id": str(ent.id), "confidence": 1.0, "evidence": [first_id]})
            speaker_actors[speaker_key] = ref
    for a in dict_items("actors", "actors"):
        if not _str(a.get("name")):
            drops("actors", a, "no_name")
        elif not ev(a):
            drops("actors", a, "no_valid_evidence")
        elif fresh("actors", a):
            et = str(a.get("entity_type") or "person").lower()
            actors.append({"ref": a["ref"], "name": a["name"].strip(), "aliases": [x for x in _list(a.get("aliases")) if isinstance(x, str) and x.strip()],
                           "entity_type": et if et in ("person", "character", "organisation", "team") else "person", "explicit": bool(a.get("explicit")),
                           "existing_id": _str(a.get("existing_id")), "confidence": _num(a.get("confidence"), 0.7), "evidence": ev(a)})
    actor_refs = {a["ref"] for a in actors}
    norm = lambda t: "".join(ch for ch in str(t).lower() if ch.isalpha())
    if len(speaker_actors) < 2:        # no pinned identity for a role: fall back to the product-supplied speaker NAME matched against the interpreter's actors
        by_name = {norm(a["name"]): a["ref"] for a in actors}
        for a in actors:
            for al in a["aliases"]:
                by_name.setdefault(norm(al), a["ref"])
        for role, name in speakers.items():
            if role not in speaker_actors and norm(name) in by_name:
                speaker_actors[role] = by_name[norm(name)]

    known = known or {}
    stubs: Dict[Any, str] = {}

    def actor_ref(x: Any, evidence: List[str]) -> Optional[str]:
        """A local actor ref, or the id of a known actor (declared here as a link-by-id stub). Anything else resolves to nothing."""
        if isinstance(x, str) and x in actor_refs:
            return x
        if isinstance(x, str) and x in (known.get("actors") or {}) and evidence:
            ref = stubs.setdefault(("actor", x), f"known_{len(stubs)}")
            if ref not in actor_refs:
                actors.append({"ref": ref, "name": known["actors"][x], "aliases": [], "entity_type": "person", "explicit": False, "existing_id": x,
                               "confidence": 1.0, "evidence": evidence[:1]})
                actor_refs.add(ref)
                seen.add(ref)
            return ref
        return None

    events: List[Dict[str, Any]] = []
    event_refs: set = set()

    def event_ref(x: Any, evidence: List[str]) -> Optional[str]:
        """A local event ref, or the id of a known event (declared here as a same_as-by-id stub so the link survives)."""
        if isinstance(x, str) and x in event_refs:
            return x
        if isinstance(x, str) and x in (known.get("events") or {}) and evidence:
            ref = stubs.setdefault(("event", x), f"known_ev_{len(stubs)}")
            if ref not in event_refs:
                events.append({"ref": ref, "label": known["events"][x], "kind": "event", "when": {"phrase": None, "precision": "unknown"}, "where": None,
                               "participants": [], "holder": None, "formation": "reported", "confidence": 1.0, "evidence": evidence[:1], "conflicts_with": [],
                               "same_as": x, "possibly_same_as": None})
                event_refs.add(ref)
                seen.add(ref)
            return ref
        return None

    rels = []
    for r in dict_items("relationships", "relationships"):
        r_actors = [actor_ref(x, ev(r)) for x in _list(r.get("actors"))]
        if len(r_actors) != 2 or None in r_actors:
            drops("relationships", r, "actors_not_two_known_refs")
        elif not ev(r):
            drops("relationships", r, "no_valid_evidence")
        elif fresh("relationships", r):
            rels.append({"ref": r["ref"], "actors": r_actors, "type": _str(r.get("type")) or "related", "directional": bool(r.get("directional")),
                         "existing_id": _str(r.get("existing_id")), "formation": _formation(r.get("formation"), "inferred"), "confidence": _num(r.get("confidence"), 0.7),
                         "evidence": ev(r)})
    rel_refs = {r["ref"] for r in rels}
    for e in dict_items("events", "events"):
        if not _str(e.get("label")):
            drops("events", e, "no_label")
        elif not ev(e):
            drops("events", e, "no_valid_evidence")
        elif fresh("events", e):
            event_refs.add(e["ref"])
            events.append({"ref": e["ref"], "label": e["label"].strip(), "kind": _str(e.get("kind")) or "event",
                           "when": {"phrase": _str(e.get("when_phrase")), "precision": "approx" if _str(e.get("when_phrase")) else "unknown"},
                           "where": _str(e.get("where")),
                           "participants": [r for r in (actor_ref(p, ev(e)) for p in _list(e.get("participants"))) if r],
                           "holder": actor_ref(e.get("holder"), ev(e)), "formation": _formation(e.get("formation"), "reported"),
                           "confidence": _num(e.get("confidence"), 0.7), "evidence": ev(e), "conflicts_with": [x for x in _list(e.get("conflicts_with")) if isinstance(x, str)],
                           "same_as": _str(e.get("same_as")), "possibly_same_as": _str(e.get("possibly_same_as"))})
    for e in events:
        e["conflicts_with"] = [x for x in e["conflicts_with"] if x in event_refs and x != e["ref"]]
    subjects = actor_refs | event_refs | rel_refs
    claims = []
    for c in dict_items("claims", "claims"):
        c_subject = actor_ref(c.get("subject"), ev(c)) or event_ref(c.get("subject"), ev(c)) or c.get("subject")
        subjects = actor_refs | event_refs | rel_refs
        if not _str(c.get("text")):
            drops("claims", c, "no_text")
        elif c_subject not in subjects:
            drops("claims", c, "unknown_subject")
        elif not ev(c):
            drops("claims", c, "no_valid_evidence")
        elif fresh("claims", c):
            claims.append({"ref": c["ref"], "subject": c_subject, "text": c["text"].strip(), "kind": "attribute" if c.get("kind") == "attribute" else "assertion",
                           "holder": actor_ref(c.get("holder"), ev(c)) or "narrator", "formation": _formation(c.get("formation"), "reported"),
                           "conflicts_with": [x for x in _list(c.get("conflicts_with")) if isinstance(x, str)], "confidence": _num(c.get("confidence"), 0.7),
                           "evidence": ev(c), "span": _str(c.get("span"))})
    claim_refs = {c["ref"] for c in claims}
    for c in claims:
        c["conflicts_with"] = [x for x in c["conflicts_with"] if x in claim_refs and x != c["ref"]]
    known_refs = actor_refs | event_refs | rel_refs | claim_refs
    narrative = []
    for n in dict_items("narrative", "narrative"):
        about = [r for r in ((actor_ref(x, ev(n)) or event_ref(x, ev(n)) or (x if x in known_refs else None)) for x in _list(n.get("about"))) if r]
        if not (_str(n.get("text")) and _str(n.get("kind"))):
            drops("narrative", n, "no_text_or_kind")
        elif not about:
            drops("narrative", n, "no_known_about_ref")
        elif not ev(n):
            drops("narrative", n, "no_valid_evidence")
        elif fresh("narrative", n):
            narrative.append({"ref": n["ref"], "kind": n["kind"].strip(), "about": about, "holder": actor_ref(n.get("holder"), ev(n)) or "model",
                              "text": n["text"].strip(), "formation": _formation(n.get("formation"), "inferred"), "confidence": _num(n.get("confidence"), 0.6),
                              "evidence": ev(n)})
    commitments = []
    for k in dict_items("commitments", "commitments"):
        k_committer, k_to = actor_ref(k.get("committer"), ev(k)), actor_ref(k.get("to"), ev(k))
        if not _str(k.get("text")) or k_committer is None:
            drops("commitments", k, "no_text_or_unknown_committer")
        elif not ev(k):
            drops("commitments", k, "no_valid_evidence")
        elif fresh("commitments", k):
            commitments.append({"ref": k["ref"], "committer": k_committer, "to": k_to, "text": k["text"].strip(),
                                "tentative": bool(k.get("tentative")), "confidence": _num(k.get("confidence"), 0.7), "evidence": ev(k)})
    dims = []
    for d in dict_items("dimensions", "dimensions"):
        d_from, d_to = actor_ref(d.get("from_actor"), ev(d)), actor_ref(d.get("to_actor"), ev(d))
        rel = d.get("relationship")
        if rel not in rel_refs and isinstance(rel, str) and rel in (known.get("relationships") or {}) and d_from and d_to and ev(d):
            stub = stubs.setdefault(("rel", rel), f"known_rel_{len(stubs)}")      # the interpreter named a known relationship by id: declare it by id
            if stub not in rel_refs:
                rels.append({"ref": stub, "actors": [d_from, d_to], "type": known["relationships"][rel], "directional": False, "existing_id": rel,
                             "formation": "inferred", "confidence": 1.0, "evidence": ev(d)[:1]})
                rel_refs.add(stub)
                seen.add(stub)
            rel = stub
        if rel not in rel_refs or d_from is None or d_to is None:
            drops("dimensions", d, "relationship_or_actor_not_declared")
        elif not (_str(d.get("dimension")) and _str(d.get("value"))):
            drops("dimensions", d, "no_dimension_or_value")
        elif not ev(d):
            drops("dimensions", d, "no_valid_evidence")
        elif fresh("dimensions", d):
            dims.append({"ref": d["ref"], "relationship": rel, "from_actor": d_from, "to_actor": d_to, "dimension": d["dimension"].strip(),
                         "value": d["value"].strip(), "about": event_ref(d.get("about"), ev(d)),
                         "durability": _durability(d.get("durability")), "supersedes": _str(d.get("supersedes")), "formation": _formation(d.get("formation"), "inferred"),
                         "confidence": _num(d.get("confidence"), 0.6), "evidence": ev(d)})
    objectives = []
    for o in dict_items("objectives", "objectives"):
        o_actor, o_toward = actor_ref(o.get("actor"), ev(o)), actor_ref(o.get("toward"), ev(o))
        if o_actor is None or not _str(o.get("text")):
            drops("objectives", o, "unknown_actor_or_no_text")
        elif not ev(o):
            drops("objectives", o, "no_valid_evidence")
        elif fresh("objectives", o):
            op = o.get("op") if o.get("op") in ("create", "update", "resolve") else "create"
            existing = _str(o.get("existing_id"))
            if op != "create" and not existing:
                op = "create"
            scope = str(o.get("scope") or "active").lower()
            state = str(o.get("state") or "unknown").lower()
            objectives.append({"ref": o["ref"], "op": op, "existing_id": existing if op != "create" else None, "actor": o_actor,
                               "toward": o_toward, "text": o["text"].strip(),
                               "scope": scope if scope in ("enduring", "active", "immediate") else "active", "cause": _str(o.get("cause")),
                               "state": state if state in ("on_track", "drifting", "at_risk", "failing", "resolved", "unknown") else "unknown",
                               "durability": _durability(o.get("durability")),
                               "strength": _num(o.get("strength"), 0.6), "conflicts_with": ([x for x in _list(o.get("conflicts_with")) if isinstance(x, str)] if isinstance(o.get("conflicts_with"), list) else None),
                               "formation": _formation(o.get("formation"), "inferred"), "confidence": _num(o.get("confidence"), 0.6), "evidence": ev(o)})
    all_refs = known_refs | {n["ref"] for n in narrative} | {k["ref"] for k in commitments}
    matters = []
    for m in dict_items("matter_candidates", "matter_candidates"):
        members = [x for x in _list(m.get("members")) if x in all_refs]
        if not (_str(m.get("display_title")) and _str(m.get("concept"))):
            drops("matter_candidates", m, "no_title_or_concept")
        elif not members:
            drops("matter_candidates", m, "no_known_members")
        elif not ev(m):
            drops("matter_candidates", m, "no_valid_evidence")
        elif fresh("matter_candidates", m):
            kind = str(m.get("kind") or "topic")
            matters.append({"ref": m["ref"], "concept": m["concept"].strip(), "display_title": m["display_title"].strip(),
                            "kind": kind if kind in ("project", "topic", "concern", "relationship_situation", "relationship_thread", "goal", "life_situation", "routine", "other") else "topic",
                            "actors": [a for a in _list(m.get("actors")) if a in actor_refs], "members": members, "continuity_required": bool(m.get("continuity_required")),
                            "continuity_reason": _str(m.get("continuity_reason")), "attach_to_existing_matter_id": _str(m.get("attach_to_existing_matter_id")),
                            "evidence": ev(m)})
    trajectory = []
    for t in dict_items("trajectory", "trajectory"):
        t_actor = actor_ref(t.get("actor"), ev(t))
        if t_actor is None or not _str(t.get("note")):
            drops("trajectory", t, "unknown_actor_or_no_note")
        elif not ev(t):
            drops("trajectory", t, "no_valid_evidence")
        elif fresh("trajectory", t):
            trajectory.append({"ref": t["ref"], "actor": t_actor, "state": t.get("state") if t.get("state") in ("on_track", "drifting", "at_risk", "failing") else "unknown",
                               "note": t["note"].strip(), "objectives": [x for x in _list(t.get("objectives")) if isinstance(x, str)], "evidence": ev(t)})
    operational = []
    open_ids = (known.get("operational") or {})
    for o in dict_items("operational", "operational"):
        decision = str(o.get("decision") or "").lower()
        target = _str(o.get("target"))
        if decision not in ("create", "complete", "cancel", "progress", "reschedule"):
            drops("operational", o, "bad_decision")
        elif decision != "create" and target not in open_ids:
            drops("operational", o, "target_not_a_listed_open_item")
        elif decision == "create" and not _str(o.get("title")):
            drops("operational", o, "create_without_title")
        elif not ev(o):
            drops("operational", o, "no_valid_evidence")
        else:
            operational.append({"decision": decision, "kind": (_str(o.get("kind")) or "commitment").lower(), "title": _str(o.get("title")),
                                "temporal_phrase": _str(o.get("temporal_phrase")), "target": target if decision != "create" else None,
                                "canonical_title": _str(o.get("canonical_title")) or (open_ids.get(target) if target else None),
                                "new_temporal_phrase": _str(o.get("new_temporal_phrase")), "progress_amount": o.get("progress_amount") if isinstance(o.get("progress_amount"), (int, float)) else None,
                                "progress_unit": _str(o.get("progress_unit")), "confidence": _num(o.get("confidence"), 0.8), "evidence": ev(o)})
    op_reviews = []
    for r in dict_items("operational_review", "operational_review"):
        rid, st = _str(r.get("id")), str(r.get("status") or "").lower()
        if st not in ("holds", "updated", "completed", "cancelled", "superseded", "unclear") or rid not in open_ids:
            drops("operational_review", {"ref": rid}, "bad_status_or_unlisted_id")
        elif st in ("updated", "completed", "cancelled", "superseded") and not ev(r):
            drops("operational_review", {"ref": rid}, "verdict_without_evidence")
        else:
            op_reviews.append({"id": rid, "status": st, "note": _str(r.get("note")), "evidence": ev(r)})
    reviews = []
    for r in dict_items("state_review", "state_review"):
        if r.get("status") in ("holds", "superseded", "resolved", "unclear") and _str(r.get("id")):
            reviews.append({"id": r["id"].strip(), "status": r["status"], "note": _str(r.get("note"))})
        else:
            drops("state_review", {"ref": r.get("id")}, "bad_id_or_status")
    brief = None
    b = raw.get("brief")
    if isinstance(b, dict) and _str(b.get("text")):
        raw_turns = b.get("raw_turns")
        brief = {"text": b["text"].strip(), "lines": [{"text": str(l.get("text")).strip(), "refs": [r for r in _list(l.get("refs")) if isinstance(r, str)]}
                                                      for l in _list(b.get("lines")) if isinstance(l, dict) and _str(l.get("text"))],
                 "now": _str(b.get("now")), "unresolved": [str(x).strip() for x in _list(b.get("unresolved")) if _str(x)][:6],
                 "transient": [str(x).strip() for x in _list(b.get("transient")) if _str(x)][:6],
                 "changed": [str(x).strip() for x in _list(b.get("changed")) if _str(x)][:6],
                 "spent": [str(x).strip() for x in _list(b.get("spent")) if _str(x)][:10],
                 "raw_turns": raw_turns if isinstance(raw_turns, int) and not isinstance(raw_turns, bool) and 0 <= raw_turns <= 3 else None,
                 "raw_reason": _str(b.get("raw_reason"))}
    return {
        "contract_version": "world-delta-v1", "workspace_id": workspace_id, "owner": owner,
        "source": {"producer": "world-interpreter", "model": model, "version": "wi-2", "run_id": run_id, "session_id": session_id,
                   "messages": [{"id": m["id"], "speaker": m["speaker"], "text": m["text"]} for m in messages], "policy": policy if policy in ("grounded", "generative") else "grounded",
                   "covered_through": {"message_id": messages[-1]["id"], "ordinal": covered_ordinal} if messages else None,
                   "owner_actor": speaker_actors.get("user"), "speaker_actors": speaker_actors},
        "actors": actors, "relationships": rels, "events": events, "claims": claims, "narrative": narrative, "commitments": commitments,
        "dimensions": dims, "objectives": objectives, "matter_candidates": matters, "trajectory": trajectory, "brief": brief, "reviews": reviews,
        "operational": operational, "operational_reviews": op_reviews,
    }


async def world_state_for_prompt(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, Any]:
    """The current world as the interpreter should see it: ids included so it can recognise instead of duplicate. Selection is by recency only."""
    from src.models.identity import Entity, ModelEntry, RelationshipEdge
    from src.models.matter import Matter
    from src.models.world import ContinuationBrief, RelationshipDimension, TrajectoryNote, WorldEvent, WorldIdentity, WorldObjective
    ents = (await db.execute(select(Entity).where(Entity.honcho_workspace_id == workspace_id, Entity.frame_scope == owner))).scalars().all()
    names = {e.id: e.display_name for e in ents}
    ids = list(names)
    roles = {r.entity_id: r.role for r in (await db.execute(select(WorldIdentity).where(
        WorldIdentity.honcho_workspace_id == workspace_id, WorldIdentity.owner_peer_id == owner))).scalars().all()}
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
        "actors": [{"id": str(e.id), "name": e.display_name, "type": e.entity_type, **({"role": roles[e.id]} if e.id in roles else {})} for e in ents],
        "relationships": [{"id": str(r.id), "between": [names.get(r.from_entity_id), names.get(r.to_entity_id)], "type": r.role} for r in edges],
        "events": [{"id": str(e.id), "label": e.label, "kind": e.kind, "when": e.when_phrase, "where": e.place, "status": e.status} for e in events],
        "objectives": [{"id": str(o.id), "actor": names.get(o.actor_entity_id), "toward": names.get(o.toward_entity_id), "text": o.text, "scope": o.scope,
                        "state": o.state, "cause": o.cause} for o in objs],
        "dimensions": [{"id": str(d.id), "from": names.get(d.from_entity_id), "to": names.get(d.to_entity_id), "dimension": d.dimension, "value": d.value, "durability": d.durability} for d in dims],
        "recent_entries": [{"kind": e.claim_kind, "text": e.claim[:160], "holder": e.holder_actor, "formation": e.formation, "status": e.epistemic_status} for e in entries],
        "matters": [{"id": str(m.id), "title": m.title, "kind": m.kind} for m in matters],
        "last_brief": brief.text if brief else None, "last_trajectory_note": note.note if note else None,
    }


async def honcho_context(workspace_id: str, owner: str, session_id: str, evidence_text: str) -> Optional[Dict[str, Any]]:
    """Long-horizon input from Honcho (derived summaries + semantic search over the stored raw evidence). Honcho is evidence storage and retrieval
    for these worlds; this interpreter remains the single semantic author. Bounded, fail-open."""
    try:
        from src.config import settings
        from src.services.turn_context import _honcho_client, honcho_peer_id
        client = _honcho_client() if settings.HONCHO_CONTEXT_ENABLED else None
        if client is None:
            return None
        summaries = await client.session_summaries(workspace_id, session_id)
        if summaries:
            try:
                if await client.session_has_rewound(workspace_id, session_id):
                    summaries = None     # written over the discarded branch too: it does not describe the live timeline
            except Exception:
                pass
        hits = await client.peer_search(workspace_id, honcho_peer_id(owner), evidence_text[-450:], limit=6)
        # a message the product discarded (edit / retry / rewind) is not evidence of the live timeline: the Runtime's own retrieval already drops it, and so must this read
        earlier = [{"text": str(h.get("content") or "")[:300], "when": h.get("created_at"), "session": h.get("session_id")} for h in (hits or []) if not (h.get("metadata") or {}).get("rewound")]
        out = {"summary": {k: (v or "")[:900] for k, v in (summaries or {}).items() if v}, "earlier_evidence": earlier}
        return out if out["summary"] or earlier else None
    except Exception as exc:
        logger.warning("honcho context failed open: %s", exc)
        return None


def message_hash(speaker: str, text: str) -> str:
    import hashlib
    return hashlib.sha1(f"{speaker}|{' '.join(str(text).split()).lower()}".encode()).hexdigest()[:20]


async def covered_message_ids(db: AsyncSession, workspace_id: str, owner: str) -> set:
    """Evidence this world has already been interpreted over: the message ids of its applied interpreter runs. Pure ledger arithmetic."""
    return (await _coverage(db, workspace_id, owner))[0]


async def _coverage(db: AsyncSession, workspace_id: str, owner: str):
    from collections import Counter
    from src.models.world import ProducerRun
    rows = (await db.execute(select(ProducerRun.input_json).where(
        ProducerRun.honcho_workspace_id == workspace_id, ProducerRun.owner_peer_id == owner, ProducerRun.producer == "world-interpreter",
        ProducerRun.status == "applied"))).scalars().all()
    covered: set = set()
    synthetic: Counter = Counter()
    for blob in rows:
        try:
            data = json.loads(blob or "{}")
        except ValueError:
            continue
        covered.update(data.get("message_ids") or [])
        synthetic.update(data.get("synthetic_hashes") or [])
    return covered, synthetic


def split_fresh(messages: List[Dict[str, str]], covered: set, synthetic: Any) -> List[bool]:
    """For each offered message: is it still uninterpreted? Covered by id, or (persisted message only) by matching an already-interpreted SYNTHETIC
    message of the same speaker and text, consumed one-for-one. Mechanical identity; no similarity judgement."""
    pool = dict(synthetic)
    out = []
    for m in messages:
        if m["id"] in covered:
            out.append(False)
            continue
        h = message_hash(m["speaker"], m["text"])
        if m.get("synthetic") != "true" and pool.get(h, 0) > 0:
            pool[h] -= 1
            out.append(False)
            continue
        out.append(True)
    return out


def _utc() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _finish(db: AsyncSession, rid: Any, status: str, detail: Dict[str, Any], counts: Optional[Dict[str, Any]] = None) -> None:
    from src.models.world import ProducerRun
    rtype = ProducerRun
    try:
        await db.rollback()
        fresh_run = await db.get(rtype, rid)
        fresh_run.status, fresh_run.finished_at = status, _utc()
        fresh_run.detail_json = json.dumps({**json.loads(fresh_run.detail_json or "{}"), **detail}, default=str)[:200000]
        if counts is not None:
            fresh_run.counts_json = json.dumps({**json.loads(fresh_run.counts_json or "{}"), **counts}, default=str)
        db.add(fresh_run)
        await db.commit()
    except Exception as exc:          # observability must never mask the real outcome
        logger.warning("could not finish run %s as %s: %s", rid, status, exc)


def _busy_receipt(run_id: str, model: str) -> Dict[str, Any]:
    return {"status": "busy", "run_id": run_id, "counts": {}, "rejected": [], "repaired": [], "refs": {}, "covered_through": None, "snapshot_version": None,
            "model": model, "interpreted": {}}


def apply_overrides(base: str, overrides: Optional[Dict[str, Any]]) -> str:
    """Lab-only interpreter prompt variants: exact-text replacements and an append, so a sentence can be tested without touching source. A
    replacement that matches nothing fails loudly (a silently ignored override would make an experiment look like it tested something)."""
    text = base
    for pair in (overrides or {}).get("system_replace") or []:
        old, new = pair
        if old not in text:
            raise ValueError(f"system_replace text not found: {old[:80]!r}")
        text = text.replace(old, new)
    extra = (overrides or {}).get("system_append")
    return text + ("\n" + extra if extra else "")


async def interpret(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str, messages: List[Dict[str, str]], speakers: Dict[str, str],
                    policy: str, constitution: Optional[Dict[str, str]], adapter: Any, covered_ordinal: int = 0, model: Optional[str] = None,
                    now: Optional[datetime] = None, matter_adapter: Any = None, user_actor: Optional[str] = None,
                    companion_actor: Optional[str] = None, timezone: str = "UTC", overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One interpretation pass as a transaction over a world.

    Protocol: open a run (queued) -> take the world's cross-process lease -> under the lease compute, by message id, what is still uninterpreted
    (the ledger is the applied runs) -> running -> model -> structural cleanup (drops recorded) -> materialise -> applied. Any failure leaves a
    failed run and its evidence uncovered, so the next delivery interprets it again. Callers may send any overlapping window."""
    from src.models.world import ProducerRun
    from src.services import world_identity, world_lease
    model_id = (overrides or {}).get("model") or model or INTERPRETER_MODEL
    system = apply_overrides(SYSTEM, overrides)
    run = ProducerRun(honcho_workspace_id=workspace_id, owner_peer_id=owner, producer="world-interpreter", model=model_id, version="wi-2", status="queued",
                      input_json=json.dumps({"session_id": session_id, "message_ids": [], "offered_ids": [m["id"] for m in messages][:world_materializer.MAX_RUN_MESSAGE_IDS]}))
    db.add(run)
    await db.commit()
    rid = run.id                  # read now: later rollbacks expire the instance
    from src import call_context as _cc, runtime_model as _rm
    _person = _cc.person_of(owner)
    if not overrides and _person and _rm.PERSON_DAILY_BUDGET_USD > 0 and await _cc.person_spent_today(_person) >= _rm.PERSON_DAILY_BUDGET_USD:
        # The cost contract: a person's background cognition stops at the daily ceiling; nothing is lost (the evidence stays uncovered and the next delivery after 00:00 UTC takes it).
        await _finish(db, rid, "deferred", {"reason": "person_budget"}, {"deferred": "person_budget"})
        return _busy_receipt(str(rid), model_id)
    key, holder = world_lease.lease_key(workspace_id, owner), str(rid)
    if not await world_lease.acquire(db, key, holder, wait_seconds=LEASE_WAIT_SECONDS):
        await _finish(db, rid, "deferred", {"reason": "lease_timeout"}, {"deferred": "lease_timeout"})
        return _busy_receipt(holder, model_id)
    try:
        covered, synthetic = await _coverage(db, workspace_id, owner)
        flags = split_fresh(messages, covered, synthetic)
        fresh_msgs = [m for m, f in zip(messages, flags) if f]
        if not fresh_msgs:
            await _finish(db, rid, "skipped", {"reason": "already_interpreted", "offered": len(messages)})
            return {"status": "already_interpreted", "run_id": holder, "counts": {}, "rejected": [], "repaired": [], "refs": {}, "covered_through": None,
                    "snapshot_version": None, "model": model_id, "interpreted": {}}
        first_new = flags.index(True)
        context = [m for m, f in zip(messages[:first_new], flags[:first_new]) if not f][-CONTEXT_MESSAGES:]
        fresh = [m for m, f in zip(messages[first_new:], flags[first_new:]) if f]
        run.status, run.started_at = "running", _utc()
        run.input_json = json.dumps({"session_id": session_id, "message_ids": [m["id"] for m in fresh][:world_materializer.MAX_RUN_MESSAGE_IDS],
                                     "synthetic_hashes": [message_hash(m["speaker"], m["text"]) for m in fresh if m.get("synthetic") == "true"],
                                     "context_ids": [m["id"] for m in context], "offered_ids": [m["id"] for m in messages][:world_materializer.MAX_RUN_MESSAGE_IDS]})
        db.add(run)
        await db.commit()
        return await _interpret_locked(db, run=run, rid=rid, workspace_id=workspace_id, owner=owner, session_id=session_id, context=context, fresh=fresh,
                                       speakers=speakers, policy=policy, constitution=constitution, adapter=adapter, covered_ordinal=covered_ordinal,
                                       model_id=model_id, now=now, matter_adapter=matter_adapter, user_actor=user_actor, companion_actor=companion_actor, timezone=timezone,
                                       system=system, overrides=overrides)
    except Exception as exc:
        await _finish(db, rid, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}, {"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        raise
    finally:
        await world_lease.release(db, key, holder)


async def _interpret_locked(db: AsyncSession, *, run: Any, rid: Any, workspace_id: str, owner: str, session_id: str, context: List[Dict[str, str]],
                            fresh: List[Dict[str, str]], speakers: Dict[str, str], policy: str, constitution: Optional[Dict[str, str]], adapter: Any,
                            covered_ordinal: int, model_id: str, now: Optional[datetime], matter_adapter: Any, user_actor: Optional[str],
                            companion_actor: Optional[str], timezone: str = "UTC", system: str = SYSTEM, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from src.models.world_model import WorldModelSnapshot
    from src.services import world_identity
    first_id = (context + fresh)[0]["id"]
    pinned = await world_identity.ensure(db, workspace_id=workspace_id, owner=owner, session_id=session_id, user_name=user_actor,
                                         companion_name=companion_actor, first_message_id=first_id)
    prior_snap = (await db.execute(select(WorldModelSnapshot.version).where(
        WorldModelSnapshot.honcho_workspace_id == workspace_id, WorldModelSnapshot.owner_peer_id == owner,
        WorldModelSnapshot.superseded_by_id.is_(None)).order_by(WorldModelSnapshot.compiled_at.desc()).limit(1))).scalars().first()
    messages = context + fresh
    from src.services import executive
    state = await world_state_for_prompt(db, workspace_id, owner)
    state["operational_state"] = await executive.operational_snapshot(db, workspace_id, owner)
    from src.services import standing_requests as _sr
    state["standing_requests"] = await _sr.active(db, workspace_id, owner)
    speaker_label = {"user": user_actor or "the user (name not supplied)", "assistant": companion_actor or speakers.get("assistant", "the companion")}
    proactive = await executive.outbound_index(db, workspace_id, owner, [m["id"] for m in context + fresh])
    line = lambda m: f"[{m['id']}] {speaker_label.get(m['speaker'], speakers.get(m['speaker'], m['speaker']))} ({'user' if m['speaker'] == 'user' else 'companion'}): {m['text']}" + (f"  [a proactive message you sent to carry out: {proactive[m['id']]['title']}]" if m['id'] in proactive else "")
    evidence = "\n".join(line(m) for m in fresh)
    honcho = await honcho_context(workspace_id, owner, session_id, evidence)
    toward = constitution.get("toward") if constitution else None
    prompt = (f"PRODUCT POLICY: {policy}\n"
              f"IDENTITIES (product-supplied): `user` = {user_actor or 'the human (name not supplied)'}; `companion` = {companion_actor or speakers.get('assistant', 'the companion')}\n"
              f"CHARACTER CONSTITUTIONAL ORIENTATION (product-authored; {constitution.get('actor') if constitution else 'the companion'} toward "
              f"{toward or 'the user'}): {constitution.get('text') if constitution else 'none'}\n\n"
              f"CURRENT WORLD STATE (ids are real; `operational_state` lists the open time-bound items):\n{json.dumps(state, ensure_ascii=False, default=str)}\n\n"
              + (f"HONCHO CONTEXT (long-term store):\n{json.dumps(honcho, ensure_ascii=False)}\n\n" if honcho else "")
              + (("EARLIER MESSAGES (already interpreted; context only, do not re-derive what the CURRENT WORLD STATE already holds):\n"
                  + "\n".join(line(m) for m in context) + "\n\n") if context else "")
              + f"NEW EVIDENCE:\n{evidence}")
    raw = await adapter.generate_structured(system=system, prompt=prompt, json_schema={"type": "object"}, model_id=model_id, max_tokens=9000,
                                            temperature=0.1, strict=False, timeout=INTERPRETER_TIMEOUT)
    raw = raw if isinstance(raw, dict) else {}
    drops = _Drops()
    delta_dict = normalize(raw, messages=messages, speakers=speakers, workspace_id=workspace_id, owner=owner, session_id=session_id, model=model_id,
                           run_id=str(rid), policy=policy, covered_ordinal=covered_ordinal, pinned=pinned, drops=drops,
                           known={"actors": {a["id"]: a["name"] for a in state["actors"]}, "relationships": {r["id"]: r["type"] for r in state["relationships"]},
                                  "events": {e["id"]: e["label"] for e in state["events"]},
                                  "operational": {x["id"]: x["title"] for kind in ("expectations", "open_loops", "commitments") for x in state["operational_state"][kind]}})
    delta = WorldDelta(**delta_dict)
    known_operational = [x["id"] for kind in ("expectations", "open_loops", "commitments") for x in state["operational_state"][kind]]
    receipt = await world_materializer.materialize(db, delta, now=now, adapter=matter_adapter, constitution=constitution, run=run)
    if isinstance(raw.get("standing_requests"), list):
        receipt["standing_requests"] = await _sr.sync(db, workspace_id, owner, [str(x) for x in raw["standing_requests"]], source="interpreter")
    receipt["operational"] = await commit_operational(db, delta.operational, messages=messages, workspace_id=workspace_id, owner=owner, session_id=session_id,
                                                      timezone=timezone, now=now)
    receipt["operational"]["reviews"] = await apply_operational_reviews(db, delta.operational_reviews, messages=messages, now=now)
    listed = list(known_operational)
    reviewed = {r.id for r in delta.operational_reviews}
    receipt["operational"]["coverage"] = {"listed": len(listed), "reviewed": len([i for i in listed if i in reviewed]), "unreviewed_ids": [i for i in listed if i not in reviewed]}
    kinds = ("actors", "relationships", "events", "claims", "narrative", "commitments", "dimensions", "objectives", "matter_candidates", "trajectory")
    receipt["usage"] = getattr(adapter, "last_usage", None)
    receipt["model"] = model_id
    receipt["status"] = "applied"
    receipt["interpreted"] = {k: len(delta_dict[k]) for k in kinds} | {"brief": bool(delta_dict["brief"])}
    receipt["proposed"] = {k: len(_list(raw.get(k))) for k in kinds}          # what the model returned, before structural cleanup
    shown = {"objectives": [o["id"] for o in state["objectives"]], "dimensions": [d["id"] for d in state["dimensions"]]}
    reviewed = {r["id"] for r in delta_dict["reviews"]}
    unreviewed = [i for ids in shown.values() for i in ids if i not in reviewed]
    receipt["review_coverage"] = {"shown": sum(len(v) for v in shown.values()), "reviewed": sum(len(v) for v in shown.values()) - len(unreviewed), "unreviewed_ids": unreviewed}
    detail = {
        "evidence": {"session_id": session_id, "fresh_ids": [m["id"] for m in fresh], "context_ids": [m["id"] for m in context],
                     "covered_through": receipt.get("covered_through")},
        "identities": {role: {"entity_id": str(e.id), "name": e.display_name, "provisional": e.provisional} for role, e in pinned.items()},
        "honcho": {"used": bool(honcho), "summaries": sorted((honcho or {}).get("summary", {}).keys()), "earlier_hits": len((honcho or {}).get("earlier_evidence", []))},
        "state_shown": {k: len(v) for k, v in state.items() if isinstance(v, list)} | {"review_ids": shown},
        "proposed": receipt["proposed"], "kept": receipt["interpreted"], "dropped": drops.items, "rejected": receipt["rejected"], "repaired": receipt["repaired"],
        "operational": receipt["operational"], "superseded": receipt.get("superseded", []), "reviews": receipt.get("reviews", []), "review_coverage": receipt["review_coverage"],
        "snapshot": {"before": prior_snap, "after": receipt.get("snapshot_version")}, "model": model_id, "usage": receipt["usage"],
        **({"interpreter_overrides": {"system_replace": (overrides or {}).get("system_replace"), "system_append": (overrides or {}).get("system_append"),
                                      "model": (overrides or {}).get("model")}} if overrides else {}),
    }
    await _finish(db, rid, "applied", detail, {"proposed": receipt["proposed"], "kept": receipt["interpreted"], "dropped": len(drops.items)})
    from src.services import executive
    await executive.link_replies(db, workspace_id, owner, messages, proactive)
    # The executive reconsiders only when something it acts on changed: operational items (reminders, plans, completions), commitments, objectives or a new Matter.
    # A pass that only refreshed claims, relationships or the story brief gives it nothing to decide; the daily review and its own scheduled wakes cover the rest.
    op = receipt.get("operational") or {}
    acts_on = bool(op.get("committed")) or any(receipt["interpreted"].get(k) for k in ("commitments", "objectives", "matter_candidates"))
    if acts_on:
        await executive.note_changed(db, workspace_id, owner, "world_interpreted")      # no-op unless the world's policy enables the executive
    return receipt


async def commit_operational(db: AsyncSession, items: List[Any], *, messages: List[Dict[str, str]], workspace_id: str, owner: str, session_id: str,
                             timezone: str, now: Optional[datetime]) -> Dict[str, Any]:
    """The interpreter decided these are operational (a reminder, a commitment, a completion...). Each becomes the same typed candidate the narrow lane
    produced and goes through the SAME deterministic commit path: temporal grounding, shaping, lifecycle, idempotent persistence. Per-item failures are
    recorded, never fatal to the run."""
    if not items:
        return {"committed": [], "failed": []}
    from datetime import timezone as dt_tz
    from src.routers import v1_events
    from src.schemas.expectation import TurnEventIngest
    from src.services.narrow_realtime import NarrowDecision, NarrowRealtimeExtractor
    by_id = {m["id"]: m for m in messages}
    stamp = now or datetime.now(dt_tz.utc)
    committed, failed = [], []
    for it in items:
        try:
            msg = by_id[it.evidence[0]]
            if it.decision in ("complete", "cancel") and it.target:
                # The interpreter named exactly which listed item this closes: applying a known id is mechanics, not interpretation (and works across
                # sessions, unlike the fuzzy session-scoped matchers).
                applied = await _close_by_id(db, it.target, it.decision, msg["text"][:500], stamp)
                (committed if applied else failed).append({"decision": it.decision, "title": it.canonical_title or it.title, **applied} if applied else
                                                          {"title": it.title, "reason": "target_not_found"})
                continue
            decision = NarrowDecision(decision=it.decision, kind=it.kind if it.kind in ("reminder", "event", "deadline", "commitment") else "commitment", title=it.title,
                                      temporal_phrase=it.temporal_phrase, target_key=it.target, canonical_title=it.canonical_title, evidence_text=msg["text"][:500],
                                      new_temporal_phrase=it.new_temporal_phrase, progress_amount=it.progress_amount, progress_unit=it.progress_unit,
                                      confidence=it.confidence, valid=True)
            cand = NarrowRealtimeExtractor.to_candidate(None, decision)
            if cand is None:
                failed.append({"title": it.title, "reason": "no_candidate"})
                continue
            if cand.resolution_hint is not None and it.target:
                cand.resolution_hint["target_id"] = it.target       # exact id: the lifecycle mutates precisely this item
            payload = TurnEventIngest(workspace_id=workspace_id, session_id=session_id, honcho_message_id=msg["id"], peer_id=owner, text=msg["text"],
                                      now=stamp if stamp.tzinfo else stamp.replace(tzinfo=dt_tz.utc), timezone=timezone or "UTC")
            result = await v1_events._ingest_turn_event_locked(payload, db, candidates_override=[cand])
            committed.append({"decision": it.decision, "title": it.title or it.canonical_title, "mutations": [m.get("mutation") for m in result.get("operational_mutations", []) if isinstance(m, dict)],
                              "expectations": result.get("expectations_created_count", 0), "closed": len(result.get("mutated_expectation_ids", []))})
        except Exception as exc:
            await db.rollback()
            logger.warning("operational commit failed: %s", exc)
            failed.append({"title": it.title, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return {"committed": committed, "failed": failed}


async def _close_by_id(db: AsyncSession, target: str, decision: str, evidence: str, now: Any) -> Optional[Dict[str, Any]]:
    """Complete / cancel one open operational item (expectation, open loop, or commitment candidate) by its exact id, and close what hangs off it."""
    from uuid import UUID
    from src.models.commitment_candidate import CommitmentCandidate, CommitmentCandidateStatus
    from src.models.expectation import Expectation, OutcomeState
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    try:
        tid = UUID(str(target))
    except (TypeError, ValueError):
        return None
    done = decision == "complete"
    stamp = now.replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
    exp = await db.get(Expectation, tid)
    if exp is not None:
        exp.outcome_state = OutcomeState.FULFILLED if done else OutcomeState.CANCELLED
        exp.resolution_evidence, exp.updated_at = evidence, stamp
        db.add(exp)
        for loop in (await db.execute(select(OpenLoop).where(OpenLoop.expectation_id == tid, OpenLoop.status == OpenLoopStatus.OPEN))).scalars().all():
            loop.status, loop.resolution_evidence = (OpenLoopStatus.RESOLVED if done else OpenLoopStatus.ABANDONED), evidence
            db.add(loop)
        await db.commit()
        return {"closed": "expectation", "id": str(tid), "outcome": exp.outcome_state.value if hasattr(exp.outcome_state, "value") else str(exp.outcome_state)}
    loop = await db.get(OpenLoop, tid)
    if loop is not None:
        loop.status, loop.resolution_evidence, loop.updated_at = (OpenLoopStatus.RESOLVED if done else OpenLoopStatus.ABANDONED), evidence, stamp
        db.add(loop)
        await db.commit()
        return {"closed": "open_loop", "id": str(tid)}
    cc = await db.get(CommitmentCandidate, tid)
    if cc is not None:
        cc.status, cc.resolution_evidence, cc.updated_at = (CommitmentCandidateStatus.FULFILLED if done else CommitmentCandidateStatus.DISMISSED), evidence, stamp
        db.add(cc)
        await db.commit()
        return {"closed": "commitment", "id": str(tid)}
    return None


async def apply_operational_reviews(db: AsyncSession, reviews: List[Any], *, messages: List[Dict[str, str]], now: Optional[datetime]) -> List[Dict[str, Any]]:
    """Apply the interpreter's verdicts on listed open items. completed / cancelled / superseded close the item by its exact id (mechanics); holds / updated /
    unclear change nothing here (an update's new timing arrives through `operational`). Every verdict is recorded with whether it took effect."""
    from datetime import timezone as dt_tz
    by_id = {m["id"]: m for m in messages}
    stamp = now or datetime.now(dt_tz.utc)
    out = []
    for r in reviews:
        entry = {"id": r.id, "status": r.status, "applied": r.status in ("holds", "updated", "unclear")}
        if r.status in ("completed", "cancelled", "superseded"):
            text = by_id[r.evidence[0]]["text"][:500] if r.evidence and r.evidence[0] in by_id else (r.note or "")
            result = await _close_by_id(db, r.id, "complete" if r.status == "completed" else "cancel", text, stamp)
            entry["applied"] = bool(result)
            if result:
                entry["closed"] = result.get("closed")
        out.append(entry)
    return out
