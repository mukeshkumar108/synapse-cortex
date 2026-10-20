"""Connected understanding: storage operations and DETERMINISTIC views.

Interpretation (who/what is this, how are they related, is this relationship stated or inferred) happens once, in
the connect pass (`world_agent`). Everything here is retrieval: plain reads over stored entities and links plus the
authoritative records they point to, at the current clock. No model runs when a person or project is mentioned.

Rules the code enforces (not model obedience):
- a `stated` link must carry a quote that exists in the session transcript; otherwise it is stored as `inferred`;
- inferred relations are always rendered as inferred, never as plain fact;
- a link points at its authoritative record (ledger key, attention id, entity); the record is read at query time,
  so a completed obligation or a changed deadline is reflected immediately and no fact is stored twice;
- `suppressed` stops unprompted surfacing (overview, cues) but never deletes the memory; a mention still resolves;
- sensitivity is carried, never inferred by code.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.known_world import CueExposure, KnownEntity, KnownEntityAlias, KnownLink
from src.models.world import AttentionAction, LedgerItem, utc_now
from src.services import ledger_views

SUMMARY_MAX = 500
OVERVIEW_PEOPLE_PROJECTS = 6
OVERVIEW_SITUATIONS = 4
MENTION_LIMIT = 3
SITTING_GAP_MIN = 45               # exposure counts once per sitting-sized window, not once per turn
EXPOSURE_DEMOTE_AFTER = 3          # a situation shown this many sittings without engagement stops occupying the overview
STALE_SITUATION_DAYS = 3
LIVE = ("active", "dormant")
SITUATION_KINDS = ("situation", "concern", "worry", "health", "decision", "curiosity", "question")
FORMS = ("", "situation", "happening", "disposition", "pattern")
PERTINENT_LIMIT = 4
RECENT_DAYS = (3, 14, 60)
SELF_KIND = "self"
SELF_NAME = "the person"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _now() -> datetime:
    return utc_now()


def _refs(raw: str) -> List[Dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def is_situation(e: KnownEntity) -> bool:
    return str(e.form or "") == "situation" or (not e.form and str(e.kind or "").lower() in SITUATION_KINDS)


def is_record(e: KnownEntity) -> bool:
    """Happenings, dispositions and patterns: remembered things that are not people/projects/situations. They surface by relevance, never by listing."""
    return str(e.form or "") in ("happening", "disposition", "pattern")


def norm_tags(raw: Any) -> str:
    items = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    out: List[str] = []
    for t in items:
        t = re.sub(r"[^a-z0-9/ \-]+", "", str(t).lower()).strip()
        if len(t) >= 2 and t not in out:
            out.append(t[:40])
    return ",".join(out[:8])


def _tag_words(tags: str) -> set:
    return {w for t in tags.split(",") for w in re.split(r"[/ \-]+", t) if len(w) >= 3}


def _tag_domains(tags: str) -> set:
    return {t.split("/")[0].strip() for t in tags.split(",") if t.strip()}


def is_self(e: KnownEntity) -> bool:
    return str(e.kind or "").lower() == SELF_KIND


def neutral_user(text: str) -> str:
    """Stored summaries say "the person" (neutral, reusable by any product). In what is shown to a companion the user is simply "the user"."""
    return re.sub(r"\b(T|t)he person\b", lambda m: f"{'T' if m.group(1) == 'T' else 't'}he user", text)


def _user_rel(relation: str) -> str:
    """"partner of" -> "User's partner"; anything else reads as "<relation> User"."""
    r = relation.strip()
    for tail in (" of", " to", " for"):
        if r.lower().endswith(tail):
            return f"User's {r[:-len(tail)].strip()}"
    return f"{r} User"


def _cut(s: str, n: int) -> str:
    """Shorten at a word boundary, never mid-word."""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"


async def ensure_self(db: AsyncSession, ws: str, owner: str) -> KnownEntity:
    """The anchor for relationships TO the person themself ("Ashley: partner of the person"), so no other entity has to stand in for
    them. Created by code (mechanical, not a judgement), never shown as an entity, never edited by the model."""
    found = (await db.execute(select(KnownEntity).where(KnownEntity.honcho_workspace_id == ws, KnownEntity.owner_peer_id == owner,
                                                        KnownEntity.kind == SELF_KIND))).scalars().first()
    if found is not None:
        return found
    e = KnownEntity(honcho_workspace_id=ws, owner_peer_id=owner, kind=SELF_KIND, name=SELF_NAME, name_key=norm(SELF_NAME), summary="",
                    basis="stated", source_refs_json="[]")
    db.add(e)
    await db.flush()
    return e


# ------------------------------------------------------------------ store ----

async def get(db: AsyncSession, ws: str, owner: str, entity_id: Any) -> Optional[KnownEntity]:
    try:
        uid = entity_id if isinstance(entity_id, UUID) else UUID(str(entity_id))
    except Exception:
        return None
    e = (await db.execute(select(KnownEntity).where(KnownEntity.id == uid, KnownEntity.honcho_workspace_id == ws,
                                                    KnownEntity.owner_peer_id == owner))).scalars().first()
    seen = 0
    while e is not None and e.merged_into_id is not None and seen < 5:        # a merged entity always resolves to its survivor
        e = (await db.execute(select(KnownEntity).where(KnownEntity.id == e.merged_into_id, KnownEntity.honcho_workspace_id == ws,
                                                        KnownEntity.owner_peer_id == owner))).scalars().first()
        seen += 1
    return e


async def list_all(db: AsyncSession, ws: str, owner: str, statuses: Sequence[str] = LIVE, limit: int = 300) -> List[KnownEntity]:
    rows = (await db.execute(select(KnownEntity).where(
        KnownEntity.honcho_workspace_id == ws, KnownEntity.owner_peer_id == owner,
        KnownEntity.status.in_(list(statuses))).order_by(KnownEntity.last_touched_at.desc()).limit(limit))).scalars().all()
    return list(rows)


async def aliases_of(db: AsyncSession, ws: str, owner: str, entity_id: UUID) -> List[KnownEntityAlias]:
    return list((await db.execute(select(KnownEntityAlias).where(
        KnownEntityAlias.honcho_workspace_id == ws, KnownEntityAlias.owner_peer_id == owner,
        KnownEntityAlias.entity_id == entity_id))).scalars().all())


async def find(db: AsyncSession, ws: str, owner: str, query: str, statuses: Sequence[str] = ("active", "dormant", "resolved"),
               exact: bool = False) -> List[KnownEntity]:
    """Entities a name or phrase may refer to: exact alias/name first, then (unless exact) whole-word containment. Deterministic."""
    q = norm(query)
    if not q:
        return []
    al = (await db.execute(select(KnownEntityAlias).where(
        KnownEntityAlias.honcho_workspace_id == ws, KnownEntityAlias.owner_peer_id == owner))).scalars().all()
    ids: List[UUID] = []
    for a in al:
        if a.alias_key == q:
            ids.append(a.entity_id)
    ents = (await db.execute(select(KnownEntity).where(
        KnownEntity.honcho_workspace_id == ws, KnownEntity.owner_peer_id == owner,
        KnownEntity.status.in_(list(statuses))))).scalars().all()
    out: Dict[UUID, KnownEntity] = {e.id: e for e in ents if e.id in ids or e.name_key == q}
    if not out and not exact:
        for e in ents:
            keys = {e.name_key} | {a.alias_key for a in al if a.entity_id == e.id}
            if any(k and (f" {q} " in f" {k} " or f" {k} " in f" {q} ") for k in keys):
                out[e.id] = e
    return list(out.values())


async def mentions(db: AsyncSession, ws: str, owner: str, text: str, limit: int = MENTION_LIMIT) -> Tuple[List[KnownEntity], List[Tuple[str, List[KnownEntity]]]]:
    """Which known entities does this text name? A deterministic NOMINATION by alias match (whole words, >= 3 characters); it decides
    nothing about meaning: the snapshot it produces is facts and the foreground model decides what the person meant. Returns
    (unambiguous entities, [(alias, candidates)] for aliases that name more than one live entity)."""
    t = f" {norm(text)} "
    if len(t.strip()) < 3:
        return [], []
    ents = {e.id: e for e in await list_all(db, ws, owner, statuses=("active", "dormant", "resolved")) if not is_self(e) and not is_record(e)}
    al = (await db.execute(select(KnownEntityAlias).where(
        KnownEntityAlias.honcho_workspace_id == ws, KnownEntityAlias.owner_peer_id == owner))).scalars().all()
    by_key: Dict[str, List[UUID]] = {}
    for e in ents.values():
        if e.name_key:
            by_key.setdefault(e.name_key, []).append(e.id)
        toks = e.name_key.split()
        if str(e.kind).lower() == "person" and len(toks) >= 2 and len(toks[0]) >= 3:
            by_key.setdefault(toks[0], []).append(e.id)     # people are usually referred to by first name; a nomination, never a decision
    for a in al:
        if a.entity_id in ents:
            by_key.setdefault(a.alias_key, []).append(a.entity_id)
    found: Dict[UUID, KnownEntity] = {}
    ambiguous: List[Tuple[str, List[KnownEntity]]] = []
    for key, idlist in sorted(by_key.items(), key=lambda kv: -len(kv[0])):
        if len(key) < 3 or f" {key} " not in t:
            continue
        uniq = list(dict.fromkeys(idlist))
        if len(uniq) == 1:
            found.setdefault(uniq[0], ents[uniq[0]])
        else:
            # one alias, several entities: report the ambiguity unless a longer, more specific name already resolved one of them
            if not any(u in found for u in uniq):
                ambiguous.append((key, [ents[u] for u in uniq]))
    return list(found.values())[:limit], ambiguous[:2]


async def create(db: AsyncSession, ws: str, owner: str, *, name: str, kind: str = "person", summary: str = "", sensitive: bool = False,
                 basis: str = "stated", aliases: Iterable[str] = (), run_id: Optional[UUID] = None, session_id: str = "",
                 quote: str = "", form: str = "", tags: Any = "", occurred_on: Optional[datetime] = None, significance: int = 2) -> KnownEntity:
    e = KnownEntity(form=form if form in FORMS else "", tags=norm_tags(tags), occurred_on=occurred_on,
                    significance=min(3, max(1, int(significance or 2))),honcho_workspace_id=ws, owner_peer_id=owner, kind=str(kind or "person").strip().lower()[:40], name=name.strip()[:200],
                    name_key=norm(name), summary=str(summary or "").strip()[:SUMMARY_MAX], sensitive=bool(sensitive),
                    basis="stated" if basis == "stated" else "inferred", run_id=run_id,
                    source_refs_json=json.dumps([{"session": session_id, "quote": quote[:300]}] if (session_id or quote) else []))
    db.add(e)
    await db.flush()
    await add_alias(db, ws, owner, e.id, name, basis=e.basis)
    for a in aliases:
        await add_alias(db, ws, owner, e.id, a, basis=basis)
    return e


async def add_alias(db: AsyncSession, ws: str, owner: str, entity_id: UUID, alias: str, basis: str = "stated") -> Optional[KnownEntityAlias]:
    key = norm(alias)
    if len(key) < 2:
        return None
    have = (await db.execute(select(KnownEntityAlias).where(
        KnownEntityAlias.honcho_workspace_id == ws, KnownEntityAlias.owner_peer_id == owner,
        KnownEntityAlias.entity_id == entity_id, KnownEntityAlias.alias_key == key))).scalars().first()
    if have is not None:
        return have
    a = KnownEntityAlias(honcho_workspace_id=ws, owner_peer_id=owner, entity_id=entity_id, alias=alias.strip()[:200], alias_key=key,
                         basis="stated" if basis == "stated" else "inferred")
    db.add(a)
    await db.flush()
    return a


async def touch(db: AsyncSession, e: KnownEntity, session_id: str = "", quote: str = "") -> None:
    e.last_touched_at = _now()
    e.updated_at = _now()
    if session_id or quote:
        refs = _refs(e.source_refs_json)
        if not any(r.get("session") == session_id and r.get("quote") == quote[:300] for r in refs):
            refs.append({"session": session_id, "quote": quote[:300]})
        e.source_refs_json = json.dumps(refs[-12:])


async def link(db: AsyncSession, ws: str, owner: str, *, from_id: UUID, relation: str, target_kind: str, target_ref: str, basis: str,
               evidence: str = "", session_id: str = "", run_id: Optional[UUID] = None) -> Tuple[KnownLink, bool]:
    """Create (or refresh) a link. Returns (link, created). An identical current link is refreshed, never duplicated, and an
    inference the person later confirms is upgraded to stated. Different relations between the same pair COEXIST (an adviser
    can also be a friend): a change of relationship is an explicit act (`supersede`) by the connect pass, never a side effect."""
    relation = relation.strip()[:200]
    existing = (await db.execute(select(KnownLink).where(
        KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner, KnownLink.from_entity_id == from_id,
        KnownLink.target_kind == target_kind, KnownLink.target_ref == target_ref, KnownLink.status == "current"))).scalars().all()
    for ex in existing:
        if norm(ex.relation) == norm(relation):
            if basis == "stated" and ex.basis != "stated":
                ex.basis, ex.evidence = "stated", evidence[:500]
            ex.updated_at = _now()
            return ex, False
    new = KnownLink(honcho_workspace_id=ws, owner_peer_id=owner, from_entity_id=from_id, relation=relation, target_kind=target_kind,
                    target_ref=target_ref, basis="stated" if basis == "stated" else "inferred", evidence=evidence[:500],
                    session_id=session_id, run_id=run_id)
    db.add(new)
    await db.flush()
    return new, True


async def supersede(db: AsyncSession, ws: str, owner: str, link_id: Any, reason: str) -> Optional[KnownLink]:
    try:
        uid = link_id if isinstance(link_id, UUID) else UUID(str(link_id))
    except Exception:
        return None
    lk = (await db.execute(select(KnownLink).where(KnownLink.id == uid, KnownLink.honcho_workspace_id == ws,
                                                   KnownLink.owner_peer_id == owner))).scalars().first()
    if lk is not None and lk.status == "current":
        lk.status, lk.note, lk.updated_at = "superseded", str(reason or "corrected")[:200], _now()
    return lk


async def restore(db: AsyncSession, ws: str, owner: str, link_id: Any) -> Optional[KnownLink]:
    """Undo a supersede (the link was retired by mistake)."""
    try:
        uid = link_id if isinstance(link_id, UUID) else UUID(str(link_id))
    except Exception:
        return None
    lk = (await db.execute(select(KnownLink).where(KnownLink.id == uid, KnownLink.honcho_workspace_id == ws,
                                                   KnownLink.owner_peer_id == owner))).scalars().first()
    if lk is not None and lk.status == "superseded":
        lk.status, lk.note, lk.updated_at = "current", "", _now()
    return lk


async def merge(db: AsyncSession, ws: str, owner: str, keep_id: Any, absorb_id: Any) -> Optional[KnownEntity]:
    """Two names for one thing. The absorbed entity keeps resolving to the survivor; its aliases and links move; nothing is deleted."""
    keep, absorb = await get(db, ws, owner, keep_id), await get(db, ws, owner, absorb_id)
    if keep is None or absorb is None or keep.id == absorb.id:
        return None
    for a in await aliases_of(db, ws, owner, absorb.id):
        a.entity_id = keep.id
    await add_alias(db, ws, owner, keep.id, absorb.name, basis="stated")
    for lk in (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                        KnownLink.from_entity_id == absorb.id))).scalars().all():
        lk.from_entity_id = keep.id
    for lk in (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                        KnownLink.target_kind == "entity", KnownLink.target_ref == str(absorb.id)))).scalars().all():
        lk.target_ref = str(keep.id)
    absorb.status, absorb.merged_into_id, absorb.updated_at = "merged", keep.id, _now()
    keep.last_touched_at = _now()
    if absorb.summary and len(keep.summary) < 120:
        keep.summary = (keep.summary + " " + absorb.summary).strip()[:SUMMARY_MAX]
    return keep


# ------------------------------------------------------------- rendering ----

def _label(basis: str) -> str:
    return "" if basis == "stated" else " (inferred, not confirmed)"


def _ago(then: Optional[datetime], now: datetime) -> str:
    if then is None:
        return "unknown"
    d = (now.replace(tzinfo=None) - then.replace(tzinfo=None)).days
    return "today" if d <= 0 else ("yesterday" if d == 1 else f"{d} days ago")


class Ctx:
    """The clock a view is read at."""

    def __init__(self, now: datetime, tz: str, default_tz: str = "UTC") -> None:
        zone = ledger_views._zone(tz, default_tz)
        self.now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
        self.today = self.now.date()
        self.tz = zone.key


async def _find_self(db: AsyncSession, ws: str, owner: str) -> Optional[KnownEntity]:
    return (await db.execute(select(KnownEntity).where(KnownEntity.honcho_workspace_id == ws, KnownEntity.owner_peer_id == owner,
                                                       KnownEntity.kind == SELF_KIND))).scalars().first()


async def _relation_to_self(db: AsyncSession, ws: str, owner: str, e: KnownEntity, self_e: Optional[KnownEntity]) -> str:
    """How this entity relates to the person, read from its current links (stated or inferred, labelled)."""
    if self_e is None:
        return ""
    rows = (await db.execute(select(KnownLink).where(
        KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner, KnownLink.from_entity_id == e.id,
        KnownLink.target_kind == "entity", KnownLink.target_ref == str(self_e.id), KnownLink.status == "current"))).scalars().all()
    return "; ".join(dict.fromkeys(f"{_user_rel(l.relation)}{_label(l.basis)}" for l in rows))


async def _entity_links(db: AsyncSession, ws: str, owner: str, e: KnownEntity, include_superseded: bool = False) -> List[KnownLink]:
    q = select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner, KnownLink.from_entity_id == e.id)
    if not include_superseded:
        q = q.where(KnownLink.status == "current")
    out = list((await db.execute(q.order_by(KnownLink.created_at))).scalars().all())
    # links where this entity is the TARGET of another entity's link (read from the other side)
    inbound = (await db.execute(select(KnownLink).where(
        KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner, KnownLink.target_kind == "entity",
        KnownLink.target_ref == str(e.id), *( [] if include_superseded else [KnownLink.status == "current"] )))).scalars().all()
    return out + list(inbound)


async def _ledger_rows(db: AsyncSession, ws: str, owner: str, keys: Iterable[str]) -> List[Dict[str, Any]]:
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        return []
    rows = (await db.execute(select(LedgerItem).where(LedgerItem.honcho_workspace_id == ws, LedgerItem.owner_peer_id == owner,
                                                      LedgerItem.situation_key.in_(keys)))).scalars().all()
    return [{"key": i.situation_key, "kind": i.kind, "title": i.title, "status": i.status,
             "expected_date": i.expected_date.strftime("%Y-%m-%d") if i.expected_date else None, "expected_time": i.expected_time,
             "time_basis": i.time_basis, "time_zone": i.time_zone, "time_role": i.time_role, "importance": i.importance,
             "waiting_on": i.waiting_on, "question": i.question_text, "detail": i.detail,
             "updated_at": i.updated_at.isoformat() if i.updated_at else None, "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in rows]


def _ledger_line(row: Dict[str, Any], ctx: Ctx) -> str:
    it = ledger_views.to_item(row, ledger_views._zone(ctx.tz))
    if it.status in ledger_views.CLOSED:
        return f"- {it.title}: {it.status}"
    band = ledger_views.classify(it, ctx.now, ctx.today)
    return ledger_views.line(it, "week" if band == "older" else band, ctx.today)


async def _actions_for(db: AsyncSession, ws: str, owner: str, e: KnownEntity) -> List[AttentionAction]:
    return list((await db.execute(select(AttentionAction).where(
        AttentionAction.honcho_workspace_id == ws, AttentionAction.owner_peer_id == owner, AttentionAction.source == "entity",
        AttentionAction.source_ref == str(e.id), AttentionAction.state.in_(["pending", "due", "held"])))).scalars().all())


async def _open_count(db: AsyncSession, ws: str, owner: str, e: KnownEntity) -> int:
    keys = [l.target_ref for l in await _entity_links(db, ws, owner, e) if l.target_kind == "ledger"]
    rows = await _ledger_rows(db, ws, owner, keys)
    return sum(1 for r in rows if r["status"] in ledger_views.OPEN)


async def snapshot_text(db: AsyncSession, ws: str, owner: str, e: KnownEntity, ctx: Ctx, depth: str = "snapshot") -> str:
    """Self-contained, factual account of one entity read from its authoritative sources. depth: snapshot | connected | deep."""
    links = await _entity_links(db, ws, owner, e, include_superseded=(depth in ("connected", "deep")))
    cur = [l for l in links if l.status == "current"]
    head = f"{e.name} ({e.kind}{', sensitive' if e.sensitive else ''}){_label(e.basis)}"
    lines = [head + (": " + e.summary.strip().rstrip(".") + "." if e.summary.strip() else ".")]
    # relations to other entities (outbound as written, inbound described from this entity's side)
    rel_lines: List[str] = []
    for l in cur:
        if l.target_kind != "entity":
            continue
        inbound = l.from_entity_id != e.id
        other = await get(db, ws, owner, l.from_entity_id if inbound else l.target_ref)
        if other is None or other.status == "merged":
            continue
        if is_record(other) or is_self(other):
            if is_self(other):
                rel_lines.append(f"- User: {l.relation} {e.name}{_label(l.basis)}" if inbound else f"- {e.name}: {_user_rel(l.relation)}{_label(l.basis)}")
            continue
        subj, obj = (other, e) if inbound else (e, other)
        rel_lines.append(f"- {subj.name}: {l.relation} {obj.name}{_label(l.basis)}")
    if rel_lines:
        lines.append("Connected to:\n" + "\n".join(dict.fromkeys(rel_lines)))
    # remembered happenings, dispositions and patterns that involve this entity (newest first)
    recs: List[Tuple[KnownEntity, KnownLink]] = []
    for l in cur:
        if l.target_kind != "entity":
            continue
        other = await get(db, ws, owner, l.from_entity_id if l.from_entity_id != e.id else l.target_ref)
        if other is not None and is_record(other) and other.status in LIVE and not other.suppressed and other.id != e.id:
            recs.append((other, l))
    if recs:
        recs.sort(key=lambda t: (t[0].occurred_on or t[0].last_touched_at), reverse=True)
        cap = 3 if depth == "snapshot" else 6
        rl: List[str] = []
        for r, l in recs[:cap]:
            rl.append(await _record_line(db, ws, owner, r, ctx, via=l))
        lines.append("Remembered:\n" + "\n".join(dict.fromkeys(rl)))
    # operational matters, read from the ledger now
    keys = [l.target_ref for l in cur if l.target_kind == "ledger"]
    rows = await _ledger_rows(db, ws, owner, keys)
    open_rows = [r for r in rows if r["status"] in ledger_views.OPEN]
    closed_rows = [r for r in rows if r["status"] in ledger_views.CLOSED]
    if open_rows:
        lines.append("Open matters:\n" + "\n".join(_ledger_line(r, ctx) for r in sorted(open_rows, key=lambda r: (r["expected_date"] or "9999", r["title"]))[:8]))
    if depth in ("connected", "deep") and closed_rows:
        lines.append("Recently closed:\n" + "\n".join(_ledger_line(r, ctx) for r in closed_rows[:5]))
    # situations connected to this entity (the other side's summary and how recently it moved)
    sits = []
    for l in cur:
        if l.target_kind == "entity":
            other = await get(db, ws, owner, l.from_entity_id if l.from_entity_id != e.id else l.target_ref)
            if other is not None and is_situation(other) and other.id != e.id and other.status in LIVE:
                sits.append(f"- {other.name}{_label(l.basis)}: {other.summary.strip().rstrip('.')}. Last update {_ago(other.last_touched_at, ctx.now)}.")
    if sits:
        lines.append("Developing situations:\n" + "\n".join(dict.fromkeys(sits)))
    if is_situation(e):
        lines.append(f"Status: {e.status}. Last update {_ago(e.last_touched_at, ctx.now)}." + (" Not to be raised unprompted." if e.suppressed else ""))
    acts = await _actions_for(db, ws, owner, e)
    if acts and not e.suppressed:
        lines.append("Follow-ups intended:\n" + "\n".join(f"- {a.intent}" for a in acts[:3]))
    if depth in ("connected", "deep"):
        old = [l for l in links if l.status == "superseded"]
        if old:
            lines.append("Earlier understanding (superseded):\n" + "\n".join(f"- {l.relation} ({l.note or 'replaced'})" for l in old[:5]))
        al = [a.alias for a in await aliases_of(db, ws, owner, e.id) if norm(a.alias) != e.name_key]
        if al:
            lines.append("Also known as: " + ", ".join(al[:6]) + ".")
    if depth == "deep":
        ev = [f"\"{l.evidence}\" ({l.relation})" for l in cur if l.basis == "stated" and l.evidence][:6]
        src = [r for r in _refs(e.source_refs_json) if r.get("quote")][-4:]
        if ev or src:
            lines.append("Supporting evidence:\n" + "\n".join(["- " + x for x in ev] + [f"- \"{r['quote']}\"" for r in src]))
        for l in cur:
            if l.target_kind == "entity":
                other = await get(db, ws, owner, l.from_entity_id if l.from_entity_id != e.id else l.target_ref)
                if other is not None and other.summary and not is_situation(other):
                    lines.append(f"{other.name}: {other.summary.strip()}")
        lines.append(f"First recorded {e.first_seen_at.strftime('%-d %b %Y')}; last update {_ago(e.last_touched_at, ctx.now)}.")
    return neutral_user("\n".join(lines))


async def _rank(db: AsyncSession, ws: str, owner: str, ents: List[KnownEntity], ctx: Ctx) -> List[Tuple[float, KnownEntity, int]]:
    scored: List[Tuple[float, KnownEntity, int]] = []
    for e in ents:
        n_open = await _open_count(db, ws, owner, e)
        age = max(0, (ctx.now.replace(tzinfo=None) - e.last_touched_at.replace(tzinfo=None)).days)
        score = 3.0 * min(n_open, 4) + max(0.0, 10.0 - age * 0.5) + (2.0 if e.sensitive and is_situation(e) and age <= 14 else 0.0)
        scored.append((score, e, n_open))
    scored.sort(key=lambda t: (-t[0], t[1].name))
    return scored


async def overview_text(db: AsyncSession, ws: str, owner: str, ctx: Ctx, sensitive: str = "full") -> Tuple[str, List[Tuple[str, str]]]:
    """A compact account of the person's current world, from maintained records only. Selective, not exhaustive."""
    ents = [e for e in await list_all(db, ws, owner, statuses=("active",)) if not e.suppressed and not is_self(e) and not is_record(e)]
    self_e = await _find_self(db, ws, owner)
    exp = {r.ref: r for r in (await db.execute(select(CueExposure).where(
        CueExposure.honcho_workspace_id == ws, CueExposure.owner_peer_id == owner, CueExposure.source == "entity"))).scalars().all()}
    people_projects = [e for e in ents if not is_situation(e)]
    situations = []
    for e in ents:
        if not is_situation(e):
            continue
        x = exp.get(str(e.id))
        worn_out = bool(x and x.shown_count >= EXPOSURE_DEMOTE_AFTER and (x.engaged_at is None or (x.first_shown_at and x.engaged_at < x.first_shown_at))
                        and (ctx.now.replace(tzinfo=None) - e.last_touched_at.replace(tzinfo=None)).days >= STALE_SITUATION_DAYS)
        if not worn_out:
            situations.append(e)
    shown: List[Tuple[str, str]] = []
    blocks: List[str] = []
    pp = (await _rank(db, ws, owner, people_projects, ctx))[:OVERVIEW_PEOPLE_PROJECTS]
    if pp:
        lines = []
        for _, e, n_open in pp:
            tail = f" {n_open} open matter{'s' if n_open != 1 else ''}." if n_open else ""
            rel = await _relation_to_self(db, ws, owner, e, self_e)
            lead = f"{rel}. " if rel else ""
            lines.append(f"- {e.name} ({e.kind}){_label(e.basis)}: {lead}{e.summary.strip().rstrip('.')}.{tail}" if e.summary.strip() else f"- {e.name} ({e.kind}): {lead.rstrip()}{tail}")
            shown.append(("entity", str(e.id)))
        blocks.append("People, projects and places:\n" + "\n".join(lines))
    ss = (await _rank(db, ws, owner, situations, ctx))[:OVERVIEW_SITUATIONS]
    if ss:
        lines = []
        for _, e, _n in ss:
            tag = " (sensitive)" if e.sensitive else ""
            body = e.summary.strip().rstrip(".") if (sensitive == "full" or not e.sensitive) else "details available if they raise it"
            lines.append(f"- {e.name}{tag}: {body}. Last update {_ago(e.last_touched_at, ctx.now)}.")
            shown.append(("entity", str(e.id)))
        blocks.append("Developing situations:\n" + "\n".join(lines))
    recent = [e for e in await list_all(db, ws, owner, statuses=("active",), limit=300)
              if e.form == "happening" and not e.suppressed and (e.significance or 2) >= 3
              and (ctx.now.replace(tzinfo=None) - (e.occurred_on or e.last_touched_at).replace(tzinfo=None)).days <= 7]
    recent.sort(key=lambda e: (e.occurred_on or e.last_touched_at), reverse=True)
    if recent:
        lines = []
        for e in recent[:2]:
            lines.append(f"- {e.name} ({_ago(e.occurred_on or e.last_touched_at, ctx.now)})" + ("" if (e.sensitive and sensitive != "full") else f": {e.summary.strip().rstrip('.')}."))
            shown.append(("entity", str(e.id)))
        blocks.append("Recent consequential happenings:\n" + "\n".join(lines))
    if not blocks:
        return "", []
    head = f"[THEIR WORLD RIGHT NOW — maintained record, {ctx.now.strftime('%A %-d %B %Y')}. Each line reflects the latest recorded state.]"
    return neutral_user(head + "\n" + "\n".join(blocks)), shown


