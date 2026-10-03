"""Cortex materialiser for WorldDelta candidates (docs/WORLD_CONTRACT.md).

Pipeline: candidates -> deterministic grounding/provenance repair -> (optional) judgement of AMBIGUOUS candidates only -> materialisation.
Cortex never reads prose here: it resolves identity, places claims on the existing epistemic ladder (`epistemics.write_claim`), resolves Matters
through the existing resolver, records the producing run on every row, and returns a receipt with `covered_through` so the Runtime can retire the
provisional state Cortex has absorbed. Candidates, not truth: a lower-firmness candidate never replaces a firmer claim.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from difflib import SequenceMatcher

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.identity import Entity, EntityAlias, EntityLink, ModelEntry
from datetime import timedelta

from src.models.world import ProducerRun, RelationshipDimension, RowProvenance, TrajectoryNote, WorldEvent, WorldLink, WorldObjective
from src.schemas.world_delta import WorldDelta
from src.services import entity_service, epistemics

logger = logging.getLogger(__name__)

SELF_EXPRESSION_CONFIDENCE_CAP = 0.4
DIRECTIONAL_RELATIONSHIPS = {"parent", "child", "manager", "employee", "mentor", "mentee", "employer", "boss", "report", "teacher", "student"}
RELATIONAL_KINDS = {"rupture", "concealment", "disclosure", "trust_change", "reconciliation", "relationship_shift"}
CONTINUITY_MEMBER_KINDS = RELATIONAL_KINDS | {"commitment", "ambiguity"}
CONTINUITY_MATTER_KINDS = {"project", "goal", "routine", "relationship_situation", "relationship_thread", "concern", "life_situation"}
RELATIONAL_LABEL = {"rupture": "rupture", "concealment": "concealed strain", "trust_change": "trust strain", "reconciliation": "repair",
                    "disclosure": "disclosure aftermath", "relationship_shift": "changing relationship"}
RELATIONAL_PRIORITY = ["rupture", "concealment", "trust_change", "disclosure", "relationship_shift", "reconciliation"]
TRAJECTORY_NOTE_TTL = timedelta(hours=72)
AT_RISK_STATES = {"at_risk", "failing"}
EVENT_MERGE_RATIO, EVENT_POSSIBLE_RATIO = 0.9, 0.6
Judge = Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Dict[str, Any]]]]


def _naive(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower().replace("’", "'")).strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:80]


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


class _Ctx:
    """Mutable state of one materialisation."""
    def __init__(self, db: AsyncSession, delta: WorldDelta, run: ProducerRun, now: datetime):
        self.db, self.delta, self.run, self.now = db, delta, run, now
        self.ws, self.owner, self.sess = delta.workspace_id, delta.owner, delta.source.session_id
        self.msgs = {m.id: m for m in delta.source.messages}
        self.entities: Dict[str, Entity] = {}
        self.edges: Dict[str, Any] = {}
        self.events: Dict[str, WorldEvent] = {}
        self.entries: Dict[str, ModelEntry] = {}
        self.rejected: List[Dict[str, str]] = []
        self.repaired: List[Dict[str, str]] = []
        self.refs: Dict[str, Dict[str, str]] = {}
        self.matters: List[Any] = []
        self.objectives: Dict[str, WorldObjective] = {}
        self.entities_by_id: Dict[Any, Entity] = {}
        self.rel_entries: Dict[Any, List[ModelEntry]] = {}
        self.rel_edges: Dict[Any, Any] = {}
        self.counts: Dict[str, int] = {}

    def reject(self, ref: str, reason: str) -> None:
        self.rejected.append({"ref": ref, "reason": reason})

    def count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def holder_name(self, holder: Optional[str]) -> Optional[str]:
        if holder in (None, "narrator", "model"):
            return None          # a model INFERENCE about the world has no holder; its formation (inferred/observed) already says so.
                                 # ("system" is reserved for the companion's own thoughts and would force the perspective kind.)
        ent = self.entities.get(holder)
        return ent.display_name if ent else None

    async def prov(self, row_type: str, row_id: UUID) -> None:
        exists = (await self.db.execute(select(RowProvenance.id).where(
            RowProvenance.run_id == self.run.id, RowProvenance.row_type == row_type, RowProvenance.row_id == row_id))).first()
        if not exists:
            self.db.add(RowProvenance(honcho_workspace_id=self.ws, run_id=self.run.id, row_type=row_type, row_id=row_id))

    async def link(self, from_type: str, from_id: UUID, to_type: str, to_id: UUID, role: str) -> None:
        exists = (await self.db.execute(select(WorldLink.id).where(
            WorldLink.honcho_workspace_id == self.ws, WorldLink.from_type == from_type, WorldLink.from_id == from_id,
            WorldLink.to_type == to_type, WorldLink.to_id == to_id, WorldLink.role == role))).first()
        if not exists:
            self.db.add(WorldLink(honcho_workspace_id=self.ws, from_type=from_type, from_id=from_id, to_type=to_type, to_id=to_id, role=role))


# ----------------------------------------------------------------------------- grounding (deterministic)
def _evidence_ok(ctx: _Ctx, ref: str, evidence: List[str]) -> bool:
    if ctx.msgs and any(e not in ctx.msgs for e in evidence):
        ctx.reject(ref, "evidence_not_in_input")
        return False
    return True


def _span_ok(ctx: _Ctx, claim: Any) -> bool:
    if not claim.span or not ctx.msgs:
        return True
    haystack = _norm(" ".join(ctx.msgs[e].text for e in claim.evidence if e in ctx.msgs))
    if _norm(claim.span) and _norm(claim.span) in haystack:
        return True
    ctx.reject(claim.ref, "span_not_verbatim")
    return False


def _repair_holder(ctx: _Ctx, item: Any, holder: Optional[str]) -> Optional[str]:
    """An explicit statement belongs to whoever SPOKE it. The message speaker is a fact; the producer's holder is a guess."""
    speakers = {ctx.msgs[e].speaker for e in item.evidence if e in ctx.msgs}
    actors = {ctx.delta.source.speaker_actors.get(s) for s in speakers}
    if getattr(item, "formation", None) == "explicit" and len(speakers) == 1 and None not in actors:
        speaker_actor = next(iter(actors))
        if holder not in (None, "model", "narrator") and holder != speaker_actor:
            ctx.repaired.append({"ref": item.ref, "field": "holder", "from": holder, "to": speaker_actor})
            return speaker_actor
    return holder


