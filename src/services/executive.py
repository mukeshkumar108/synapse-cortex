"""Executive function for a companion world: attention over time, planning, initiative, action selection, observation, revision.

One model pass reads the CANONICAL world (interpreter state), the operational state (expectations, loops, commitments, work items, what was already
raised) and the clock, and returns typed INTENTS: what deserves attention, what to raise and when, what to prepare, what to do, what to wait on and
when to look again. Code owns mechanics only: it supplies the facts, validates ids, stores intents in `work_items`, enforces the autonomy policy by
consequence / reversibility / authority, schedules wakes, and leases the world. It never decides what matters.

Cognition is wake-driven, not polled: a wake is a cheap row (a time, a reason). The tick scans for due wakes with plain SQL and the model runs only
for worlds that have one. `wait` is a valid outcome and costs nothing until the next wake. The engine belongs to a world, not to a product: whether it
runs and how proactive delivery is limited is per-world product policy (`world_policies`)."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.executive import ExecutiveWake, WorldPolicy
from src.models.work_item import WorkItem
from src.models.world import ProducerRun
from src.services import world_lease

logger = logging.getLogger(__name__)

EXECUTIVE_MODEL = os.getenv("WORLD_EXECUTIVE_MODEL", os.getenv("WORLD_INTERPRETER_MODEL", "openai/gpt-5.6-luna-pro"))
EXECUTIVE_TIMEOUT = float(os.getenv("WORLD_EXECUTIVE_TIMEOUT_SECONDS", "120"))
DEFAULT_POLICY: Dict[str, Any] = {
    "executive": {"enabled": False, "daily_review_hours": 24, "timezone": "Europe/London"},
    "proactive": {"quiet_hours": [22, 8], "min_gap_hours": 4.0, "max_per_day": 2, "pressure_threshold": 0.6},
    # delegated authority as state: scoped standing permission, e.g. {"tool": "calendar.", "max_consequence": "low", "allow_irreversible": false}
    "autonomy": {"delegations": []},
    # who reads conversation into operational state (reminders, loops, completions): "legacy" (turn-by-turn narrow lane) or "interpreter" (the one semantic
    # reader). Transitional: removed together with the legacy ingestion once its tests are migrated.
    "operational": {"owner": "legacy"},
    # product-declared capabilities: [{"tool": "task.create", "description": "...", "args": {...}, "consequence": "low", "reversible": true}]. The PRODUCT states each tool's risk;
    # the model's own consequence claim can never lower it.
    "capabilities": {"tools": []},
}
ACTIVE_STATUSES = ("proposed", "surfaced", "in_progress", "waiting")
MAX_RETRIES = 3

SYSTEM = """You are the EXECUTIVE FUNCTION of a long-running companion (a real-life assistant or a fictional character). You are not the character's voice:
you decide what the companion should be attending to over time, and a separate voice model will speak. You are given the CANONICAL WORLD (people, events,
objectives, relationships, a brief), the OPERATIONAL STATE (expectations/reminders with windows, open loops, commitments, existing INTENTS), what was already
raised with the user, the current time, and WHY you were woken.

Return typed INTENTS: what the companion should attend to, raise, prepare, do, or wait on. Principles:
- You decide meaning and priority; facts (times, ids) come from the input. Never invent an id. Cite the ids you rely on.
- Doing nothing is a valid, common outcome. Return no intents (and no next_review_at) when nothing needs the companion now or later. Do not manufacture activity.
- Attention over time: use `wake_at` ONLY when you can name what will change by then (a window ends, an answer is due, an event passes). That is how the
  companion stays active between conversations without being polled. `waiting_on` says what an intent is waiting for.
- Initiative: `surface_now=true` only if reaching out to the user now is genuinely worthwhile, given what was already raised (do not nag; an ignored item
  needs more reason, not repetition), the user's recent activity, and whether silence is kinder. `message_gist` is the substance in neutral words, never a script.
- Actions: `act` is for something the companion itself can do with a tool listed in `capabilities` (and only those). State `tool` and `args`, the `consequence` (none|low|moderate|high), whether it
  is `reversible`, and the `authority_basis`: explicit_request | delegated | inferred. Do not claim anything was done: results arrive later as receipts.
- Observation and revision: update or close existing intents by id (`op` update|done|cancel|fail) when evidence or receipts changed them. A fictional world
  follows the same logic, grounded in that world's own relationships; the character's behaviour is not yours to script.
- Keep an AGENDA: what the companion is carrying across all concerns, not one reaction at a time. Each concern has a `horizon` (now | today | this_week |
  ongoing) and a `stance` (pursue | defer | set_aside). Choose among concerns and sequence them: the closest deadline must not always win over the
  important-but-not-urgent thing; look for opportunities (two things that combine, a quiet window, a dependency that just cleared) and for concerns that
  have become relevant again. Setting something aside is a decision: close the intent (`op: cancel`) with a `reason`, and it is remembered so you do not
  keep reconsidering it. `agenda` is your current view; replace it each pass.