async def mentions_text(db: AsyncSession, ws: str, owner: str, text: str, ctx: Ctx) -> Tuple[str, List[Tuple[str, str]]]:
    found, ambiguous = await mentions(db, ws, owner, text)
    if not found and not ambiguous:
        return "", []
    parts: List[str] = []
    shown: List[Tuple[str, str]] = []
    for e in found:
        parts.append(await snapshot_text(db, ws, owner, e, ctx))
        shown.append(("entity", str(e.id)))
    for alias, cands in ambiguous:
        parts.append(f"\"{alias}\" could mean " + " or ".join(f"{c.name} ({c.kind}: {_cut(c.summary.rstrip('.'), 90)})" for c in cands)
                     + ". Which one is meant has not been established.")
    return "[WHO OR WHAT THEY MEAN — maintained record]\n" + "\n\n".join(parts), shown


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


def _words_meet(a: set, b: set) -> bool:
    """A word of the message and a tag word meet if equal or one begins the other (sleep / sleeping, book / books); 4+ letters for prefixes."""
    for x in a:
        for y in b:
            if x == y or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x))):
                return True
    return False


async def _record_line(db: AsyncSession, ws: str, owner: str, r: KnownEntity, ctx: Ctx, via: Optional[KnownLink] = None) -> str:
    when = ""
    if r.form == "happening" and r.occurred_on is not None:
        when = f", {r.occurred_on.strftime('%-d %b')} ({_ago(r.occurred_on, ctx.now)})"
    label = {"happening": "happened", "disposition": r.kind or "disposition", "pattern": "provisional pattern"}.get(r.form, r.kind)
    who = []
    for l in (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                         KnownLink.from_entity_id == r.id, KnownLink.target_kind == "entity",
                                                         KnownLink.status == "current"))).scalars().all():
        o = await get(db, ws, owner, l.target_ref)
        if o is not None and not is_self(o) and not is_record(o) and o.name not in who:
            who.append(o.name)
    inv = f"; involving {', '.join(who[:3])}" if who else ""
    sens = ", sensitive" if r.sensitive else ""
    return f"- {r.name} ({label}{when}{inv}{sens}){_label(r.basis)}: {r.summary.strip().rstrip('.')}."