def _assistant_asserted(ctx: _Ctx, item: Any, holder: Optional[str]) -> bool:
    """Grounded products: something only the COMPANION said about the world is not the user's world. (The companion's own commitments and
    perspective are handled elsewhere; this is about facts it asserts about the user's life or third parties.)"""
    if ctx.delta.source.policy != "grounded":
        return False
    assistant = ctx.delta.source.speaker_actors.get("assistant")
    subject = getattr(item, "subject", None)
    return bool(assistant) and holder == assistant and subject != assistant


# ----------------------------------------------------------------------------- materialisation steps
async def _actors(ctx: _Ctx) -> None:
    for a in ctx.delta.actors:
        if not _evidence_ok(ctx, a.ref, a.evidence):
            continue
        names = [a.name] + list(a.aliases)
        found: Dict[UUID, Entity] = {}
        for alias in names:
            for ent in await entity_service.find_entities(ctx.db, workspace_id=ctx.ws, alias=alias, frame=ctx.owner):
                found[ent.id] = ent
        if len(found) > 1:
            ctx.reject(a.ref, "ambiguous_actor")
            continue
        if found:
            ent = next(iter(found.values()))
            created = False
        else:
            ent = await entity_service._provision(ctx.db, workspace_id=ctx.ws, session_id=ctx.sess, display_name=a.name, frame=ctx.owner,
                                                  message_id=a.evidence[0], entity_type=a.entity_type, confidence=a.confidence)
            created = True
        have = {r.alias for r in (await ctx.db.execute(select(EntityAlias).where(EntityAlias.entity_id == ent.id))).scalars().all()}
        for alias in names:
            norm = entity_service.normalize_alias(alias)
            if norm and norm not in have:
                ctx.db.add(EntityAlias(entity_id=ent.id, alias=norm, provenance_message_id=a.evidence[0]))
                have.add(norm)
        if a.explicit and ent.provisional:
            ent.provisional = False                       # named explicitly: not a guess
        if a.entity_type == "character" and ent.entity_type == "person":
            ent.entity_type = "character"
        ent.confidence = max(ent.confidence, a.confidence)
        ctx.db.add(ent)
        await ctx.db.commit()
        ctx.entities[a.ref] = ent
        ctx.entities_by_id[ent.id] = ent
        ctx.refs[a.ref] = {"type": "entity", "id": str(ent.id)}
        await ctx.prov("entity", ent.id)
        ctx.count("actors_created" if created else "actors_linked")


async def _edge_between(ctx: _Ctx, x: UUID, y: UUID, role: Optional[str] = None) -> Optional[Any]:
    from src.models.identity import RelationshipEdge
    stmt = select(RelationshipEdge).where(
        RelationshipEdge.honcho_workspace_id == ctx.ws, RelationshipEdge.end_at.is_(None),
        or_((RelationshipEdge.from_entity_id == x) & (RelationshipEdge.to_entity_id == y),
            (RelationshipEdge.from_entity_id == y) & (RelationshipEdge.to_entity_id == x)))
    if role:
        stmt = stmt.where(RelationshipEdge.role == role)
    return (await ctx.db.execute(stmt.order_by(RelationshipEdge.created_at))).scalars().first()


async def _relationships(ctx: _Ctx) -> None:
    for r in ctx.delta.relationships:
        if not _evidence_ok(ctx, r.ref, r.evidence):
            continue
        a, b = (ctx.entities.get(x) for x in r.actors)
        if a is None or b is None:
            ctx.reject(r.ref, "actor_not_materialised")
            continue
        edge, created = None, False
        if r.type.lower() not in DIRECTIONAL_RELATIONSHIPS:        # symmetric kinds: one canonical identity per (actor set, kind), either direction
            edge = await _edge_between(ctx, a.id, b.id, role=r.type)
        if edge is None:
            edge, created = await entity_service.get_or_create_edge(
                ctx.db, workspace_id=ctx.ws, from_entity_id=a.id, to_entity_id=b.id, role=r.type, message_id=r.evidence[0], confidence=r.confidence)
        ctx.rel_edges[edge.id] = edge
        ctx.edges[r.ref] = edge
        ctx.refs[r.ref] = {"type": "edge", "id": str(edge.id)}
        await ctx.prov("edge", edge.id)
        ctx.count("relationships_created" if created else "relationships_linked")


async def _similar_event(ctx: _Ctx, ev: Any, parts: List[str]) -> Tuple[Optional[WorldEvent], Optional[WorldEvent]]:
    """(merge_target, possible_same_as). Merge only on near-identical label + compatible time/place + nested participants; two meetings of the
    same people at the same place in different months must stay two events, so anything weaker is only linked as possible_same_as."""
    rows = (await ctx.db.execute(select(WorldEvent).where(
        WorldEvent.honcho_workspace_id == ctx.ws, WorldEvent.owner_peer_id == ctx.owner, WorldEvent.superseded_by_id.is_(None),
        WorldEvent.kind == ev.kind))).scalars().all()
    label, phrase, place = _norm(ev.label), _norm(ev.when.phrase if ev.when and ev.when.phrase else ""), _norm(ev.where or "")
    mine = set(parts)
    best_merge, best_possible = None, None
    for row in rows:
        ratio = SequenceMatcher(None, label, _norm(row.label)).ratio()
        if ratio < EVENT_POSSIBLE_RATIO:
            continue
        theirs = {str(l) for l in (await ctx.db.execute(select(EntityLink.entity_id).where(
            EntityLink.object_type == "event", EntityLink.object_id == row.id))).scalars().all()}
        nested = (not mine or not theirs) or mine <= theirs or theirs <= mine
        when_ok = not phrase or not _norm(row.when_phrase or "") or phrase == _norm(row.when_phrase or "")
        place_ok = not place or not _norm(row.place or "") or place == _norm(row.place or "")
        if ratio >= EVENT_MERGE_RATIO and nested and when_ok and place_ok:
            best_merge = best_merge or row
        elif (mine & theirs) or ratio >= 0.75:
            best_possible = best_possible or row
    return best_merge, (best_possible if best_merge is None else None)