- PLAN ACROSS CONCERNS, not one at a time. When several things compete, decide together: which is urgent now, which matters but can wait (`defer` with a
  `wake_at`), which is blocked on someone or something (`waiting_on`, and `depends_on`: titles/ids of the intents it needs first), and which can be done
  together (`combine_with`: titles/ids of intents that fit into one move or one window). Reflect the sequence in the `agenda`. A good plan reduces what
  the user has to carry and what the companion raises; it does not multiply reminders.
- Learn from what happened: `recent_outcomes` shows what followed earlier outreach (answered, ignored, completed, still open) and `set_aside` shows what
  was deliberately dropped. Adjust future initiative to it, in your own judgement; do not repeat what already failed to land. `external_events` are things
  that happened outside the conversation that may change what matters.
- Be concise. Every intent needs `rationale`.

OUTPUT: ONE JSON object: {"intents":[{"op":"create|update|done|cancel|fail","id":null|"<existing intent id>","kind":"ask|remind|check_in|prepare|act|wait|reconsider|<other>",
"title":"","rationale":"","about":{"type":"expectation|open_loop|commitment|objective|matter|event|null","id":null},"importance":0.0-1.0,
"urgency":"normal|acute","surface_now":false,"message_gist":null,"wake_at":null|"<ISO 8601 with offset>","waiting_on":null,"expected_observation":null,
"consequence":"none|low|moderate|high","reversible":true,"authority_basis":null,"action":null|{"tool":"","args":{}},"horizon":"now|today|this_week|ongoing","stance":"pursue|defer|set_aside","reason":null,"depends_on":[],"combine_with":[]}],
"agenda":{"carrying":[{"title":"","horizon":"","stance":"","why":""}],"sequence_note":""},"next_review_at":null|"<ISO 8601>","note":""}"""


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return _naive(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _str(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text if text and text.lower() != "null" else None


# ----------------------------------------------------------------------------- policy
async def get_policy(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, Any]:
    row = (await db.execute(select(WorldPolicy).where(WorldPolicy.honcho_workspace_id == workspace_id, WorldPolicy.owner_peer_id == owner))).scalars().first()
    stored = json.loads(row.policy_json or "{}") if row else {}
    return {section: {**defaults, **(stored.get(section) or {})} for section, defaults in DEFAULT_POLICY.items()}


async def set_policy(db: AsyncSession, workspace_id: str, owner: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    row = (await db.execute(select(WorldPolicy).where(WorldPolicy.honcho_workspace_id == workspace_id, WorldPolicy.owner_peer_id == owner))).scalars().first()
    merged = {**(json.loads(row.policy_json or "{}") if row else {})}
    for section, values in (policy or {}).items():
        if section in DEFAULT_POLICY and isinstance(values, dict):
            merged[section] = {**(merged.get(section) or {}), **values}
    if row is None:
        row = WorldPolicy(honcho_workspace_id=workspace_id, owner_peer_id=owner)
    row.policy_json, row.updated_at = json.dumps(merged), _utc()
    db.add(row)
    await db.commit()
    return await get_policy(db, workspace_id, owner)


# ----------------------------------------------------------------------------- wakes
async def add_wake(db: AsyncSession, workspace_id: str, owner: str, due_at: datetime, reason: str, *, attempts: int = 0, dedupe: bool = True,
                   detail: Optional[Dict[str, Any]] = None) -> None:
    due_at = _naive(due_at)
    if dedupe and not detail:
        existing = (await db.execute(select(ExecutiveWake.id).where(
            ExecutiveWake.honcho_workspace_id == workspace_id, ExecutiveWake.owner_peer_id == owner, ExecutiveWake.consumed_at.is_(None),
            ExecutiveWake.reason == reason, ExecutiveWake.due_at <= due_at + timedelta(minutes=5), ExecutiveWake.due_at >= due_at - timedelta(minutes=5)))).first()
        if existing:
            return
    db.add(ExecutiveWake(honcho_workspace_id=workspace_id, owner_peer_id=owner, due_at=due_at, reason=reason[:200], attempts=attempts,
                          detail_json=json.dumps(detail, default=str)[:4000] if detail else None))
    await db.commit()


async def note_changed(db: AsyncSession, workspace_id: str, owner: str, reason: str = "world_changed", delay_seconds: int = 90,
                       detail: Optional[Dict[str, Any]] = None) -> None:
    """Something relevant to this world changed (new interpretation, a receipt, an external event): reconsider soon. A no-op unless the world's policy
    enables the executive, so it costs one row read for worlds that have not opted in."""
    try:
        if (await get_policy(db, workspace_id, owner))["executive"].get("enabled"):
            await add_wake(db, workspace_id, owner, _utc() + timedelta(seconds=delay_seconds), reason, detail=detail)
    except Exception as exc:
        logger.warning("executive wake not recorded: %s", exc)


async def operational_snapshot(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, Any]:
    """Open time-bound state with ids: expectations (reminders/plans with windows), open loops, commitments. Read by the interpreter (to close/update by id)
    and by the executive (to decide attention)."""
    from sqlalchemy import or_
    from src.models.commitment_candidate import CommitmentCandidate, CommitmentCandidateStatus
    from src.models.expectation import Expectation, OutcomeState
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    exps = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id, or_(Expectation.owner_peer_id == owner, Expectation.subject_peer_id == owner),
        Expectation.outcome_state == OutcomeState.UNKNOWN, Expectation.superseded_by_id.is_(None)).order_by(Expectation.expected_window_end.asc().nullslast()).limit(25))).scalars().all()
    loops = (await db.execute(select(OpenLoop).where(
        OpenLoop.honcho_workspace_id == workspace_id, OpenLoop.owner_peer_id == owner, OpenLoop.status == OpenLoopStatus.OPEN).order_by(OpenLoop.created_at.desc()).limit(20))).scalars().all()
    commits = (await db.execute(select(CommitmentCandidate).where(
        CommitmentCandidate.honcho_workspace_id == workspace_id, CommitmentCandidate.owner_peer_id == owner,
        CommitmentCandidate.status.in_((CommitmentCandidateStatus.PENDING, CommitmentCandidateStatus.MATERIALIZED))).order_by(CommitmentCandidate.created_at.desc()).limit(20))).scalars().all()
    return {
        "expectations": [{"id": str(e.id), "title": e.title, "summary": (e.summary or "")[:160], "window": [_iso(e.expected_window_start), _iso(e.expected_window_end)],
                          "deadline": _iso(e.hard_deadline_at), "phrase": e.raw_temporal_phrase, "direction": e.direction} for e in exps],
        "open_loops": [{"id": str(l.id), "title": l.title, "summary": (l.summary or "")[:160], "expires_at": _iso(l.expires_at)} for l in loops],
        "commitments": [{"id": str(c.id), "title": c.title, "phrase": c.raw_temporal_phrase, "status": getattr(c.status, "value", c.status)} for c in commits],
    }


# ----------------------------------------------------------------------------- context
async def build_context(db: AsyncSession, workspace_id: str, owner: str, *, now: datetime, policy: Dict[str, Any], reasons: List[str],
                        external_events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from src.models.operational_state import ProactiveLog, TurnStamp
    from src.services.world_interpreter import world_state_for_prompt
    external_events = external_events or []
    tz = ZoneInfo(policy["executive"].get("timezone") or "Europe/London")
    local = now.replace(tzinfo=timezone.utc).astimezone(tz)
    world = await world_state_for_prompt(db, workspace_id, owner)
    ops = await operational_snapshot(db, workspace_id, owner)
    items = (await db.execute(select(WorkItem).where(
        WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.status.in_(ACTIVE_STATUSES)).order_by(WorkItem.updated_at.desc()).limit(30))).scalars().all()
    raised = (await db.execute(select(ProactiveLog).where(
        ProactiveLog.honcho_workspace_id == workspace_id, ProactiveLog.owner_peer_id == owner).order_by(ProactiveLog.at.desc()).limit(8))).scalars().all()
    last_turn = (await db.execute(select(TurnStamp.turn_at).where(
        TurnStamp.honcho_workspace_id == workspace_id, TurnStamp.owner_peer_id == owner).order_by(TurnStamp.turn_at.desc()).limit(1))).scalar()
    since = now - timedelta(days=14)
    past = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.source_agent == "executive",
                                                    WorkItem.updated_at >= since).order_by(WorkItem.updated_at.desc()).limit(60))).scalars().all()
    turns_after = {}
    for i in past:       # raw facts only: did the user say anything after we raised it? the executive judges what that means
        if i.last_surfaced_at:
            nxt = (await db.execute(select(TurnStamp.turn_at).where(TurnStamp.honcho_workspace_id == workspace_id, TurnStamp.owner_peer_id == owner,
                                                                    TurnStamp.turn_at > i.last_surfaced_at).order_by(TurnStamp.turn_at.asc()).limit(1))).scalar()
            turns_after[i.id] = nxt
    outcomes = [{"id": str(i.id), "title": i.action, "kind": i.kind, "raised_at": _iso(i.last_surfaced_at), "times_raised": i.surfaced_count, "status_now": i.status,
                 "user_next_active_after": _iso(turns_after.get(i.id)), "what_was_said": json.loads(i.extra_json or "{}").get("outbound_text"), "receipt": json.loads(i.receipt_json) if i.receipt_json else None}
                for i in past if i.last_surfaced_at][:20]
    set_aside = [{"id": str(i.id), "title": i.action, "reason": json.loads(i.extra_json or "{}").get("reason")} for i in past if i.status == "cancelled"][:15]
    agenda_row = next((i for i in past if i.kind == "agenda"), None)
    agenda_prev = json.loads(agenda_row.extra_json or "{}").get("agenda") if agenda_row else None
    intents = [{"id": str(i.id), "kind": i.kind, "title": i.action, "status": i.status, "wake_at": _iso(i.wake_at), "waiting_on": i.waiting_on,
                "importance": i.importance, "surfaced_count": i.surfaced_count, "last_surfaced_at": _iso(i.last_surfaced_at), "receipt": json.loads(i.receipt_json) if i.receipt_json else None}
               for i in items if i.kind != "agenda"]
    return {"now": {"utc": now.isoformat() + "Z", "local": local.isoformat(), "weekday": local.strftime("%A")}, "woken_because": reasons, "world": world,
            "operational": ops, "intents": intents,
            "already_raised": [{"at": _iso(r.at), "what": r.item_key, "decision": r.decision} for r in raised],
            "user_last_active": _iso(last_turn), "policy": {"proactive": policy["proactive"], "delegations": policy["autonomy"].get("delegations") or [], "capabilities": policy["capabilities"].get("tools") or []},
            "recent_outcomes": outcomes, "set_aside": set_aside, "external_events": external_events, "agenda": agenda_prev}


# ----------------------------------------------------------------------------- autonomy
CONSEQUENCE_RANK = {"none": 0, "low": 1, "moderate": 2, "high": 3}


def permission(intent: Dict[str, Any], delegations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Explicit product policy over what the model labelled: authority comes from consequence, reversibility and the basis of authorisation, never from
    how confident the inference was. Internal cognition, scheduling and in-policy outreach are autonomous; consequential, external or irreversible
    actions need confirmation unless authority was explicitly delegated."""
    if intent.get("kind") != "act":
        return {"mode": "autonomous"}
    tool = str((intent.get("action") or {}).get("tool") or "")
    for d in delegations or []:        # standing, scoped authority granted earlier: within it the action needs no fresh confirmation
        if tool and tool.startswith(str(d.get("tool") or "\0")) and CONSEQUENCE_RANK.get(intent.get("consequence") or "low", 1) <= CONSEQUENCE_RANK.get(d.get("max_consequence") or "none", 0) \
                and (bool(intent.get("reversible")) or bool(d.get("allow_irreversible"))):
            return {"mode": "autonomous", "basis": "delegation"}
    low_risk = intent.get("consequence") in ("none", "low") and bool(intent.get("reversible"))
    authorised = intent.get("authority_basis") in ("explicit_request", "delegated")
    if low_risk and authorised:
        return {"mode": "autonomous"}
    why = "consequential_or_irreversible" if not low_risk else "no_explicit_authority"
    return {"mode": "needs_confirmation", "reason": why}


