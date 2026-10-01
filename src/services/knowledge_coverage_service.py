"""Knowledge coverage: what is known, partial, unknown, stale, conflicting.

Hierarchical, generic `subject_key` paths (docs/CORTEX_ARCHITECTURE.md §11):

    routines                       partial   (parent frame)
    routines/walk_morning          known     (declared, with timing)
    routines/walk_morning/timing   unknown   (a USEFUL gap hanging off known evidence)
    people/<entity>/relationship   unknown   (mentioned repeatedly, role never stated)

Rules that make this safe:
* A coverage row carries NO value. `unknown` means "no evidence", never a
  guess — missing information is never filled to complete a profile.
* Only useful gaps exist: (a) children of paths Cortex has evidence about,
  (b) gaps explicitly registered by consolidation, (c) a six-parent generic
  acquaintance frame so a cold start can answer "what do we not know yet".
  No fixed profile ontology below that.
* Derived rows are reconstructable (replaced on every derive); registered gaps
  persist until evidence arrives for their path.
* Gaps may feed curiosity; Runtime/product policy decides whether and how to ask.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.world_model import COVERAGE_STATUSES, KnowledgeCoverage
from src.services.world_read import WorldReader
from src.services.world_scope import Scope

KEY_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+){0,3}$")  # generic path, max depth 4
STALE_ROUTINE_DAYS = 90
STALE_PERSON_DAYS = 180
MAX_ROWS_PER_SCOPE = 80

# Minimal generic acquaintance frame (parents only, product-agnostic).
FRAME = {
    "person": "who this person is: background, circumstances",
    "routines": "how their days/weeks are shaped",
    "people": "who matters in their life and how",
    "work_or_projects": "what they spend effort on",
    "preferences_and_boundaries": "how they like things done; what to avoid",
    "relationship_with_system": "what they expect of and have been through with this companion",
}


@dataclass
class Cov:
    subject_key: str
    status: str
    basis: str
    evidence_count: int = 0
    evidence_refs: List[str] = field(default_factory=list)
    last_evidence_at: Optional[datetime] = None
    why_useful: str = ""
    source: str = "derived"

    @property
    def parent_key(self) -> Optional[str]:
        return self.subject_key.rsplit("/", 1)[0] if "/" in self.subject_key else None


def _slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:48] or "unknown"


def derive(reader: WorldReader) -> List[Cov]:
    """Pure derivation of coverage from the reader's evidence."""
    now = reader.now
    out: Dict[str, Cov] = {}

    def put(c: Cov) -> None:
        out[c.subject_key] = c

    def refs_of(items) -> List[str]:
        return [r for i in items for r in i["evidence_refs"]][:6]

    def newest(items) -> Optional[datetime]:
        return max((i["_updated_at"] for i in items), default=None)

    # --- routines: declared vs observed; timing is a useful child gap --------
    recs = reader.of("recurrence")
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        by_key.setdefault(r["canonical_key"], []).append(r)
    for ckey, rs in by_key.items():
        path = f"routines/{_slug(ckey)}"
        live = [r for r in rs if r["live"]]
        if not live:
            continue
        declared = [r for r in live if r["declared"]]
        last = newest(live)
        stale = last is not None and now - last > timedelta(days=STALE_ROUTINE_DAYS)
        cadences = {(r["cadence"], r["preferred_window"]) for r in declared}
        if stale:
            status, basis = "stale", "last evidence older than %d days" % STALE_ROUTINE_DAYS
        elif len({c for c, _ in cadences}) > 1:
            status, basis = "conflicting", "declared with different cadences"
        elif declared:
            status, basis = "known", "declared by the user"
        else:
            status, basis = "partial", "observed pattern only; never declared"
        put(Cov(path, status, basis, len(live), refs_of(live), last,
                "shapes how days go", "derived"))
        if declared and not any(w for _, w in cadences):
            put(Cov(f"{path}/timing", "unknown", "cadence declared but time of day never stated",
                    0, [], None, "needed to follow through at the right moment", "derived"))
    routine_children = [c for k, c in out.items() if k.startswith("routines/") and k.count("/") == 1]
    put(_parent("routines", routine_children, "how their days/weeks are shaped"))

    # --- people: an entity referenced repeatedly whose role is unknown -------
    role_known = {str(e.from_entity_id) for e in reader.edges} | {str(e.to_entity_id) for e in reader.edges}
    entity_refs: Dict[str, List[Dict[str, Any]]] = {}
    for it in reader.items:
        for eid in it["entity_ids"]:
            entity_refs.setdefault(eid, []).append(it)
    people: List[Cov] = []
    for eid, its in entity_refs.items():
        ent = next((e for k, e in reader.entities.items() if str(k) == eid), None)
        if ent is None or ent.entity_type != "person":
            continue
        path = f"people/{_slug(ent.display_name)}"
        last = newest(its)
        if eid in role_known:
            status = "stale" if last and now - last > timedelta(days=STALE_PERSON_DAYS) else "known"
            c = Cov(path, status, "relationship edge recorded" if status == "known"
                    else "no mention for %d days" % STALE_PERSON_DAYS, len(its), refs_of(its), last,
                    "people matter to how things land")
            put(c)
            people.append(c)
        elif len(its) >= 2:
            put(Cov(path, "partial", "mentioned repeatedly", len(its), refs_of(its), last,
                    "people matter to how things land"))
            put(Cov(f"{path}/relationship", "unknown",
                    "referenced in %d places but who they are to the user was never stated" % len(its),
                    0, refs_of(its), last, "natural to learn who they are when they come up again"))
            people.append(out[path])
    put(_parent("people", people, FRAME["people"]))

    # --- person: facts by their own category (no invented taxonomy) ----------
    facts = [f for f in reader.of("fact") if f["holder"] == "user"]
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for f in facts:
        by_cat.setdefault(_slug(f.get("category") or "general"), []).append(f)
    person_children = []
    for cat, fs in by_cat.items():
        firm = [f for f in fs if f["formation"] in ("explicit", "reported", "source_linked")]
        c = Cov(f"person/{cat}", "known" if len(firm) >= 2 else "partial",
                "%d firm fact(s)" % len(firm), len(fs), refs_of(fs), newest(fs), "knowing someone's background")
        put(c)
        person_children.append(c)
    put(_parent("person", person_children, FRAME["person"]))

    # --- work_or_projects: from Matters (project/goal kinds) -----------------
    proj = [m for m in reader.matters.values() if m.kind in ("project", "goal") and m.status in ("active", "dormant")]
    pc = [Cov(f"work_or_projects/{_slug(m.title)}", "known" if m.formation == "explicit" else "partial",
              "matter %s" % m.status, len(reader.matter_links.get(m.id, [])), [], m.last_touched,
              "what they spend effort on") for m in proj[:12]]
    for c in pc:
        put(c)
    put(_parent("work_or_projects", pc, FRAME["work_or_projects"]))

    # --- preferences and boundaries: suppressions + preference entries -------
    prefs = [m for m in reader.items if m["kind"] == "model_entry" and m.get("claim_kind") in ("preference", "boundary")]
    pcs: List[Cov] = []
    if reader.suppressions:
        c = Cov("preferences_and_boundaries/avoid", "known", "explicit suppressions recorded",
                len(reader.suppressions), [s.honcho_message_id for s in reader.suppressions][:6],
                max(s.created_at for s in reader.suppressions), "never surface what they asked to avoid")
        put(c)
        pcs.append(c)
    if prefs:
        c = Cov("preferences_and_boundaries/stated", "known", "stated preferences", len(prefs), refs_of(prefs),
                newest(prefs), "how they like things done")
        put(c)
        pcs.append(c)
    put(_parent("preferences_and_boundaries", pcs, FRAME["preferences_and_boundaries"]))

    # --- relationship with the system ----------------------------------------
    rel = [i for i in reader.items if i["direction"] in ("user_to_system", "system_to_user", "shared")]
    rcs: List[Cov] = []
    if rel:
        asks = [i for i in rel if i["direction"] == "user_to_system"]
        owed = [i for i in rel if i["direction"] == "system_to_user"]
        if asks:
            c = Cov("relationship_with_system/requests", "known", "user requests on record", len(asks),
                    refs_of(asks), newest(asks), "what they expect of the companion")
            put(c)
            rcs.append(c)
        if owed:
            c = Cov("relationship_with_system/commitments", "known", "system commitments on record",
                    len(owed), refs_of(owed), newest(owed), "what the companion owes")
            put(c)
            rcs.append(c)
    put(_parent("relationship_with_system", rcs, FRAME["relationship_with_system"]))

    # --- conflicting claims surface as conflicting coverage -------------------
    conflicts = [i for i in reader.items if i["kind"] == "model_entry" and i["status"] == "conflicting"]
    for i in conflicts[:6]:
        put(Cov(f"claims/{i['ref']['id'][:8]}", "conflicting",
                "a firm statement and a later interpretation disagree", 1, i["evidence_refs"][:3],
                i["_updated_at"], "resolve by what the user actually says next"))
    return list(out.values())