async def _events(ctx: _Ctx) -> None:
    for ev in ctx.delta.events:
        if not _evidence_ok(ctx, ev.ref, ev.evidence):
            continue
        parts = sorted(str(ctx.entities[p].id) for p in ev.participants if p in ctx.entities)
        key = hashlib.sha1(f"{_norm(ev.label)}|{_norm(ev.kind)}|{','.join(parts)}".encode()).hexdigest()[:20]
        existing = (await ctx.db.execute(select(WorldEvent).where(
            WorldEvent.honcho_workspace_id == ctx.ws, WorldEvent.owner_peer_id == ctx.owner, WorldEvent.canonical_key == key,
            WorldEvent.superseded_by_id.is_(None)))).scalars().first()
        when = ev.when
        possible = None
        if existing is None:
            existing, possible = await _similar_event(ctx, ev, parts)
        if existing is not None:
            refs = list(dict.fromkeys(json.loads(existing.evidence_refs_json or "[]") + ev.evidence))
            existing.evidence_refs_json = json.dumps(refs)
            existing.confidence = max(existing.confidence, ev.confidence)
            existing.updated_at = ctx.now
            ctx.db.add(existing)
            row, created = existing, False
        else:
            row = WorldEvent(
                honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, canonical_key=key, label=ev.label[:300], kind=ev.kind,
                when_start=_parse_dt(when.start if when else None), when_end=_parse_dt(when.end if when else None),
                when_phrase=(when.phrase if when else None), when_precision=(when.precision if when else "unknown"), place=ev.where,
                holder_actor=ctx.holder_name(_repair_holder(ctx, ev, ev.holder)), formation=epistemics.formation_class(ev.formation),
                confidence=ev.confidence, evidence_refs_json=json.dumps(ev.evidence), first_message_id=ev.evidence[0], run_id=ctx.run.id)
            ctx.db.add(row)
            created = True
        await ctx.db.flush()
        if possible is not None and possible.id != row.id:      # identity is uncertain: never merge destructively, keep both and say so
            await ctx.link("event", row.id, "event", possible.id, "possible_same_as")
            ctx.count("events_possible_same")
        for pref in ev.participants:
            ent = ctx.entities.get(pref)
            if ent is None:
                continue
            exists = (await ctx.db.execute(select(EntityLink.id).where(
                EntityLink.object_type == "event", EntityLink.object_id == row.id, EntityLink.entity_id == ent.id))).first()
            if not exists:
                ctx.db.add(EntityLink(honcho_workspace_id=ctx.ws, object_type="event", object_id=row.id, role="participant",
                                      entity_id=ent.id, confidence=0.8, provenance_message_id=ev.evidence[0]))
        for sup in ev.supersedes:
            prior = ctx.events.get(sup)
            if prior is not None and prior.id != row.id:
                prior.superseded_by_id, prior.status = row.id, "superseded"
                ctx.db.add(prior)
        await ctx.db.commit()
        ctx.events[ev.ref] = row
        ctx.refs[ev.ref] = {"type": "event", "id": str(row.id)}
        await ctx.prov("event", row.id)
        ctx.count("events_created" if created else "events_linked")


def _model_kind(ctx: _Ctx, subject: str) -> str:
    if subject in ctx.edges:
        return "relationship"
    if ctx.delta.source.owner_actor and subject == ctx.delta.source.owner_actor:
        return "user"
    return "character"


def _subject_entity(ctx: _Ctx, subject: str) -> Optional[UUID]:
    if subject in ctx.entities:
        return ctx.entities[subject].id
    if subject in ctx.edges:                              # relationship: the party that is not the owner's own character
        edge = ctx.edges[subject]
        owner_actor = ctx.entities.get(ctx.delta.source.owner_actor or "")
        if owner_actor is not None and owner_actor.id == edge.from_entity_id:
            return edge.to_entity_id
        return edge.from_entity_id
    return None


async def _write(ctx: _Ctx, *, ref: str, subject: str, text: str, claim_kind: str, holder: Optional[str], formation: str, confidence: float,
                 evidence: List[str], status: Optional[str] = None, supersedes: Optional[List[str]] = None) -> Optional[ModelEntry]:
    prior_id = None
    for sup in supersedes or []:
        if sup in ctx.entries:
            prior_id = ctx.entries[sup].id
    verbatim = " | ".join(ctx.msgs[e].text[:300] for e in evidence if e in ctx.msgs)[:1500]
    try:
        entry = await epistemics.write_claim(
            ctx.db, workspace_id=ctx.ws, session_id=ctx.sess, message_id=evidence[0], owner_peer_id=ctx.owner,
            model_kind=_model_kind(ctx, subject), claim=text, evidence_verbatim=verbatim, formation=formation, confidence=confidence,
            claim_kind=claim_kind, subject_entity_id=_subject_entity(ctx, subject), holder_actor=holder, direction="world",
            evidence_refs=evidence, supersedes_id=prior_id)
    except ValueError as exc:
        ctx.reject(ref, f"claim_rejected:{exc}")
        return None
    if status and entry.epistemic_status == "current":
        entry.epistemic_status = status
        ctx.db.add(entry)
        await ctx.db.commit()
    ctx.entries[ref] = entry
    ctx.refs[ref] = {"type": "model_entry", "id": str(entry.id)}
    await ctx.prov("model_entry", entry.id)
    if subject in ctx.events:
        await ctx.link("model_entry", entry.id, "event", ctx.events[subject].id, "about")
    if subject in ctx.edges:
        await ctx.link("model_entry", entry.id, "relationship", ctx.edges[subject].id, "about")
    await ctx.db.commit()
    return entry