# ----------------------------------------------------------------------------- the pass
def _known_ids(ctx: Dict[str, Any]) -> Dict[str, set]:
    w = ctx["world"]
    return {"expectation": {e["id"] for e in ctx["operational"]["expectations"]}, "open_loop": {l["id"] for l in ctx["operational"]["open_loops"]},
            "commitment": {c["id"] for c in ctx["operational"]["commitments"]}, "objective": {o["id"] for o in w["objectives"]},
            "matter": {m["id"] for m in w["matters"]}, "event": {e["id"] for e in w["events"]}}


async def run_pass(db: AsyncSession, *, workspace_id: str, owner: str, reasons: List[str], adapter: Any, now: Optional[datetime] = None,
                   external_events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    now = _naive(now) if now else _utc()
    policy = await get_policy(db, workspace_id, owner)
    run = ProducerRun(honcho_workspace_id=workspace_id, owner_peer_id=owner, producer="executive", model=EXECUTIVE_MODEL, version="ex-1", status="queued",
                      input_json=json.dumps({"reasons": reasons}))
    db.add(run)
    await db.commit()
    rid = run.id
    key, holder = world_lease.lease_key(workspace_id, owner) + "|exec", str(rid)
    if not await world_lease.acquire(db, key, holder, wait_seconds=20):
        await _finish(db, rid, "deferred", {"reason": "lease_timeout"})
        return {"status": "deferred", "run_id": holder}
    try:
        run.status, run.started_at = "running", _utc()
        db.add(run)
        await db.commit()
        ctx = await build_context(db, workspace_id, owner, now=now, policy=policy, reasons=reasons, external_events=external_events)
        prompt = "CONTEXT (ids are real):\n" + json.dumps(ctx, ensure_ascii=False, default=str)
        raw = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"type": "object"}, model_id=EXECUTIVE_MODEL, max_tokens=4000,
                                                temperature=0.2, strict=False, timeout=EXECUTIVE_TIMEOUT)
        usage = getattr(adapter, "last_usage", None)
        outcome = await apply_intents(db, workspace_id=workspace_id, owner=owner, raw=raw if isinstance(raw, dict) else {}, ctx=ctx, run_id=str(rid), now=now)
        await _finish(db, rid, "applied", {"reasons": reasons, "context": {"expectations": len(ctx["operational"]["expectations"]), "open_loops": len(ctx["operational"]["open_loops"]),
                      "commitments": len(ctx["operational"]["commitments"]), "intents_in": len(ctx["intents"])}, **outcome, "note": _str((raw or {}).get("note")), "usage": usage},
                      {"intents_applied": len(outcome["applied"]), "dropped": len(outcome["dropped"])})
        return {"status": "applied", "run_id": holder, **outcome}
    except Exception as exc:
        await _finish(db, rid, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        raise
    finally:
        await world_lease.release(db, key, holder)


async def apply_intents(db: AsyncSession, *, workspace_id: str, owner: str, raw: Dict[str, Any], ctx: Dict[str, Any], run_id: str, now: datetime) -> Dict[str, Any]:
    known = _known_ids(ctx)
    existing = {i["id"] for i in ctx["intents"]}
    applied: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    wakes: List[Dict[str, Any]] = []
    for it in (raw.get("intents") if isinstance(raw.get("intents"), list) else []):
        if not isinstance(it, dict):
            dropped.append({"reason": "not_an_object"})
            continue
        op = str(it.get("op") or "create").lower()
        title = _str(it.get("title"))
        wake_at = _parse(it.get("wake_at"))
        if wake_at is not None and wake_at <= now:
            wake_at = None          # a wake in the past is not a plan; nothing will change by then
        if op == "create":
            if not title:
                dropped.append({"reason": "no_title", "intent": str(it)[:80]})
                continue
            about = it.get("about") if isinstance(it.get("about"), dict) else {}
            a_type, a_id = _str(about.get("type")), _str(about.get("id"))
            if a_type and a_id and a_id not in known.get(a_type, set()):
                a_type = a_id = None             # an id that was not shown is never trusted
            action = it.get("action") if isinstance(it.get("action"), dict) else None
            kind = (_str(it.get("kind")) or "reconsider").lower()
            if kind == "act" and not (action and _str(action.get("tool"))):
                dropped.append({"reason": "act_without_tool", "title": title})
                continue
            catalog = {c.get("tool"): c for c in (ctx["policy"].get("capabilities") or []) if isinstance(c, dict)}
            if kind == "act":
                spec = catalog.get(_str((action or {}).get("tool")))
                if spec is None:
                    dropped.append({"reason": "unknown_tool", "title": title, "tool": _str((action or {}).get("tool"))})
                    continue
                it = {**it, "consequence": spec.get("consequence") or "high", "reversible": bool(spec.get("reversible", False))}      # the product's declared risk, not the model's claim
            decision = permission({"kind": kind, "consequence": _str(it.get("consequence")) or "low", "reversible": bool(it.get("reversible", False)),
                                   "authority_basis": _str(it.get("authority_basis")), "action": action}, ctx["policy"].get("delegations"))
            if kind == "act" and not (action and _str(action.get("tool"))):
                dropped.append({"reason": "act_without_tool", "title": title})
                continue
            extra = {"horizon": _str(it.get("horizon")), "stance": _str(it.get("stance")), "depends_on": [str(x)[:120] for x in (it.get("depends_on") or []) if x][:6],
                     "combine_with": [str(x)[:120] for x in (it.get("combine_with") or []) if x][:6], "rationale": _str(it.get("rationale")), "surface_now": bool(it.get("surface_now")), "urgency": _str(it.get("urgency")) or "normal",
                     "message_gist": _str(it.get("message_gist")), "expected_observation": _str(it.get("expected_observation")),
                     "consequence": _str(it.get("consequence")), "reversible": bool(it.get("reversible", False)), "authority_basis": _str(it.get("authority_basis")),
                     "permission": decision}
            status = "waiting" if kind in ("wait", "reconsider") or _str(it.get("waiting_on")) else "proposed"
            if kind == "act" and decision["mode"] == "autonomous":
                status = "in_progress"           # approved for execution; completion only ever comes from a receipt
            if kind == "act" and decision["mode"] == "needs_confirmation":
                extra.update({"requires_confirmation": True, "surface_now": True, "message_gist": extra["message_gist"] or f"Offer to: {title}"})
                kind = "ask"
            row = WorkItem(honcho_workspace_id=workspace_id, owner_peer_id=owner, parent_type=a_type or "world", parent_id=a_id or owner, owner="sophie",
                           action=title[:300], status=status, importance=max(0.0, min(1.0, float(it.get("importance") or 0.5))),
                           authority="ask" if extra.get("requires_confirmation") else ("act" if kind == "act" else "prepare"), source_agent="executive",
                           evidence_text=_str(it.get("rationale")), provenance_json=json.dumps({"run_id": run_id}), kind=kind, wake_at=wake_at,
                           waiting_on=_str(it.get("waiting_on")) or (("; ".join(extra["depends_on"])) if extra.get("depends_on") else None), run_id=run_id, tool_json=json.dumps(action) if action else None, extra_json=json.dumps(extra))
            db.add(row)
            await db.flush()
            applied.append({"op": "create", "id": str(row.id), "kind": kind, "status": status, "permission": decision["mode"]})
            if wake_at:
                wakes.append({"due": wake_at, "reason": f"intent:{row.id}"})
            continue
        target_id = _str(it.get("id"))
        if op not in ("update", "done", "cancel", "fail") or not target_id or target_id not in existing:
            dropped.append({"reason": "unknown_intent_id_or_op", "id": target_id, "op": op})
            continue
        row = await db.get(WorkItem, uuid.UUID(target_id))
        if row is None or row.honcho_workspace_id != workspace_id or row.owner_peer_id != owner:
            dropped.append({"reason": "intent_not_in_world", "id": target_id})
            continue
        extra = json.loads(row.extra_json or "{}")
        if op == "update":
            if title:
                row.action = title[:300]
            for field, key in (("waiting_on", "waiting_on"),):
                if _str(it.get(key)) is not None:
                    setattr(row, field, _str(it.get(key)))
            if it.get("importance") is not None:
                row.importance = max(0.0, min(1.0, float(it["importance"])))
            if wake_at is not None:
                row.wake_at = wake_at
                wakes.append({"due": wake_at, "reason": f"intent:{row.id}"})
            elif row.wake_at is not None and row.wake_at <= now:
                row.wake_at = None          # that wake has fired; a stale time is not a plan
            for key in ("rationale", "message_gist", "expected_observation", "urgency"):
                if _str(it.get(key)) is not None:
                    extra[key] = _str(it.get(key))
            if "surface_now" in it:
                extra["surface_now"] = bool(it.get("surface_now"))
            if extra.get("requires_confirmation") and row.tool_json and _str(it.get("authority_basis")) in ("explicit_request", "delegated"):
                # The executive judged that authority has now been given (e.g. the user said yes). The permission is re-derived from the PRODUCT's declared risk.
                tool = (json.loads(row.tool_json) or {}).get("tool")
                spec = next((c for c in (ctx["policy"].get("capabilities") or []) if isinstance(c, dict) and c.get("tool") == tool), None)
                if spec is not None:
                    again = permission({"kind": "act", "consequence": spec.get("consequence") or "high", "reversible": bool(spec.get("reversible", False)),
                                        "authority_basis": _str(it.get("authority_basis")), "action": {"tool": tool}}, ctx["policy"].get("delegations"))
                    if again["mode"] == "autonomous":
                        row.kind, row.status = "act", "in_progress"
                        extra.update({"requires_confirmation": False, "surface_now": False, "authority_granted": _str(it.get("authority_basis"))})
        else:
            row.status = {"done": "done", "cancel": "cancelled", "fail": "failed"}[op]
            if _str(it.get("reason")):
                extra["reason"] = _str(it.get("reason"))
            extra["surface_now"] = False
            row.wake_at = None
        row.run_id, row.updated_at, row.extra_json = run_id, _utc(), json.dumps(extra)
        db.add(row)
        applied.append({"op": op, "id": target_id, "status": getattr(row.status, "value", row.status)})
    agenda = raw.get("agenda") if isinstance(raw.get("agenda"), dict) else None
    if agenda and isinstance(agenda.get("carrying"), list):
        row = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.kind == "agenda"))).scalars().first()
        payload = {"agenda": {"carrying": [c for c in agenda["carrying"] if isinstance(c, dict)][:25], "sequence_note": _str(agenda.get("sequence_note")), "as_of": now.isoformat()}}
        if row is None:
            row = WorkItem(honcho_workspace_id=workspace_id, owner_peer_id=owner, parent_type="world", parent_id=owner, owner="sophie", action="agenda", status="in_progress",
                           source_agent="executive", kind="agenda", provenance_json=json.dumps({"run_id": run_id}), run_id=run_id, extra_json=json.dumps(payload))
        else:
            row.extra_json, row.run_id, row.updated_at = json.dumps(payload), run_id, _utc()
        db.add(row)
    await db.commit()
    nxt = _parse(raw.get("next_review_at"))
    if nxt and nxt > now:
        wakes.append({"due": nxt, "reason": "next_review"})
    for w in wakes:
        await add_wake(db, workspace_id, owner, w["due"], w["reason"])
    return {"applied": applied, "dropped": dropped, "wakes": [{"due": w["due"].isoformat(), "reason": w["reason"]} for w in wakes]}


