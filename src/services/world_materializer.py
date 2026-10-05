"""Cortex materialiser for WorldDelta candidates (docs/WORLD_CONTRACT.md).

Pipeline: the interpreter's typed result -> deterministic grounding/provenance repair -> materialisation. This module makes no semantic judgement:
identity, continuity, objectives, dimensions, trajectory and the brief all arrive as the interpreter's decisions (docs/SEMANTIC_BOUNDARY_INVENTORY.md).
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
TRAJECTORY_NOTE_TTL = timedelta(hours=72)


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


MAX_RUN_MESSAGE_IDS = 2000      # the run's evidence ledger: coverage is computed from these ids, so they are stored whole
MAX_REJECTED_DETAIL = 40


class _Ctx:
    """Mutable state of one materialisation."""
    def __init__(self, db: AsyncSession, delta: WorldDelta, run: ProducerRun, now: datetime, constitution: Optional[Dict[str, str]] = None):
        self.db, self.delta, self.run, self.now = db, delta, run, now
        self.constitution = constitution or {}
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
        self.rel_edges: Dict[Any, Any] = {}
        self.counts: Dict[str, int] = {}
        self.superseded: List[Dict[str, str]] = []
        self.review_results: List[Dict[str, Any]] = []

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
        known = await _known(ctx, Entity, a.existing_id)
        if known is not None and known.frame_scope == ctx.owner:
            found[known.id] = known                      # the interpreter recognised an actor it was shown: identity is its decision
        for alias in ([] if found else names):
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


async def _known(ctx: _Ctx, model: Any, raw_id: Optional[str]) -> Optional[Any]:
    """Resolve an id the interpreter echoed from the world state it was shown. Mechanical: a malformed or foreign id simply resolves to nothing."""
    if not raw_id:
        return None
    try:
        row = await ctx.db.get(model, UUID(str(raw_id)))
    except (ValueError, TypeError):
        return None
    ws = getattr(row, "honcho_workspace_id", ctx.ws) if row is not None else None
    return row if row is not None and ws == ctx.ws else None


async def _relationships(ctx: _Ctx) -> None:
    from src.models.identity import RelationshipEdge
    for r in ctx.delta.relationships:
        if not _evidence_ok(ctx, r.ref, r.evidence):
            continue
        a, b = (ctx.entities.get(x) for x in r.actors)
        if a is None or b is None:
            ctx.reject(r.ref, "actor_not_materialised")
            continue
        edge, created = await _known(ctx, RelationshipEdge, r.existing_id), False
        if edge is None and not r.directional:            # the interpreter said A->B and B->A are the same relationship: one identity, either direction
            edge = await _edge_between(ctx, a.id, b.id, role=r.type)
        if edge is None:
            edge, created = await entity_service.get_or_create_edge(
                ctx.db, workspace_id=ctx.ws, from_entity_id=a.id, to_entity_id=b.id, role=r.type, message_id=r.evidence[0], confidence=r.confidence)
        ctx.rel_edges[edge.id] = edge
        ctx.edges[r.ref] = edge
        ctx.refs[r.ref] = {"type": "edge", "id": str(edge.id)}
        await ctx.prov("edge", edge.id)
        ctx.count("relationships_created" if created else "relationships_linked")



async def _events(ctx: _Ctx) -> None:
    for ev in ctx.delta.events:
        if not _evidence_ok(ctx, ev.ref, ev.evidence):
            continue
        parts = sorted(str(ctx.entities[p].id) for p in ev.participants if p in ctx.entities)
        key = hashlib.sha1(f"{_norm(ev.label)}|{_norm(ev.kind)}|{','.join(parts)}".encode()).hexdigest()[:20]
        holder_ref = _repair_holder(ctx, ev, ev.holder)
        assistant = ctx.delta.source.speaker_actors.get("assistant")
        event_formation = "hypothesis" if (ctx.delta.source.policy == "grounded" and assistant and holder_ref == assistant) else ev.formation
        if event_formation != ev.formation:
            ctx.count("assistant_assertions_downgraded")
        existing = (await ctx.db.execute(select(WorldEvent).where(
            WorldEvent.honcho_workspace_id == ctx.ws, WorldEvent.owner_peer_id == ctx.owner, WorldEvent.canonical_key == key,
            WorldEvent.superseded_by_id.is_(None)))).scalars().first()
        when = ev.when
        possible = None
        if existing is None and ev.same_as:
            existing = ctx.events.get(ev.same_as) or await _known(ctx, WorldEvent, ev.same_as)
            if existing is not None:
                ctx.count("events_merged_by_interpreter")
        if ev.possibly_same_as:
            possible = ctx.events.get(ev.possibly_same_as) or await _known(ctx, WorldEvent, ev.possibly_same_as)
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
                holder_actor=ctx.holder_name(holder_ref), formation=epistemics.formation_class(event_formation),
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
            claim_kind=claim_kind, open_kind=True, subject_entity_id=_subject_entity(ctx, subject), holder_actor=holder, direction="world",
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



async def _claims(ctx: _Ctx) -> None:
    for c in ctx.delta.claims:
        if not _evidence_ok(ctx, c.ref, c.evidence) or not _span_ok(ctx, c):
            continue
        formation = c.formation
        holder_ref = _repair_holder(ctx, c, c.holder)
        holder = ctx.holder_name(holder_ref)
        capped = _assistant_asserted(ctx, c, holder_ref)
        if capped:                                           # stays on the record as the companion's own statement, never as established fact
            formation = "hypothesis"
            ctx.count("assistant_assertions_downgraded")
        kind = c.kind or "assertion"
        entry = await _write(ctx, ref=c.ref, subject=c.subject, text=c.text, claim_kind=kind, holder=holder, formation=formation,
                             confidence=min(c.confidence, 0.3) if capped else c.confidence,
                             evidence=c.evidence, supersedes=c.supersedes, status="uncertain" if capped else None)
        if entry is not None:
            ctx.count("claims_written")


async def _attach_to_relationship(ctx: _Ctx, n: Any, entry: ModelEntry, holder: Optional[str]) -> None:
    """Relational narrative hangs under the shared relationship the interpreter pointed at (`about` names a relationship ref). No guessing."""
    edge = next((ctx.edges[a] for a in n.about if a in ctx.edges), None)
    if edge is None:
        return
    await ctx.link("model_entry", entry.id, "relationship", edge.id, "about")
    await ctx.db.commit()


async def _narrative(ctx: _Ctx) -> None:
    for n in ctx.delta.narrative:
        if not _evidence_ok(ctx, n.ref, n.evidence):
            continue
        subject = n.about[0] if n.about else None
        if subject is None:
            ctx.reject(n.ref, "narrative_without_subject")
            continue
        formation, confidence, kind = n.formation, n.confidence, n.kind
        if kind == "self_expression":                     # I9: rhetoric / performance is never a world claim, only a low-firmness perspective
            kind, formation, confidence = "perspective", "observed", min(confidence, SELF_EXPRESSION_CONFIDENCE_CAP)
        holder = ctx.holder_name(_repair_holder(ctx, n, n.holder))
        entry = await _write(ctx, ref=n.ref, subject=subject, text=n.text, claim_kind=kind, holder=holder, formation=formation,
                             confidence=confidence, evidence=n.evidence, status="uncertain" if kind == "perspective" and n.kind == "self_expression" else None)
        if entry is not None:
            ctx.count("narrative_written")
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
    """Whether something needs continuity (future behaviour depends on it) is a semantic judgement made by the interpreter and carried as
    `continuity_required` with a reason. Code resolves identity through the existing Matter resolver (nominate, bounded model judge) and stores."""
    from src.services import matter_service as ms
    from src.services.world_scope import resolve_scope
    items: List[Dict[str, Any]] = []
    for mc in ctx.delta.matter_candidates:
        if not _evidence_ok(ctx, mc.ref, mc.evidence):
            continue
        if not mc.continuity_required:
            ctx.reject(mc.ref, f"no_continuity_need:{(mc.continuity_reason or 'interpreter judged none')[:120]}")
            continue
        member_entries = [ctx.entries[m] for m in mc.members if m in ctx.entries]
        if not member_entries:
            ctx.reject(mc.ref, "matter_candidate_has_no_materialised_claim_members")
            continue
        kind = "relationship_situation" if mc.kind == "relationship_thread" else mc.kind
        actor_ids = {ctx.entities[a].id for a in mc.actors if a in ctx.entities}
        key = f"concept:{_slug(mc.concept)}"
        if kind == "relationship_situation" and len(actor_ids) == 2:        # identity rule: one relationship situation per related actor
            edge = await _edge_between(ctx, *list(actor_ids))
            if edge is not None:
                key = _relationship_matter_key(ctx, edge)
        items.append({"ref": mc.ref, "title": mc.display_title[:200], "kind": kind, "key": key, "entries": member_entries,
                      "events": [ctx.events[m] for m in mc.members if m in ctx.events], "actors": actor_ids,
                      "attach": mc.attach_to_existing_matter_id})
    if not items:
        return
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
    """The constitutional orientation is product-authored configuration supplied by the trusted caller, never extracted from dialogue."""
    c = ctx.constitution
    if not c or not c.get("text"):
        return
    actor = next((e for e in ctx.entities.values() if _norm(e.display_name) == _norm(c.get("actor", ""))), None)
    toward = next((e for e in ctx.entities.values() if _norm(e.display_name) == _norm(c.get("toward", ""))), None)
    if actor is None:
        return
    key = f"constitution:{actor.id}"
    row = (await ctx.db.execute(select(WorldObjective).where(
        WorldObjective.honcho_workspace_id == ctx.ws, WorldObjective.owner_peer_id == ctx.owner, WorldObjective.canonical_key == key))).scalars().first()
    if row is None:
        row = WorldObjective(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor.id, canonical_key=key, text=c["text"], scope="constitutional",
                             toward_entity_id=toward.id if toward else None, strength=1.0, state="unknown", formation="explicit", confidence=1.0,
                             run_id=ctx.run.id)
    elif row.text != c["text"]:
        row.text, row.updated_at = c["text"], ctx.now
    ctx.db.add(row)
    await ctx.db.commit()
    ctx.objectives["constitution"] = row
    await ctx.prov("objective", row.id)


async def _objectives(ctx: _Ctx) -> None:
    """Objective reconciliation is the interpreter's: it sees the current objectives (with ids) and says create / update / resolve. Code only
    resolves the ids, stores the typed result, and refuses to touch the constitutional objective."""
    pending: List[Tuple[Any, WorldObjective]] = []
    for o in ctx.delta.objectives:
        if not _evidence_ok(ctx, o.ref, o.evidence):
            continue
        actor, toward = ctx.entities.get(o.actor), ctx.entities.get(o.toward or "")
        if actor is None:
            ctx.reject(o.ref, "actor_not_materialised")
            continue
        row = None
        if o.op in ("update", "resolve"):
            row = await _known(ctx, WorldObjective, o.existing_id)
            if row is None or row.scope == "constitutional" or row.owner_peer_id != ctx.owner:
                ctx.reject(o.ref, "unknown_or_protected_objective")
                continue
        if row is None:
            row = WorldObjective(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor.id,
                                 canonical_key=hashlib.sha1(f"{actor.id}|{o.ref}|{ctx.run.id}".encode()).hexdigest()[:20], text=o.text[:300],
                                 scope=o.scope, toward_entity_id=toward.id if toward else None, strength=o.strength, cause=o.cause, state=o.state, durability=o.durability,
                                 formation=epistemics.formation_class(o.formation), confidence=o.confidence, run_id=ctx.run.id,
                                 evidence_refs_json=json.dumps(o.evidence))
            ctx.count("objectives_created")
        else:
            row.text, row.scope, row.state, row.strength = o.text[:300] or row.text, o.scope, o.state, o.strength
            row.durability = o.durability if o.durability != "unknown" else row.durability
            row.cause = o.cause or row.cause
            row.toward_entity_id = toward.id if toward else row.toward_entity_id
            row.evidence_refs_json = json.dumps(list(dict.fromkeys(json.loads(row.evidence_refs_json or "[]") + o.evidence)))
            row.updated_at = ctx.now
            ctx.count("objectives_updated")
        if o.op == "resolve" or o.state == "resolved":
            row.status, row.state = "resolved", "resolved"
            ctx.count("objectives_resolved")
        ctx.db.add(row)
        await ctx.db.flush()
        ctx.objectives[o.ref] = row
        pending.append((o, row))
        ctx.refs[o.ref] = {"type": "objective", "id": str(row.id)}
        await ctx.prov("objective", row.id)
    for o, row in pending:                                  # conflicts resolve once every objective of the delta has an id
        if o.conflicts_with is None:                        # the interpreter said nothing about conflicts: never erase what is recorded
            continue
        ids = []
        for c in o.conflicts_with:
            if c == "constitution":
                ids.append("constitution")
            elif c in ctx.objectives:
                ids.append(str(ctx.objectives[c].id))
            elif await _known(ctx, WorldObjective, c) is not None:
                ids.append(c)
        row.conflicts_json = json.dumps(ids)
        ctx.db.add(row)
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
        name = _slug(d.dimension).replace("-", "_") or "dimension"
        tier_durable = d.durability == "durable"          # promotion policy: a sustained reading may replace a facet of any tier; a moment or an unconfirmed reading never replaces a sustained one (they coexist)
        stmt = select(RelationshipDimension).where(
            RelationshipDimension.honcho_workspace_id == ctx.ws, RelationshipDimension.owner_peer_id == ctx.owner,
            (RelationshipDimension.durability != "durable") if not tier_durable else (RelationshipDimension.durability.is_not(None)), RelationshipDimension.from_entity_id == a.id,
            RelationshipDimension.to_entity_id == b.id, RelationshipDimension.dimension == name, RelationshipDimension.superseded_by_id.is_(None))
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
                                    dimension=name, value=d.value[:200], durability=d.durability, about_event_id=about.id if about else None, formation=formation,
                                    confidence=d.confidence, evidence_refs_json=json.dumps(d.evidence), run_id=ctx.run.id)
        ctx.db.add(row)
        await ctx.db.flush()
        if prior is not None:
            prior.superseded_by_id = row.id
            ctx.db.add(prior)
            ctx.superseded.append({"kind": "dimension", "id": str(prior.id), "by": str(row.id), "how": "same_key"})
        replaced = await _known(ctx, RelationshipDimension, d.supersedes)      # the interpreter says this replaces a known facet (state changed)
        if replaced is not None and replaced.owner_peer_id == ctx.owner and replaced.id != row.id and replaced.superseded_by_id is None:
            replaced.superseded_by_id = row.id
            ctx.db.add(replaced)
            ctx.count("dimensions_superseded_by_interpreter")
            ctx.superseded.append({"kind": "dimension", "id": str(replaced.id), "by": str(row.id), "how": "interpreter"})
        await ctx.prov("dimension", row.id)
        ctx.count("dimensions_written")
    await ctx.db.commit()


async def _reviews(ctx: _Ctx) -> None:
    """Record what became of each review verdict. A 'superseded'/'resolved' verdict whose replacement never arrived is surfaced as unapplied,
    never silently treated as either still-true or changed."""
    for r in ctx.delta.reviews:
        row, kind = None, None
        for model, k in ((RelationshipDimension, "dimension"), (WorldObjective, "objective")):
            row = await _known(ctx, model, r.id)
            if row is not None:
                kind = k
                break
        if row is None:
            ctx.review_results.append({"id": r.id, "status": r.status, "kind": None, "applied": False, "reason": "unknown_id"})
            continue
        if r.status == "superseded":
            applied = kind == "dimension" and row.superseded_by_id is not None
        elif r.status == "resolved":
            applied = kind == "objective" and row.status != "current"
        else:
            applied = True
        ctx.review_results.append({"id": r.id, "status": r.status, "kind": kind, "applied": applied, "note": (r.note or "")[:200]})
        if not applied:
            ctx.count("reviews_unapplied")


async def _trajectory(ctx: _Ctx) -> None:
    """Store the interpreter's trajectory assessments (expiring, evidence-linked interpretations) and the character-level state they imply.
    Code decides nothing about WHY someone is drifting or what a plausible path is: that text and state come from the interpreter."""
    for t in ctx.delta.trajectory:
        if not _evidence_ok(ctx, t.ref, t.evidence):
            continue
        actor = ctx.entities.get(t.actor)
        if actor is None:
            ctx.reject(t.ref, "actor_not_materialised")
            continue
        basis = []
        for o in t.objectives:
            row = ctx.objectives.get(o) or await _known(ctx, WorldObjective, o)
            if row is not None:
                basis.append(str(row.id))
        const = ctx.objectives.get("constitution")
        for prior in (await ctx.db.execute(select(TrajectoryNote).where(
                TrajectoryNote.honcho_workspace_id == ctx.ws, TrajectoryNote.owner_peer_id == ctx.owner, TrajectoryNote.actor_entity_id == actor.id,
                TrajectoryNote.superseded_by_id.is_(None)))).scalars().all():
            prior.expires_at = min(prior.expires_at or ctx.now, ctx.now)      # superseded below; expired now so it can never be shown again
            ctx.db.add(prior)
        row = TrajectoryNote(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, actor_entity_id=actor.id, state=t.state, note=t.note.strip(),
                             basis_json=json.dumps({"objectives": basis, "constitution": str(const.id) if const else None, "evidence": t.evidence}),
                             run_id=ctx.run.id, expires_at=ctx.now + TRAJECTORY_NOTE_TTL)
        ctx.db.add(row)
        await ctx.db.flush()
        for prior in (await ctx.db.execute(select(TrajectoryNote).where(
                TrajectoryNote.honcho_workspace_id == ctx.ws, TrajectoryNote.owner_peer_id == ctx.owner, TrajectoryNote.actor_entity_id == actor.id,
                TrajectoryNote.superseded_by_id.is_(None), TrajectoryNote.id != row.id))).scalars().all():
            prior.superseded_by_id = row.id
            ctx.db.add(prior)
        if const is not None and const.actor_entity_id == actor.id:
            const.state, const.updated_at = t.state, ctx.now
            ctx.db.add(const)
        await ctx.prov("trajectory_note", row.id)
        ctx.count("trajectory_notes")
    await ctx.db.commit()


async def _brief(ctx: _Ctx) -> None:
    from src.models.world import ContinuationBrief
    b = ctx.delta.brief
    if b is None or not b.text.strip():
        return
    row = ContinuationBrief(honcho_workspace_id=ctx.ws, owner_peer_id=ctx.owner, text=b.text.strip()[:2000],
                            lines_json=json.dumps([{"text": l.text, "refs": [ctx.refs.get(r, {}).get("id", r) for r in l.refs]} for l in b.lines]),
                            scene_json=json.dumps({"now": b.now, "unresolved": b.unresolved, "transient": b.transient, "changed": b.changed, "spent": b.spent,
                                                   "raw_turns": b.raw_turns, "raw_reason": b.raw_reason}),
                            producer=ctx.delta.source.producer, run_id=ctx.run.id)
    ctx.db.add(row)
    await ctx.db.flush()
    for prior in (await ctx.db.execute(select(ContinuationBrief).where(
            ContinuationBrief.honcho_workspace_id == ctx.ws, ContinuationBrief.owner_peer_id == ctx.owner,
            ContinuationBrief.superseded_by_id.is_(None), ContinuationBrief.id != row.id))).scalars().all():
        prior.superseded_by_id = row.id
        ctx.db.add(prior)
    await ctx.db.commit()
    await ctx.prov("continuation_brief", row.id)
    ctx.count("brief_written")




# ----------------------------------------------------------------------------- entry point
async def materialize(db: AsyncSession, delta: WorldDelta, *, now: Optional[datetime] = None,
                      adapter: Any = None, compile_snapshot: bool = True,
                      constitution: Optional[Dict[str, str]] = None, run: Optional[ProducerRun] = None) -> Dict[str, Any]:
    now_n = _naive(now)
    if run is None:
        run = ProducerRun(
            honcho_workspace_id=delta.workspace_id, owner_peer_id=delta.owner, producer=delta.source.producer, model=delta.source.model,
            version=delta.source.version, external_run_id=delta.source.run_id, status="running", started_at=now_n,
            input_json=json.dumps({"session_id": delta.source.session_id, "message_ids": [m.id for m in delta.source.messages][:MAX_RUN_MESSAGE_IDS]}),
            covered_through_json=json.dumps(delta.source.covered_through.model_dump() if delta.source.covered_through else {}))
        db.add(run)
    else:        # a run the caller opened (queued/leased): the delta fills in what it produced
        run.model, run.version, run.external_run_id, run.status = delta.source.model, delta.source.version, delta.source.run_id, "running"
        run.covered_through_json = json.dumps(delta.source.covered_through.model_dump() if delta.source.covered_through else {})
        db.add(run)
    await db.commit()
    ctx = _Ctx(db, delta, run, now_n, constitution)
    try:
        await _actors(ctx)
        await _relationships(ctx)
        await _events(ctx)
        await _claims(ctx)
        await _narrative(ctx)
        await _commitments(ctx)
        await _conflicts(ctx)
        await _constitution(ctx)
        await _objectives(ctx)
        await _dimensions(ctx)
        await _reviews(ctx)
        await _matters(ctx, adapter)
        await _trajectory(ctx)
        await _brief(ctx)
    except Exception as exc:
        # A run that did not finish is never left looking applied: its evidence stays uncovered so the next pass interprets it again.
        await db.rollback()
        failed = await db.get(ProducerRun, run.id)
        if failed is not None:
            failed.status, failed.finished_at = "failed", now_n
            failed.counts_json = json.dumps({**ctx.counts, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "rejected": len(ctx.rejected)})
            db.add(failed)
            await db.commit()
        exc.run_recorded = True      # the interpreter must not add a second failed row for this pass
        raise
    run.status, run.finished_at = "applied", now_n
    run.counts_json = json.dumps({**ctx.counts, "rejected": len(ctx.rejected), "repaired": len(ctx.repaired), "rejected_detail": ctx.rejected[:MAX_REJECTED_DETAIL]})
    db.add(run)
    await db.commit()          # applied BEFORE the snapshot compiles: the resident frontier is computed from applied runs
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
    return {"run_id": str(run.id), "counts": ctx.counts, "rejected": ctx.rejected, "repaired": ctx.repaired, "refs": ctx.refs,
            "superseded": ctx.superseded, "reviews": ctx.review_results,
            "covered_through": delta.source.covered_through.model_dump() if delta.source.covered_through else None,
            "snapshot_version": snapshot_version, "producer": delta.source.producer}