def _is_quote(ctx: _Ctx, claim: Any) -> bool:
    """A claim that merely repeats what was said is evidence, not a proposition about the world."""
    text = _norm(claim.text)
    if len(text) < 12 or not ctx.msgs:
        return False
    if not re.search(r"\b(i|i m|i ve|i ll|i d|me|my|you|you re|your)\b", text):          # restated in the third person = a proposition
        return False
    return text in _norm(" ".join(ctx.msgs[e].text for e in claim.evidence if e in ctx.msgs))


async def _claims(ctx: _Ctx, verdicts: Dict[str, Dict[str, Any]]) -> None:
    for c in ctx.delta.claims:
        if not _evidence_ok(ctx, c.ref, c.evidence) or not _span_ok(ctx, c):
            continue
        v = verdicts.get(c.ref, {})
        if v.get("action") == "reject":
            ctx.reject(c.ref, f"judge:{v.get('reason', 'rejected')}")
            continue
        if _is_quote(ctx, c):
            ctx.reject(c.ref, "quote_not_proposition")
            continue
        formation = v.get("formation") or c.formation
        holder_ref = _repair_holder(ctx, c, c.holder)
        holder = ctx.holder_name(holder_ref)
        capped = _assistant_asserted(ctx, c, holder_ref)
        if capped:                                           # stays on the record as the companion's own statement, never as established fact
            formation = "hypothesis"
            ctx.count("assistant_assertions_downgraded")
        kind = "attribute" if c.predicate and c.subject in ctx.entities else "assertion"
        entry = await _write(ctx, ref=c.ref, subject=c.subject, text=c.text, claim_kind=kind, holder=holder, formation=formation,
                             confidence=min(c.confidence, 0.3) if capped else (c.confidence if v.get("action") != "downgrade" else min(c.confidence, 0.5)),
                             evidence=c.evidence, supersedes=c.supersedes, status="uncertain" if capped else None)
        if entry is not None:
            ctx.count("claims_written")


async def _attach_to_relationship(ctx: _Ctx, n: Any, entry: ModelEntry, holder: Optional[str]) -> None:
    """Relational narrative belongs to the shared relationship (directional facets hang beneath it): find the edge between the actors involved,
    else between the single involved actor and the owner's own character."""
    direct = next((ctx.edges[a] for a in n.about if a in ctx.edges), None)       # the producer already pointed at the relationship
    if direct is not None:
        ctx.rel_entries.setdefault(direct.id, []).append(entry)
        ctx.rel_edges[direct.id] = direct
        await ctx.link("model_entry", entry.id, "relationship", direct.id, "about")
        await ctx.db.commit()
        return
    involved = [ctx.entities[a] for a in n.about if a in ctx.entities]
    if holder:
        involved += [e for e in ctx.entities.values() if e.display_name == holder]
    uniq = list({e.id: e for e in involved}.values())
    owner_ent = ctx.entities.get(ctx.delta.source.owner_actor or "")
    if len(uniq) == 1 and owner_ent is not None and owner_ent.id != uniq[0].id:
        uniq.append(owner_ent)
    edge = None
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            edge = edge or await _edge_between(ctx, uniq[i].id, uniq[j].id)
    if edge is None and len(ctx.rel_edges) == 1:
        edge = next(iter(ctx.rel_edges.values()))
    if edge is None:
        return
    ctx.rel_entries.setdefault(edge.id, []).append(entry)
    ctx.rel_edges[edge.id] = edge
    await ctx.link("model_entry", entry.id, "relationship", edge.id, "about")
    await ctx.db.commit()


async def _narrative(ctx: _Ctx, verdicts: Dict[str, Dict[str, Any]]) -> None:
    for n in ctx.delta.narrative:
        if not _evidence_ok(ctx, n.ref, n.evidence):
            continue
        v = verdicts.get(n.ref, {})
        if v.get("action") == "reject":
            ctx.reject(n.ref, f"judge:{v.get('reason', 'rejected')}")
            continue
        subject = n.about[0] if n.about else None
        if subject is None:
            ctx.reject(n.ref, "narrative_without_subject")
            continue
        formation, confidence, kind = v.get("formation") or n.formation, n.confidence, n.kind
        if kind == "self_expression":                     # I9: rhetoric / performance is never a world claim, only a low-firmness perspective
            kind, formation, confidence = "perspective", "observed", min(confidence, SELF_EXPRESSION_CONFIDENCE_CAP)
        holder = ctx.holder_name(_repair_holder(ctx, n, n.holder))
        entry = await _write(ctx, ref=n.ref, subject=subject, text=n.text, claim_kind=kind, holder=holder, formation=formation,
                             confidence=confidence, evidence=n.evidence, status="uncertain" if kind == "perspective" and n.kind == "self_expression" else None)
        if entry is not None:
            ctx.count("narrative_written")
            if kind in RELATIONAL_KINDS:
                await _attach_to_relationship(ctx, n, entry, holder)


async def _commitments(ctx: _Ctx) -> None:
    for k in ctx.delta.commitments:
        if not _evidence_ok(ctx, k.ref, k.evidence):
            continue
        entry = await _write(ctx, ref=k.ref, subject=k.committer, text=k.text, claim_kind="commitment", holder=ctx.holder_name(k.committer),
                             formation="inferred" if k.tentative else "explicit", confidence=min(k.confidence, 0.5) if k.tentative else k.confidence,
                             evidence=k.evidence, status="uncertain" if k.tentative else None)
        if entry is not None:
            ctx.count("commitments_written")