async def pertinent_text(db: AsyncSession, ws: str, owner: str, text: str, mentioned: Sequence[KnownEntity], ctx: Ctx,
                         sensitive: str = "full") -> Tuple[str, List[Tuple[str, str]]]:
    """A SMALL selection of remembered happenings, dispositions and patterns that bear on what the person just said. Not a dump of everything in
    a domain, and not limited to what is directly linked to someone named: relevance comes from (a) a link to a mentioned entity, (b) a shared
    tag or domain with the mentioned entities, (c) a word of the message matching one of the record's tags. Recency and significance rank
    among the relevant ones; nothing appears on recency alone. A pattern stands in for the happenings that support it."""
    recs = [e for e in await list_all(db, ws, owner, statuses=("active",), limit=400) if is_record(e) and not e.suppressed]
    if not recs:
        return "", []
    links = (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                        KnownLink.target_kind == "entity", KnownLink.status == "current"))).scalars().all()
    adj: Dict[UUID, set] = {}
    support: Dict[UUID, set] = {}
    for l in links:
        t = UUID(l.target_ref)
        adj.setdefault(l.from_entity_id, set()).add(t)
        adj.setdefault(t, set()).add(l.from_entity_id)
    ment = {e.id for e in mentioned}
    ctx_tags = {t for e in mentioned for t in e.tags.split(",") if t}
    ctx_domains = _tag_domains(",".join(ctx_tags)) if ctx_tags else set()
    words = {_stem(w) for w in norm(text).split() if len(w) >= 3}
    scored: List[Tuple[float, KnownEntity]] = []
    for r in recs:
        s = 0.0
        if adj.get(r.id, set()) & ment:
            s += 4
        rt = {t for t in r.tags.split(",") if t}
        if _words_meet({_stem(w) for w in _tag_words(r.tags)}, words):
            s += 3
        if rt & ctx_tags:
            s += 3
        elif _tag_domains(r.tags) & ctx_domains:
            s += 2
        if s == 0:
            continue
        if r.form == "happening":
            age = max(0, (ctx.now.replace(tzinfo=None) - (r.occurred_on or r.last_touched_at).replace(tzinfo=None)).days)
            s += 3 if age <= RECENT_DAYS[0] else 2 if age <= RECENT_DAYS[1] else 1 if age <= RECENT_DAYS[2] else 0
        s += (r.significance or 2) - 1 + (1 if r.form == "pattern" else 0)
        scored.append((s, r))
    scored.sort(key=lambda t: (-t[0], t[1].name))
    chosen = [r for _, r in scored]
    pat_support = {n for r in chosen if r.form == "pattern" for n in adj.get(r.id, set())}
    chosen = [r for r in chosen if r.form == "pattern" or r.id not in pat_support][:PERTINENT_LIMIT]
    if not chosen:
        return "", []
    lines = []
    for r in chosen:
        if r.sensitive and sensitive != "full":
            lines.append(f"- {r.name} (sensitive): details available if they raise it.")
        else:
            lines.append(await _record_line(db, ws, owner, r, ctx))
    head = "[REMEMBERED THAT BEARS ON THIS — maintained record, chosen because it connects to what they just said; not everything held is shown]"
    return neutral_user(head + "\n" + "\n".join(lines)), [("entity", str(r.id)) for r in chosen]


