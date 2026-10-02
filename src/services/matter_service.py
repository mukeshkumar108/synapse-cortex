"""Matter service: identity, lifecycle, links, relations, salience.

A Matter is a generic coherence layer over the specialised primitives
(docs/CORTEX_ARCHITECTURE.md §3). This module owns ONLY that layer:

* `resolve_or_create_matter` — identity/dedupe (never "one Matter per row")
* `sync_primitives` — the single idempotent step that resolves unlinked
  primitives into Matters, then refreshes lifecycle + salience components.
  It is the one write path used by session apply, the sweeper, WorldModel
  compilation and backfill.
* lifecycle derived from linked primitives (never invented)
* inspectable salience components (never one opaque score)

Specialised primitives keep their semantics: Expectation owns outcome state,
OpenLoop owns unresolved-loop state, RecurringIntention owns recurrence,
WorkItem owns executable work. A Matter only reads them.

No keyword matching assigns meaning: kind comes from the source primitive's
structured type (and structured DomainAnnotation tags); identity comes from
links, lineage, semantic relations, canonical keys, entity overlap and
bounded semantic judgement.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.matter import (
    MATTER_KINDS, MATTER_RELATIONS, Matter, MatterLink, MatterRelation,
)
from src.services.world_scope import Scope, resolve_scope

logger = logging.getLogger(__name__)

# --- policy constants (documented, not tuned per scenario) -------------------
RECENT_TERMINAL_DAYS = 14        # a recently settled primitive may still found a (resolved) Matter
HISTORY_HORIZON_DAYS = 120       # older terminal primitives never found Matters
DORMANT_AFTER_DAYS = 21          # no live primitive and untouched this long -> dormant
ARCHIVE_RESOLVED_AFTER_DAYS = 90
ARCHIVE_DORMANT_AFTER_DAYS = 180
SYNC_LIMIT_PER_TYPE = 400
JUDGE_BUDGET_PER_SYNC = 6

SAME_MATTER_RELATIONS = frozenset({
    "same_as", "refines", "supersedes", "resolves", "fulfils",
    "partially_fulfils", "reopens",
})
STRUCTURAL_RELATIONS = {"part_of": "part_of", "depends_on": "depends_on"}

# Kind refinement: a Matter's kind may only move to a more specific kind.
_KIND_SPECIFICITY = {
    "other": 0, "topic": 1, "goal": 2, "project": 2, "routine": 2,
    "life_situation": 3, "concern": 3, "relationship_situation": 3,
}


def _naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _now(now: Optional[datetime]) -> datetime:
    return _naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)


def _tokens(text: str) -> Set[str]:
    from src.services.lifecycle_service import LifecycleService
    return LifecycleService._significant_tokens(text or "")


def token_key(title: str) -> str:
    """Canonical key: sorted significant tokens. Empty when too thin to be an
    identity on its own (<2 tokens)."""
    toks = sorted(_tokens(title))
    return "-".join(toks[:8]) if len(toks) >= 2 else ""


def _hash(text: str) -> str:
    from src.models.semantic import content_hash_for
    return content_hash_for(text)


# ============================================================================
# Primitive adapters: structured state of each source primitive type
# ============================================================================

def _models() -> Dict[str, Any]:
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.domain_annotation import DomainAnnotation
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.models.identity import ModelEntry
    from src.models.open_loop import OpenLoop
    from src.models.operational_state import RecurringIntention
    from src.models.work_item import WorkItem
    return {
        "expectation": Expectation, "open_loop": OpenLoop,
        "recurrence": RecurringIntention, "commitment": CommitmentCandidate,
        "work_item": WorkItem, "domain_annotation": DomainAnnotation,
        "fact": Fact, "model_entry": ModelEntry,
    }


@dataclass
class PrimitiveRef:
    object_type: str
    object_id: UUID
    row: Any
    title: str
    text: str
    kind: str
    live: bool
    terminal: bool
    touched_at: datetime
    created_at: datetime
    message_id: Optional[str] = None
    candidate_key: Optional[str] = None
    session_id: Optional[str] = None
    formation: str = "inferred"
    confidence: float = 0.7
    key_hint: Optional[str] = None
    entity_ids: Set[UUID] = field(default_factory=set)
    related: List[Tuple[str, UUID]] = field(default_factory=list)
    link_only: bool = False          # may attach to an existing Matter, never found one
    importance: Optional[float] = None

    @property
    def canonical_key(self) -> str:
        return self.key_hint or token_key(self.title)


def _val(x: Any) -> str:
    return str(getattr(x, "value", x) or "").lower()


def describe(object_type: str, row: Any, now: datetime) -> Optional[PrimitiveRef]:
    """Structured read of one primitive. Returns None when the row can never
    found or join a Matter (e.g. app-owned source-linked tasks, superseded)."""
    created = _naive(getattr(row, "created_at", None)) or now
    touched = _naive(getattr(row, "updated_at", None)) or created
    recent_cut = now - timedelta(days=RECENT_TERMINAL_DAYS)
    horizon_cut = now - timedelta(days=HISTORY_HORIZON_DAYS)

    def finish(ref: PrimitiveRef) -> Optional[PrimitiveRef]:
        if ref.terminal and ref.touched_at < horizon_cut:
            return None
        if ref.terminal and ref.touched_at < recent_cut:
            ref.link_only = True
        return ref

    if object_type == "expectation":
        if getattr(row, "source_system", None) or getattr(row, "superseded_by_id", None):
            return None
        outcome = _val(row.outcome_state)
        etype = _val(row.expectation_type)
        kind = {"planned_event": "life_situation", "user_intention": "goal",
                "user_commitment": "goal"}.get(etype, "topic")
        return finish(PrimitiveRef(
            "expectation", row.id, row, row.title, f"{row.title}. {row.summary}", kind,
            live=outcome == "unknown",
            terminal=outcome in ("fulfilled", "cancelled", "superseded"),
            touched_at=touched, created_at=created, message_id=row.honcho_message_id,
            candidate_key=row.candidate_key, session_id=row.honcho_session_id,
            formation=row.formation or "explicit", confidence=row.extraction_confidence))
    if object_type == "open_loop":
        status = _val(row.status)
        return finish(PrimitiveRef(
            "open_loop", row.id, row, row.title, f"{row.title}. {row.summary}", "topic",
            live=status == "open",
            terminal=status in ("resolved", "abandoned", "superseded", "expired"),
            touched_at=touched, created_at=created, message_id=row.honcho_message_id,
            candidate_key=row.candidate_key, session_id=row.honcho_session_id,
            formation="explicit" if row.invited else "inferred",
            related=[("expectation", row.expectation_id)] if row.expectation_id else []))
    if object_type == "recurrence":
        if getattr(row, "superseded_by_id", None):
            return None
        status = _val(row.status)
        return finish(PrimitiveRef(
            "recurrence", row.id, row, row.title, row.title,
            "goal" if _val(row.semantic_type) == "measurable_goal" else "routine",
            live=status == "active",
            terminal=status in ("completed", "cancelled", "superseded"),
            touched_at=touched, created_at=created, message_id=row.honcho_message_id,
            candidate_key=row.candidate_key, session_id=row.honcho_session_id,
            formation="inferred" if _val(row.semantic_type) == "observed_pattern" else "explicit",
            confidence=row.confidence, key_hint=f"routine:{row.canonical_key}"))
    if object_type == "commitment":
        status = _val(row.status)
        system_promise = row.evidence_class == "character_promise"
        return finish(PrimitiveRef(
            "commitment", row.id, row, row.title, f"{row.title}. {row.notes or ''}".strip(),
            "topic" if system_promise else "goal",
            live=status in ("pending", "materialized"),
            terminal=status in ("dismissed", "expired", "violated", "fulfilled"),
            touched_at=touched, created_at=created, message_id=row.source_message_id,
            candidate_key=row.candidate_key, session_id=row.honcho_session_id,
            formation="explicit" if _val(row.authority) == "act" else "inferred"))
    if object_type == "work_item":
        status = _val(row.status)
        related: List[Tuple[str, UUID]] = []
        try:
            related.append(("*", UUID(str(row.parent_id))))
        except (ValueError, TypeError):
            pass
        return finish(PrimitiveRef(
            "work_item", row.id, row, row.parent_title or row.action,
            f"{row.parent_title or ''}. {row.action}", "other",
            live=status in ("proposed", "surfaced", "in_progress"),
            terminal=status in ("done", "cancelled", "superseded"),
            touched_at=touched, created_at=created, message_id=None,
            session_id=row.honcho_session_id, importance=row.importance,
            formation="inferred", related=related))
    if object_type == "domain_annotation":
        kind = kind_for_annotation(_val(row.domain), _val(row.category))
        return PrimitiveRef(
            "domain_annotation", row.id, row, row.annotation_summary[:200],
            row.annotation_summary, kind or "other", live=True, terminal=False,
            touched_at=touched, created_at=created, message_id=row.honcho_message_id,
            candidate_key=row.candidate_key, session_id=row.honcho_session_id,
            formation="inferred", link_only=kind is None)
    if object_type == "fact":
        return PrimitiveRef(
            "fact", row.id, row, row.title, f"{row.title}. {row.evidence_verbatim}",
            "other", live=False, terminal=False, touched_at=touched, created_at=created,
            message_id=row.honcho_message_id, candidate_key=row.candidate_key,
            session_id=row.honcho_session_id, formation=row.formation or "explicit",
            confidence=row.confidence, link_only=True)
    if object_type == "model_entry":
        if getattr(row, "superseded_by_id", None):
            return None
        ref = PrimitiveRef(
            "model_entry", row.id, row, row.claim[:200], row.claim, "other",
            live=False, terminal=False, touched_at=touched, created_at=created,
            message_id=row.honcho_message_id, session_id=row.honcho_session_id,
            formation=row.formation or "inferred", confidence=row.confidence,
            link_only=True)
        if getattr(row, "subject_matter_id", None):
            ref.related = [("matter", row.subject_matter_id)]
        elif row.model_kind == "relationship" and row.subject_entity_id \
                and _val(getattr(row, "holder_actor", None)) != "system":
            # One relationship situation per related entity: structured identity.
            ref.kind = "relationship_situation"
            ref.key_hint = f"relationship:{row.subject_entity_id}"
            ref.link_only = False
            ref.entity_ids = {row.subject_entity_id}
        return ref
    return None


def kind_for_annotation(domain: str, category: str) -> Optional[str]:
    """Structured DomainAnnotation tags -> Matter kind. None = the annotation
    alone does not found a Matter (wins/jokes/preferences just attach)."""
    if category in ("struggle", "fear"):
        return "relationship_situation" if domain in ("relationship", "family") else "concern"
    if category == "hope" or domain == "goal":
        return "goal"
    if domain in ("decision", "emotional_landmark"):
        return "life_situation"
    return None


# ============================================================================
# Index (in-memory, per sync pass; the DB stays authoritative)
# ============================================================================

_TITLE_ATTRS = {
    "expectation": ("title", "summary"), "open_loop": ("title", "summary"),
    "recurrence": ("title",), "commitment": ("title",), "work_item": ("parent_title", "action"),
    "fact": ("title",), "model_entry": ("claim",), "domain_annotation": ("annotation_summary",),
}


class MatterIndex:
    def __init__(self) -> None:
        self.matters: Dict[UUID, Matter] = {}
        self.link_map: Dict[Tuple[str, UUID], UUID] = {}
        self.by_object_id: Dict[UUID, UUID] = {}
        self.key_map: Dict[str, UUID] = {}
        self.tokens: Dict[UUID, Set[str]] = {}
        self.entity_map: Dict[UUID, Set[UUID]] = {}
        self.hash_map: Dict[str, Set[UUID]] = {}
        self.names: Dict[UUID, Set[str]] = {}
        self.samples: Dict[UUID, List[str]] = {}   # a few member texts, for judge context

    def add_matter(self, m: Matter) -> None:
        self.matters[m.id] = m
        if m.canonical_key:
            self.key_map.setdefault(m.canonical_key, m.id)
        self.tokens.setdefault(m.id, set()).update(_tokens(m.title))
        self.hash_map.setdefault(_hash(m.title), set()).add(m.id)

    def add_link(self, matter_id: UUID, object_type: str, object_id: UUID,
                 texts: Iterable[str] = ()) -> None:
        self.link_map[(object_type, object_id)] = matter_id
        self.by_object_id[object_id] = matter_id
        for t in texts:
            if t:
                self.tokens.setdefault(matter_id, set()).update(_tokens(t))
                self.hash_map.setdefault(_hash(t), set()).add(matter_id)
        first = next((t for t in texts if t), None)
        samples = self.samples.setdefault(matter_id, [])
        if first and first not in samples and len(samples) < 3:
            samples.append(first[:120])

    def describe_matter(self, matter_id: UUID) -> str:
        m = self.matters[matter_id]
        extra = [s for s in self.samples.get(matter_id, []) if s != m.title][:2]
        return "; ".join([m.title] + extra)[:300]

    def add_entity(self, matter_id: UUID, entity_id: UUID) -> None:
        self.entity_map.setdefault(entity_id, set()).add(matter_id)

    def resolve_merged(self, matter_id: UUID) -> UUID:
        seen = set()
        while matter_id in self.matters and self.matters[matter_id].merged_into_id \
                and matter_id not in seen:
            seen.add(matter_id)
            matter_id = self.matters[matter_id].merged_into_id
        return matter_id


def _matter_scope_clause(scope: Scope):
    if scope.owner_peer_id:
        return Matter.owner_peer_id == scope.owner_peer_id
    return Matter.owner_peer_id.is_(None)


async def load_index(db: AsyncSession, scope: Scope) -> MatterIndex:
    from src.models.identity import Entity, EntityLink
    index = MatterIndex()
    matters = (await db.execute(select(Matter).where(
        Matter.honcho_workspace_id == scope.workspace_id,
        _matter_scope_clause(scope),
        Matter.merged_into_id.is_(None),
        Matter.status != "archived"))).scalars().all()
    for m in matters:
        index.add_matter(m)
    if not matters:
        return index
    ids = [m.id for m in matters]
    links = (await db.execute(select(MatterLink).where(MatterLink.matter_id.in_(ids)))).scalars().all()
    by_type: Dict[str, List[UUID]] = {}
    for link in links:
        by_type.setdefault(link.object_type, []).append(link.object_id)
    models = _models()
    titles: Dict[UUID, List[str]] = {}
    for otype, oids in by_type.items():
        model, attrs = models.get(otype), _TITLE_ATTRS.get(otype)
        if not model or not attrs:
            continue
        for row in (await db.execute(select(model).where(model.id.in_(oids)))).scalars().all():
            titles[row.id] = [str(getattr(row, a, "") or "") for a in attrs]
            if len(attrs) > 1:
                titles[row.id].append(" ".join(titles[row.id]))
    for link in links:
        index.add_link(link.matter_id, link.object_type, link.object_id,
                       titles.get(link.object_id, ()))
    for el in (await db.execute(select(EntityLink).where(
            EntityLink.object_type == "matter", EntityLink.object_id.in_(ids)))).scalars().all():
        index.add_entity(el.object_id, el.entity_id)
    ent_ids = list(index.entity_map)
    if ent_ids:
        for e in (await db.execute(select(Entity).where(Entity.id.in_(ent_ids)))).scalars().all():
            index.names[e.id] = _tokens(e.display_name)
    return index


async def _entity_ids_for(db: AsyncSession, workspace_id: str, object_type: str,
                          object_ids: List[UUID]) -> Dict[UUID, Set[UUID]]:
    from src.models.identity import EntityLink
    out: Dict[UUID, Set[UUID]] = {}
    if not object_ids:
        return out
    for el in (await db.execute(select(EntityLink).where(
            EntityLink.honcho_workspace_id == workspace_id,
            EntityLink.object_type == object_type,
            EntityLink.object_id.in_(object_ids)))).scalars().all():
        out.setdefault(el.object_id, set()).add(el.entity_id)
    return out


# ============================================================================
# Identity: resolve_or_create_matter
# ============================================================================

@dataclass
class Resolution:
    matter: Optional[Matter]
    how: str            # link|lineage|relation|key|entity|judge|created|skipped
    created: bool = False
    # Matter<->Matter edges discovered while resolving (applied by the caller).
    edges: List[Tuple[str, UUID]] = field(default_factory=list)


async def _lineage_matter(db: AsyncSession, ref: PrimitiveRef, index: MatterIndex) -> Optional[UUID]:
    """Matter of an explicitly related / superseding / sibling primitive."""
    for rtype, rid in ref.related:
        if rtype == "matter":
            mid = index.resolve_merged(rid)
            if mid in index.matters:
                return mid
        elif rtype == "*":
            if rid in index.by_object_id:
                return index.resolve_merged(index.by_object_id[rid])
        elif (rtype, rid) in index.link_map:
            return index.resolve_merged(index.link_map[(rtype, rid)])
    models = _models()
    # Supersession lineage (predecessor/successor) for expectations/recurrences.
    for otype in ("expectation", "recurrence"):
        if ref.object_type != otype:
            continue
        model = models[otype]
        preds = (await db.execute(select(model.id).where(
            model.superseded_by_id == ref.object_id))).scalars().all()
        succ = getattr(ref.row, "superseded_by_id", None)
        for oid in list(preds) + ([succ] if succ else []):
            if (otype, oid) in index.link_map:
                return index.resolve_merged(index.link_map[(otype, oid)])
    # Same (message, candidate) siblings: annotations/facts share the candidate
    # that produced the primitive.
    if ref.object_type in ("domain_annotation", "fact") and ref.message_id:
        for otype in ("expectation", "open_loop", "commitment", "fact"):
            if otype == ref.object_type:
                continue
            model = models[otype]
            mcol = "source_message_id" if otype == "commitment" else "honcho_message_id"
            ws = ref.row.honcho_workspace_id
            rows = (await db.execute(select(model.id).where(
                model.honcho_workspace_id == ws,
                getattr(model, mcol) == ref.message_id,
                model.candidate_key == (ref.candidate_key or "primary")))).scalars().all()
            for oid in rows:
                if (otype, oid) in index.link_map:
                    return index.resolve_merged(index.link_map[(otype, oid)])
    return None


async def _relation_matches(db: AsyncSession, ref: PrimitiveRef,
                            index: MatterIndex) -> Tuple[Set[UUID], List[Tuple[str, UUID]]]:
    """Existing semantic relations (reified claims) between this primitive's
    text and text already in a Matter. same-matter relations return Matters to
    join; part_of/depends_on return Matter-relation edges to record."""
    from src.models.semantic import RelationStatus, SemanticClaim, SemanticRelation
    hashes = {_hash(ref.title), _hash(ref.text)}
    ws = ref.row.honcho_workspace_id
    claim_rows = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == ws,
        SemanticClaim.content_hash.in_(hashes)))).scalars().all()
    if not claim_rows:
        return set(), []
    mine = {c.id for c in claim_rows}
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == ws,
        SemanticRelation.status == RelationStatus.ACTIVE,
        (SemanticRelation.from_claim_id.in_(mine)) | (SemanticRelation.to_claim_id.in_(mine))
    ))).scalars().all()
    same: Set[UUID] = set()
    structural: List[Tuple[str, UUID]] = []
    for rel in rels:
        other_hash = rel.to_content_hash if rel.from_claim_id in mine else rel.from_content_hash
        for mid in index.hash_map.get(other_hash, ()):
            mid = index.resolve_merged(mid)
            rtype = _val(rel.rel_type)
            if rtype in SAME_MATTER_RELATIONS:
                same.add(mid)
            elif rtype in STRUCTURAL_RELATIONS:
                structural.append((STRUCTURAL_RELATIONS[rtype], mid))
    return same, structural


async def _entity_candidates(ref: PrimitiveRef, index: MatterIndex):
    cands: Set[UUID] = set()
    for eid in ref.entity_ids:
        cands |= {index.resolve_merged(m) for m in index.entity_map.get(eid, ())}
    names: Set[str] = set()
    for eid in ref.entity_ids:
        names |= index.names.get(eid, set())
    return cands, names


def _newest(index: MatterIndex, ids: Iterable[UUID]) -> Optional[UUID]:
    pool = [i for i in ids if i in index.matters]
    return max(pool, key=lambda i: index.matters[i].last_touched) if pool else None


async def resolve_or_create_matter(
    db: AsyncSession, ref: PrimitiveRef, index: MatterIndex, scope: Scope, *,
    now: datetime, adapter: Any = None, allow_judge: bool = False,
    judge_budget: Optional[List[int]] = None, create: bool = True,
) -> Resolution:
    """Resolve the real-world Matter a primitive belongs to, creating one only
    when nothing existing fits. Order (most to least specific):

      1 existing link for this object        4 exact canonical key
      2 lineage (related/superseded/sibling) 5 entity overlap + non-name content overlap
      3 semantic relations (same-matter)     6 bounded semantic judgement (ambiguous only)

    Under-merging is repairable (`merge_matters`); over-merging corrupts, so
    ambiguity defaults to creating a separate Matter plus a `related_to` edge.
    """
    key = (ref.object_type, ref.object_id)
    if key in index.link_map:
        return Resolution(index.matters.get(index.resolve_merged(index.link_map[key])), "link")

    mid = await _lineage_matter(db, ref, index)
    if mid is not None:
        return Resolution(index.matters[mid], "lineage")

    same, structural = await _relation_matches(db, ref, index)
    edges: List[Tuple[str, UUID]] = list(structural)
    if same:
        return Resolution(index.matters[_newest(index, same)], "relation", edges=edges)

    ckey = ref.canonical_key
    if ckey and ckey in index.key_map:
        mid = index.resolve_merged(index.key_map[ckey])
        if mid in index.matters:
            return Resolution(index.matters[mid], "key", edges=edges)

    cands, name_tokens = await _entity_candidates(ref, index)
    if cands:
        new_tokens = _tokens(ref.text) - name_tokens
        scored = []
        for cid in cands:
            if cid not in index.matters:
                continue
            shared = (index.tokens.get(cid, set()) - name_tokens) & new_tokens
            if shared:
                scored.append((len(shared), cid))
        scored.sort(key=lambda t: -t[0])
        if len(scored) == 1 or (len(scored) > 1 and scored[0][0] > scored[1][0]):
            return Resolution(index.matters[scored[0][1]], "entity", edges=edges)
        if scored:  # ambiguous between >=2 equally-overlapping Matters
            ambiguous = [cid for _, cid in scored[:3]]
            judged = await _judge_candidates(ref, index, ambiguous, adapter, allow_judge, judge_budget)
            if judged is not None:
                return Resolution(index.matters[judged], "judge", edges=edges)
            edges += [("related_to", cid) for cid in ambiguous]
        else:  # same actor, disjoint content: ask the bounded judge, else a distinct Matter
            recent = sorted((i for i in cands if i in index.matters),
                            key=lambda i: index.matters[i].last_touched, reverse=True)[:2]
            judged = await _judge_candidates(ref, index, recent, adapter, allow_judge, judge_budget)
            if judged is not None:
                return Resolution(index.matters[judged], "judge", edges=edges)
            edges += [("related_to", cid) for cid in recent]
    elif allow_judge and adapter is not None:
        pool = [m for m, toks in index.tokens.items()
                if m in index.matters and len(toks & _tokens(ref.text)) >= 2]
        judged = await _judge_candidates(ref, index, pool[:3], adapter, allow_judge, judge_budget)
        if judged is not None:
            return Resolution(index.matters[judged], "judge", edges=edges)

    if not create:
        return Resolution(None, "skipped")
    matter = await _create_matter(db, ref, scope, now)
    index.add_matter(matter)
    return Resolution(matter, "created", created=True, edges=edges)


async def _judge_candidates(ref: PrimitiveRef, index: MatterIndex, candidates: List[UUID],
                            adapter: Any, allow: bool, budget: Optional[List[int]]) -> Optional[UUID]:
    if not (allow and adapter is not None and candidates):
        return None
    from src.services import semantic_judge
    accepted = []
    for cid in candidates:
        if budget is not None:
            if budget[0] <= 0:
                break
            budget[0] -= 1
        result = await semantic_judge.judge(
            kind="same_matter", earlier=index.describe_matter(cid), later=ref.text, adapter=adapter)
        if result is not None:
            accepted.append(cid)
    # Exactly one accepted verdict, else still ambiguous: stay separate.
    return accepted[0] if len(accepted) == 1 else None


async def _create_matter(db: AsyncSession, ref: PrimitiveRef, scope: Scope, now: datetime) -> Matter:
    kind = ref.kind if ref.kind in MATTER_KINDS else "other"
    first = min(ref.created_at, now)
    matter = Matter(
        honcho_workspace_id=scope.workspace_id, owner_peer_id=scope.owner_peer_id,
        kind=kind, title=ref.title[:200], canonical_key=ref.canonical_key,
        status="active" if ref.live or not ref.terminal else "resolved",
        first_seen=first, active_since=first, last_touched=ref.touched_at,
        confidence=ref.confidence,
        formation="explicit" if _firm(ref.formation) else "inferred",
        origin_session_id=ref.session_id, origin_message_id=ref.message_id,
        last_touched_session_id=ref.session_id)
    db.add(matter)
    await db.flush()
    return matter


def _firm(formation: Any) -> bool:
    from src.services.epistemics import is_firm
    return is_firm(formation)


async def attach(db: AsyncSession, matter: Matter, ref: PrimitiveRef, index: MatterIndex,
                 *, how: str, role: str = "subject") -> bool:
    """Idempotently link a primitive (and its entities) to a Matter and fold
    its touch into the Matter. Returns True when a new link was written."""
    key = (ref.object_type, ref.object_id)
    created = False
    if key not in index.link_map:
        db.add(MatterLink(
            honcho_workspace_id=matter.honcho_workspace_id, matter_id=matter.id,
            object_type=ref.object_type, object_id=ref.object_id, role=role,
            confidence=1.0 if how in ("link", "lineage", "created", "key") else 0.7,
            provenance_message_id=ref.message_id))
        index.add_link(matter.id, ref.object_type, ref.object_id, (ref.title, ref.text))
        created = True
    matter.last_touched = max(matter.last_touched, ref.touched_at)
    if ref.session_id:
        matter.last_touched_session_id = ref.session_id
    if (ref.kind in MATTER_KINDS
            and (not ref.link_only or ref.object_type == "domain_annotation")
            and _KIND_SPECIFICITY.get(ref.kind, 0) > _KIND_SPECIFICITY.get(matter.kind, 0)):
        matter.kind = ref.kind  # kinds only ever refine toward more specific
    if _firm(ref.formation):
        matter.formation = "explicit"
    matter.confidence = max(matter.confidence, ref.confidence)
    if not matter.canonical_key and ref.canonical_key:
        matter.canonical_key = ref.canonical_key
        index.key_map.setdefault(ref.canonical_key, matter.id)
    matter.updated_at = _now(None)
    db.add(matter)
    for eid in ref.entity_ids:
        await link_entity_to_matter(db, matter, eid, index, message_id=ref.message_id)
    return created


async def link_entity_to_matter(db: AsyncSession, matter: Matter, entity_id: UUID,
                                index: Optional[MatterIndex] = None, *, role: str = "subject",
                                confidence: float = 0.7, message_id: Optional[str] = None) -> bool:
    """Entity <-> Matter via the existing EntityLink machinery."""
    from src.models.identity import Entity, EntityLink
    if index is not None and matter.id in index.entity_map.get(entity_id, ()):
        return False
    exists = (await db.execute(select(EntityLink.id).where(
        EntityLink.object_type == "matter", EntityLink.object_id == matter.id,
        EntityLink.entity_id == entity_id))).first()
    if exists is None:
        db.add(EntityLink(honcho_workspace_id=matter.honcho_workspace_id,
                          object_type="matter", object_id=matter.id, role=role,
                          entity_id=entity_id, confidence=confidence,
                          provenance_message_id=message_id))
    if index is not None:
        index.add_entity(matter.id, entity_id)
        if entity_id not in index.names:
            ent = await db.get(Entity, entity_id)
            index.names[entity_id] = _tokens(ent.display_name) if ent else set()
    return exists is None


async def add_matter_relation(db: AsyncSession, workspace_id: str, from_id: UUID, to_id: UUID,
                              rel_type: str, *, formation: str = "inferred",
                              confidence: float = 0.7, evidence: Optional[List[str]] = None) -> Optional[MatterRelation]:
    """Matter <-> Matter relation. Vocabulary is bounded (related_to|part_of|depends_on)."""
    if rel_type not in MATTER_RELATIONS:
        raise ValueError(f"matter relation {rel_type!r} not in {sorted(MATTER_RELATIONS)}")
    if from_id == to_id:
        return None
    existing = (await db.execute(select(MatterRelation).where(
        MatterRelation.honcho_workspace_id == workspace_id,
        MatterRelation.from_matter_id == from_id, MatterRelation.to_matter_id == to_id,
        MatterRelation.rel_type == rel_type))).scalars().first()
    if existing is not None:
        return existing
    if rel_type == "related_to":  # symmetric: store one direction only
        rev = (await db.execute(select(MatterRelation).where(
            MatterRelation.from_matter_id == to_id, MatterRelation.to_matter_id == from_id,
            MatterRelation.rel_type == "related_to"))).scalars().first()
        if rev is not None:
            return rev
    rel = MatterRelation(honcho_workspace_id=workspace_id, from_matter_id=from_id,
                         to_matter_id=to_id, rel_type=rel_type, formation=formation,
                         confidence=confidence, evidence_refs_json=json.dumps(evidence or []))
    db.add(rel)
    await db.flush()
    return rel


# ============================================================================
# Collection of unlinked primitives
# ============================================================================

_TYPE_ORDER = ("recurrence", "expectation", "open_loop", "commitment", "work_item",
               "model_entry", "domain_annotation", "fact")


async def _collect_unlinked(db: AsyncSession, scope: Scope, now: datetime,
                            limit: int) -> List[PrimitiveRef]:
    models = _models()
    linked_ids = select(MatterLink.object_id).where(
        MatterLink.honcho_workspace_id == scope.workspace_id)
    horizon = now - timedelta(days=HISTORY_HORIZON_DAYS)
    refs: List[PrimitiveRef] = []
    for otype in _TYPE_ORDER:
        model = models[otype]
        stmt = select(model).where(model.honcho_workspace_id == scope.workspace_id,
                                   model.id.not_in(linked_ids))
        stmt = stmt.where(scope.clause(model))
        if hasattr(model, "superseded_by_id"):
            stmt = stmt.where(model.superseded_by_id.is_(None))
        if otype == "expectation":
            stmt = stmt.where(model.source_system.is_(None))
        if hasattr(model, "updated_at"):
            stmt = stmt.where(model.updated_at >= horizon)
        stmt = stmt.order_by(model.created_at.asc()).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        ents = await _entity_ids_for(db, scope.workspace_id, otype, [r.id for r in rows])
        for row in rows:
            ref = describe(otype, row, now)
            if ref is None:
                continue
            ref.entity_ids |= ents.get(row.id, set())
            refs.append(ref)
    # Chronological, as live ingestion would have seen them: a Matter forms
    # around the earliest mention and later mentions attach to it. (Type order
    # breaks ties so a parent row is processed before the rows that point at it.)
    order = {t: i for i, t in enumerate(_TYPE_ORDER)}
    refs.sort(key=lambda r: (r.created_at, order[r.object_type]))
    return refs


# ============================================================================
# Lifecycle + salience (derived from linked primitives)
# ============================================================================

async def _member_rows(db: AsyncSession, matter_ids: List[UUID], now: datetime
                       ) -> Dict[UUID, List[PrimitiveRef]]:
    models = _models()
    links = (await db.execute(select(MatterLink).where(MatterLink.matter_id.in_(matter_ids)))).scalars().all()
    by_type: Dict[str, List[UUID]] = {}
    for l in links:
        by_type.setdefault(l.object_type, []).append(l.object_id)
    rows: Dict[Tuple[str, UUID], Any] = {}
    for otype, oids in by_type.items():
        model = models.get(otype)
        if model is None:
            continue
        for row in (await db.execute(select(model).where(model.id.in_(oids)))).scalars().all():
            rows[(otype, row.id)] = row
    out: Dict[UUID, List[PrimitiveRef]] = {mid: [] for mid in matter_ids}
    for l in links:
        row = rows.get((l.object_type, l.object_id))
        if row is None:
            continue
        ref = describe(l.object_type, row, now)
        if ref is None:
            # still a member (e.g. superseded row): treat as terminal history
            created = _naive(getattr(row, "created_at", None)) or now
            ref = PrimitiveRef(l.object_type, l.object_id, row, getattr(row, "title", ""), "",
                               "other", live=False, terminal=True,
                               touched_at=_naive(getattr(row, "updated_at", None)) or created,
                               created_at=created)
        out[l.matter_id].append(ref)
    return out


def compute_components(members: List[PrimitiveRef], now: datetime,
                       user_peer_id: Optional[str] = None) -> Dict[str, Any]:
    """Inspectable foreground components in [0,1] with raw counts alongside.
    No opaque score and no inferred emotional weight (docs §9)."""
    if not members:
        return {"recency": 0.0, "frequency": 0.0, "explicit_importance": 0.0,
                "temporal_pressure": 0.0, "unresolvedness": 0.0,
                "repeated_user_initiation": 0.0, "recent_activity": 0.0, "raw": {}}
    last = max(m.touched_at for m in members)
    days = max(0.0, (now - last).total_seconds() / 86400)
    touches_30 = [m for m in members if (now - m.touched_at).days < 30]
    touches_48h = [m for m in members if (now - m.touched_at) <= timedelta(hours=48)]
    imp = [m.importance for m in members if m.importance is not None and m.live]
    # temporal pressure: nearest live window/deadline on a member expectation
    pressure, hrs_to = 0.0, None
    for m in members:
        if m.object_type != "expectation" or not m.live:
            continue
        for attr in ("hard_deadline_at", "expected_window_end", "expected_window_start"):
            t = _naive(getattr(m.row, attr, None))
            if t is None:
                continue
            h = (t - now).total_seconds() / 3600
            if -36 <= h <= 72:
                p = 1.0 if h <= 0 else max(0.0, 1 - h / 72)
                if p > pressure:
                    pressure, hrs_to = p, round(h, 1)
    unresolved = sum(1 for m in members if m.live and m.object_type in
                     ("open_loop", "expectation", "commitment"))
    user_msgs = {m.message_id for m in members if m.message_id
                 and not str(m.message_id).startswith("consolidation:")
                 and (user_peer_id is None or getattr(m.row, "owner_peer_id", user_peer_id) == user_peer_id)
                 and (now - m.created_at).days < 30}
    return {
        "recency": round(1 / (1 + days / 7), 3),
        "frequency": round(min(1.0, len(touches_30) / 8), 3),
        "explicit_importance": round(max(imp), 3) if imp else 0.0,
        "temporal_pressure": round(pressure, 3),
        "unresolvedness": round(min(1.0, unresolved / 3), 3),
        "repeated_user_initiation": round(min(1.0, len(user_msgs) / 4), 3),
        "recent_activity": round(min(1.0, len(touches_48h) / 3), 3),
        "raw": {"days_since_touch": round(days, 1), "touches_30d": len(touches_30),
                "touches_48h": len(touches_48h), "unresolved_members": unresolved,
                "hours_to_nearest_window": hrs_to, "distinct_user_messages_30d": len(user_msgs)},
    }


DEFAULT_WEIGHTS = {"recency": 1.0, "frequency": 1.0, "explicit_importance": 1.0,
                   "temporal_pressure": 1.0, "unresolvedness": 1.0,
                   "repeated_user_initiation": 1.0, "recent_activity": 1.0}


def foreground_rank(components: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> float:
    """Transparent weighted mean of the components. Weights are policy
    (product-supplied); the components stay product-neutral."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(w.values()) or 1.0
    return round(sum(float(components.get(k, 0.0)) * v for k, v in w.items()) / total, 4)


