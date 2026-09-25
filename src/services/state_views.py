"""Derived state views: reusable intelligence, not foreground packets.

Architecture: durable state + semantic relations -> THESE derivations ->
consumers (packet compiler, moves, operationalisation, planner) select,
rank, truncate, and project minimally per turn.

Deliberately does NOT call compile_attention_packet: the packet compiler
adds ranking, truncation, foreground selection, and write side effects
(occurrence creation, surface marking). Views must be queryable without
those — full untruncated lists; consumers narrow per turn.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import TemporalState

logger = logging.getLogger(__name__)


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def _active_suppressions(db: AsyncSession, workspace_id: str,
                               now: datetime):
    from src.models.suppression import Suppression, SuppressionStatus
    rows = (await db.execute(select(Suppression).where(
        Suppression.honcho_workspace_id == workspace_id,
        Suppression.status == SuppressionStatus.ACTIVE,
    ))).scalars().all()
    now_utc = _naive_utc(now)
    live = [s for s in rows
            if not (s.suppressed_until and s.suppressed_until < now_utc)]
    return live


def _suppressed_ids(suppressions, kind: str) -> set:
    out = set()
    for s in suppressions:
        if str(getattr(s.target_type, "value", s.target_type) or "") == kind \
                and getattr(s, "target_id", None):
            out.add(str(s.target_id))
    return out


async def compile_views(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: Optional[str],
    now: datetime,
    timezone_str: str = "UTC",
) -> Dict[str, List[Dict[str, Any]]]:
    """Project the nine read views. Full lists; consumers select per turn."""
    from src.models.attention_candidate import (
        AttentionCandidate, AttentionCandidateStatus,
    )
    from src.models.clarification import ClarificationCandidate, ClarificationStatus
    from src.models.commitment_candidate import (
        CommitmentCandidate, CommitmentCandidateStatus,
    )
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.models.operational_state import RecurringOccurrence
    from src.models.work_item import WorkItem
    from src.models.semantic import SemanticClaim, SemanticRelation
    from src.services import semantic_views as graph
    from src.services.expectation_engine import derive_expectation_read_model
    from src.services.state_roles import derive_roles

    suppressions = await _active_suppressions(db, workspace_id, now)
    supp_exp = _suppressed_ids(suppressions, "expectation")
    supp_loop = _suppressed_ids(suppressions, "open_loop")

    exps = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.honcho_session_id == session_id,
        Expectation.superseded_by_id.is_(None),
    ).order_by(Expectation.created_at.desc()).limit(60))).scalars().all()
    unknowns = [e for e in exps
                if e.outcome_state == OutcomeState.UNKNOWN
                and str(e.id) not in supp_exp]
    read_models = {str(e.id): derive_expectation_read_model(e, now) for e in unknowns}

    loops = (await db.execute(select(OpenLoop).where(
        OpenLoop.honcho_workspace_id == workspace_id,
        OpenLoop.honcho_session_id == session_id,
        OpenLoop.status == OpenLoopStatus.OPEN,
    ).order_by(OpenLoop.created_at.desc()).limit(20))).scalars().all()
    loops = [lp for lp in loops if str(lp.id) not in supp_loop]

    clars = (await db.execute(select(ClarificationCandidate).where(
        ClarificationCandidate.honcho_workspace_id == workspace_id,
        ClarificationCandidate.honcho_session_id == session_id,
        ClarificationCandidate.status == ClarificationStatus.PENDING,
    ).limit(10))).scalars().all()

    atts = (await db.execute(select(AttentionCandidate).where(
        AttentionCandidate.honcho_workspace_id == workspace_id,
        AttentionCandidate.honcho_session_id == session_id,
        AttentionCandidate.status.in_([AttentionCandidateStatus.ACTIVE,
                                       AttentionCandidateStatus.SURFACED]),
    ).limit(20))).scalars().all()

    cands = (await db.execute(select(CommitmentCandidate).where(
        CommitmentCandidate.honcho_workspace_id == workspace_id,
        CommitmentCandidate.honcho_session_id == session_id,
        CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
    ).limit(10))).scalars().all()

    work_items = (await db.execute(select(WorkItem).where(
        WorkItem.honcho_workspace_id == workspace_id,
    ).order_by(WorkItem.created_at.desc()).limit(20))).scalars().all()

    occs = (await db.execute(select(RecurringOccurrence).where(
        RecurringOccurrence.honcho_workspace_id == workspace_id,
    ).order_by(RecurringOccurrence.created_at.desc()).limit(10))).scalars().all()

    claims = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == workspace_id).limit(200))).scalars().all()
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == workspace_id).limit(200))).scalars().all()
    roles = derive_roles(expectations=exps, open_loops=loops, commitments=cands,
                         clarifications=clars, attentions=atts,
                         relations=rels, claims=claims, now=now)

    def has_role(kind: str, row_id: Any, *want: str) -> bool:
        have = set(roles.get(f"{kind}:{row_id}", []))
        return bool(have & set(want))

    todo = ([{"kind": "expectation", "id": str(e.id), "title": e.title,
              "why": f"unknown {read_models[str(e.id)].get('temporal_state')}",
              "roles": roles.get(f"expectation:{e.id}", [])}
             for e in unknowns]
            + [{"kind": "work_item", "id": str(w.id),
                "title": f"{w.action} ({w.parent_title})" if w.parent_title else w.action,
                "why": f"work item {w.status}"}
               for w in work_items
               if str(getattr(w.status, "value", w.status) or "") in (
                   "proposed", "surfaced", "in_progress")])

    due = _due_windows(unknowns, now)
    reminder = ([{"kind": "reminder", "id": str(e.id), "title": e.title,
                  "why": "reminder window due"}
                 for e in due]
                + [{"kind": "occurrence", "id": str(o.id),
                    "title": f"recurring occurrence {o.user_day}",
                    "why": "pending occurrence"}
                   for o in occs
                   if str(getattr(o.status, "value", o.status) or "") == "pending"])

    calendar = [{"kind": "expectation", "id": str(e.id), "title": e.title,
                 "why": f"planned event {read_models[str(e.id)].get('temporal_state')}"}
                for e in unknowns
                if str(getattr(e.expectation_type, "value", e.expectation_type)
                       or "") == "planned_event"]

    open_matter = ([{"kind": "open_loop", "id": str(lp.id),
                     "title": f"{lp.title or ''} {lp.summary or ''}".strip(),
                     "why": "open loop"}
                    for lp in loops]
                   + [{"kind": "expectation", "id": str(e.id), "title": e.title,
                       "why": "unknown expectation"}
                      for e in unknowns]
                   + [{"kind": "clarification", "id": str(c.id),
                       "title": c.description, "why": "pending clarification"}
                      for c in clars])

    waiting_on = ([{"kind": "expectation", "id": str(e.id), "title": e.title,
                    "why": f"third-party subject {e.subject_peer_id}"}
                   for e in unknowns
                   if (e.subject_peer_id or "").lower() not in (
                       "", (owner_peer_id or "").lower(), "sophie")]
                  + [{"kind": "graph", "title": t, "why": "relation-backed waiting-on"}
                     for t in graph.waiting_on(list(claims), list(rels))])

    worry = [{"kind": "annotation", "id": a["id"], "title": a["title"], "why": a["why"]}
             for a in await _worry_annotations(
                 db, workspace_id=workspace_id, session_id=session_id,
                 owner_peer_id=owner_peer_id)]

    follow_up = ([{"kind": "expectation", "id": str(e.id), "title": e.title,
                   "why": "follow-up eligible"}
                  for e in unknowns
                  if _followup_eligible(read_models[str(e.id)].get("temporal_state"),
                                        e.outcome_state)]
                 + [{"kind": "clarification", "id": str(c.id),
                     "title": c.description, "why": "pending clarification"}
                    for c in clars])

    companion_obligation = (
        [{"kind": "commitment", "id": str(c.id),
          "title": c.title,
          "why": "actionable self commitment"}
         for c in cands
         if str(getattr(c.authority, "value", c.authority) or "") == "act"]
        + [{"kind": "work_item", "id": str(w.id),
            "title": f"{w.action} ({w.parent_title})" if w.parent_title else w.action,
            "why": "sophie-owned work"}
           for w in work_items
           if str(getattr(w, "owner", "") or "").lower() == "sophie"])

    opportunities = ([{"kind": "attention", "id": str(a.id), "title": a.content,
                       "why": f"latent {a.kind}"}
                      for a in atts]
                     + [{"kind": "open_loop", "id": str(lp.id),
                         "title": f"{lp.title or ''} {lp.summary or ''}".strip(),
                         "why": "reentry opportunity"}
                        for lp in loops])
    relationship_context = await _relationship_context(
        db, workspace_id=workspace_id, session_id=session_id,
        owner_peer_id=owner_peer_id)
    narrative_continuity = await _narrative_continuity(
        db, workspace_id=workspace_id, session_id=session_id, unknowns=unknowns,
        loops=loops, cands=cands, user_peer_id=owner_peer_id)

    views = {
        "todo": todo, "reminder": reminder, "calendar": calendar,
        "open_matter": open_matter, "waiting_on": waiting_on, "worry": worry,
        "follow_up": follow_up, "companion_obligation": companion_obligation,
        "conversation_opportunity": opportunities,
        "relationship_context": relationship_context,
        "narrative_continuity": narrative_continuity,
    }
    return _with_signals(views)


# Section-level machine signals for downstream pressure/attention policy.
# Deterministic from section/kind provenance — never content inspection.
_SECTION_SIGNALS = {
    "todo": {"actionable": True},
    "reminder": {"urgent": True, "actionable": True},
    "calendar": {"actionable": True},
    "follow_up": {"actionable": True},
    "worry": {"protective": True},
    "companion_obligation": {"actionable": True},
}


def _with_signals(views: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for section, view_items in views.items():
        base = {"protective": False, "urgent": False, "actionable": False,
                **_SECTION_SIGNALS.get(section, {})}
        annotated = []
        for item in view_items or []:
            if not isinstance(item, dict):
                continue
            signals = dict(base)
            if item.get("kind") == "commitment":
                signals["actionable"] = True
            annotated.append({**item, "signals": signals})
        out[section] = annotated
    return out


def _followup_eligible(temporal_value: Any, outcome: Any) -> bool:
    """Read-only wrapper: string temporal states back to enum members."""
    from src.services.expectation_engine import is_followup_eligible
    try:
        temporal = TemporalState(str(temporal_value))
    except ValueError:
        return False
    return bool(is_followup_eligible(temporal, outcome))


def _due_windows(unknowns: List[Any], now: datetime) -> List[Any]:
    """Read-only due scan over reminder windows (no fired-marking; the
    executor owns mutation)."""
    import json as _json
    now_utc = _naive_utc(now)
    due = []
    for exp in unknowns:
        try:
            windows = _json.loads(exp.reminder_windows_json or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(windows, list):
            continue
        for w in windows:
            if not isinstance(w, dict) or w.get("fired"):
                continue
            try:
                start = datetime.fromisoformat(str(w.get("start", "")))
            except ValueError:
                continue
            if start.tzinfo:
                start = start.astimezone(timezone.utc).replace(tzinfo=None)
            if start <= now_utc:
                due.append(exp)
                break
    return due


async def _relationship_context(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    owner_peer_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Relationship trajectory + salient history from model-produced rows
    (ModelEntry claims, relationship edges, T2, emotional landmarks).
    Structure and provenance preserved; no compression into prose."""
    from src.models.current_meaning import scope_key_for
    from src.models.domain_annotation import (
        CategoryTag, DomainAnnotation, DomainTag,
    )
    from src.models.identity import ModelEntry, RelationshipEdge
    from src.services.current_meaning_service import get_active, row_to_dict

    entries = (await db.execute(select(ModelEntry).where(
        ModelEntry.honcho_workspace_id == workspace_id,
        ModelEntry.honcho_session_id == session_id,
    ).order_by(ModelEntry.created_at.desc()).limit(10))).scalars().all()
    edges = (await db.execute(select(RelationshipEdge).where(
        RelationshipEdge.honcho_workspace_id == workspace_id,
    ).limit(10))).scalars().all()
    landmarks = (await db.execute(select(DomainAnnotation).where(
        DomainAnnotation.honcho_workspace_id == workspace_id,
        DomainAnnotation.honcho_session_id == session_id,
        DomainAnnotation.domain == DomainTag.EMOTIONAL_LANDMARK,
    ).order_by(DomainAnnotation.created_at.desc()).limit(5))).scalars().all()
    items = ([{"kind": "model_entry", "id": str(e.id), "title": e.claim,
               "why": f"{e.model_kind} belief ({e.formation})"}
              for e in entries]
             + [{"kind": "relationship_edge", "id": str(g.id),
                 "title": f"{g.from_entity_id}->{g.to_entity_id} ({g.role})",
                 "why": "relationship structure"}
                for g in edges]
             + [{"kind": "emotional_landmark", "id": str(m.id),
                 "title": m.annotation_summary, "why": str(m.category.value)}
                for m in landmarks])
    try:
        scope = scope_key_for(workspace_id, "sophie", session_id, owner_peer_id)
        current = await get_active(db, scope_key=scope)
        if current is not None:
            data = row_to_dict(current)
            items.append({"kind": "current_meaning", "id": str(data.get("id")),
                          "title": "; ".join(data.get("means", []) or [])[:280],
                          "why": "T2 trajectory context"})
    except Exception as err:
        logger.warning("relationship context T2 read failed: %s", err)
    return items