def _parent(key: str, children: List[Cov], why: str) -> Cov:
    if not children:
        return Cov(key, "unknown", "no evidence yet", 0, [], None, why)
    sts = {c.status for c in children}
    ev = sum(c.evidence_count for c in children)
    refs = [r for c in children for r in c.evidence_refs][:6]
    last = max((c.last_evidence_at for c in children if c.last_evidence_at), default=None)
    if "conflicting" in sts:
        status = "conflicting"
    elif sts == {"known"}:
        status = "known"
    elif sts <= {"stale"}:
        status = "stale"
    else:
        status = "partial"
    return Cov(key, status, "%d child path(s)" % len(children), ev, refs, last, why)


async def refresh(db: AsyncSession, reader: WorldReader) -> List[Cov]:
    """Replace derived rows with a fresh derivation; reconcile registered gaps
    (a registered gap whose path now has evidence becomes derived)."""
    scope: Scope = reader.scope
    derived = {c.subject_key: c for c in derive(reader)}
    rows = (await db.execute(select(KnowledgeCoverage).where(
        KnowledgeCoverage.honcho_workspace_id == scope.workspace_id,
        KnowledgeCoverage.owner_peer_id == scope.owner_peer_id
        if scope.owner_peer_id else KnowledgeCoverage.owner_peer_id.is_(None)))).scalars().all()
    existing = {r.subject_key: r for r in rows}
    try:
        async with db.begin_nested():  # SAVEPOINT: concurrent derivations may race on the unique path
            now = reader.now
            seen = set()
            for key, c in derived.items():
                if len(seen) >= MAX_ROWS_PER_SCOPE:
                    break
                seen.add(key)
                row = existing.get(key)
                if row is None:
                    row = KnowledgeCoverage(honcho_workspace_id=scope.workspace_id,
                                            owner_peer_id=scope.owner_peer_id, subject_key=key)
                why = c.why_useful or row.why_useful
                why = row.why_useful if (row.source == "registered" and row.why_useful) else why
                refs = json.dumps(c.evidence_refs)
                source = "derived" if (c.evidence_count or row.source != "registered") else row.source
                new_vals = (c.parent_key, c.status, c.basis, c.evidence_count, c.last_evidence_at, refs, why, source)
                old_vals = (row.parent_key, row.status, row.basis, row.evidence_count, row.last_evidence_at,
                            row.evidence_refs_json, row.why_useful, row.source)
                if row.id in {r.id for r in rows} and new_vals == old_vals:
                    continue  # unchanged: leave updated_at alone so fingerprints stay stable
                (row.parent_key, row.status, row.basis, row.evidence_count, row.last_evidence_at,
                 row.evidence_refs_json, row.why_useful, row.source) = new_vals
                row.updated_at = now
                db.add(row)
            for key, row in existing.items():
                if key not in derived and row.source == "derived":
                    await db.delete(row)  # derived rows are reconstructable
    except IntegrityError:
        pass  # another reader wrote the same derived rows; derived state is reconstructable
    await db.commit()
    return list(derived.values())