async def _finish(db: AsyncSession, rid: Any, status: str, detail: Dict[str, Any], counts: Optional[Dict[str, Any]] = None) -> None:
    try:
        await db.rollback()
        row = await db.get(ProducerRun, rid)
        row.status, row.finished_at = status, _utc()
        row.detail_json = json.dumps({**json.loads(row.detail_json or "{}"), **detail}, default=str)[:100000]
        if counts is not None:
            row.counts_json = json.dumps(counts)
        db.add(row)
        await db.commit()
    except Exception as exc:
        logger.warning("could not finish executive run %s: %s", rid, exc)


# ----------------------------------------------------------------------------- tick (cheap scan; model only when a world has a reason)
async def tick(db: AsyncSession, *, adapter: Any, now: Optional[datetime] = None, max_worlds: int = 5) -> Dict[str, Any]:
    now = _naive(now) if now else _utc()
    await _daily_reviews(db, now)
    due = (await db.execute(select(ExecutiveWake).where(ExecutiveWake.consumed_at.is_(None), ExecutiveWake.due_at <= now).order_by(ExecutiveWake.due_at.asc()).limit(100))).scalars().all()
    worlds: Dict[tuple, List[ExecutiveWake]] = {}
    for w in due:
        worlds.setdefault((w.honcho_workspace_id, w.owner_peer_id), []).append(w)
    ran, skipped = [], 0
    for (ws, owner), wakes in list(worlds.items())[:max_worlds]:
        claimed = []
        for w in wakes:         # atomic claim: two processes can never run the same wake
            res = await db.execute(update(ExecutiveWake).where(ExecutiveWake.id == w.id, ExecutiveWake.consumed_at.is_(None)).values(consumed_at=now))
            if res.rowcount:
                claimed.append(w)
        await db.commit()
        if not claimed:
            continue
        if not (await get_policy(db, ws, owner))["executive"].get("enabled"):
            skipped += 1
            continue
        try:
            events = [{"reason": w.reason, "at": _iso(w.created_at), **(json.loads(w.detail_json) if w.detail_json else {})} for w in claimed if w.detail_json]
            result = await run_pass(db, workspace_id=ws, owner=owner, reasons=sorted({w.reason.split(":")[0] for w in claimed}), adapter=adapter, now=now, external_events=events)
            if result["status"] == "deferred":
                await add_wake(db, ws, owner, now + timedelta(minutes=2), "retry:lease", attempts=max(w.attempts for w in claimed) + 1)
            ran.append({"workspace_id": ws, "owner": owner, "status": result["status"], "run_id": result.get("run_id")})
        except Exception as exc:
            attempts = max(w.attempts for w in claimed) + 1
            logger.warning("executive pass failed for %s (attempt %s): %s", owner, attempts, exc)
            if attempts < MAX_RETRIES:
                await add_wake(db, ws, owner, now + timedelta(minutes=5 * attempts), "retry:error", attempts=attempts, dedupe=False)
            ran.append({"workspace_id": ws, "owner": owner, "status": "failed", "error": type(exc).__name__})
    return {"due_worlds": len(worlds), "ran": ran, "skipped_disabled": skipped}


