"""WorldReader: ONE transient, scoped read of canonical Cortex primitives.

This is the private gather step shared by WorldModel sections, projections and
knowledge-coverage derivation (docs/CORTEX_ARCHITECTURE.md §6). It reads the
authoritative rows once, normalises them into small *items* that always carry
provenance (formation, confidence, evidence refs, direction, matter link), and
is discarded after use. It must NOT become an exposed mega-packet, a cache, or
a prompt payload — callers expose only filtered/compressed views of it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.matter import Matter, MatterLink, MatterRelation
from src.services import actor_direction as ad
from src.services.epistemics import formation_class, derive_status as claim_status
from src.services.world_scope import Scope, resolve_scope

HORIZON_DAYS = 180
PER_TYPE_LIMIT = 600
Item = Dict[str, Any]


def naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _val(x: Any) -> str:
    return str(getattr(x, "value", x) or "")


def public(item: Item) -> Item:
    """Drop internal datetime keys; ISO-format the rest for output."""
    out = {}
    for k, v in item.items():
        if k.startswith("_"):
            continue
        out[k] = v
    for k in ("created_at", "updated_at", "effective_at"):
        if isinstance(item.get("_" + k), datetime):
            out[k] = item["_" + k].isoformat()
    return out


@dataclass
class UserDay:
    tz: str
    now: datetime

    def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.tz)
        except Exception:
            return ZoneInfo("UTC")

    def local(self, dt: datetime) -> datetime:
        aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        return aware.astimezone(self.zone())

    @property
    def today(self) -> date:
        return self.local(self.now).date()

    def bounds(self, day: date) -> tuple:
        """[start, end) of a local user day, as naive UTC."""
        z = self.zone()
        start = datetime.combine(day, time.min, tzinfo=z).astimezone(timezone.utc).replace(tzinfo=None)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=z).astimezone(timezone.utc).replace(tzinfo=None)
        return start, end


class WorldReader:
    """Loads once; everything after `load()` is in-memory and read-only."""

    def __init__(self, db: AsyncSession, scope: Scope, now: datetime, tz: str = "UTC"):
        self.db = db
        self.scope = scope
        self.now = naive(now) or datetime.utcnow()
        self.tz = tz
        self.day = UserDay(tz, self.now)
        self.items: List[Item] = []
        self.matters: Dict[UUID, Matter] = {}
        self.matter_links: Dict[UUID, List[MatterLink]] = {}
        self.matter_of: Dict[UUID, UUID] = {}
        self.matter_relations: List[MatterRelation] = []
        self.entities: Dict[UUID, Any] = {}
        self.edges: List[Any] = []
        self.entity_links: Dict[UUID, Set[UUID]] = {}      # object id -> entity ids
        self.matter_entities: Dict[UUID, Set[UUID]] = {}   # matter id -> entity ids
        self.model_entries: List[Any] = []
        self.suppressions: List[Any] = []
        self.rows: Dict[tuple, Any] = {}
        self.loaded = False

    # ---------------------------------------------------------------- load
    async def load(self) -> "WorldReader":
        from src.models.commitment_candidate import CommitmentCandidate
        from src.models.domain_annotation import DomainAnnotation
        from src.models.expectation import Expectation
        from src.models.fact import Fact
        from src.models.identity import Entity, EntityLink, ModelEntry, RelationshipEdge
        from src.models.attention_candidate import AttentionCandidate
        from src.models.open_loop import OpenLoop
        from src.models.operational_state import RecurringIntention
        from src.models.suppression import Suppression, SuppressionStatus
        from src.models.work_item import WorkItem

        db, scope, now = self.db, self.scope, self.now
        horizon = now - timedelta(days=HORIZON_DAYS)

        async def rows(model, *extra, order=None):
            stmt = select(model).where(model.honcho_workspace_id == scope.workspace_id,
                                       scope.clause(model), *extra)
            if hasattr(model, "updated_at"):
                stmt = stmt.where(model.updated_at >= horizon)
            stmt = stmt.order_by((order or model.updated_at).desc()).limit(PER_TYPE_LIMIT)
            return (await db.execute(stmt)).scalars().all()

        exps = await rows(Expectation, Expectation.superseded_by_id.is_(None))
        loops = await rows(OpenLoop)
        recs = await rows(RecurringIntention, RecurringIntention.superseded_by_id.is_(None))
        coms = await rows(CommitmentCandidate)
        works = await rows(WorkItem)
        facts = await rows(Fact)
        atts = await rows(AttentionCandidate)
        self.model_entries = list(await rows(ModelEntry))
        self.suppressions = list((await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == scope.workspace_id, scope.clause(Suppression),
            Suppression.status == SuppressionStatus.ACTIVE))).scalars().all())
        self.annotations = list((await db.execute(select(DomainAnnotation).where(
            DomainAnnotation.honcho_workspace_id == scope.workspace_id,
            scope.clause(DomainAnnotation), DomainAnnotation.created_at >= horizon
        ).limit(PER_TYPE_LIMIT))).scalars().all())

        # Matters in scope + their links/relations
        mstmt = select(Matter).where(Matter.honcho_workspace_id == scope.workspace_id,
                                     Matter.merged_into_id.is_(None))
        mstmt = mstmt.where(Matter.owner_peer_id == scope.owner_peer_id) if scope.owner_peer_id \
            else mstmt.where(Matter.owner_peer_id.is_(None))
        for m in (await db.execute(mstmt)).scalars().all():
            self.matters[m.id] = m
        if self.matters:
            ids = list(self.matters)
            for l in (await db.execute(select(MatterLink).where(MatterLink.matter_id.in_(ids)))).scalars().all():
                self.matter_links.setdefault(l.matter_id, []).append(l)
                self.matter_of[l.object_id] = l.matter_id
            self.matter_relations = list((await db.execute(select(MatterRelation).where(
                MatterRelation.from_matter_id.in_(ids)))).scalars().all())

        all_rows = ([("expectation", r) for r in exps] + [("open_loop", r) for r in loops]
                    + [("recurrence", r) for r in recs] + [("commitment", r) for r in coms]
                    + [("work_item", r) for r in works] + [("fact", r) for r in facts]
                    + [("attention", r) for r in atts]
                    + [("model_entry", r) for r in self.model_entries])
        obj_ids = [r.id for _, r in all_rows]
        # Entity links (object -> entities, matter -> entities)
        for el in (await db.execute(select(EntityLink).where(
                EntityLink.honcho_workspace_id == scope.workspace_id,
                EntityLink.object_id.in_(obj_ids + list(self.matters))))).scalars().all():
            self.entity_links.setdefault(el.object_id, set()).add(el.entity_id)
            if el.object_type == "matter":
                self.matter_entities.setdefault(el.object_id, set()).add(el.entity_id)
        ent_ids = {e for s in self.entity_links.values() for e in s}
        ent_ids |= {r.subject_entity_id for _, r in all_rows if getattr(r, "subject_entity_id", None)}
        if ent_ids:
            for e in (await db.execute(select(Entity).where(Entity.id.in_(list(ent_ids))))).scalars().all():
                self.entities[e.id] = e
            self.edges = list((await db.execute(select(RelationshipEdge).where(
                RelationshipEdge.honcho_workspace_id == scope.workspace_id,
                RelationshipEdge.end_at.is_(None),
                (RelationshipEdge.from_entity_id.in_(list(ent_ids))) | (RelationshipEdge.to_entity_id.in_(list(ent_ids)))
            ))).scalars().all())

        for otype, row in all_rows:
            self.rows[(otype, row.id)] = row
            item = self._item(otype, row)
            if item:
                self.items.append(item)
        self.loaded = True
        return self

    # ------------------------------------------------------------ normalise
    def _base(self, otype: str, row: Any, *, title: str, summary: str = "", status: str,
              live: bool, formation: str, confidence: float, message_id: Optional[str]) -> Item:
        direction = ad.effective_direction(row, user_peer_id=self.scope.owner_peer_id)
        holder = "system" if ad.is_system_held(row, user_peer_id=self.scope.owner_peer_id) else (
            "world" if direction == ad.WORLD else "user")
        mid = self.matter_of.get(row.id)
        created = naive(getattr(row, "created_at", None)) or self.now
        updated = naive(getattr(row, "updated_at", None)) or created
        return {
            "ref": {"type": otype, "id": str(row.id)},
            "kind": otype, "title": title[:200], "summary": (summary or "")[:240],
            "status": status, "live": live, "direction": direction, "holder": holder,
            "formation": formation_class(formation), "confidence": round(float(confidence or 0), 3),
            "evidence_refs": [message_id] if message_id else [],
            "entity_ids": sorted(str(e) for e in self.entity_links.get(row.id, ())),
            "matter_id": str(mid) if mid else None,
            "_created_at": created, "_updated_at": updated,
        }

    def _item(self, otype: str, row: Any) -> Optional[Item]:
        from src.services.expectation_engine import derive_temporal_state
        if otype == "expectation":
            outcome = _val(row.outcome_state)
            it = self._base(otype, row, title=row.title, summary=row.summary, status=outcome,
                            live=outcome == "unknown", formation=row.formation or "explicit",
                            confidence=row.extraction_confidence, message_id=row.honcho_message_id)
            it.update({
                "expectation_type": _val(row.expectation_type),
                "temporal_state": _val(derive_temporal_state(row, self.now)),
                "source_system": row.source_system,
                "_start": naive(row.expected_window_start), "_end": naive(row.expected_window_end),
                "_deadline": naive(row.hard_deadline_at),
                "raw_temporal_phrase": row.raw_temporal_phrase,
                "resolution_evidence": row.resolution_evidence,
                "_effective_at": naive(row.effective_at),
            })
            return it
        if otype == "open_loop":
            st = _val(row.status)
            it = self._base(otype, row, title=row.title, summary=row.summary, status=st,
                            live=st == "open" and not (row.expires_at and naive(row.expires_at) <= self.now),
                            formation="explicit" if row.invited else "inferred", confidence=0.8,
                            message_id=row.honcho_message_id)
            it["invited"] = bool(row.invited)
            it["expectation_id"] = str(row.expectation_id) if row.expectation_id else None
            return it
        if otype == "recurrence":
            st = _val(row.status)
            it = self._base(otype, row, title=row.title, summary=row.cadence, status=st,
                            live=st == "active",
                            formation="observed" if _val(row.semantic_type) == "observed_pattern" else "explicit",
                            confidence=row.confidence, message_id=row.honcho_message_id)
            it.update({"semantic_type": row.semantic_type, "cadence": row.cadence,
                       "preferred_window": row.preferred_window, "canonical_key": row.canonical_key,
                       "declared": _val(row.semantic_type) != "observed_pattern",
                       "target_amount": row.target_amount, "target_unit": row.target_unit})
            return it
        if otype == "commitment":
            st = _val(row.status)
            it = self._base(otype, row, title=row.title, summary=row.notes or "", status=st,
                            live=st in ("pending", "materialized"),
                            formation="explicit" if _val(row.authority) == "act" else "inferred",
                            confidence=0.8, message_id=row.source_message_id)
            it.update({"evidence_class": row.evidence_class, "authority": _val(row.authority)})
            return it
        if otype == "work_item":
            st = _val(row.status)
            it = self._base(otype, row, title=row.parent_title or row.action, summary=row.action,
                            status=st, live=st in ("proposed", "surfaced", "in_progress"),
                            formation="inferred", confidence=row.importance or 0.5, message_id=None)
            it.update({"owner": _val(row.owner), "importance": row.importance,
                       "parent_type": row.parent_type, "parent_id": row.parent_id,
                       "_end": naive(row.due_window_end)})
            return it
        if otype == "fact":
            it = self._base(otype, row, title=row.title, summary=row.evidence_verbatim, status="current",
                            live=False, formation=row.formation or "explicit",
                            confidence=row.confidence, message_id=row.honcho_message_id)
            it["category"] = row.category
            return it
        if otype == "attention":
            st = _val(row.status)
            it = self._base(otype, row, title=row.content, summary="", status=st, live=st == "active",
                            formation="inferred", confidence=row.confidence,
                            message_id=row.source_message_id)
            it.update({"attention_kind": _val(row.kind)})
            return it
        if otype == "model_entry":
            now = self.now
            status = claim_status(row, now)
            it = self._base(otype, row, title=row.claim, summary="", status=status,
                            live=status in ("current", "uncertain", "conflicting"),
                            formation=row.formation, confidence=row.confidence,
                            message_id=row.honcho_message_id)
            try:
                refs = json.loads(row.evidence_refs_json or "[]")
            except (TypeError, ValueError):
                refs = []
            it["evidence_refs"] = [r for r in dict.fromkeys(list(refs) + it["evidence_refs"]) if r]
            it.update({"model_kind": row.model_kind, "claim_kind": row.claim_kind or row.model_kind,
                       "holder_actor": row.holder_actor,
                       "subject_entity_id": str(row.subject_entity_id) if row.subject_entity_id else None,
                       "subject_matter_id": str(row.subject_matter_id) if row.subject_matter_id else None,
                       "epistemic_status": status, "_effective_at": naive(row.effective_at)})
            if row.subject_matter_id:
                it["matter_id"] = str(row.subject_matter_id)
            if row.holder_actor == "system":
                it["holder"] = "system"
            return it
        return None

    # ------------------------------------------------------------- selectors
    def of(self, *kinds: str, live: Optional[bool] = None) -> List[Item]:
        out = [i for i in self.items if i["kind"] in kinds]
        if live is not None:
            out = [i for i in out if i["live"] is live]
        return out

    def matter_items(self, matter_id: UUID) -> List[Item]:
        return [i for i in self.items if i.get("matter_id") == str(matter_id)]

    def entity_name(self, entity_id: Any) -> str:
        try:
            e = self.entities.get(UUID(str(entity_id)))
        except ValueError:
            e = None
        return e.display_name if e else str(entity_id)

    def components(self, matter: Matter) -> Dict[str, Any]:
        try:
            return json.loads(matter.salience_components_json or "{}")
        except (TypeError, ValueError):
            return {}

    def touched_between(self, start: datetime, end: datetime) -> List[Item]:
        return [i for i in self.items
                if start <= i["_updated_at"] < end or start <= i["_created_at"] < end]

    def when_of(self, item: Item) -> Optional[datetime]:
        """The moment a forward-looking item is expected (window/deadline)."""
        return item.get("_deadline") or item.get("_start") or item.get("_end") or item.get("_effective_at")


async def open_reader(db: AsyncSession, workspace_id: str, owner_peer_id: Optional[str],
                      now: datetime, tz: str = "UTC", session_id: Optional[str] = None,
                      scope: Optional[Scope] = None) -> WorldReader:
    scope = scope or await resolve_scope(db, workspace_id, owner_peer_id, session_id)
    return await WorldReader(db, scope, now, tz).load()