_SOFT_TYPES = ("fact", "model_entry", "domain_annotation")


# A user->system open loop is a conversational thread ("the user said something").
# It is closed when the thread is answered or the user restates/confirms it. That
# closes the THREAD, not the thing the user was talking about: a plan that has
# been confirmed is still a plan. These closure evidences therefore never resolve
# a Matter on their own; only outcome evidence (completion, cancellation,
# supersession, an elapsed window) does.
CONVERSATIONAL_CLOSURE_EVIDENCE = ("semantic_proposal:", "answered_in_turn:")
# Quiet period before a conversationally-closed Matter stops being foreground.
CONVERSATIONAL_CLOSURE_QUIET = timedelta(hours=24)


def _closed_conversationally(m: PrimitiveRef) -> bool:
    if m.object_type != "open_loop":
        return False
    direction = getattr(getattr(m.row, "direction", None), "value", getattr(m.row, "direction", None))
    evidence = str(getattr(m.row, "resolution_evidence", None) or "")
    return str(direction) == "user_to_system" and evidence.startswith(CONVERSATIONAL_CLOSURE_EVIDENCE)


def derive_status(matter: Matter, members: List[PrimitiveRef], now: datetime) -> Tuple[str, Optional[datetime]]:
    """Lifecycle derived from members (never invented). Returns (status, resolved_at).

    active   any live member, or a recently touched Matter with only soft
             evidence (concerns/topics persist; low salience != gone)
    dormant  paused/suppressed members, or untouched for DORMANT_AFTER_DAYS
    resolved every lifecycle-bearing member is terminal
    archived resolved/dormant long enough ago (history is kept, never deleted)
    """
    if matter.status == "archived" and not any(m.live for m in members):
        return "archived", matter.resolved_at
    if any(m.live for m in members):
        return "active", None
    core = [m for m in members if m.object_type not in _SOFT_TYPES]
    idle = (now - max([m.touched_at for m in members] + [matter.last_touched])).days
    if core and all(m.terminal for m in core) and all(_closed_conversationally(m) for m in core):
        # Only the conversation about it was closed: stay foreground for a quiet
        # window, then rest as dormant (history kept) rather than "resolved".
        if idle > ARCHIVE_DORMANT_AFTER_DAYS:
            return "archived", matter.resolved_at
        quiet_for = now - max([m.touched_at for m in members] + [matter.last_touched])
        return ("active", None) if quiet_for < CONVERSATIONAL_CLOSURE_QUIET else ("dormant", None)
    if core and all(m.terminal for m in core):
        resolved_at = max(m.touched_at for m in core)
        if (now - resolved_at).days > ARCHIVE_RESOLVED_AFTER_DAYS:
            return "archived", resolved_at
        return "resolved", resolved_at
    if idle > ARCHIVE_DORMANT_AFTER_DAYS:
        return "archived", matter.resolved_at
    paused = any(not m.terminal and not m.live for m in core)
    if paused or idle > DORMANT_AFTER_DAYS:
        return "dormant", None
    return "active", None