async def _daily_reviews(db: AsyncSession, now: datetime) -> None:
    """Safety net for enabled worlds: if there has been activity but no executive pass for a day, schedule one. Mechanical; costs nothing otherwise."""
    from src.models.operational_state import TurnStamp
    for pol in (await db.execute(select(WorldPolicy))).scalars().all():
        cfg = {**DEFAULT_POLICY["executive"], **((json.loads(pol.policy_json or "{}")).get("executive") or {})}
        if not cfg.get("enabled"):
            continue
        horizon = now - timedelta(hours=float(cfg.get("daily_review_hours") or 24))
        last = (await db.execute(select(ProducerRun.created_at).where(
            ProducerRun.honcho_workspace_id == pol.honcho_workspace_id, ProducerRun.owner_peer_id == pol.owner_peer_id, ProducerRun.producer == "executive",
            ProducerRun.status == "applied").order_by(ProducerRun.created_at.desc()).limit(1))).scalar()
        if last and last > horizon:
            continue
        active = (await db.execute(select(TurnStamp.turn_at).where(
            TurnStamp.honcho_workspace_id == pol.honcho_workspace_id, TurnStamp.owner_peer_id == pol.owner_peer_id, TurnStamp.turn_at > now - timedelta(days=7)).limit(1))).scalar()
        if active or last is None:
            await add_wake(db, pol.honcho_workspace_id, pol.owner_peer_id, now, "daily_review")