async def _conflicts(ctx: _Ctx) -> None:
    pairs = [(c.ref, other) for c in ctx.delta.claims for other in c.conflicts_with] + \
            [(e.ref, other) for e in ctx.delta.events for other in e.conflicts_with]
    for a_ref, b_ref in pairs:
        a, b = ctx.entries.get(a_ref) or ctx.events.get(a_ref), ctx.entries.get(b_ref) or ctx.events.get(b_ref)
        if a is None or b is None:
            continue
        for row in (a, b):
            if isinstance(row, ModelEntry):
                if row.epistemic_status in ("current", "uncertain"):
                    row.epistemic_status = "conflicting"
            else:
                row.status = "conflicting"
            ctx.db.add(row)
        ta, tb = ("model_entry" if isinstance(a, ModelEntry) else "event"), ("model_entry" if isinstance(b, ModelEntry) else "event")
        await ctx.link(ta, a.id, tb, b.id, "conflicts_with")
        ctx.count("conflicts_recorded")
    await ctx.db.commit()


def _relationship_matter_key(ctx: _Ctx, edge: Any) -> str:
    """One relationship situation per related actor: the party that is not the owner's own character."""
    owner_ent = ctx.entities.get(ctx.delta.source.owner_actor or "")
    other = edge.to_entity_id if owner_ent is not None and owner_ent.id == edge.from_entity_id else edge.from_entity_id
    if owner_ent is not None and owner_ent.id == edge.to_entity_id:
        other = edge.from_entity_id
    return f"relationship:{other}"


async def _matters(ctx: _Ctx, adapter: Any) -> None:
    """Matter admission is about CONTINUITY NEED (does future behaviour depend on this unresolved state?), not about topics the model noticed.
    A topic whose members are only plain facts about the past stays memory; a relational rupture/concealment/commitment is a Matter."""
    items: List[Dict[str, Any]] = []
    for mc in ctx.delta.matter_candidates:
        if not _evidence_ok(ctx, mc.ref, mc.evidence):
            continue
        member_entries = [ctx.entries[m] for m in mc.members if m in ctx.entries]
        if not member_entries:
            ctx.reject(mc.ref, "matter_candidate_has_no_materialised_claim_members")
            continue
        kind = "relationship_situation" if mc.kind == "relationship_thread" else mc.kind
        needs_continuity = kind in CONTINUITY_MATTER_KINDS or any(
            e.claim_kind in CONTINUITY_MEMBER_KINDS or e.epistemic_status in ("conflicting", "uncertain") for e in member_entries)
        if not needs_continuity:
            ctx.reject(mc.ref, "no_continuity_need")
            continue
        actor_ids = {ctx.entities[a].id for a in mc.actors if a in ctx.entities}
        key = f"concept:{_slug(mc.concept)}"
        title, upgraded = mc.display_title[:200], False
        if kind in ("topic", "concern", "other") and len(actor_ids) == 2 and any(e.claim_kind in RELATIONAL_KINDS for e in member_entries):
            kind, upgraded = "relationship_situation", True                       # what continues is the relationship's state, not the model's topic label
        if kind == "relationship_situation" and len(actor_ids) == 2:
            ids = list(actor_ids)
            edge = await _edge_between(ctx, ids[0], ids[1])
            if edge is not None:
                key = _relationship_matter_key(ctx, edge)
                kinds = {e.claim_kind for e in member_entries}
                label = next((RELATIONAL_LABEL[k] for k in RELATIONAL_PRIORITY if k in kinds), "relationship")
                names = [ctx.entities_by_id[x].display_name for x in (edge.from_entity_id, edge.to_entity_id) if x in ctx.entities_by_id]
                if len(names) == 2 and upgraded:
                    title = f"{names[0]} and {names[1]}: {label}"
        items.append({"ref": mc.ref, "title": title, "kind": kind, "key": key, "entries": member_entries,
                      "events": [ctx.events[m] for m in mc.members if m in ctx.events], "actors": actor_ids})
    taken = {i["key"] for i in items}
    for edge_id, entries in ctx.rel_entries.items():           # relational state that needs continuity gets its relationship Matter even if no candidate asked
        edge = ctx.rel_edges[edge_id]
        key = _relationship_matter_key(ctx, edge)
        if key in taken:
            continue
        kinds = {e.claim_kind for e in entries}
        label = next((RELATIONAL_LABEL[k] for k in RELATIONAL_PRIORITY if k in kinds), "relationship")
        names = {e.id: e.display_name for e in ctx.entities.values()}
        a, b = names.get(edge.from_entity_id, "?"), names.get(edge.to_entity_id, "?")
        items.append({"ref": f"rel:{edge_id}", "title": f"{a} and {b}: {label}", "kind": "relationship_situation", "key": key,
                      "entries": entries, "events": [], "actors": {edge.from_entity_id, edge.to_entity_id}})
        taken.add(key)
    if not items:
        return
    from src.services import matter_service as ms
    from src.services.world_scope import resolve_scope
    scope = await resolve_scope(ctx.db, ctx.ws, ctx.owner, ctx.sess)
    index = await ms.load_index(ctx.db, scope)
    for it in items:
        member_entries, actor_ids = it["entries"], it["actors"]
        anchor = member_entries[0]
        text = f"{it['title']}. " + " ".join(e.claim for e in member_entries[:6])
        ref = ms.PrimitiveRef("model_entry", anchor.id, anchor, it["title"], text, it["kind"], live=True, terminal=False,
                              touched_at=ctx.now, created_at=ctx.now, message_id=anchor.honcho_message_id, session_id=ctx.sess,
                              formation="inferred", confidence=0.7, key_hint=it["key"], entity_ids=set(actor_ids), link_only=False)
        res = await ms.resolve_or_create_matter(ctx.db, ref, index, scope, now=ctx.now, adapter=adapter, allow_judge=adapter is not None, create=True)
        matter = res.matter
        if matter is None:
            ctx.reject(it["ref"], "matter_resolution_skipped")
            continue
        for i, entry in enumerate(member_entries):
            member = ms.PrimitiveRef("model_entry", entry.id, entry, entry.claim[:200], entry.claim, "other", live=False, terminal=False,
                                     touched_at=ctx.now, created_at=ctx.now, message_id=entry.honcho_message_id, session_id=ctx.sess,
                                     formation=entry.formation or "inferred", confidence=entry.confidence, link_only=True, entity_ids=set(actor_ids))
            await ms.attach(ctx.db, matter, member, index, how=res.how if i == 0 else "key")
        for ev in it["events"]:
            await ctx.link("event", ev.id, "matter", matter.id, "member")
        await ctx.db.commit()
        await ctx.prov("matter", matter.id)
        ctx.matters.append(matter)
        ctx.refs[it["ref"]] = {"type": "matter", "id": str(matter.id), "resolution": res.how}
        ctx.count("matters_created" if res.created else "matters_attached")
    if ctx.matters:
        await ms.refresh_matters(ctx.db, ctx.matters, ctx.now, ctx.owner)
        await ctx.db.commit()