async def refresh_matters(db: AsyncSession, matters: List[Matter], now: datetime,
                          user_peer_id: Optional[str] = None) -> int:
    """Recompute lifecycle + salience components for the given Matters."""
    if not matters:
        return 0
    members = await _member_rows(db, [m.id for m in matters], now)
    changed = 0
    for m in matters:
        mem = members.get(m.id, [])
        dirty = False
        status, resolved_at = derive_status(m, mem, now)
        if status != m.status:
            if status == "active" and m.status in ("resolved", "dormant"):
                m.active_since = now
            m.status = status
            m.resolved_at = resolved_at if status in ("resolved", "archived") else None
            changed += 1
            dirty = True
        elif status == "resolved" and resolved_at and m.resolved_at != resolved_at:
            m.resolved_at = resolved_at
            dirty = True
        if mem:
            last = max(x.touched_at for x in mem)
            if last > m.last_touched:
                m.last_touched, dirty = last, True
        comp = json.dumps(compute_components(mem, now, user_peer_id), sort_keys=True)
        if comp != m.salience_components_json:
            m.salience_components_json, dirty = comp, True
        if dirty:
            m.updated_at = now
            db.add(m)
    return changed


# ============================================================================
# sync_primitives: the single write path
# ============================================================================

async def sync_primitives(
    db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
    session_id: Optional[str] = None, now: Optional[datetime] = None,
    allow_judge: bool = False, adapter: Any = None,
    limit: int = SYNC_LIMIT_PER_TYPE, scope: Optional[Scope] = None,
) -> Dict[str, Any]:
    """Resolve unlinked primitives into Matters, then refresh lifecycle +
    salience for every non-archived Matter in scope. Idempotent."""
    now = _now(now)
    scope = scope or await resolve_scope(db, workspace_id, owner_peer_id, session_id)
    index = await load_index(db, scope)
    refs = await _collect_unlinked(db, scope, now, limit)
    budget = [JUDGE_BUDGET_PER_SYNC]
    stats = {"scanned": len(refs), "linked": 0, "created": 0, "skipped": 0, "by": {}}
    touched: Dict[UUID, Matter] = {}
    from sqlalchemy.exc import IntegrityError
    for ref in refs:
        try:
            async with db.begin_nested():  # SAVEPOINT: a lost race rolls back only this primitive
                res = await resolve_or_create_matter(
                    db, ref, index, scope, now=now, adapter=adapter, allow_judge=allow_judge,
                    judge_budget=budget, create=not ref.link_only)
                if res.matter is None:
                    stats["skipped"] += 1
                    continue
                if await attach(db, res.matter, ref, index, how=res.how):
                    stats["linked"] += 1
                stats["created"] += int(res.created)
                for rel_type, other in res.edges:
                    await add_matter_relation(
                        db, workspace_id, res.matter.id, other, rel_type, formation="inferred",
                        evidence=[f"{ref.object_type}:{ref.object_id}"])
                stats["by"][res.how] = stats["by"].get(res.how, 0) + 1
                touched[res.matter.id] = res.matter
                # Short write transactions: commit per resolved primitive so no write
                # lock is held across later reads or (slow) semantic-judge awaits.
                # sync is idempotent, so partial progress is always safe to resume.
            await db.commit()
        except IntegrityError:
            # Another reconciler won the race for this primitive (unique subject
            # link). The savepoint (incl. any Matter we founded) rolled back;
            # reload the index (drops the ghost Matter) and move on.
            index = await load_index(db, scope)
            stats["conflicts"] = stats.get("conflicts", 0) + 1
    await db.commit()
    if allow_judge and adapter is not None:
        stats["dedupe"] = await dedupe_matters(db, scope, adapter=adapter, now=now,
                                               budget=JUDGE_BUDGET_PER_SYNC)
        index = await load_index(db, scope)
    live = [m for m in index.matters.values()]
    stats["status_changes"] = await refresh_matters(db, live, now, scope.owner_peer_id)
    await db.commit()
    stats["matters"] = len(live)
    return stats