async def packet(db: AsyncSession, ws: str, owner: str, text: str, ctx: Ctx, sensitive: str = "full") -> Dict[str, Any]:
    ov, s1 = await overview_text(db, ws, owner, ctx, sensitive)
    found, _amb = await mentions(db, ws, owner, text or "")
    mt, s2 = await mentions_text(db, ws, owner, text or "", ctx)
    pt, s3 = await pertinent_text(db, ws, owner, text or "", found, ctx, sensitive)
    return {"overview": ov, "mentions": "\n\n".join(x for x in (mt, pt) if x), "shown": [{"source": a, "ref": b} for a, b in dict.fromkeys(s1 + s2 + s3)]}


async def entity_view(db: AsyncSession, ws: str, owner: str, query: str, ctx: Ctx, depth: str = "connected") -> Dict[str, Any]:
    cands = await find(db, ws, owner, query)
    live = [c for c in cands if c.status != "merged"]
    if not live:
        return {"found": False, "text": f"Nothing is recorded under \"{query}\"."}
    if len(live) > 1 and len({norm(c.name) for c in live}) > 1:
        return {"found": True, "ambiguous": True,
                "text": f"\"{query}\" could mean: " + "; ".join(f"{c.name} ({c.kind}): {_cut(c.summary, 100)}" for c in live[:4]) + ". Which one is meant has not been established.",
                "entities": [{"id": str(c.id), "name": c.name} for c in live[:4]]}
    e = live[0]
    return {"found": True, "entity": {"id": str(e.id), "name": e.name, "kind": e.kind}, "text": await snapshot_text(db, ws, owner, e, ctx, depth)}