async def register_gap(db: AsyncSession, *, scope: Scope, subject_key: str, why_useful: str,
                       basis: str = "registered by consolidation") -> KnowledgeCoverage:
    """Register a useful gap. Registers `unknown` only — never a value. A path
    that already has derived evidence is left alone."""
    subject_key = (subject_key or "").strip().strip("/")
    if not KEY_RE.match(subject_key):
        raise ValueError("subject_key must be a lowercase path like 'routines/weekday_morning' (max depth 4)")
    row = (await db.execute(select(KnowledgeCoverage).where(
        KnowledgeCoverage.honcho_workspace_id == scope.workspace_id,
        KnowledgeCoverage.owner_peer_id == scope.owner_peer_id if scope.owner_peer_id
        else KnowledgeCoverage.owner_peer_id.is_(None),
        KnowledgeCoverage.subject_key == subject_key))).scalars().first()
    if row is not None:
        if why_useful and not row.why_useful:
            row.why_useful = why_useful[:240]
            db.add(row)
            await db.commit()
        return row
    row = KnowledgeCoverage(
        honcho_workspace_id=scope.workspace_id, owner_peer_id=scope.owner_peer_id,
        subject_key=subject_key,
        parent_key=subject_key.rsplit("/", 1)[0] if "/" in subject_key else None,
        status="unknown", source="registered", basis=basis[:240], why_useful=why_useful[:240])
    db.add(row)
    await db.commit()
    return row