async def dedupe_matters(db: AsyncSession, scope: Scope, *, adapter: Any, now: Optional[datetime] = None,
                         budget: int = JUDGE_BUDGET_PER_SYNC) -> Dict[str, Any]:
    """Repair under-merged Matters. Pairs that share a linked entity are asked
    to the bounded semantic judge ("same specific real-world matter?"); only an
    accepted, verbatim-grounded verdict merges (`merge_matters`). Verdicts of
    "distinct" are remembered on the pair's `related_to` edge so the same pair
    is never re-judged. No adapter -> nothing happens (fail-closed)."""
    from itertools import combinations
    from src.services import semantic_judge
    out = {"judged": 0, "merged": 0, "distinct": 0}
    if adapter is None or budget <= 0:
        return out
    index = await load_index(db, scope)
    live = {m for m, mat in index.matters.items() if mat.status in ("active", "dormant", "resolved")}
    pairs: Set[Tuple[UUID, UUID]] = set()
    for mids in index.entity_map.values():
        for a, b in combinations(sorted((m for m in mids if m in live), key=str), 2):
            pairs.add((a, b))
    judged_distinct: Set[frozenset] = set()
    for rel in (await db.execute(select(MatterRelation).where(
            MatterRelation.honcho_workspace_id == scope.workspace_id,
            MatterRelation.rel_type == "related_to"))).scalars().all():
        if "judged:distinct" in (rel.evidence_refs_json or ""):
            judged_distinct.add(frozenset((rel.from_matter_id, rel.to_matter_id)))
    gone: Set[UUID] = set()
    # most recently touched first: fresh fragmentation matters most
    ordered = sorted(pairs, key=lambda p: -max(index.matters[p[0]].last_touched, index.matters[p[1]].last_touched).timestamp())
    for a, b in ordered:
        if budget <= 0:
            break
        if a in gone or b in gone or frozenset((a, b)) in judged_distinct:
            continue
        budget -= 1
        out["judged"] += 1
        res = await semantic_judge.judge(kind="same_matter", earlier=index.describe_matter(a),
                                         later=index.describe_matter(b), adapter=adapter)
        if res is not None:
            older, newer = sorted((a, b), key=lambda m: (index.matters[m].first_seen, str(m)))
            await merge_matters(db, older, newer)
            gone.add(newer)
            out["merged"] += 1
        else:
            rel = await add_matter_relation(db, scope.workspace_id, a, b, "related_to", formation="judged",
                                            evidence=["judged:distinct"])
            if rel is not None and "judged:distinct" not in (rel.evidence_refs_json or ""):
                rel.evidence_refs_json = json.dumps(sorted(set(json.loads(rel.evidence_refs_json or "[]")) | {"judged:distinct"}))
                db.add(rel)
            await db.commit()
            out["distinct"] += 1
    return out


