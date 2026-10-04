"""WorldModel: a persisted, versioned, reconstructable derived snapshot.

NOT authoritative truth, NOT a prompt payload (docs/CORTEX_ARCHITECTURE.md §6):
the complete model is never inserted wholesale into a foreground turn. Runtime
caches/inspects it and asks projections for small fragments.

Mechanism (repo-native, no event bus): one snapshot row per (workspace, owner)
with per-section source fingerprints. `get_world_model` is a cheap fingerprint
check; stale sections are patched from ONE transient read, everything is
rebuildable from the primitives, and the previous version is kept (superseded)
for recoverability.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.world_model import WorldModelSnapshot
from src.services import knowledge_coverage_service as kcs
from src.services import matter_service as ms
from src.services.projection_service import Projections
from src.services.world_read import iso, naive, open_reader
from src.services.world_scope import Scope, resolve_scope

logger = logging.getLogger(__name__)

WORLD_MODEL_VERSION = "world-model-v1"
TTL_HOURS = 6   # recency/temporal state decay with the clock, not only with writes

# section -> source tables whose change makes it stale ("day" = user-day rollover)
SECTION_SOURCES: Dict[str, Tuple[str, ...]] = {
    "person": ("facts", "model_entries", "entities", "relationship_edges", "matters"),
    "relationship_with_system": ("expectations", "open_loops", "commitment_candidates",
                                 "attention_candidates", "work_items", "model_entries", "suppressions"),
    "recent": ("expectations", "open_loops", "commitment_candidates", "work_items",
               "matters", "model_entries", "day"),
    "matters": ("matters", "matter_links", "expectations", "open_loops", "recurring_intentions",
                "commitment_candidates", "work_items", "model_entries"),
    "people": ("matters", "entity_links", "entities", "relationship_edges"),
    "routines_patterns": ("recurring_intentions", "model_entries"),
    "forward": ("expectations", "work_items", "commitment_candidates", "recurring_intentions", "day"),
    "unresolved": ("expectations", "open_loops", "commitment_candidates", "model_entries", "matters"),
    "uncertainty": ("model_entries", "expectations", "knowledge_coverage"),
    "coverage": ("expectations", "open_loops", "recurring_intentions", "facts", "model_entries",
                 "matters", "entity_links", "relationship_edges", "suppressions", "knowledge_coverage"),
    "system_perspective": ("model_entries",),
    "depth_index": ("expectations", "open_loops", "commitment_candidates", "work_items", "facts",
                    "model_entries", "matters"),
}
PRIMITIVE_TABLES = ("expectations", "open_loops", "recurring_intentions", "commitment_candidates",
                    "work_items", "facts", "model_entries", "attention_candidates", "suppressions",
                    "entities", "entity_links", "relationship_edges", "domain_annotations")


# ------------------------------------------------------------------ compaction
def _trim(item: Dict[str, Any], *extra: str) -> Dict[str, Any]:
    """Compact WorldModel item: provenance and direction kept, bulk dropped.
    (Projections return the richer shape; the snapshot is for cheap inspection.)"""
    out: Dict[str, Any] = {"ref": f"{item['ref']['type']}:{item['ref']['id']}", "title": item["title"],
                           "status": item["status"], "formation": item["formation"],
                           "confidence": item["confidence"]}
    if item.get("direction"):
        out["direction"] = item["direction"]
    if item.get("holder") == "system":
        out["holder"] = "system"
    if item.get("evidence_refs"):
        out["evidence"] = item["evidence_refs"][:2]
    if item.get("matter_id"):
        out["matter"] = item["matter_id"]
    for k in extra:
        if item.get(k) is not None:
            out[k] = item[k]
    return out


def _change(c: Dict[str, Any]) -> Dict[str, Any]:
    ref = c.get("matter") or c.get("item") or c.get("claim") or c.get("now") or {}
    title = ref.get("title") or ref.get("claim")
    return {"change": c["change"], "at": c["at"], "title": title,
            "ref": ref.get("ref") if isinstance(ref.get("ref"), str) else
            (f"{ref['ref']['type']}:{ref['ref']['id']}" if isinstance(ref.get("ref"), dict) else ref.get("id"))}


# ------------------------------------------------------------------ fingerprints
async def _table_fingerprints(db: AsyncSession, scope: Scope, now: datetime, tz: str) -> Dict[str, str]:
    from src.models.attention_candidate import AttentionCandidate
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.domain_annotation import DomainAnnotation
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.models.identity import Entity, EntityLink, ModelEntry, RelationshipEdge
    from src.models.matter import Matter, MatterLink
    from src.models.open_loop import OpenLoop
    from src.models.operational_state import RecurringIntention
    from src.models.suppression import Suppression
    from src.models.work_item import WorkItem
    from src.models.world_model import KnowledgeCoverage
    from src.services.world_read import UserDay

    ws = scope.workspace_id

    async def fp(model, ts_col: str, *extra) -> str:
        where = [model.honcho_workspace_id == ws, *extra]
        if hasattr(model, "owner_peer_id") or hasattr(model, "honcho_session_id"):
            where.append(scope.clause(model))
        col = getattr(model, ts_col)
        row = (await db.execute(select(func.count(), func.max(col)).where(*where))).one()
        return f"{row[0]}:{row[1].isoformat() if row[1] else ''}"

    out = {
        "expectations": await fp(Expectation, "updated_at"),
        "open_loops": await fp(OpenLoop, "updated_at"),
        "recurring_intentions": await fp(RecurringIntention, "updated_at"),
        "commitment_candidates": await fp(CommitmentCandidate, "updated_at"),
        "work_items": await fp(WorkItem, "updated_at"),
        "facts": await fp(Fact, "updated_at"),
        "model_entries": await fp(ModelEntry, "updated_at"),
        "attention_candidates": await fp(AttentionCandidate, "updated_at"),
        "suppressions": await fp(Suppression, "created_at"),
        "domain_annotations": await fp(DomainAnnotation, "created_at"),
        "entities": await fp(Entity, "updated_at"),
        "relationship_edges": await fp(RelationshipEdge, "updated_at"),
        "entity_links": await fp(EntityLink, "created_at"),
        "matters": await fp(Matter, "updated_at",
                            (Matter.owner_peer_id == scope.owner_peer_id) if scope.owner_peer_id
                            else Matter.owner_peer_id.is_(None)),
        "matter_links": await fp(MatterLink, "created_at"),
        "knowledge_coverage": await fp(KnowledgeCoverage, "updated_at"),
        "day": UserDay(tz, now).today.isoformat(),
    }
    return out


def _section_fps(tables: Dict[str, str]) -> Dict[str, str]:
    return {name: hashlib.sha1("|".join(f"{t}={tables.get(t, '')}" for t in srcs).encode()).hexdigest()[:16]
            for name, srcs in SECTION_SOURCES.items()}


def _primitive_fp(tables: Dict[str, str]) -> str:
    return hashlib.sha1("|".join(f"{t}={tables.get(t, '')}" for t in PRIMITIVE_TABLES).encode()).hexdigest()[:16]


# --------------------------------------------------------------------- sections
def _compact_matter(p: Projections, m) -> Dict[str, Any]:
    b = p._matter_brief(m, with_members=3)
    comps = sorted(((k, v) for k, v in b["components"].items() if v), key=lambda kv: -kv[1])[:3]
    return {"id": b["id"], "title": b["title"], "kind": b["kind"], "status": b["status"],
            "last_touched": b["last_touched"], "rank": b["rank"], "driven_by": dict(comps),
            "people": b["people"][:3],
            "members": [f"{x['ref']['type']}:{x['ref']['id']}" for x in b.get("members", [])]}


def _s_person(p: Projections) -> Dict[str, Any]:
    r = p.r
    facts = [i for i in r.of("fact") if i["holder"] == "user"]
    claims = [i for i in r.of("model_entry") if i.get("model_kind") == "user" and i["holder"] != "system"
              and i["status"] in ("current", "uncertain", "conflicting")]
    ov = p.user_overview()
    return {"facts": [_trim(i, "category") for i in facts[:8]],
            "claims": [_trim(i, "claim_kind", "epistemic_status") for i in claims[:8]],
            "circle": [{k: c[k] for k in ("entity_id", "name", "role", "mentions")} for c in ov["circle"][:6]]}


def _s_relationship(p: Projections) -> Dict[str, Any]:
    r = p.r
    rel = lambda **kw: [i for i in r.items if i["kind"] != "model_entry"
                        and all(i.get(k) == v for k, v in kw.items())]
    asks = [_trim(i) for i in rel(direction="user_to_system", live=True)][:8]
    owed = [_trim(i) for i in rel(direction="system_to_user", live=True) if i["kind"] in ("commitment", "work_item")][:8]
    preds = [_trim(i) for i in rel(direction="system_to_user", live=True)
             if i["kind"] == "expectation" and i["formation"] in ("inferred", "hypothesis", "observed")][:5]
    carries = [_trim(i, "attention_kind") for i in rel(direction="system_to_user", live=True) if i["kind"] == "attention"][:5]
    claims = [i for i in r.of("model_entry") if i["live"] and i["holder"] != "system"]
    repair = [_trim(i, "claim_kind", "epistemic_status") for i in claims if i.get("claim_kind") == "repair"][:4]
    devs = [_trim(i, "claim_kind", "epistemic_status") for i in claims
            if i.get("claim_kind") == "relationship_development" or i.get("model_kind") == "relationship"][:6]
    collab = [_trim(i, "claim_kind") for i in claims if i.get("claim_kind") == "pattern"
              and i["direction"] in ("shared", "user_to_system", "system_to_user")][:4]
    shared_work = [_trim(i) for i in r.of("work_item", live=True) if i["holder"] == "system"][:5]
    bounds = [{"topic": s.topic_or_entity, "target_type": getattr(s.target_type, "value", s.target_type),
               "reason": s.reason, "until": iso(s.suppressed_until), "evidence_refs": [s.honcho_message_id]}
              for s in r.suppressions][:6]
    first = min((i["_created_at"] for i in r.items), default=None)
    lanes = sorted(r.scope.lane_ids)
    return {
        "history": {"first_evidence_at": iso(first), "lanes": len(lanes),
                    "items_recorded": len(r.items)},
        "user_to_system": asks,
        "system_to_user": {"commitments": owed, "working_predictions": preds, "carries": carries},
        "shared": {"repair": repair, "developments": devs, "collaboration_patterns": collab,
                   "shared_work": shared_work},
        "boundaries_and_preferences": bounds,
    }


def _s_recent(p: Projections) -> Dict[str, Any]:
    day = p.r.day
    t0, t1 = day.bounds(day.today)
    y0, _ = day.bounds(day.today - timedelta(days=1))
    d3, _ = day.bounds(day.today - timedelta(days=6))
    def digest(w):
        per = p.period(*w)
        # last_touched/status let a consumer say HOW LONG AGO something happened.
        return {"occupied": [{"matter_id": o["id"], "title": o["title"], "touches": o["touch_count"],
                              "last_touched": o["last_touched"], "status": o["status"]}
                             for o in per["occupied"][:5]],
                "resolved": [r["title"] for r in per["resolved"][:4]], "activity": per["activity"]}
    return {"today": digest((t0, t1)), "yesterday": digest((y0, t0)),
            "recent_days": digest((d3, y0)),
            "significant_changes": [_change(c) for c in p.recent_changes(days=7)["changes"][:8]]}


def _s_matters(p: Projections) -> Dict[str, Any]:
    ranked = p._ranked_matters(("active",))
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for m in ranked:
        by_kind.setdefault(m.kind, []).append({"id": str(m.id), "title": m.title, "rank": p._matter_brief(m)["rank"]})
    resolved = sorted([m for m in p.r.matters.values() if m.status == "resolved"],
                      key=lambda m: m.resolved_at or m.last_touched, reverse=True)
    return {
        "active": [_compact_matter(p, m) for m in ranked[:12]],
        "active_total": len(ranked),
        "dormant": [{"id": str(m.id), "title": m.title, "kind": m.kind, "last_touched": iso(m.last_touched)}
                    for m in p._ranked_matters(("dormant",))[:8]],
        "recently_resolved": [{"id": str(m.id), "title": m.title, "resolved_at": iso(m.resolved_at)}
                              for m in resolved[:5]],
        "by_kind": {k: [x["id"] for x in v[:6]] for k, v in by_kind.items()},
    }


def _s_people(p: Projections) -> Dict[str, Any]:
    r = p.r
    scores: Dict[str, Dict[str, Any]] = {}
    for m in r.matters.values():
        if m.status not in ("active", "dormant"):
            continue
        rank = ms.foreground_rank(r.components(m))
        for eid in r.matter_entities.get(m.id, ()):
            e = r.entities.get(eid)
            if e is None or e.entity_type != "person":
                continue
            s = scores.setdefault(str(eid), {"entity_id": str(eid), "name": e.display_name,
                                             "matters": [], "score": 0.0, "last_touched": None})
            s["matters"].append({"id": str(m.id), "title": m.title})
            s["score"] += rank
            s["last_touched"] = max(filter(None, [s["last_touched"], iso(m.last_touched)]))
    role = {}
    for ed in r.edges:
        role[str(ed.to_entity_id)] = ed.role
    for s in scores.values():
        s["role"] = role.get(s["entity_id"])
        s["score"] = round(s["score"], 3)
    ranked = sorted(scores.values(), key=lambda s: (-s["score"], s["name"]))
    return {"salient": ranked[:8]}


def _s_routines(p: Projections) -> Dict[str, Any]:
    r = p.r
    recs = r.of("recurrence", live=True)
    declared = [_trim(i, "cadence", "preferred_window", "semantic_type") for i in recs if i["declared"]]
    observed = [_trim(i, "cadence", "semantic_type") for i in recs if not i["declared"]]
    pats = [_trim(i, "claim_kind", "epistemic_status") for i in r.of("model_entry")
            if i.get("claim_kind") in ("pattern", "observation") and i["live"] and i["holder"] != "system"]
    return {"declared": declared[:8], "observed": observed[:8], "pattern_claims": pats[:6],
            "note": "declared = user said so; observed/pattern claims carry their own formation"}


def _s_forward(p: Projections) -> Dict[str, Any]:
    day = p.r.day
    today = p.period(*day.bounds(day.today))
    wk = p.period(day.bounds(day.today + timedelta(days=1))[0], day.bounds(day.today + timedelta(days=7))[1])
    later_start = day.bounds(day.today + timedelta(days=8))[0]
    later = p.period(later_start, later_start + timedelta(days=60))
    fx = lambda xs: [{"title": x["title"], "at": x["expected_at"], "ref": f"{x['ref']['type']}:{x['ref']['id']}",
                      "direction": x.get("direction"), "status": x["status"],
                      "temporal_state": x.get("temporal_state")} for x in xs]
    return {"today": fx(today["expected"][:8]),
            "routines_today": [r["title"] for r in p._declared_routines_on(day.today)[:6]],
            "this_week": fx(wk["expected"][:10]), "later": fx(later["expected"][:6])}


def _s_unresolved(p: Projections) -> Dict[str, Any]:
    u = p.unresolved()
    short = lambda xs: [{"ref": f"{x['ref']['type']}:{x['ref']['id']}", "title": x["title"],
                         "direction": x.get("direction"), "status": x["status"]} for x in xs]
    return {"by_matter": [{"id": g["id"], "title": g["title"], "kind": g["kind"], "open": short(g["open"][:3]),
                           "repair": short(g["repair"][:2])} for g in u["by_matter"][:8]],
            "unattached": short(u["unattached"][:5]), "owed_by_system": short(u["owed_by_system"][:5]),
            "repair": short(u["repair"]),
            "constraints": u["constraints"]}


def _s_uncertainty(p: Projections) -> Dict[str, Any]:
    r = p.r
    uncertain = [_trim(i, "claim_kind", "epistemic_status") for i in r.of("model_entry")
                 if i["status"] in ("uncertain", "conflicting", "stale") and i["holder"] != "system"]
    elapsed = [_trim(i, "temporal_state") for i in r.of("expectation", live=True)
               if i.get("temporal_state") in ("window_elapsed", "deadline_passed")]
    return {"claims": uncertain[:8], "outcome_unknown": elapsed[:8],
            "note": "unknown outcome is not failure; hypotheses stay hypotheses"}


def _s_coverage(p: Projections) -> Dict[str, Any]:
    gaps = [{k: g[k] for k in ("subject_key", "status", "why_useful")} for g in kcs.gaps(p.coverage, 10)]
    return {"counts": kcs_counts(p.coverage), "gaps": gaps,
            "frame": {c["subject_key"]: c["status"] for c in p.coverage if "/" not in c["subject_key"]}}


def kcs_counts(rows):
    out: Dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def _s_system_perspective(p: Projections) -> Dict[str, Any]:
    items = [_trim(i, "claim_kind", "holder_actor", "epistemic_status") for i in p.r.of("model_entry")
             if i["holder"] == "system" and i["live"]]
    return {"actor": "system", "entries": items[:8],
            "note": "actor-owned perspective; evidence-qualified; never world truth"}


def _s_depth(p: Projections) -> Dict[str, Any]:
    return p.depth()


SECTION_BUILDERS = {
    "person": _s_person, "relationship_with_system": _s_relationship, "recent": _s_recent,
    "matters": _s_matters, "people": _s_people, "routines_patterns": _s_routines,
    "forward": _s_forward, "unresolved": _s_unresolved, "uncertainty": _s_uncertainty,
    "coverage": _s_coverage, "system_perspective": _s_system_perspective, "depth_index": _s_depth,
}


# ---------------------------------------------------------------------- world layer (docs/WORLD_CONTRACT.md)
# Compact resident stubs for actors / relationships / events / narrative state + an index manifest + covered_through. Derived and rebuildable
# like every other section; empty (and therefore invisible to old readers) when the owner has no world rows.
# Claim kinds that state plain propositions or operational facts. Every other kind written through the world path is model-authored narrative
# state (open vocabulary: rupture, resentment, ...), so there is no closed list of narrative kinds to fall out of date.
_PROPOSITION_KINDS = frozenset({"assertion", "attribute", "commitment", "user_model", "correction", "decision", "matter_summary", "observation"})


def _is_narrative(kind: Optional[str]) -> bool:
    return bool(kind) and kind not in _PROPOSITION_KINDS


async def _world_fingerprint(db: AsyncSession, workspace_id: str, owner: Optional[str]) -> str:
    from sqlalchemy import func
    from src.models.identity import Entity, ModelEntry
    from src.models.world import ContinuationBrief, ProducerRun, RelationshipDimension, TrajectoryNote, WorldEvent, WorldObjective
    if not owner:
        return ""
    parts = []
    for model, cond in ((Entity, Entity.frame_scope == owner), (WorldEvent, WorldEvent.owner_peer_id == owner),
                        (ModelEntry, ModelEntry.owner_peer_id == owner), (ProducerRun, ProducerRun.owner_peer_id == owner),
                        (WorldObjective, WorldObjective.owner_peer_id == owner), (RelationshipDimension, RelationshipDimension.owner_peer_id == owner),
                        (TrajectoryNote, TrajectoryNote.owner_peer_id == owner), (ContinuationBrief, ContinuationBrief.owner_peer_id == owner)):
        row = (await db.execute(select(func.count(), func.max(model.updated_at) if hasattr(model, "updated_at") else func.max(model.created_at))
                                .where(model.honcho_workspace_id == workspace_id, cond))).one()
        parts.append(f"{row[0]}:{row[1]}")
    return "|".join(parts)


async def build_world_layer(db: AsyncSession, workspace_id: str, owner: Optional[str]) -> Dict[str, Any]:
    import json as _json
    from src.models.identity import Entity, EntityLink, ModelEntry, RelationshipEdge
    from src.models.world import ProducerRun, WorldEvent, WorldLink
    if not owner:
        return {}
    ents = (await db.execute(select(Entity).where(Entity.honcho_workspace_id == workspace_id, Entity.frame_scope == owner))).scalars().all()
    events = (await db.execute(select(WorldEvent).where(
        WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
        WorldEvent.superseded_by_id.is_(None)).order_by(WorldEvent.created_at.desc()).limit(12))).scalars().all()
    if not ents and not events:
        return {}
    names = {e.id: e.display_name for e in ents}
    ids = list(names)
    edges = (await db.execute(select(RelationshipEdge).where(
        RelationshipEdge.honcho_workspace_id == workspace_id, RelationshipEdge.from_entity_id.in_(ids)))).scalars().all() if ids else []
    entries = (await db.execute(select(ModelEntry).where(
        ModelEntry.honcho_workspace_id == workspace_id, ModelEntry.owner_peer_id == owner,
        ModelEntry.superseded_by_id.is_(None)).order_by(ModelEntry.updated_at.desc()))).scalars().all()
    links = (await db.execute(select(EntityLink).where(EntityLink.honcho_workspace_id == workspace_id,
                                                      EntityLink.entity_id.in_(ids)))).scalars().all() if ids else []
    wlinks = (await db.execute(select(WorldLink).where(WorldLink.honcho_workspace_id == workspace_id,
                                                      WorldLink.to_type == "relationship"))).scalars().all()
    by_event = {ev.id: ev for ev in events}
    narrative_rows = [e for e in entries if _is_narrative(e.claim_kind)]
    edge_states: Dict[Any, List[str]] = {}
    entry_by_id = {e.id: e for e in entries}
    for wl in wlinks:
        entry = entry_by_id.get(wl.from_id)
        if entry is not None and _is_narrative(entry.claim_kind):
            edge_states.setdefault(wl.to_id, []).append(entry.claim[:110])
    actors = []
    for e in ents:
        mine = [x for x in entries if x.subject_entity_id == e.id and not _is_narrative(x.claim_kind) and x.epistemic_status != "superseded"]
        rel = [f"{ed.role} of {names.get(ed.to_entity_id) if ed.from_entity_id == e.id else names.get(ed.from_entity_id)}"
               for ed in edges if e.id in (ed.from_entity_id, ed.to_entity_id)]
        event_ids = [l.object_id for l in links if l.entity_id == e.id and l.object_type == "event" and l.object_id in by_event]
        last = max((by_event[i] for i in event_ids), key=lambda ev: ev.created_at, default=None)
        matters = len({l.object_id for l in links if l.entity_id == e.id and l.object_type == "matter"})
        actors.append({"ref": str(e.id), "name": e.display_name, "type": e.entity_type, "provisional": e.provisional,
                       "relations": rel[:3], "claims": [x.claim[:90] for x in sorted(mine, key=lambda x: -x.confidence)[:3]],
                       "matters": matters, "last_event": last.label[:80] if last else None})
    relationships = [{"ref": str(ed.id), "type": ed.role, "parties": [names.get(ed.from_entity_id), names.get(ed.to_entity_id)],
                      "states": edge_states.get(ed.id, [])[:2]} for ed in edges]
    ev_stubs = [{"ref": str(ev.id), "label": ev.label[:90], "kind": ev.kind, "when": ev.when_phrase, "where": ev.place, "status": ev.status,
                 "participants": [names.get(l.entity_id) for l in links if l.object_type == "event" and l.object_id == ev.id and names.get(l.entity_id)]}
                for ev in events]
    narrative = [{"ref": str(x.id), "kind": x.claim_kind, "text": x.claim[:130], "formation": x.formation, "status": x.epistemic_status}
                 for x in sorted(narrative_rows, key=lambda x: (-x.confidence, x.claim))[:8]]
    runs = (await db.execute(select(ProducerRun).where(ProducerRun.honcho_workspace_id == workspace_id, ProducerRun.owner_peer_id == owner,
                                                       ProducerRun.status == "applied").order_by(ProducerRun.created_at.desc()))).scalars().all()
    covered = {}
    for r in runs:
        if r.producer not in covered and r.covered_through_json and r.covered_through_json != "{}":
            covered[r.producer] = {**_json.loads(r.covered_through_json), "run_id": str(r.id), "at": r.created_at.isoformat()}
    continuation = await build_continuation(db, workspace_id, owner, names, edges, narrative_rows, actors, now=datetime.now(timezone.utc).replace(tzinfo=None))
    return {
        "actors": actors, "relationships": relationships, "events": ev_stubs, "narrative": narrative, **continuation,
        "world_index": {"actors": [{"ref": a["ref"], "name": a["name"]} for a in actors], "events": len(events), "narrative": len(narrative_rows),
                        "available_via": {"actor": "projection person(entity_id)", "matter": "projection matter(matter_id)",
                                          "timeline": "projection timeline", "evidence": "Honcho message ids in evidence_refs"}},
        "covered_through": covered,
    }


ACUTE_TTL = timedelta(hours=72)     # explicit lifecycle policy: a moment-in-time reading lapses unless a later pass re-affirms it


async def build_continuation(db: AsyncSession, workspace_id: str, owner: str, names: Dict[Any, str], edges: List[Any], narrative_rows: List[Any],
                             actors: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Continuation projection: the interpreter's versioned brief (a projection of structured state, never a source of truth), plus the current
    objectives, directional relationship dimensions and the live trajectory note, plus a routing manifest. Code only reads, orders by recency and
    renders: it chooses no meaning."""
    from src.models.matter import Matter
    from src.models.world import ContinuationBrief, RelationshipDimension, TrajectoryNote, WorldObjective
    brief = (await db.execute(select(ContinuationBrief).where(
        ContinuationBrief.honcho_workspace_id == workspace_id, ContinuationBrief.owner_peer_id == owner,
        ContinuationBrief.superseded_by_id.is_(None)).order_by(ContinuationBrief.created_at.desc()).limit(1))).scalars().first()
    dims = (await db.execute(select(RelationshipDimension).where(
        RelationshipDimension.honcho_workspace_id == workspace_id, RelationshipDimension.owner_peer_id == owner,
        RelationshipDimension.superseded_by_id.is_(None)).order_by(RelationshipDimension.updated_at.desc()).limit(40))).scalars().all()
    objectives = (await db.execute(select(WorldObjective).where(
        WorldObjective.honcho_workspace_id == workspace_id, WorldObjective.owner_peer_id == owner,
        WorldObjective.status == "current").order_by(WorldObjective.updated_at.desc()))).scalars().all()
    notes = (await db.execute(select(TrajectoryNote).where(
        TrajectoryNote.honcho_workspace_id == workspace_id, TrajectoryNote.owner_peer_id == owner,
        TrajectoryNote.superseded_by_id.is_(None)).order_by(TrajectoryNote.created_at.desc()))).scalars().all()
    if now is not None:
        notes = [n for n in notes if n.expires_at is None or n.expires_at > now]
        dims = [d for d in dims if d.durability != "acute" or now - d.updated_at < ACUTE_TTL]
        objectives = [o for o in objectives if o.durability != "acute" or o.scope == "constitutional" or now - o.updated_at < ACUTE_TTL]
    const = next((o for o in objectives if o.scope == "constitutional"), None)
    intent: Dict[str, Any] = {"constitution": ({"actor": names.get(const.actor_entity_id), "text": const.text, "state": const.state, "ref": str(const.id)}
                                              if const else None), "objectives": [], "trajectory_note": None}
    for o in [o for o in objectives if o.scope != "constitutional"][:10]:
        intent["objectives"].append({"ref": str(o.id), "actor": names.get(o.actor_entity_id), "toward": names.get(o.toward_entity_id) if o.toward_entity_id else None,
                                     "text": o.text, "scope": o.scope, "state": o.state, "durability": o.durability, "strength": o.strength, "cause": o.cause,
                                     "conflicts": _json_list(o.conflicts_json)})
    mine = [n for n in notes if const is not None and n.actor_entity_id == const.actor_entity_id] or notes     # the constitutional actor's own note
    if mine:
        intent["trajectory_note"] = {"ref": str(mine[0].id), "actor": names.get(mine[0].actor_entity_id), "state": mine[0].state, "text": mine[0].note,
                                      "label": "interpretation", "expires_at": mine[0].expires_at.isoformat() if mine[0].expires_at else None}
    matters = (await db.execute(select(Matter).where(Matter.honcho_workspace_id == workspace_id, Matter.owner_peer_id == owner,
                                                    Matter.status == "active"))).scalars().all()
    manifest = {"actors": [{"ref": a["ref"], "name": a["name"]} for a in actors],
                "relationships": [{"ref": str(ed.id), "type": ed.role} for ed in edges],
                "matters": [{"ref": str(m.id), "title": m.title} for m in matters[:8]], "objectives": len(objectives)}
    return {"continuation": {
        "brief": {"text": brief.text if brief else "", "lines": _json_list(brief.lines_json) if brief else [], "version": str(brief.id) if brief else None,
                  "derived_from": "interpreter projection of structured world state"},
        "dimensions": [{"ref": str(d.id), "from": names.get(d.from_entity_id), "to": names.get(d.to_entity_id), "dimension": d.dimension, "value": d.value,
                        "durability": d.durability, "formation": d.formation} for d in dims],
        "active_intent": intent, "manifest": manifest}}