# ----------------------------------------------------------------------------- delivery + receipts
async def surfaced_agenda(db: AsyncSession, workspace_id: str, owner: str) -> List[Dict[str, Any]]:
    """Executive intents that want to reach the user, shaped for the initiative gate (which owns quiet hours, budget and cadence)."""
    rows = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner,
                                                    WorkItem.source_agent == "executive", WorkItem.kind != "agenda", WorkItem.status.in_(ACTIVE_STATUSES)).order_by(WorkItem.importance.desc()))).scalars().all()
    out = []
    for r in rows:
        extra = json.loads(r.extra_json or "{}")
        if not extra.get("surface_now"):
            continue
        out.append({"what": r.action, "pressure": r.importance, "status": "outstanding", "severity": "acute" if extra.get("urgency") == "acute" else "normal",
                    "id": str(r.id), "work_item_id": str(r.id), "kind": r.kind, "title": r.action, "message_gist": extra.get("message_gist"), "rationale": r.evidence_text,
                    "next_move": extra.get("message_gist"), "why": r.evidence_text,       # the fields the Runtime composer forwards to the foreground model
                    "requires_confirmation": bool(extra.get("requires_confirmation"))})
    return out


async def mark_surfaced(db: AsyncSession, work_item_id: str, now: datetime) -> None:
    row = await db.get(WorkItem, uuid.UUID(work_item_id))
    if row is not None:
        extra = json.loads(row.extra_json or "{}")
        extra["surface_now"] = False            # raised once; the executive decides on a later pass whether it deserves raising again
        row.status, row.surfaced_count, row.last_surfaced_at, row.extra_json = "surfaced", (row.surfaced_count or 0) + 1, _naive(now), json.dumps(extra)
        db.add(row)
        await db.commit()
        await note_changed(db, row.honcho_workspace_id, row.owner_peer_id, "intent_surfaced", delay_seconds=1800)


