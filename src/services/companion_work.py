"""The companion's working space: one implementation for every companion and surface.

Writes here are explicit companion acts. They never call a model, never create a
memory run, and never touch notebook/ledger/arc/preparation, so they cannot
trigger listening, Ling, consolidation or a preparation rebuild. Reads are plain
SQL. Product policy (per companion, per surface) is enforced here, whoever calls.

Policy: COMPANION_WORK_POLICY is JSON {"<companion_id>": {"foreground": "off|read|write",
"independent": "off|read|write"}}. A companion not listed has the capability off.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.companion_work import CompanionWork, CompanionWorkEvent
from src.models.world import utc_now

SURFACES = ("foreground", "independent")
LEVELS = ("off", "read", "write")
ACTIONS = ("create", "revise", "continue", "complete", "abandon")
# What the companion is shown are ordinary words; the stored vocabulary stays internal.
WORDS = {"new": "create", "add": "continue", "rewrite": "revise", "finish": "complete", "discard": "abandon"}
DEFAULT_POLICY = {"sophie": {"foreground": "write", "independent": "write"}}
MAX_TEXT = 8000
EXCERPT = 360


class WorkError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def load_policy() -> Dict[str, Dict[str, str]]:
    raw = os.getenv("COMPANION_WORK_POLICY", "").strip()
    if not raw:
        return dict(DEFAULT_POLICY)
    try:
        parsed = json.loads(raw)
        return {str(k): {s: str(v.get(s, "off")) for s in SURFACES} for k, v in parsed.items() if isinstance(v, dict)}
    except Exception:
        return dict(DEFAULT_POLICY)


def level(companion_id: str, surface: str) -> str:
    lv = (load_policy().get(companion_id) or {}).get(surface, "off")
    return lv if lv in LEVELS else "off"


def require(companion_id: str, surface: str, need: str) -> None:
    if surface not in SURFACES:
        raise WorkError("bad_surface", f"surface must be one of {SURFACES}")
    have = level(companion_id, surface)
    if LEVELS.index(have) < LEVELS.index(need):
        raise WorkError("policy_denied", f"working space is '{have}' for {companion_id} on {surface}; '{need}' is not permitted")


Scope = Tuple[str, str, str]   # (workspace_id, owner, companion_id)


def _evidence_list(evidence: Any) -> List[Any]:
    if isinstance(evidence, list):
        return [e if isinstance(e, (dict, str)) else str(e) for e in evidence][:12]
    if isinstance(evidence, (dict, str)) and evidence:
        return [evidence]
    return []


async def _find(db: AsyncSession, scope: Scope, ref: str) -> CompanionWork:
    ref = (ref or "").strip().lower()
    if not ref:
        raise WorkError("missing_id", "which item? give its id from your list")
    rows = (await db.execute(select(CompanionWork).where(
        CompanionWork.honcho_workspace_id == scope[0], CompanionWork.owner_peer_id == scope[1],
        CompanionWork.companion_id == scope[2]))).scalars().all()
    hits = [r for r in rows if str(r.id).lower() == ref or str(r.id).lower().startswith(ref)]
    if not hits:
        raise WorkError("not_found", f"no item of yours with id '{ref}'")
    if len(hits) > 1:
        raise WorkError("ambiguous", f"'{ref}' matches more than one item; give more of the id")
    return hits[0]


async def act(db: AsyncSession, scope: Scope, *, surface: str, action: str, item_id: Optional[str] = None,
              title: str = "", text: str = "", kind: str = "", note: str = "", evidence: Any = None,
              sitting_id: str = "", conversation_id: str = "") -> Dict[str, Any]:
    """One explicit companion act. Returns {item, event}."""
    require(scope[2], surface, "write")
    action = WORDS.get(action, action)
    if action not in ACTIONS:
        raise WorkError("bad_action", f"action must be one of {ACTIONS}")
    text, note, title, kind = (text or "")[:MAX_TEXT], (note or "")[:1000], (title or "").strip()[:200], (kind or "").strip()[:60]
    now = utc_now()
    if action == "create":
        if not (title or text.strip()):
            raise WorkError("empty", "a new item needs a title or some text")
        item = CompanionWork(honcho_workspace_id=scope[0], owner_peer_id=scope[1], companion_id=scope[2],
                             title=title or text.strip().split("\n", 1)[0][:120], text=text, kind=kind,
                             origin_sitting_id=sitting_id, origin_surface=surface, origin_conversation_id=conversation_id)
        db.add(item)
        await db.flush()
        written = text
    else:
        item = await _find(db, scope, item_id or "")
        if item.status != "open" and action != "revise":
            raise WorkError("not_open", f"that item is {item.status}; only revise can reopen it")
        if action in ("revise", "continue") and not text.strip():
            raise WorkError("empty", f"{action} needs text")
        if action == "revise":
            item.text = text
            if title:
                item.title = title
            if kind:
                item.kind = kind
            item.status = "open"
            item.closed_at = None
            written = text
        elif action == "continue":
            item.text = (item.text.rstrip() + "\n\n" + text.strip())[:MAX_TEXT * 4]
            written = text
        else:
            if action == "complete" and text.strip():
                item.text = (item.text.rstrip() + "\n\n" + text.strip())[:MAX_TEXT * 4]      # a closing addition is kept, not dropped
            item.status = "completed" if action == "complete" else "abandoned"
            item.closed_at = now
            written = text
        item.version += 1
        item.updated_at = now
    ev = CompanionWorkEvent(
        work_id=item.id, honcho_workspace_id=scope[0], owner_peer_id=scope[1], companion_id=scope[2],
        version=item.version, action=action, author=f"companion:{scope[2]}", surface=surface,
        sitting_id=sitting_id, conversation_id=conversation_id, text=written, note=note,
        evidence_json=json.dumps(_evidence_list(evidence))[:20000])
    db.add(ev)
    await db.commit()
    return {"item": item, "event": ev}


async def list_items(db: AsyncSession, scope: Scope, *, status: Optional[str] = "open", limit: int = 20) -> List[CompanionWork]:
    q = select(CompanionWork).where(
        CompanionWork.honcho_workspace_id == scope[0], CompanionWork.owner_peer_id == scope[1],
        CompanionWork.companion_id == scope[2])
    if status:
        q = q.where(CompanionWork.status == status)
    rows = (await db.execute(q.order_by(CompanionWork.updated_at.desc()).limit(limit))).scalars().all()
    return list(rows)


async def get_with_events(db: AsyncSession, scope: Scope, ref: str) -> Dict[str, Any]:
    item = await _find(db, scope, ref)
    evs = (await db.execute(select(CompanionWorkEvent).where(CompanionWorkEvent.work_id == item.id)
                            .order_by(CompanionWorkEvent.version.asc(), CompanionWorkEvent.created_at.asc()))).scalars().all()
    return {"item": item, "events": list(evs)}


def short(item: CompanionWork) -> str:
    return str(item.id)[:8]


def _ago(then: datetime, now: datetime) -> str:
    s = max(0, int((now - then).total_seconds()))
    if s < 3600:
        return f"{max(1, s // 60)}m ago"
    if s < 172800:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def _where(item: CompanionWork) -> str:
    return {"foreground": "while talking with them", "independent": "on your own"}.get(item.origin_surface, "earlier")


def line(item: CompanionWork, now: datetime, excerpt: int = EXCERPT) -> str:
    body = " ".join((item.text or "").split())
    body = (body[:excerpt] + "…") if len(body) > excerpt else body
    return f"- [{short(item)}] {item.title} (written {_where(item)}; updated {_ago(item.updated_at, now)})" + (f": {body}" if body else "")


async def context_block(db: AsyncSession, scope: Scope, surface: str, limit: int = 12, excerpt: int = EXCERPT) -> str:
    """What the companion sees of its own open work at the start of a sitting. A pure read."""
    if level(scope[2], surface) == "off":
        return ""
    items = await list_items(db, scope, status="open", limit=limit)
    if not items:
        return ""
    now = utc_now()
    return "\n".join(line(i, now, excerpt) for i in items)


def full_text(item: CompanionWork, events: List[CompanionWorkEvent]) -> str:
    out = [f"[{short(item)}] {item.title} — {'still open' if item.status == 'open' else item.status}",
           "", item.text or "(no text yet)", "", "What you did with it, oldest first:"]
    for e in events:
        ev = _evidence_list(json.loads(e.evidence_json or "[]"))
        out.append(f"- {e.created_at:%Y-%m-%d %H:%M}Z {e.action} ({'in conversation' if e.surface == 'foreground' else 'on your own'})"
                   + (f" note: {e.note}" if e.note else "") + (f" [rests on {len(ev)} cited source(s)]" if ev else ""))
    return "\n".join(out)


async def run_tool(db: AsyncSession, scope: Scope, *, surface: str, tool: str, args: Dict[str, Any],
                   sitting_id: str = "", conversation_id: str = "", evidence: Any = None) -> Dict[str, Any]:
    """Execute a work_read / work_write call and return {ok, text, ...} where text is exactly what the model is shown."""
    try:
        if tool == "work_read":
            require(scope[2], surface, "read")
            ref = str(args.get("id") or "").strip()
            if ref:
                got = await get_with_events(db, scope, ref)
                return {"ok": True, "text": full_text(got["item"], got["events"]), "item_id": str(got["item"].id)}
            items = await list_items(db, scope, status="open", limit=30)
            now = utc_now()
            return {"ok": True, "text": "\n".join(line(i, now, 220) for i in items) or "Nothing open in your working space."}
        if tool == "work_write":
            op = str(args.get("do") or args.get("op") or args.get("action") or "").strip().lower()
            res = await act(db, scope, surface=surface, action=op, item_id=str(args.get("id") or ""),
                            title=str(args.get("title") or ""), text=str(args.get("text") or ""), kind=str(args.get("kind") or ""),
                            note=str(args.get("note") or ""), evidence=evidence if evidence is not None else args.get("evidence"),
                            sitting_id=sitting_id, conversation_id=conversation_id)
            item = res["item"]
            return {"ok": True, "text": f"Kept ({op}) as [{short(item)}], version {item.version}, {item.status}.",
                    "item_id": str(item.id), "version": item.version, "status": item.status, "event_id": str(res["event"].id)}
        return {"ok": False, "code": "unknown_tool", "text": "That is not available now."}
    except WorkError as exc:
        return {"ok": False, "code": exc.code, "text": f"Not done: {exc.message}"}