async def sync_workspace(db: AsyncSession, *, workspace_id: str, now: Optional[datetime] = None,
                         allow_judge: bool = False, adapter: Any = None) -> Dict[str, Any]:
    """Backfill driver: sync every owner that has rows in the workspace."""
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop
    from src.models.operational_state import RecurringIntention
    from src.models.commitment_candidate import CommitmentCandidate
    owners: Set[Optional[str]] = set()
    for model in (Expectation, OpenLoop, RecurringIntention, CommitmentCandidate):
        owners.update((await db.execute(select(model.owner_peer_id).where(
            model.honcho_workspace_id == workspace_id).distinct())).scalars().all())
    # System peers (owners of nothing but the system's own promises) are folded
    # into the user's scope, never synced as a world of their own.
    system_only: Set[str] = set()
    for peer in [o for o in owners if o]:
        promises = (await db.execute(select(func.count()).select_from(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.owner_peer_id == peer,
            CommitmentCandidate.evidence_class == "character_promise"))).scalar_one()
        own = 0
        for model in (Expectation, OpenLoop, RecurringIntention):
            own += (await db.execute(select(func.count()).select_from(model).where(
                model.honcho_workspace_id == workspace_id, model.owner_peer_id == peer))).scalar_one()
        if promises and not own:
            system_only.add(peer)
    results: Dict[str, Any] = {}
    for owner in sorted(owners, key=lambda o: (o is None, o or "")):
        if owner in system_only:
            continue
        scope = await resolve_scope(db, workspace_id, owner)
        results[owner or "<none>"] = await sync_primitives(
            db, workspace_id=workspace_id, owner_peer_id=owner, now=now,
            allow_judge=allow_judge, adapter=adapter, scope=scope)
    return results