async def read(db: AsyncSession, scope: Scope, *, statuses: Optional[List[str]] = None,
               prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    stmt = select(KnowledgeCoverage).where(
        KnowledgeCoverage.honcho_workspace_id == scope.workspace_id,
        KnowledgeCoverage.owner_peer_id == scope.owner_peer_id if scope.owner_peer_id
        else KnowledgeCoverage.owner_peer_id.is_(None))
    if statuses:
        bad = set(statuses) - COVERAGE_STATUSES
        if bad:
            raise ValueError(f"unknown coverage status {sorted(bad)}")
        stmt = stmt.where(KnowledgeCoverage.status.in_(statuses))
    if prefix:
        stmt = stmt.where(KnowledgeCoverage.subject_key.like(prefix.rstrip("/") + "%"))
    rows = (await db.execute(stmt.order_by(KnowledgeCoverage.subject_key))).scalars().all()
    return [view(r) for r in rows]


def view(r: KnowledgeCoverage) -> Dict[str, Any]:
    return {
        "subject_key": r.subject_key, "parent_key": r.parent_key, "status": r.status,
        "source": r.source, "basis": r.basis, "evidence_count": r.evidence_count,
        "evidence_refs": json.loads(r.evidence_refs_json or "[]"),
        "last_evidence_at": r.last_evidence_at.isoformat() if r.last_evidence_at else None,
        "why_useful": r.why_useful,
        # No value field exists by design: unknown is unknown.
    }


_GAP_ORDER = {"conflicting": 0, "unknown": 1, "partial": 2, "stale": 3}


def gaps(rows: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    """Useful gaps, most actionable first: children of something we know about
    outrank bare frame parents; conflicting first. Eligibility is permission,
    never an instruction to ask."""
    cand = [r for r in rows if r["status"] in _GAP_ORDER]
    known_parents = {r["subject_key"] for r in rows if r["status"] in ("known", "partial")}
    def rank(r):
        hangs_off_evidence = bool(r["parent_key"] and r["parent_key"] in known_parents) or r["evidence_count"] > 0
        return (_GAP_ORDER[r["status"]], 0 if hangs_off_evidence else 1, -r["evidence_count"], r["subject_key"])
    out = sorted(cand, key=rank)[:limit]
    return [{**r, "eligible_for_curiosity": True,
             "note": "permission to learn naturally, not an instruction to ask"} for r in out]
