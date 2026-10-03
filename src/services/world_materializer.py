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

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.identity import Entity, EntityAlias, EntityLink, ModelEntry
from src.models.world import ProducerRun, RowProvenance, WorldEvent, WorldLink
from src.schemas.world_delta import WorldDelta
from src.services import entity_service, epistemics

logger = logging.getLogger(__name__)

SELF_EXPRESSION_CONFIDENCE_CAP = 0.4
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
        ctx.refs[a.ref] = {"type": "entity", "id": str(ent.id)}
        await ctx.prov("entity", ent.id)
        ctx.count("actors_created" if created else "actors_linked")


async def _relationships(ctx: _Ctx) -> None:
    for r in ctx.delta.relationships:
        if not _evidence_ok(ctx, r.ref, r.evidence):
            continue
        a, b = (ctx.entities.get(x) for x in r.actors)
        if a is None or b is None:
            ctx.reject(r.ref, "actor_not_materialised")
            continue
        edge, created = await entity_service.get_or_create_edge(
            ctx.db, workspace_id=ctx.ws, from_entity_id=a.id, to_entity_id=b.id, role=r.type, message_id=r.evidence[0], confidence=r.confidence)
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
        existing = (await ctx.db.execute(select(WorldEvent).where(
            WorldEvent.honcho_workspace_id == ctx.ws, WorldEvent.owner_peer_id == ctx.owner, WorldEvent.canonical_key == key,
            WorldEvent.superseded_by_id.is_(None)))).scalars().first()
        when = ev.when
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


async def _claims(ctx: _Ctx, verdicts: Dict[str, Dict[str, Any]]) -> None:
    for c in ctx.delta.claims:
        if not _evidence_ok(ctx, c.ref, c.evidence) or not _span_ok(ctx, c):
            continue
        v = verdicts.get(c.ref, {})
        if v.get("action") == "reject":
            ctx.reject(c.ref, f"judge:{v.get('reason', 'rejected')}")
            continue
        formation = v.get("formation") or c.formation
        holder = ctx.holder_name(_repair_holder(ctx, c, c.holder))
        kind = "attribute" if c.predicate and c.subject in ctx.entities else "assertion"
        entry = await _write(ctx, ref=c.ref, subject=c.subject, text=c.text, claim_kind=kind, holder=holder, formation=formation,
                             confidence=c.confidence if v.get("action") != "downgrade" else min(c.confidence, 0.5), evidence=c.evidence,
                             supersedes=c.supersedes)
        if entry is not None:
            ctx.count("claims_written")


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


async def _matters(ctx: _Ctx, adapter: Any) -> None:
    if not ctx.delta.matter_candidates:
        return
    from src.services import matter_service as ms
    from src.services.world_scope import resolve_scope
    scope = await resolve_scope(ctx.db, ctx.ws, ctx.owner, ctx.sess)
    index = await ms.load_index(ctx.db, scope)
    for mc in ctx.delta.matter_candidates:
        if not _evidence_ok(ctx, mc.ref, mc.evidence):
            continue
        member_entries = [ctx.entries[m] for m in mc.members if m in ctx.entries]
        member_events = [ctx.events[m] for m in mc.members if m in ctx.events]
        if not member_entries:
            ctx.reject(mc.ref, "matter_candidate_has_no_materialised_claim_members")
            continue
        actor_ids = {ctx.entities[a].id for a in mc.actors if a in ctx.entities}
        kind = "relationship_situation" if mc.kind == "relationship_thread" else mc.kind
        key = f"concept:{_slug(mc.concept)}"
        if kind == "relationship_situation" and len(actor_ids) == 2:
            related = next((m for m in member_entries if m.subject_entity_id), None)
            if related is not None:
                key = f"relationship:{related.subject_entity_id}"      # one relationship situation per related actor (existing identity rule)
        anchor = member_entries[0]
        text = f"{mc.display_title}. " + " ".join(e.claim for e in member_entries[:6])
        ref = ms.PrimitiveRef("model_entry", anchor.id, anchor, mc.display_title[:200], text, kind, live=True, terminal=False,
                              touched_at=ctx.now, created_at=ctx.now, message_id=anchor.honcho_message_id, session_id=ctx.sess,
                              formation="inferred", confidence=0.7, key_hint=key, entity_ids=set(actor_ids), link_only=False)
        res = await ms.resolve_or_create_matter(ctx.db, ref, index, scope, now=ctx.now, adapter=adapter, allow_judge=adapter is not None, create=True)
        matter = res.matter
        if matter is None:
            ctx.reject(mc.ref, "matter_resolution_skipped")
            continue
        for i, entry in enumerate(member_entries):
            member = ms.PrimitiveRef("model_entry", entry.id, entry, entry.claim[:200], entry.claim, "other", live=False, terminal=False,
                                     touched_at=ctx.now, created_at=ctx.now, message_id=entry.honcho_message_id, session_id=ctx.sess,
                                     formation=entry.formation or "inferred", confidence=entry.confidence, link_only=True, entity_ids=set(actor_ids))
            await ms.attach(ctx.db, matter, member, index, how=res.how if i == 0 else "key")
        for ev in member_events:
            await ctx.link("event", ev.id, "matter", matter.id, "member")
        await ctx.db.commit()
        await ctx.prov("matter", matter.id)
        ctx.matters.append(matter)
        ctx.refs[mc.ref] = {"type": "matter", "id": str(matter.id), "resolution": res.how}
        ctx.count("matters_created" if res.created else "matters_attached")
    if ctx.matters:
        await ms.refresh_matters(ctx.db, ctx.matters, ctx.now, ctx.owner)
        await ctx.db.commit()


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
                      adapter: Any = None, compile_snapshot: bool = True) -> Dict[str, Any]:
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
    await _matters(ctx, adapter)
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