# ============================================================================
# Reads, summary reference, merge
# ============================================================================

async def get_matter(db: AsyncSession, matter_id: UUID) -> Optional[Matter]:
    m = await db.get(Matter, matter_id)
    hops = 0
    while m is not None and m.merged_into_id and hops < 8:
        m = await db.get(Matter, m.merged_into_id)
        hops += 1
    return m


async def matters_for_entity(db: AsyncSession, workspace_id: str, entity_id: UUID,
                             include_inactive: bool = False) -> List[Matter]:
    from src.models.identity import EntityLink
    ids = (await db.execute(select(EntityLink.object_id).where(
        EntityLink.honcho_workspace_id == workspace_id, EntityLink.object_type == "matter",
        EntityLink.entity_id == entity_id))).scalars().all()
    if not ids:
        return []
    stmt = select(Matter).where(Matter.id.in_(ids), Matter.merged_into_id.is_(None))
    if not include_inactive:
        stmt = stmt.where(Matter.status.in_(("active", "dormant")))
    return list((await db.execute(stmt.order_by(Matter.last_touched.desc()))).scalars().all())


async def current_summary(db: AsyncSession, matter: Matter) -> Optional[Dict[str, Any]]:
    """The Matter's summary is a reference to a ModelEntry — read through it."""
    from src.models.identity import ModelEntry
    from src.services.epistemics import entry_view
    if not matter.summary_entry_id:
        return None
    entry = await db.get(ModelEntry, matter.summary_entry_id)
    while entry is not None and entry.superseded_by_id:
        entry = await db.get(ModelEntry, entry.superseded_by_id)
    return entry_view(entry, _now(None)) if entry else None