async def _narrative_continuity(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    unknowns: List[Any], loops: List[Any], cands: List[Any],
    user_peer_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """World/character commitments, expected external events, unresolved
    scene threads — the hook-generator surface for narrative continuity.
    Third-party/character undertakings stay first-class world state here,
    never converted into user/Sophie self-debt. The session user is
    explicitly NOT a character."""
    items = []
    self_peers = {"", "sophie", "user", (user_peer_id or "").lower()}
    for c in cands:
        owner = str(getattr(c, "owner_peer_id", "") or "")
        evidence_class = str(getattr(c, "evidence_class", "") or "")
        if owner.lower() not in self_peers or "character" in evidence_class:
            items.append({"kind": "character_undertaking", "id": str(c.id),
                          "title": c.title, "why": f"owned by {owner or 'character'}"})
    for e in unknowns:
        etype = str(getattr(e.expectation_type, "value", e.expectation_type) or "")
        if etype in ("external_dependency", "planned_event"):
            items.append({"kind": "expected_event", "id": str(e.id),
                          "title": e.title, "why": f"expected {etype}"})
    for lp in loops:
        items.append({"kind": "scene_thread", "id": str(lp.id),
                      "title": f"{lp.title or ''} {lp.summary or ''}".strip(),
                      "why": "unresolved thread"})
    return items


async def _worry_annotations(    db: AsyncSession, *, workspace_id: str, session_id: str,
    owner_peer_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Worry/concern from model-produced domain annotations (struggle, fear,
    emotional landmarks) — never keyword matching over raw text."""
    from sqlalchemy import or_
    from src.models.domain_annotation import (
        CategoryTag, DomainAnnotation, DomainTag,
    )
    rows = (await db.execute(select(DomainAnnotation).where(
        DomainAnnotation.honcho_workspace_id == workspace_id,
        DomainAnnotation.honcho_session_id == session_id,
        or_(
            DomainAnnotation.category.in_([CategoryTag.STRUGGLE, CategoryTag.FEAR]),
            DomainAnnotation.domain.in_([DomainTag.HEALTH, DomainTag.FAMILY,
                                         DomainTag.RELATIONSHIP,
                                         DomainTag.EMOTIONAL_LANDMARK]),
        ),
    ).order_by(DomainAnnotation.created_at.desc()).limit(6))).scalars().all()
    return [{"id": str(r.id), "title": r.annotation_summary,
             "why": f"model-annotated {r.domain.value}/{r.category.value}"}
            for r in rows]