# ----------------------------------------------------------------------------- objectives, directional dimensions, trajectory
def _okey(actor_id: UUID, text: str) -> str:
    return hashlib.sha1(f"{actor_id}|{_norm(text)[:80]}".encode()).hexdigest()[:20]


async def _constitution(ctx: _Ctx) -> None:
    c = ctx.delta.constitution
    if c is None or c.actor not in ctx.entities:
        return
    actor, toward = ctx.entities[c.actor], ctx.entities.get(c.toward or "")
    key = f"constitution:{actor.id}"
    row = (await ctx.db.execute(select(WorldObjective).where(
        WorldObjective.honcho_workspace_id == ctx.ws, WorldObjective.owner_peer_id == ctx.owner, WorldObjective.canonical_key == key))).scalars().first()
    if row is None:
        row = WorldObjective(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor.id, canonical_key=key, text=c.text, scope="constitutional",
                             toward_entity_id=toward.id if toward else None, strength=1.0, state="on_track", formation="explicit", confidence=1.0,
                             run_id=ctx.run.id)
    else:
        row.text, row.updated_at = c.text, ctx.now
    ctx.db.add(row)
    await ctx.db.commit()
    ctx.objectives["constitution"] = row
    await ctx.prov("objective", row.id)


async def _objectives(ctx: _Ctx) -> None:
    pending: List[Tuple[Any, WorldObjective]] = []
    for o in ctx.delta.objectives:
        if not _evidence_ok(ctx, o.ref, o.evidence):
            continue
        actor, toward = ctx.entities.get(o.actor), ctx.entities.get(o.toward or "")
        if actor is None:
            ctx.reject(o.ref, "actor_not_materialised")
            continue
        key = _okey(actor.id, o.text)
        row = (await ctx.db.execute(select(WorldObjective).where(
            WorldObjective.honcho_workspace_id == ctx.ws, WorldObjective.owner_peer_id == ctx.owner, WorldObjective.canonical_key == key,
            WorldObjective.status == "current"))).scalars().first()
        if row is None:
            row = WorldObjective(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor.id, canonical_key=key, text=o.text[:300],
                                 scope=o.scope, toward_entity_id=toward.id if toward else None, strength=o.strength, cause=o.cause, state=o.state,
                                 formation=epistemics.formation_class(o.formation), confidence=o.confidence, run_id=ctx.run.id,
                                 evidence_refs_json=json.dumps(o.evidence))
            ctx.count("objectives_created")
        else:
            row.state, row.strength, row.cause = o.state, o.strength, o.cause or row.cause
            row.evidence_refs_json = json.dumps(list(dict.fromkeys(json.loads(row.evidence_refs_json or "[]") + o.evidence)))
            row.updated_at = ctx.now
            ctx.count("objectives_updated")
        ctx.db.add(row)
        await ctx.db.flush()
        ctx.objectives[o.ref] = row
        pending.append((o, row))
        ctx.refs[o.ref] = {"type": "objective", "id": str(row.id)}
        await ctx.prov("objective", row.id)
    for o, row in pending:                                  # conflicts resolve once every objective of the delta has an id
        ids = [("constitution" if c == "constitution" else str(ctx.objectives[c].id)) for c in o.conflicts_with if c == "constitution" or c in ctx.objectives]
        row.conflicts_json = json.dumps(ids)
        ctx.db.add(row)
    await ctx.db.commit()


async def _derive_awareness(ctx: _Ctx) -> None:
    """Concealment implies an asymmetry that must never be assumed away: when the narrative says X is concealing something from Y (a relationship
    with a concealment entry), and no awareness facet exists for Y, record Y's awareness as 'not established' (inferred, evidence = the narrative's)."""
    for edge_id, entries in ctx.rel_entries.items():
        concealments = [e for e in entries if e.claim_kind == "concealment"]
        if not concealments:
            continue
        edge = ctx.rel_edges[edge_id]
        for entry in concealments:
            concealer = next((x for x in (edge.from_entity_id, edge.to_entity_id)
                              if (ctx.entities_by_id.get(x) is not None and ctx.entities_by_id[x].display_name == entry.holder_actor)), None)
            if concealer is None:                                  # holder is the model: the concealer is whoever the narrative text names first
                text = _norm(entry.claim)
                named = sorted(((text.find(_norm(ctx.entities_by_id[x].display_name)), x) for x in (edge.from_entity_id, edge.to_entity_id)
                                if ctx.entities_by_id.get(x) is not None and _norm(ctx.entities_by_id[x].display_name) in text))
                concealer = named[0][1] if named else None
            if concealer is None:
                continue
            other = edge.to_entity_id if concealer == edge.from_entity_id else edge.from_entity_id
            exists = (await ctx.db.execute(select(RelationshipDimension.id).where(
                RelationshipDimension.honcho_workspace_id == ctx.ws, RelationshipDimension.edge_id == edge.id, RelationshipDimension.from_entity_id == other,
                RelationshipDimension.dimension == "awareness", RelationshipDimension.superseded_by_id.is_(None)))).first()
            if exists:
                continue
            ctx.db.add(RelationshipDimension(
                honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, edge_id=edge.id, from_entity_id=other, to_entity_id=concealer, dimension="awareness",
                value="not established", formation="inferred", confidence=0.6, evidence_refs_json=entry.evidence_refs_json, run_id=ctx.run.id))
            ctx.count("awareness_derived")
    await ctx.db.commit()