async def set_matter_summary(db: AsyncSession, matter: Matter, *, claim: str, formation: str,
                             confidence: float, evidence_verbatim: str, session_id: str,
                             message_id: str, evidence_refs: Optional[List[str]] = None,
                             owner_peer_id: Optional[str] = None) -> Any:
    """Write/revise the Matter's summary through the epistemic write path."""
    from src.services.epistemics import write_claim
    entry = await write_claim(
        db, workspace_id=matter.honcho_workspace_id, session_id=session_id,
        message_id=message_id, owner_peer_id=owner_peer_id or matter.owner_peer_id,
        model_kind="user", claim=claim, evidence_verbatim=evidence_verbatim,
        formation=formation, confidence=confidence, claim_kind="matter_summary",
        subject_matter_id=matter.id, evidence_refs=evidence_refs,
        supersedes_id=matter.summary_entry_id)
    matter.summary_entry_id = entry.id
    db.add(matter)
    await db.commit()
    return entry


async def merge_matters(db: AsyncSession, keep_id: UUID, drop_id: UUID) -> Matter:
    """Repair fragmentation: fold `drop` into `keep` (links, entity links,
    relations and summary references move; `drop` is archived with
    `merged_into_id`, never deleted)."""
    from src.models.identity import EntityLink, ModelEntry
    keep, drop = await db.get(Matter, keep_id), await db.get(Matter, drop_id)
    if keep is None or drop is None or keep.id == drop.id:
        raise ValueError("merge requires two distinct existing Matters")
    existing = {(l.object_type, l.object_id) for l in (await db.execute(
        select(MatterLink).where(MatterLink.matter_id == keep.id))).scalars().all()}
    for link in (await db.execute(select(MatterLink).where(MatterLink.matter_id == drop.id))).scalars().all():
        if (link.object_type, link.object_id) in existing:
            await db.delete(link)
        else:
            link.matter_id = keep.id
            db.add(link)
    have = {e.entity_id for e in (await db.execute(select(EntityLink).where(
        EntityLink.object_type == "matter", EntityLink.object_id == keep.id))).scalars().all()}
    for el in (await db.execute(select(EntityLink).where(
            EntityLink.object_type == "matter", EntityLink.object_id == drop.id))).scalars().all():
        if el.entity_id in have:
            await db.delete(el)
        else:
            el.object_id = keep.id
            db.add(el)
    # Re-point relations; drop self-edges and edges that would duplicate an
    # existing one (related_to is symmetric).
    all_rels = (await db.execute(select(MatterRelation).where(
        MatterRelation.honcho_workspace_id == drop.honcho_workspace_id))).scalars().all()
    edges = {(r.from_matter_id, r.to_matter_id, r.rel_type) for r in all_rels
             if drop.id not in (r.from_matter_id, r.to_matter_id)}
    for rel in [r for r in all_rels if drop.id in (r.from_matter_id, r.to_matter_id)]:
        f = keep.id if rel.from_matter_id == drop.id else rel.from_matter_id
        t = keep.id if rel.to_matter_id == drop.id else rel.to_matter_id
        dup = (f, t, rel.rel_type) in edges or (rel.rel_type == "related_to" and (t, f, rel.rel_type) in edges)
        if f == t or dup:
            await db.delete(rel)
        else:
            edges.add((f, t, rel.rel_type))
            rel.from_matter_id, rel.to_matter_id = f, t
            db.add(rel)
    await db.flush()
    for me in (await db.execute(select(ModelEntry).where(ModelEntry.subject_matter_id == drop.id))).scalars().all():
        me.subject_matter_id = keep.id
        db.add(me)
    keep.first_seen = min(keep.first_seen, drop.first_seen)
    keep.last_touched = max(keep.last_touched, drop.last_touched)
    keep.summary_entry_id = keep.summary_entry_id or drop.summary_entry_id
    if drop.formation == "explicit":
        keep.formation = "explicit"
    drop.merged_into_id, drop.status, drop.updated_at = keep.id, "archived", _now(None)
    db.add_all([keep, drop])
    await db.commit()
    return keep