async def inspect(db: AsyncSession, ws: str, owner: str) -> Dict[str, Any]:
    """Everything the connected layer maintains, with provenance, for debugging 'is the problem Cortex's understanding, retrieval, or her response?'."""
    ents = await list_all(db, ws, owner, statuses=("active", "dormant", "resolved", "merged"), limit=500)
    links = (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner)
                              .order_by(KnownLink.created_at))).scalars().all()
    by_id = {e.id: e for e in ents}
    al = (await db.execute(select(KnownEntityAlias).where(KnownEntityAlias.honcho_workspace_id == ws, KnownEntityAlias.owner_peer_id == owner))).scalars().all()
    exp = (await db.execute(select(CueExposure).where(CueExposure.honcho_workspace_id == ws, CueExposure.owner_peer_id == owner))).scalars().all()
    return {"entities": [{"id": str(e.id), "name": e.name, "kind": e.kind, "form": e.form, "tags": e.tags, "occurred_on": e.occurred_on.date().isoformat() if e.occurred_on else None, "significance": e.significance, "status": e.status, "basis": e.basis, "sensitive": e.sensitive,
                          "suppressed": e.suppressed, "summary": e.summary, "merged_into": str(e.merged_into_id) if e.merged_into_id else None,
                          "aliases": [a.alias for a in al if a.entity_id == e.id], "provenance": _refs(e.source_refs_json),
                          "last_touched": e.last_touched_at.isoformat()} for e in ents],
            "links": [{"id": str(l.id), "from": by_id[l.from_entity_id].name if l.from_entity_id in by_id else str(l.from_entity_id),
                       "relation": l.relation, "target_kind": l.target_kind,
                       "target": (by_id[UUID(l.target_ref)].name if l.target_kind == "entity" and _isuuid(l.target_ref) and UUID(l.target_ref) in by_id else l.target_ref),
                       "basis": l.basis, "status": l.status, "evidence": l.evidence, "note": l.note} for l in links],
            "exposure": [{"source": x.source, "ref": x.ref, "shown_count": x.shown_count,
                          "last_shown": x.last_shown_at.isoformat() if x.last_shown_at else None,
                          "engaged": x.engaged_at.isoformat() if x.engaged_at else None} for x in exp]}