async def _dimensions(ctx: _Ctx) -> None:
    for d in ctx.delta.dimensions:
        if not _evidence_ok(ctx, d.ref, d.evidence):
            continue
        edge, a, b = ctx.edges.get(d.relationship), ctx.entities.get(d.from_actor), ctx.entities.get(d.to_actor)
        if edge is None or a is None or b is None:
            ctx.reject(d.ref, "relationship_or_actor_not_materialised")
            continue
        about = ctx.events.get(d.about or "")
        formation = epistemics.formation_class(d.formation)
        stmt = select(RelationshipDimension).where(
            RelationshipDimension.honcho_workspace_id == ctx.ws, RelationshipDimension.edge_id == edge.id, RelationshipDimension.from_entity_id == a.id,
            RelationshipDimension.to_entity_id == b.id, RelationshipDimension.dimension == d.dimension, RelationshipDimension.superseded_by_id.is_(None))
        stmt = stmt.where(RelationshipDimension.about_event_id == about.id) if about else stmt.where(RelationshipDimension.about_event_id.is_(None))
        prior = (await ctx.db.execute(stmt)).scalars().first()
        if prior is not None and _norm(prior.value) == _norm(d.value):
            prior.evidence_refs_json = json.dumps(list(dict.fromkeys(json.loads(prior.evidence_refs_json or "[]") + d.evidence)))
            prior.confidence, prior.updated_at = max(prior.confidence, d.confidence), ctx.now
            ctx.db.add(prior)
            ctx.count("dimensions_confirmed")
            continue
        if prior is not None and epistemics.FORMATION_RANK[formation] < epistemics.FORMATION_RANK[epistemics.formation_class(prior.formation)]:
            ctx.reject(d.ref, "weaker_than_current_dimension")        # a lower-firmness candidate never replaces a firmer facet
            continue
        row = RelationshipDimension(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, edge_id=edge.id, from_entity_id=a.id, to_entity_id=b.id,
                                    dimension=d.dimension, value=d.value[:200], about_event_id=about.id if about else None, formation=formation,
                                    confidence=d.confidence, evidence_refs_json=json.dumps(d.evidence), run_id=ctx.run.id)
        ctx.db.add(row)
        await ctx.db.flush()
        if prior is not None:
            prior.superseded_by_id = row.id
            ctx.db.add(prior)
        await ctx.prov("dimension", row.id)
        ctx.count("dimensions_written")
    await ctx.db.commit()


def default_trajectory_note(actor: str, user: Optional[str], objective: WorldObjective, kinds: List[str]) -> str:
    """Deterministic interpretation used when no writer model is supplied. It reframes meaning and offers a plausible direction; it never scripts a line."""
    cause = f" ({objective.cause})" if objective.cause else ""
    target = f" toward {user}" if user else ""
    rupture = f" Recent {', '.join(sorted(set(kinds)))} is real and stays on the record." if kinds else ""
    return (f"{actor}'s current aim \"{objective.text}\"{cause} pulls against the relationship{target} that {actor} ultimately wants to protect.{rupture} "
            f"Read it as a reaction to what just happened rather than a change in what {actor} wants. A plausible movement is toward honesty or "
            f"reconnection, at a pace that fits {actor}'s fear and pride; nothing here requires an immediate confession or reconciliation.")