async def record_receipt(db: AsyncSession, *, workspace_id: str, owner: str, work_item_id: str, status: str, result_ref: Optional[str], detail: Optional[str]) -> Dict[str, Any]:
    """What actually happened to an action intent. Stored as a receipt, never inferred; the executive observes and revises on its next pass."""
    row = await db.get(WorkItem, uuid.UUID(work_item_id))
    if row is None or row.honcho_workspace_id != workspace_id or row.owner_peer_id != owner:
        return {"ok": False, "reason": "unknown_work_item"}
    row.receipt_json = json.dumps({"status": status, "result_ref": result_ref, "detail": (detail or "")[:500], "at": _utc().isoformat()})
    row.status = "done" if status == "succeeded" else ("failed" if status == "failed" else row.status)
    row.updated_at = _utc()
    db.add(row)
    await db.commit()
    await note_changed(db, workspace_id, owner, "receipt", delay_seconds=5)
    return {"ok": True, "status": row.status}


async def speak_candidates(db: AsyncSession, workspace_id: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Owners with an executive intent that wants to reach the user, for the app's proactive scan (the app owns the conversation and the push channel).
    Cheap and mechanical: no model. Owners recently held back by the policy gate, or with a delivery already in flight, are left out so the scan does not
    ask the gate every minute."""
    from src.models.operational_state import ProactiveLog
    now = _naive(now) if now else _utc()
    rows = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.source_agent == "executive", WorkItem.kind != "agenda",
                                                    WorkItem.status.in_(ACTIVE_STATUSES)).limit(300))).scalars().all()
    by_owner: Dict[str, List[WorkItem]] = {}
    for r in rows:
        if json.loads(r.extra_json or "{}").get("surface_now"):
            by_owner.setdefault(r.owner_peer_id, []).append(r)
    out = []
    for owner, items in by_owner.items():
        recent = (await db.execute(select(ProactiveLog.decision, ProactiveLog.at).where(
            ProactiveLog.honcho_workspace_id == workspace_id, ProactiveLog.owner_peer_id == owner, ProactiveLog.at >= now - timedelta(minutes=15)).order_by(ProactiveLog.at.desc()))).all()
        if any(str(d).startswith("withheld") or (d == "reserved" and at >= now - timedelta(minutes=5)) for d, at in recent):
            continue
        items.sort(key=lambda r: -(r.importance or 0))
        out.append({"owner": owner, "intent_id": str(items[0].id), "title": items[0].action, "importance": items[0].importance, "count": len(items)})
    return out


async def record_outbound(db: AsyncSession, workspace_id: str, owner: str, intent_id: str, text: str, decision_id: Optional[str] = None) -> bool:
    """Exact causal link: the Runtime composed this text to carry out THIS intent (it holds the intent id), so record what was actually said on the intent.
    The executive then sees its own move, and later evidence can be related to it. No matching, no timing heuristics."""
    try:
        row = await db.get(WorkItem, uuid.UUID(intent_id))
    except (ValueError, TypeError):
        return False
    if row is None or row.honcho_workspace_id != workspace_id or row.owner_peer_id != owner:
        return False
    extra = json.loads(row.extra_json or "{}")
    extra["outbound_text"], extra["outbound_decision_id"] = (text or "")[:600], decision_id
    row.extra_json, row.updated_at = json.dumps(extra), _utc()
    db.add(row)
    await db.commit()
    return True



async def pending_actions_all(db: AsyncSession, workspace_id: str) -> List[Dict[str, Any]]:
    """Action intents cleared for execution, across every owner (the app's tool worker pulls these)."""
    rows = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.source_agent == "executive", WorkItem.kind == "act",
                                                    WorkItem.status == "in_progress", WorkItem.receipt_json.is_(None)).limit(50))).scalars().all()
    return [{"work_item_id": str(r.id), "owner": r.owner_peer_id, "title": r.action, "tool": json.loads(r.tool_json or "{}")} for r in rows]