def _isuuid(s: str) -> bool:
    try:
        UUID(str(s))
        return True
    except Exception:
        return False


# -------------------------------------------------------------- exposure ----

async def record_exposure(db: AsyncSession, ws: str, owner: str, refs: Iterable[Dict[str, str]], now: Optional[datetime] = None) -> int:
    """The Runtime reports what it actually composed into a packet. Counts once per sitting-sized window, not once per turn."""
    now = (now or _now()).replace(tzinfo=None)
    n = 0
    for r in refs:
        src, ref = str(r.get("source") or "entity"), str(r.get("ref") or "")
        if not ref:
            continue
        x = (await db.execute(select(CueExposure).where(CueExposure.honcho_workspace_id == ws, CueExposure.owner_peer_id == owner,
                                                        CueExposure.source == src, CueExposure.ref == ref))).scalars().first()
        if x is None:
            db.add(CueExposure(honcho_workspace_id=ws, owner_peer_id=owner, source=src, ref=ref, shown_count=1, first_shown_at=now, last_shown_at=now))
            n += 1
        elif x.last_shown_at is None or (now - x.last_shown_at) > timedelta(minutes=SITTING_GAP_MIN):
            x.shown_count += 1
            x.last_shown_at, x.updated_at = now, now
            n += 1
    return n


async def record_engagement(db: AsyncSession, ws: str, owner: str, source: str, ref: str, now: Optional[datetime] = None) -> None:
    """The companion actually raised it, or the person answered (judged by the attention review from the session)."""
    now = (now or _now()).replace(tzinfo=None)
    x = (await db.execute(select(CueExposure).where(CueExposure.honcho_workspace_id == ws, CueExposure.owner_peer_id == owner,
                                                    CueExposure.source == source, CueExposure.ref == ref))).scalars().first()
    if x is None:
        db.add(CueExposure(honcho_workspace_id=ws, owner_peer_id=owner, source=source, ref=ref, shown_count=0, engaged_at=now))
    else:
        x.engaged_at, x.updated_at = now, now