async def _reconcile(ctx: _Ctx, note_writer: Optional[Callable[..., Awaitable[str]]]) -> None:
    """Trajectory reconciler: compares the constitutional objective with active objectives and relational state. It never deletes an objective or
    edits a fact; it records an expiring, evidence-linked interpretation of the tension and a plausible way back."""
    const = ctx.objectives.get("constitution")
    if const is None:
        const = (await ctx.db.execute(select(WorldObjective).where(
            WorldObjective.honcho_workspace_id == ctx.ws, WorldObjective.owner_peer_id == ctx.owner, WorldObjective.scope == "constitutional"))).scalars().first()
    if const is None:
        return
    actor_ent = await ctx.db.get(Entity, const.actor_entity_id)
    user_ent = await ctx.db.get(Entity, const.toward_entity_id) if const.toward_entity_id else None
    rows = (await ctx.db.execute(select(WorldObjective).where(
        WorldObjective.honcho_workspace_id == ctx.ws, WorldObjective.owner_peer_id == ctx.owner, WorldObjective.actor_entity_id == const.actor_entity_id,
        WorldObjective.scope != "constitutional", WorldObjective.status == "current"))).scalars().all()
    tension = [o for o in rows if o.state in AT_RISK_STATES or "constitution" in json.loads(o.conflicts_json or "[]")]
    states = {o.state for o in rows}
    derived = "at_risk" if tension else ("drifting" if "drifting" in states else "on_track")
    const.state = derived
    const.updated_at = ctx.now
    ctx.db.add(const)
    if not tension or actor_ent is None:
        await ctx.db.commit()
        return
    kinds = sorted({e.claim_kind for es in ctx.rel_entries.values() for e in es if e.claim_kind in RELATIONAL_KINDS})
    target = max(tension, key=lambda o: o.strength)
    note = None
    if note_writer is not None:
        try:
            note = await note_writer({"actor": actor_ent.display_name, "user": user_ent.display_name if user_ent else None, "constitution": const.text,
                                      "objective": target.text, "cause": target.cause, "state": target.state, "relational_state": kinds})
        except Exception as exc:
            logger.warning("trajectory note writer failed open: %s", exc)
    note = (note or default_trajectory_note(actor_ent.display_name, user_ent.display_name if user_ent else None, target, kinds)).strip()
    for prior in (await ctx.db.execute(select(TrajectoryNote).where(
            TrajectoryNote.honcho_workspace_id == ctx.ws, TrajectoryNote.owner_peer_id == ctx.owner, TrajectoryNote.actor_entity_id == actor_ent.id,
            TrajectoryNote.superseded_by_id.is_(None)))).scalars().all():
        if _norm(prior.note) == _norm(note):
            prior.expires_at = ctx.now + TRAJECTORY_NOTE_TTL
            ctx.db.add(prior)
            await ctx.db.commit()
            return
    row = TrajectoryNote(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor_ent.id, objective_id=target.id, state=derived, note=note,
                         basis_json=json.dumps({"constitution": str(const.id), "objectives": [str(o.id) for o in tension],
                                                "relational_entries": [str(e.id) for es in ctx.rel_entries.values() for e in es if e.claim_kind in RELATIONAL_KINDS]}),
                         run_id=ctx.run.id, expires_at=ctx.now + TRAJECTORY_NOTE_TTL)
    ctx.db.add(row)
    await ctx.db.flush()
    for prior in (await ctx.db.execute(select(TrajectoryNote).where(
            TrajectoryNote.honcho_workspace_id == ctx.ws, TrajectoryNote.owner_peer_id == ctx.owner, TrajectoryNote.actor_entity_id == actor_ent.id,
            TrajectoryNote.superseded_by_id.is_(None), TrajectoryNote.id != row.id))).scalars().all():
        prior.superseded_by_id = row.id
        ctx.db.add(prior)
    await ctx.db.commit()
    await ctx.prov("trajectory_note", row.id)
    ctx.count("trajectory_notes")


# ----------------------------------------------------------------------------- entry point
def _ambiguous(delta: WorldDelta) -> List[Dict[str, Any]]:
    """Candidates that need epistemic judgement: interpretive or low-firmness ones. Obvious grounded facts never pay for a judge call."""
    msgs = {m.id: m.text for m in delta.source.messages}
    out = []
    for kind, group in (("claim", delta.claims), ("narrative", delta.narrative)):
        for item in group:
            interpretive = item.formation in ("inferred", "hypothesis") or kind == "narrative" or bool(getattr(item, "conflicts_with", []))
            if interpretive:
                out.append({"ref": item.ref, "type": kind, "text": item.text, "formation": item.formation,
                            "holder": item.holder, "kind": getattr(item, "kind", None),
                            "evidence": [msgs.get(e, "")[:400] for e in item.evidence]})
    return out


async def materialize(db: AsyncSession, delta: WorldDelta, *, now: Optional[datetime] = None, judge: Optional[Judge] = None,
                      adapter: Any = None, compile_snapshot: bool = True,
                      note_writer: Optional[Callable[..., Awaitable[str]]] = None) -> Dict[str, Any]:
    now_n = _naive(now)
    run = ProducerRun(
        honcho_workspace_id=delta.workspace_id, owner_peer_id=delta.owner, producer=delta.source.producer, model=delta.source.model,
        version=delta.source.version, external_run_id=delta.source.run_id,
        input_json=json.dumps({"session_id": delta.source.session_id, "message_ids": [m.id for m in delta.source.messages][:200]}),
        covered_through_json=json.dumps(delta.source.covered_through.model_dump() if delta.source.covered_through else {}))
    db.add(run)
    await db.commit()
    ctx = _Ctx(db, delta, run, now_n)
    verdicts: Dict[str, Dict[str, Any]] = {}
    ambiguous = _ambiguous(delta)
    if judge is not None and ambiguous:
        try:
            verdicts = await judge(ambiguous) or {}
            ctx.count("judged", len(ambiguous))
        except Exception as exc:  # judgement is an enhancement; candidates still ground deterministically and stay at their stated formation
            logger.warning("world judge failed open: %s", exc)
    await _actors(ctx)
    await _relationships(ctx)
    await _events(ctx)
    await _claims(ctx, verdicts)
    await _narrative(ctx, verdicts)
    await _commitments(ctx)
    await _conflicts(ctx)
    await _constitution(ctx)
    await _objectives(ctx)
    await _dimensions(ctx)
    await _derive_awareness(ctx)
    await _matters(ctx, adapter)
    await _reconcile(ctx, note_writer)
    snapshot_version = None
    if compile_snapshot:
        try:
            from src.services import world_model_service
            snap = await world_model_service.compile_world_model(
                db, workspace_id=delta.workspace_id, owner_peer_id=delta.owner, now=now_n, timezone_str="UTC",
                session_id=delta.source.session_id, force=True)
            snapshot_version = (snap.get("meta") or {}).get("version")
        except Exception as exc:
            logger.warning("snapshot compile after materialisation failed: %s", exc)
    run.counts_json = json.dumps({**ctx.counts, "rejected": len(ctx.rejected), "repaired": len(ctx.repaired)})
    db.add(run)
    await db.commit()
    return {"run_id": str(run.id), "counts": ctx.counts, "rejected": ctx.rejected, "repaired": ctx.repaired, "refs": ctx.refs,
            "covered_through": delta.source.covered_through.model_dump() if delta.source.covered_through else None,
            "snapshot_version": snapshot_version, "producer": delta.source.producer}