def _json_list(raw: Optional[str]) -> List[Any]:
    try:
        return json.loads(raw or "[]")
    except ValueError:
        return []


# ---------------------------------------------------------------------- service
async def _latest(db: AsyncSession, scope: Scope) -> Optional[WorldModelSnapshot]:
    stmt = select(WorldModelSnapshot).where(
        WorldModelSnapshot.honcho_workspace_id == scope.workspace_id,
        WorldModelSnapshot.superseded_by_id.is_(None))
    stmt = stmt.where(WorldModelSnapshot.owner_peer_id == scope.owner_peer_id) if scope.owner_peer_id \
        else stmt.where(WorldModelSnapshot.owner_peer_id.is_(None))
    return (await db.execute(stmt.order_by(WorldModelSnapshot.compiled_at.desc()).limit(1))).scalars().first()


def _envelope(snapshot: WorldModelSnapshot, status: str, stale: List[str]) -> Dict[str, Any]:
    body = json.loads(snapshot.snapshot_json)
    body["meta"] = {**body.get("meta", {}), "snapshot_id": str(snapshot.id), "version": snapshot.version,
                    "compiled_at": snapshot.compiled_at.isoformat(), "freshness": status,
                    "patched_sections": stale}
    return body


async def compile_world_model(db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
                              now: datetime, timezone_str: str = "UTC", session_id: Optional[str] = None,
                              force: bool = False, sync: bool = False) -> Dict[str, Any]:
    """Compile (or patch) and persist the WorldModel. Returns the model with
    `meta` (snapshot id/version/freshness/patched sections). The snapshot is
    product-NEUTRAL (shared reality stays shared): product weighting is applied
    only by projections at read time.

    A READ never mutates canonical state: Matter reconciliation
    (`sync_primitives`) is owned by mutation boundaries (sweeper, session
    consolidation, backfill, explicit /matters/sync). This function writes
    only disposable derived state (snapshot + coverage rows). `sync=True` is
    for those boundaries (backfill passes it explicitly)."""
    now_n = naive(now)
    scope = await resolve_scope(db, workspace_id, owner_peer_id, session_id)
    prev = await _latest(db, scope)
    tables = await _table_fingerprints(db, scope, now_n, timezone_str)
    fps = _section_fps(tables)
    prim_fp = _primitive_fp(tables)
    world_fp = await _world_fingerprint(db, workspace_id, owner_peer_id)
    prev_body = json.loads(prev.snapshot_json) if prev else {}
    prev_fps = json.loads(prev.fingerprints_json) if prev else {}
    fresh_age = prev is not None and (now_n - prev.compiled_at) < timedelta(hours=TTL_HOURS) \
        and (now_n - prev.compiled_at) >= timedelta(0)
    stale = list(SECTION_BUILDERS) if (force or prev is None or not fresh_age) else [
        s for s in SECTION_BUILDERS if prev_fps.get(s) != fps[s] or s not in prev_body]
    world_changed = prev is not None and prev_fps.get("_world", "") != world_fp
    if prev is not None and not stale and not world_changed:
        return _envelope(prev, "fresh", [])

    sync_stats = None
    if sync and (force or prev is None or prev_fps.get("_primitives") != prim_fp or not fresh_age):
        sync_stats = await ms.sync_primitives(db, workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                                              session_id=session_id, now=now_n, scope=scope)
        tables = await _table_fingerprints(db, scope, now_n, timezone_str)
        fps = _section_fps(tables)
        prim_fp = _primitive_fp(tables)
        stale = list(SECTION_BUILDERS) if (force or prev is None or not fresh_age) else [
            s for s in SECTION_BUILDERS if prev_fps.get(s) != fps[s] or s not in prev_body]
    reader = await open_reader(db, workspace_id, owner_peer_id, now_n, timezone_str, session_id, scope=scope)
    # coverage derives from the reader first (sections consume it)
    await kcs.refresh(db, reader)
    cov = await kcs.read(db, scope)
    projections = Projections(reader, cov)
    # coverage rows changed -> recompute fingerprint of dependent sections
    tables = await _table_fingerprints(db, scope, now_n, timezone_str)
    fps = _section_fps(tables)
    body: Dict[str, Any] = {k: v for k, v in prev_body.items() if k not in stale and k in SECTION_BUILDERS}
    for name in stale:
        body[name] = SECTION_BUILDERS[name](projections)
    body.update(await build_world_layer(db, workspace_id, owner_peer_id))
    try:
        from src.services import executive
        body["executive"] = await executive.executive_layer(db, workspace_id, owner_peer_id or "", now_n)
    except Exception:
        body["executive"] = {}
    body["meta"] = {
        "model_version": WORLD_MODEL_VERSION, "scope": {"workspace_id": workspace_id, "owner_peer_id": owner_peer_id},
        "timezone": timezone_str, "user_day": reader.day.today.isoformat(),
        "authoritative": False,
        "contract": ["derived and reconstructable; authoritative state is the Cortex primitives",
                     "never insert the whole model into a prompt; query projections for fragments"],
        "sync": sync_stats,
    }
    snap = WorldModelSnapshot(
        honcho_workspace_id=workspace_id, owner_peer_id=owner_peer_id,
        version=(prev.version + 1) if prev else 1, compiled_at=now_n,
        snapshot_json=json.dumps(body, default=str),
        fingerprints_json=json.dumps({**fps, "_primitives": _primitive_fp(tables), "_world": world_fp}))
    db.add(snap)
    await db.flush()
    if prev is not None:
        prev.superseded_by_id = snap.id
        db.add(prev)
    await db.commit()
    return _envelope(snap, "compiled" if prev is None or len(stale) == len(SECTION_BUILDERS) else "patched", stale)


async def get_world_model(db: AsyncSession, **kwargs: Any) -> Dict[str, Any]:
    """Cheap read: returns the stored snapshot when fresh, patches stale
    sections otherwise."""
    return await compile_world_model(db, **kwargs)


async def invalidate(db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
                     sections: Optional[List[str]] = None) -> Dict[str, Any]:
    """Mark sections (default: all) stale. The snapshot stays recoverable; the
    next read recompiles exactly what was invalidated."""
    scope = await resolve_scope(db, workspace_id, owner_peer_id)
    snap = await _latest(db, scope)
    if snap is None:
        return {"invalidated": [], "had_snapshot": False}
    fps = json.loads(snap.fingerprints_json)
    names = list(SECTION_BUILDERS) if not sections else [s for s in sections if s in SECTION_BUILDERS]
    for s in names:
        fps[s] = "invalidated"
    snap.fingerprints_json = json.dumps(fps)
    db.add(snap)
    await db.commit()
    return {"invalidated": names, "had_snapshot": True}
