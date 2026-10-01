"""Projections: views over shared Cortex state — never separate memory stores.

person(entity_id) · matter(matter_id) · timeline(subject, window) · today() ·
week() · period(start, end) · unresolved() · recent_changes() ·
knowledge_gaps() · depth() · why(object)

Person cards, project cards and period views are *projections of the
primitives*: they are computed from a transient WorldReader on demand, carry
formation/confidence/evidence refs on every claim, and persist nothing.
(docs/CORTEX_ARCHITECTURE.md §7)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import knowledge_coverage_service as kcs
from src.services import matter_service as ms
from src.services.epistemics import entry_view, explain
from src.services.world_read import Item, WorldReader, iso, naive, open_reader

TERMINAL = {"fulfilled", "cancelled", "superseded", "resolved", "abandoned", "expired",
            "done", "dismissed", "violated", "completed"}
CAPS = {"matters": 12, "items": 8, "people": 8}


def _trim(item: Item, *extra: str) -> Dict[str, Any]:
    """Compact public item: provenance + direction always kept."""
    keys = ("ref", "kind", "title", "status", "direction", "holder", "formation", "confidence",
            "evidence_refs", "matter_id") + extra
    out = {k: item[k] for k in keys if k in item}
    for k in ("created_at", "updated_at"):
        out[k] = iso(item.get("_" + k))
    return out


def _rank(reader: WorldReader, matter, weights: Optional[Dict[str, float]] = None,
          kind_weights: Optional[Dict[str, float]] = None) -> float:
    base = ms.foreground_rank(reader.components(matter), weights)
    return round(base * float((kind_weights or {}).get(matter.kind, 1.0)), 4)


class Projections:
    def __init__(self, reader: WorldReader, coverage: Optional[List[Dict[str, Any]]] = None,
                 weights: Optional[Dict[str, float]] = None,
                 kind_weights: Optional[Dict[str, float]] = None):
        self.r = reader
        self.coverage = coverage or []
        self.weights = weights            # product policy over salience components
        self.kind_weights = kind_weights  # product policy over generic Matter kinds

    # -------------------------------------------------------------- helpers
    def _matter_brief(self, m, *, with_members: int = 0) -> Dict[str, Any]:
        comp = self.r.components(m)
        out = {
            "id": str(m.id), "title": m.title, "kind": m.kind, "status": m.status,
            "first_seen": iso(m.first_seen), "last_touched": iso(m.last_touched),
            "resolved_at": iso(m.resolved_at), "formation": m.formation,
            "components": {k: v for k, v in comp.items() if k != "raw"},
            "rank": _rank(self.r, m, self.weights, self.kind_weights),
            "people": [self.r.entity_name(e) for e in sorted(self.r.matter_entities.get(m.id, ()), key=str)][:4],
        }
        if with_members:
            members = sorted(self.r.matter_items(m.id), key=lambda i: (not i["live"], -i["_updated_at"].timestamp()))
            out["members"] = [_trim(i) for i in members[:with_members]]
        return out

    def _ranked_matters(self, statuses=("active",)) -> List[Any]:
        ms_ = [m for m in self.r.matters.values() if m.status in statuses]
        return sorted(ms_, key=lambda m: (-_rank(self.r, m, self.weights, self.kind_weights), m.title))

    # --------------------------------------------------------------- person
    def person(self, entity_id: Optional[UUID] = None) -> Dict[str, Any]:
        """Person card. entity_id=None → the user overview ("who is this person")."""
        r = self.r
        if entity_id is None:
            return self.user_overview()
        ent = r.entities.get(entity_id)
        if ent is None:
            return {"found": False, "entity_id": str(entity_id)}
        eid = str(entity_id)
        edges = [{"role": e.role, "from": r.entity_name(e.from_entity_id), "to": r.entity_name(e.to_entity_id),
                  "confidence": e.confidence, "evidence_refs": [e.provenance_message_id] if e.provenance_message_id else []}
                 for e in r.edges if entity_id in (e.from_entity_id, e.to_entity_id)]
        linked = [i for i in r.items if eid in i["entity_ids"]]
        matters = [self._matter_brief(m) for m in self._ranked_matters(("active", "dormant"))
                   if entity_id in r.matter_entities.get(m.id, ())]
        claims = [i for i in r.of("model_entry") if i.get("subject_entity_id") == eid]
        return {
            "found": True, "entity_id": eid, "name": ent.display_name, "entity_type": ent.entity_type,
            "provisional": ent.provisional, "confidence": ent.confidence,
            "relationships": edges,
            "matters": matters[:CAPS["matters"]],
            "live": [_trim(i) for i in linked if i["live"]][:CAPS["items"]],
            "facts": [_trim(i) for i in linked if i["kind"] == "fact"][:CAPS["items"]],
            "claims": [_trim(i, "claim_kind", "holder_actor", "epistemic_status") for i in claims][:CAPS["items"]],
            "coverage": [c for c in self.coverage if c["subject_key"].startswith(
                "people/" + kcs._slug(ent.display_name))],
            "last_seen": iso(max((i["_updated_at"] for i in linked), default=None)),
            "note": "projection of canonical state; not a separate store",
        }

    def user_overview(self) -> Dict[str, Any]:
        r = self.r
        facts = [i for i in r.of("fact") if i["holder"] == "user"]
        claims = [i for i in r.of("model_entry")
                  if i.get("model_kind") == "user" and i["holder"] != "system"
                  and i["status"] in ("current", "uncertain", "conflicting")]
        circle = []
        for eid, e in r.entities.items():
            if e.entity_type != "person":
                continue
            its = [i for i in r.items if str(eid) in i["entity_ids"]]
            role = next((ed.role for ed in r.edges if eid in (ed.from_entity_id, ed.to_entity_id)), None)
            circle.append({"entity_id": str(eid), "name": e.display_name, "role": role,
                           "mentions": len(its), "last_seen": iso(max((i["_updated_at"] for i in its), default=None))})
        circle.sort(key=lambda c: (-c["mentions"], c["name"]))
        return {
            "found": True, "subject": "user", "scope": r.scope.owner_peer_id,
            "facts": [_trim(i, "category") for i in sorted(facts, key=lambda i: -i["_updated_at"].timestamp())][:CAPS["items"] + 4],
            "claims": [_trim(i, "claim_kind", "holder_actor", "epistemic_status") for i in claims][:CAPS["items"] + 4],
            "circle": circle[:CAPS["people"]],
            "alive_matters": [self._matter_brief(m) for m in self._ranked_matters()][:6],
            "routines_declared": [_trim(i, "cadence", "preferred_window") for i in r.of("recurrence", live=True) if i["declared"]][:6],
            "note": "every claim carries formation/confidence/evidence; unknowns are in knowledge_gaps",
        }

    # --------------------------------------------------------------- matter
    def matter(self, matter_id: UUID) -> Dict[str, Any]:
        r = self.r
        m = r.matters.get(matter_id)
        if m is None:
            return {"found": False, "matter_id": str(matter_id)}
        items = r.matter_items(matter_id)
        by_dir: Dict[str, List[Dict[str, Any]]] = {}
        for i in sorted(items, key=lambda i: (not i["live"], -i["_updated_at"].timestamp())):
            if i["kind"] in ("model_entry", "fact"):
                continue
            by_dir.setdefault(i["direction"] or "unspecified", []).append(_trim(i))
        claims = [i for i in items if i["kind"] == "model_entry"]
        summary = None
        if m.summary_entry_id:
            se = next((e for e in r.model_entries if e.id == m.summary_entry_id), None)
            while se is not None and se.superseded_by_id:
                se = next((e for e in r.model_entries if e.id == se.superseded_by_id), None)
            summary = entry_view(se, r.now) if se else None
        rels = []
        for rel in r.matter_relations:
            if matter_id in (rel.from_matter_id, rel.to_matter_id):
                other = rel.to_matter_id if rel.from_matter_id == matter_id else rel.from_matter_id
                om = r.matters.get(other)
                rels.append({"rel_type": rel.rel_type,
                             "direction": "out" if rel.from_matter_id == matter_id else "in",
                             "matter_id": str(other), "title": om.title if om else None,
                             "formation": rel.formation, "confidence": rel.confidence})
        card = self._matter_brief(m)
        card.update({
            "found": True,
            "salience_raw": r.components(m).get("raw", {}),
            "summary": summary,   # via ModelEntry reference; None when no summary claim exists
            "by_direction": by_dir,
            "claims": [_trim(c, "claim_kind", "holder_actor", "epistemic_status") for c in claims
                       if c["holder"] != "system"],
            "system_perspectives": [_trim(c, "claim_kind", "holder_actor", "epistemic_status") for c in claims
                                    if c["holder"] == "system"],
            "relations": rels,
            "unresolved": [_trim(i) for i in items if i["live"] and i["kind"] not in ("model_entry", "fact")],
            "timeline": self.timeline(("matter", matter_id))["events"][-8:],
            "depth": {"why": "projection why(ref) for any ref above",
                      "longitudinal_read": {"matter_refs": [str(matter_id)]}},
        })
        return card

    # ------------------------------------------------------------- timeline
    def timeline(self, subject: Tuple[str, Any], start: Optional[datetime] = None,
                 end: Optional[datetime] = None) -> Dict[str, Any]:
        """Events for a matter or entity, oldest first, from canonical rows."""
        r = self.r
        stype, sid = subject[0], str(subject[1])
        if stype == "matter":
            items = r.matter_items(UUID(sid))
            m = r.matters.get(UUID(sid))
        elif stype == "entity":
            items, m = [i for i in r.items if sid in i["entity_ids"]], None
        else:
            raise ValueError("timeline subject must be ('matter'|'entity', id)")
        events: List[Dict[str, Any]] = []
        if m is not None:
            events.append({"at": iso(m.first_seen), "event": "matter_first_seen", "title": m.title})
            if m.resolved_at:
                events.append({"at": iso(m.resolved_at), "event": "matter_resolved", "title": m.title})
        for i in items:
            base = {"ref": i["ref"], "title": i["title"], "direction": i["direction"],
                    "formation": i["formation"], "kind": i["kind"]}
            events.append({**base, "at": iso(i["_created_at"]), "event": "recorded"})
            if i["status"] in TERMINAL and i["_updated_at"] > i["_created_at"]:
                events.append({**base, "at": iso(i["_updated_at"]), "event": f"became_{i['status']}"})
        lo, hi = naive(start), naive(end)
        events = [e for e in events if (lo is None or e["at"] >= lo.isoformat())
                  and (hi is None or e["at"] < hi.isoformat())]
        events.sort(key=lambda e: e["at"])
        return {"subject": {"type": stype, "id": sid}, "window": [iso(lo), iso(hi)], "events": events}

    # ------------------------------------------------------- period/today/week
    def period(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """What occupied the user in [start,end) and what is expected in it."""
        r, start, end = self.r, naive(start), naive(end)
        touched = r.touched_between(start, end)
        by_matter: Dict[str, List[Item]] = {}
        loose: List[Item] = []
        for i in touched:
            if i["kind"] in ("fact", "attention"):
                continue
            (by_matter.setdefault(i["matter_id"], []) if i.get("matter_id") else loose).append(i)
        occupied = []
        for mid, its in by_matter.items():
            m = r.matters.get(UUID(mid))
            if m is None:
                continue
            occupied.append({**self._matter_brief(m),
                             "touched_by": [_trim(i) for i in its][:4], "touch_count": len(its)})
        occupied.sort(key=lambda o: (-o["touch_count"], -o["rank"]))
        expected = []
        for i in r.items:
            if not i["live"] or i["kind"] not in ("expectation", "work_item", "commitment"):
                continue
            when = r.when_of(i)
            if when is not None and start <= when < end:
                brief = _trim(i, "temporal_state") if i["kind"] == "expectation" else _trim(i)
                expected.append({**brief, "expected_at": iso(when)})
        expected.sort(key=lambda e: e["expected_at"])
        resolved = [_trim(i) for i in touched if i["status"] in TERMINAL and i["kind"] != "model_entry"
                    and start <= i["_updated_at"] < end]
        return {
            "window": [iso(start), iso(end)],
            "occupied": occupied[:CAPS["matters"]],
            "unattached": [_trim(i) for i in loose][:CAPS["items"]],
            "expected": expected[:CAPS["matters"]],
            "resolved": resolved[:CAPS["items"] + 4],
            "activity": {"items_touched": len(touched),
                         "distinct_user_messages": len({e for i in touched for e in i["evidence_refs"]
                                                        if not str(e).startswith("consolidation:")})},
        }

    def _declared_routines_on(self, day: date) -> List[Dict[str, Any]]:
        out = []
        for i in self.r.of("recurrence", live=True):
            if not i["declared"]:
                continue
            if i["cadence"] == "daily" or i["cadence"] == "interval":
                out.append(_trim(i, "cadence", "preferred_window"))
            elif i["cadence"] == "weekly":
                row = self.r.rows.get(("recurrence", UUID(i["ref"]["id"])))
                try:
                    days = {int(d) for d in json.loads(row.days_of_week_json or "[]")}
                except (TypeError, ValueError):
                    days = set()
                if not days or day.weekday() in days:
                    out.append(_trim(i, "cadence", "preferred_window"))
        return out

    def today(self) -> Dict[str, Any]:
        day = self.r.day
        start, end = day.bounds(day.today)
        out = self.period(start, end)
        out["user_day"] = day.today.isoformat()
        out["routines_today"] = self._declared_routines_on(day.today)
        out["timezone"] = self.r.tz
        return out

    def week(self) -> Dict[str, Any]:
        """Rolling last 7 days (occupied) + next 7 days (expected)."""
        day = self.r.day
        today = day.today
        past_start, _ = day.bounds(today - timedelta(days=6))
        _, past_end = day.bounds(today)
        past = self.period(past_start, past_end)
        ahead = self.period(*[day.bounds(today + timedelta(days=1))[0], day.bounds(today + timedelta(days=7))[1]])
        today_b, _ = day.bounds(today)
        return {
            "user_day": today.isoformat(), "timezone": self.r.tz,
            "occupied_this_week": past["occupied"], "resolved_this_week": past["resolved"],
            "activity": past["activity"],
            "expected_today": [e for e in self.period(*day.bounds(today))["expected"]],
            "expected_ahead": ahead["expected"],
            "changes": self.recent_changes(days=7)["changes"][:8],
        }

    # ------------------------------------------------------------ unresolved
    def unresolved(self) -> Dict[str, Any]:
        """Live matters/items still open. An unknown outcome is NOT a failure."""
        r = self.r
        groups = []
        for m in self._ranked_matters(("active", "dormant")):
            live = [i for i in r.matter_items(m.id) if i["live"] and i["kind"] not in ("fact", "model_entry")]
            repair = [i for i in r.matter_items(m.id) if i["kind"] == "model_entry"
                      and i.get("claim_kind") in ("repair", "relationship_development") and i["live"]]
            if not live and not repair:
                continue
            open_items = [_trim(i, "temporal_state") if i["kind"] == "expectation" else _trim(i)
                          for i in live][:5]
            groups.append({**self._matter_brief(m), "open": open_items,
                           "repair": [_trim(i, "claim_kind", "epistemic_status") for i in repair][:3]})
        matterless = [i for i in r.items if i["live"] and not i.get("matter_id")
                      and i["kind"] in ("open_loop", "expectation", "commitment") and not i.get("source_system")]
        owed = [i for i in r.items if i["live"] and i["direction"] == "system_to_user"
                and i["kind"] in ("commitment", "expectation", "work_item")]
        # Unresolved human<->system repair is unresolved state whether or not a
        # Matter holds it (docs/CORTEX_ARCHITECTURE.md §2.1).
        repair = [i for i in r.of("model_entry") if i["live"] and i["holder"] != "system"
                  and i.get("claim_kind") == "repair"]
        return {
            "by_matter": groups[:CAPS["matters"]],
            "repair": [_trim(i, "claim_kind", "epistemic_status") for i in repair][:3],
            "unattached": [_trim(i) for i in matterless][:CAPS["items"]],
            "owed_by_system": [_trim(i) for i in owed][:CAPS["items"]],
            "constraints": {"unknown_is_not_failed": True,
                            "eligibility_is_not_instruction": True},
        }

    # --------------------------------------------------------- recent changes
    def recent_changes(self, days: float = 7, since: Optional[datetime] = None) -> Dict[str, Any]:
        r = self.r
        since = naive(since) or (r.now - timedelta(days=days))
        changes: List[Dict[str, Any]] = []
        for m in r.matters.values():
            if m.first_seen >= since:
                changes.append({"change": "new_matter", "at": iso(m.first_seen),
                                "matter": self._matter_brief(m)})
            if m.status == "resolved" and m.resolved_at and m.resolved_at >= since:
                changes.append({"change": "matter_resolved", "at": iso(m.resolved_at),
                                "matter": self._matter_brief(m)})
        by_id = {str(e.id): e for e in r.model_entries}
        for e in r.model_entries:
            if e.superseded_by_id and str(e.superseded_by_id) in by_id:
                succ = by_id[str(e.superseded_by_id)]
                if succ.created_at >= since:
                    changes.append({"change": "claim_revised", "at": iso(succ.created_at),
                                    "was": entry_view(e, r.now), "now": entry_view(succ, r.now)})
            elif (e.claim_kind in ("relationship_development", "repair", "correction")
                  and e.created_at >= since):
                changes.append({"change": e.claim_kind, "at": iso(e.created_at),
                                "claim": entry_view(e, r.now)})
            if e.epistemic_status == "conflicting" and e.updated_at >= since and not e.superseded_by_id:
                changes.append({"change": "claim_conflict", "at": iso(e.updated_at),
                                "claim": entry_view(e, r.now)})
        for i in r.items:
            if i["direction"] in ("user_to_system", "system_to_user") and i["kind"] != "model_entry":
                if i["_created_at"] >= since:
                    changes.append({"change": f"{i['direction']}_recorded", "at": iso(i["_created_at"]),
                                    "item": _trim(i)})
                elif i["status"] in TERMINAL and i["_updated_at"] >= since:
                    changes.append({"change": f"{i['direction']}_settled", "at": iso(i["_updated_at"]),
                                    "item": _trim(i)})
        changes.sort(key=lambda c: c["at"], reverse=True)
        return {"since": iso(since), "changes": changes}

    # -------------------------------------------------------------- knowledge
    def knowledge_gaps(self, limit: int = 12) -> Dict[str, Any]:
        return {"gaps": kcs.gaps(self.coverage, limit),
                "coverage_counts": _status_counts(self.coverage)}

    # ------------------------------------------------------------------ depth
    def depth(self) -> Dict[str, Any]:
        r = self.r
        kinds: Dict[str, int] = {}
        for i in r.items:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        earliest = min((i["_created_at"] for i in r.items), default=None)
        status_counts: Dict[str, int] = {}
        for m in r.matters.values():
            status_counts[m.status] = status_counts.get(m.status, 0) + 1
        return {
            "state": {"items_by_kind": kinds, "matters_by_status": status_counts,
                      "coverage": _status_counts(self.coverage)},
            "history": {"earliest_evidence_at": iso(earliest),
                        "horizon_days": 180},
            "available_via": {
                "person": "projection person(entity_id)", "matter": "projection matter(matter_id)",
                "timeline": "projection timeline(subject, window)",
                "provenance": "projection why(type, id)",
                "exact_quotes_and_obscure_history": "bounded longitudinal read (matter_refs = matter ids)",
            },
        }


def _status_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


async def open_projections(db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
                           now: datetime, tz: str = "UTC", session_id: Optional[str] = None,
                           weights: Optional[Dict[str, float]] = None,
                           kind_weights: Optional[Dict[str, float]] = None, sync: bool = False
                           ) -> Projections:
    """Open projections for a person. Reads never reconcile canonical state;
    `sync=True` exists for mutation boundaries only."""
    if sync:
        await ms.sync_primitives(db, workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                                 session_id=session_id, now=now)
    reader = await open_reader(db, workspace_id, owner_peer_id, now, tz, session_id)
    await kcs.refresh(db, reader)
    rows = await kcs.read(db, reader.scope)
    return Projections(reader, rows, weights, kind_weights)


async def why(db: AsyncSession, object_type: str, object_id: UUID,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    return await explain(db, object_type, object_id, now)
