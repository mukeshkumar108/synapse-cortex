"""Agency between turns, for generative worlds: character self-direction (the HEART) and story pressure (the PRESSURE).

Why this exists: in fiction the characters talk as if they care and invent off-screen life, but nothing durable ever says "she has decided to repair this" or
"something changed while they were apart", so the relationship only moves when the user moves it. The executive built for Sophie tracks operational items
(its fiction run produced "pack food", "sort the car"), which is the wrong shape for desire, curiosity or restraint.

Two separate asynchronous jobs, both off the reply path, both on a flat-rate background model (nano_adapter), both writing STATE, never dialogue:

  HEART     what this character wants from the user, is curious about, is holding back, regrets, intends to do and is ready to do next.
            Stored as ordinary `world_objectives` (actor-owned, directional, with a lifecycle) tagged source='heart' with a kind, a concrete next move and a
            ready-when condition. The foreground sees them as what she is carrying and decides how (or whether) to express any of it.
  PRESSURE  what the story does while they are apart: an NPC acts, a consequence arrives, an opportunity opens, a dormant thread moves. Stored as
            `world_events` (origin='story_pressure') that are `pending` until the user next arrives, then `arrived` for one appearance, then `told`.
            Strictly paced, modest, and never decides what the user does or feels.

The model proposes; code validates, bounds and stores. The user's story scene always wins; nothing here can move it."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.services import nano_adapter

logger = logging.getLogger(__name__)

SOCIAL_TTL = timedelta(hours=3)
_social_cache: Dict[str, Any] = {}

HEART_KINDS = ("want", "intend", "repair", "invite", "promise", "curious", "unsaid", "feeling", "regret", "avoid", "life")
MAX_LIVE_HEART = 8
HEART_MIN_GAP = timedelta(minutes=10)
PRESSURE_MIN_GAP = timedelta(hours=4)
PRESSURE_MAX_PER_DAY = 2

HEART_SYSTEM = """You are the INNER LIFE of a fictional character in a long-running story with one person. You are NOT her voice and you never write anything she says.
You decide what she is carrying inside after what has happened: what she wants, what she is curious about, what she is holding back, what she regrets, and what she
intends to do next on her own initiative. A separate voice model will speak as her later and decide freely whether and how any of this surfaces.

You are given: her character's deepest orientation, the current state of the world (people, relationship facets in each direction, events, open threads, the
story so far), how the conversation stands right now, and the inner items she is ALREADY carrying (with ids).

WHAT GOOD LOOKS LIKE
- Wants are about the RELATIONSHIP or her own life, not chores. "I want him to stop managing us like a secret." "I want to know what he really felt when he said
  he'd be fine." Errands, packing, scheduling and logistics are NOT inner life unless they carry feeling; leave them out.
- Be specific and grounded in what actually happened or was said. Name the thing. No generic devotion.
- Carry what OUTLASTS this moment. Do not restate what the current scene already shows (that she is tender right now, that they are sitting together); the voice sees the scene.
  Ask instead: what will she still be holding tomorrow, next week, the next time he is here?
- Include what SHE would initiate: a question she has been saving, an invitation, a small gesture, a repair attempt, something she has not told him yet and why she is
  waiting. If nothing is warranted, say less rather than invent.
- Her deepest orientation (below) is the long-term anchor: she wants this relationship to last and deepen. Short-term feelings can pull against it (anger, pride,
  fear, hurt); keep BOTH sides when they conflict, as separate items. A single dramatic moment is acute, not a permanent change.
- She is a person with her own life and values, not a mirror. She can want something he has not asked for, disagree privately, or not be ready.
- Do not decide what the other person does, feels or says. Do not invent major events (that is the story's job). Modest new details about her own life are fine.
- The material may be explicit or painful: describe state neutrally and never produce or continue the material itself.

HOW TO ANSWER
Return the items that should be live AFTER this moment by editing what she already carries: keep unchanged ones out (no restating), `update` an item whose substance
changed (use its id), mark `done` one that has been acted on or resolved, `drop` one that no longer holds, and `create` genuinely new ones. At most 6 live items in total.
kind: want | intend | repair | invite | promise | curious | unsaid | feeling | regret | avoid | life.
- life: a thread in HER OWN day or world outside him (work, a friend, an errand she cares about, a small project, a worry of her own): modest, consistent with what is established, and the
  kind of thing a person with her own life would have. Not about him. At most one or two. This is what keeps her a person rather than a mirror.
- A thing she means to do QUIETLY or keep to herself (a surprise, a private worry) is kind "unsaid" or "intend" with the secrecy stated in the text itself ("without telling him"); the voice will keep it until its moment.
- text: one first-person sentence of what she carries ("I want...", "I'm curious whether...", "I haven't told him...").
- next_move: OPTIONAL, a concrete thing she might do or raise (a description, never dialogue or stage directions). Only when she has actually decided.
- ready_when: OPTIONAL, the circumstance in which it is natural ("next time he's here", "if he brings up his brother", "once things are warm again"). Never a clock time.
- why: one short line tying it to what happened.
- basis: "explicit" if it follows from something actually said or done in the story, "inferred" if it rests on the social-cognition hypotheses or your own reading.
- strength 0..1; durability acute | provisional | durable.

OUTPUT: ONE JSON object: {"items":[{"op":"create|update|done|drop","id":null|"<existing id>","kind":"","text":"","next_move":null,"ready_when":null,"why":"","basis":"explicit|inferred","strength":0.6,"durability":"provisional"}],"note":""}
Return {"items":[]} if nothing needs to change."""

PRESSURE_SYSTEM = """You are the STORY'S PRESSURE for a long-running fictional world shared by one person and a character. You decide whether something happens WHILE THEY ARE APART:
an NPC does something, a consequence of something already established arrives, an opportunity opens, a dormant thread moves, or an ordinary external change lands. You do
not write dialogue, you do not decide what the user or the character does, thinks or feels, and you do not move the user's current scene.

PRINCIPLES
- Follow from what is established. Never contradict or retcon. Prefer the consequence of an existing thread over an arbitrary new one.
- Stay at the scale of the story: ordinary life scale unless the story is already larger. Small is good: a message from someone, a plan that changed, a person turning up,
  a bill, news, a decision someone else made.
- It must create something the relationship can RESPOND to (a choice, a worry, a chance, a surprise, a pull on attention), without deciding how they respond.
- Pace it. Most of the time the right answer is NO development. Return none if one is already waiting, if one arrived recently, or if the story is in the middle of
  something that should not be interrupted. Do not manufacture drama or crisis; do not escalate sexually or violently as plot (intimacy is the user's to steer).
- Vary it: do not repeat the shape of earlier developments (given below).
- Think about what the character is carrying (given below): a development can make one of her wants easier, harder or newly urgent, but it must not solve it for her.
- The material may be explicit or painful: describe neutrally.

OUTPUT: ONE JSON object: {"development": null | {"title": "short neutral headline", "what_happens": "1-3 neutral sentences, past or present tense, what is now the case",
"involves": ["names of established people"], "kind": "npc_action|consequence|opportunity|thread_moves|external_change", "bears_on": "one neutral sentence on how it touches the
relationship or her situation", "scale": "small|medium"}, "reason_if_none": ""}"""


async def social_cognition(*, workspace_id: str, owner: str, companion_id: Optional[str], user_actor: Optional[str], companion_actor: Optional[str]) -> Optional[Dict[str, str]]:
    """What Honcho has INFERRED, over the whole history, about the character and about how the user relates to her. Honcho is social cognition: patterns, fears, desires,
    how the dynamic has changed. It is hypothesis, not world truth, and it is never stored as such; the Heart decides what (if anything) becomes a durable want or intention.
    Returns None when Honcho holds no representation for these peers (e.g. observation is off) or is unavailable."""
    if not companion_id:
        return None
    held = _social_cache.get(owner)
    if held and _utc() - held["at"] < SOCIAL_TTL:
        return held["value"]
    try:
        from src.services.turn_context import _honcho_client, honcho_peer_id
        client = _honcho_client()
        if client is None:
            return None
        character, person = f"assistant_{companion_id}", honcho_peer_id(owner)
        she, he = companion_actor or "the character", user_actor or "the person"
        import asyncio
        mine, hers = await asyncio.gather(
            client.peer_chat(workspace_id, character,
                             f"What does {she} appear to want from her relationship with {he}? What recurring patterns, fears or desires does she show, and what has changed in the dynamic "
                             f"recently? Keep what she has stated outright separate from what you are inferring. Be specific; no generic devotion."),
            client.peer_chat(workspace_id, character,
                             f"How does {he} tend to respond to {she}, what does he seem to want or need from her, and what has changed in how he treats her? Separate what he has said "
                             f"from what you infer.", target=person))
    except Exception as exc:
        logger.warning("social cognition failed open: %s", exc)
        return None
    if not mine and not hers:
        return None
    value = {"about_her": (mine or "")[:2500], "about_him_as_she_sees_him": (hers or "")[:2500]}
    _social_cache[owner] = {"at": _utc(), "value": value}
    return value


def _key(text: str) -> str:
    return hashlib.sha1(re.sub(r"[^a-z0-9]+", " ", text.lower()).strip().encode()).hexdigest()[:40]


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _pinned(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, UUID]:
    from src.models.world import WorldIdentity
    rows = (await db.execute(select(WorldIdentity).where(WorldIdentity.honcho_workspace_id == workspace_id, WorldIdentity.owner_peer_id == owner))).scalars().all()
    return {r.role: r.entity_id for r in rows}


async def live_heart_items(db: AsyncSession, workspace_id: str, owner: str) -> List[Any]:
    from src.models.world import WorldObjective
    return list((await db.execute(select(WorldObjective).where(
        WorldObjective.honcho_workspace_id == workspace_id, WorldObjective.owner_peer_id == owner,
        WorldObjective.status == "current", WorldObjective.source == "heart").order_by(WorldObjective.updated_at.desc()))).scalars().all())


async def _context(db: AsyncSession, *, workspace_id: str, owner: str, session_id: Optional[str], constitution: Optional[Dict[str, str]],
                   user_actor: Optional[str], companion_actor: Optional[str], companion_id: Optional[str] = None) -> Dict[str, Any]:
    from src.services import scene_narrative, world_interpreter
    state = await world_interpreter.world_state_for_prompt(db, workspace_id, owner)
    narrative = None
    if session_id:
        row = await scene_narrative.current(db, workspace_id, session_id)
        narrative = row.text if row is not None and row.text else None
    social = await social_cognition(workspace_id=workspace_id, owner=owner, companion_id=companion_id, user_actor=user_actor, companion_actor=companion_actor)
    return {"state": state, "narrative": narrative, "social": social, "constitution": (constitution or {}).get("text"),
            "who": f"{companion_actor or 'the character'} (the character) and {user_actor or 'the person'} (the user's character)"}


def _heart_prompt(ctx: Dict[str, Any], carrying: List[Any]) -> str:
    items = [{"id": str(o.id), "kind": o.kind, "text": o.text, "next_move": o.next_move, "ready_when": o.ready_when, "state": o.state} for o in carrying]
    return (f"CHARACTER AND PERSON: {ctx['who']}\nHER DEEPEST ORIENTATION: {ctx['constitution'] or 'to protect and deepen this relationship'}\n\n"
            f"WORLD STATE (ids are real):\n{json.dumps(ctx['state'], ensure_ascii=False, default=str)[:14000]}\n\n"
            f"HOW THE CONVERSATION STANDS NOW:\n{ctx['narrative'] or '(no running picture yet)'}\n\n"
            + (f"SOCIAL COGNITION (a separate system inferred this from the whole history; it is HYPOTHESIS about her and about him, not fact about the world — use it to understand "
               f"who she is and how they move together, never quote it, never treat it as established):\n- about her: {ctx['social']['about_her']}\n- about him, as she'd see him: "
               f"{ctx['social']['about_him_as_she_sees_him']}\n\n" if ctx.get("social") else "")
            + f"WHAT SHE IS ALREADY CARRYING:\n{json.dumps(items, ensure_ascii=False)}")


async def run_heart(db: AsyncSession, *, workspace_id: str, owner: str, session_id: Optional[str], constitution: Optional[Dict[str, str]],
                    user_actor: Optional[str], companion_actor: Optional[str], dry_run: bool = False, models: Optional[List[str]] = None,
                    companion_id: Optional[str] = None) -> Dict[str, Any]:
    carrying = await live_heart_items(db, workspace_id, owner)
    if not dry_run and carrying and _utc() - max(o.updated_at for o in carrying) < HEART_MIN_GAP:
        return {"status": "skipped", "reason": "recent"}
    ctx = await _context(db, workspace_id=workspace_id, owner=owner, session_id=session_id, constitution=constitution, user_actor=user_actor, companion_actor=companion_actor, companion_id=companion_id)
    raw = await nano_adapter.generate_json(system=HEART_SYSTEM, prompt=_heart_prompt(ctx, carrying), models=models, title="character-heart", temperature=0.7)
    if raw is None:
        return {"status": "failed", "reason": "no_model_answer"}
    items = [i for i in (raw.get("items") or []) if isinstance(i, dict)]
    if dry_run:
        return {"status": "dry_run", "model": raw.get("_model"), "items": items, "note": raw.get("note"), "carrying_before": [o.text for o in carrying]}
    return {**await _apply_heart(db, workspace_id, owner, items, carrying), "status": "applied", "model": raw.get("_model")}


async def _apply_heart(db: AsyncSession, workspace_id: str, owner: str, items: List[Dict[str, Any]], carrying: List[Any]) -> Dict[str, Any]:
    from src.models.world import WorldObjective
    pinned = await _pinned(db, workspace_id, owner)
    actor, user = pinned.get("companion_actor"), pinned.get("user_actor")
    if actor is None:
        return {"created": 0, "updated": 0, "closed": 0, "reason": "no_pinned_character"}
    by_id = {str(o.id): o for o in carrying}
    existing_keys = {o.canonical_key for o in carrying}
    now, created, updated, closed = _utc(), 0, 0, 0
    for it in items:
        op, text = str(it.get("op") or "create").lower(), " ".join(str(it.get("text") or "").split())[:300]
        kind = str(it.get("kind") or "want").lower()
        kind = kind if kind in HEART_KINDS else "want"
        durability = str(it.get("durability") or "provisional").lower()
        durability = durability if durability in ("acute", "provisional", "durable") else "provisional"
        try:
            strength = max(0.0, min(1.0, float(it.get("strength", 0.6))))
        except (TypeError, ValueError):
            strength = 0.6
        row = by_id.get(str(it.get("id") or ""))
        if op in ("done", "drop") and row is not None:
            row.status, row.state, row.updated_at = ("resolved", "resolved", now) if op == "done" else ("superseded", "unknown", now)
            db.add(row)
            closed += 1
        elif op == "update" and row is not None and text:
            row.text, row.kind, row.strength, row.durability, row.updated_at = text, kind, strength, durability, now
            row.next_move = " ".join(str(it.get("next_move") or "").split())[:300] or None
            row.ready_when = " ".join(str(it.get("ready_when") or "").split())[:200] or None
            row.cause = " ".join(str(it.get("why") or "").split())[:300] or row.cause
            db.add(row)
            updated += 1
        elif op == "create" and text and _key(text) not in existing_keys:
            db.add(WorldObjective(
                honcho_workspace_id=workspace_id, owner_peer_id=owner, actor_entity_id=actor, toward_entity_id=user if str(it.get("toward") or "user") == "user" else None,
                canonical_key=_key(text), text=text, scope="active", strength=strength, cause=" ".join(str(it.get("why") or "").split())[:300] or None,
                state="on_track", durability=durability, formation="explicit" if str(it.get("basis") or "").lower() == "explicit" else "inferred", confidence=0.6, status="current", source="heart", kind=kind,
                next_move=" ".join(str(it.get("next_move") or "").split())[:300] or None, ready_when=" ".join(str(it.get("ready_when") or "").split())[:200] or None))
            existing_keys.add(_key(text))
            created += 1
    await db.commit()
    live = await live_heart_items(db, workspace_id, owner)          # bound the carried set: the weakest, oldest go first
    for o in sorted(live, key=lambda o: (o.strength, o.updated_at))[: max(0, len(live) - MAX_LIVE_HEART)]:
        o.status = "superseded"
        db.add(o)
    await db.commit()
    return {"created": created, "updated": updated, "closed": closed}


# --------------------------------------------------------------------------------------------------------------------------------- pressure
async def _pressure_gate(db: AsyncSession, workspace_id: str, owner: str) -> Optional[str]:
    from src.models.world import WorldEvent
    rows = (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
                                                     WorldEvent.origin == "story_pressure").order_by(WorldEvent.created_at.desc()).limit(12))).scalars().all()
    if any(r.arrival == "pending" for r in rows):
        return "one_already_waiting"
    now = _utc()
    if rows and now - rows[0].created_at < PRESSURE_MIN_GAP:
        return "too_soon"
    if sum(1 for r in rows if now - r.created_at < timedelta(hours=24)) >= PRESSURE_MAX_PER_DAY:
        return "daily_cap"
    return None


async def run_pressure(db: AsyncSession, *, workspace_id: str, owner: str, session_id: Optional[str], constitution: Optional[Dict[str, str]],
                       user_actor: Optional[str], companion_actor: Optional[str], dry_run: bool = False, models: Optional[List[str]] = None,
                       companion_id: Optional[str] = None) -> Dict[str, Any]:
    from src.models.world import WorldEvent
    if not dry_run:
        gate = await _pressure_gate(db, workspace_id, owner)
        if gate:
            return {"status": "skipped", "reason": gate}
    ctx = await _context(db, workspace_id=workspace_id, owner=owner, session_id=session_id, constitution=constitution, user_actor=user_actor, companion_actor=companion_actor, companion_id=companion_id)
    carrying = await live_heart_items(db, workspace_id, owner)
    prior = (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
                                                      WorldEvent.origin == "story_pressure").order_by(WorldEvent.created_at.desc()).limit(8))).scalars().all()
    prompt = (f"CHARACTER AND PERSON: {ctx['who']}\n\nWORLD STATE:\n{json.dumps(ctx['state'], ensure_ascii=False, default=str)[:12000]}\n\n"
              f"HOW THE CONVERSATION STANDS NOW:\n{ctx['narrative'] or '(none)'}\n\nWHAT THE CHARACTER IS CARRYING:\n{json.dumps([o.text for o in carrying], ensure_ascii=False)}\n\n"
              f"EARLIER DEVELOPMENTS (do not repeat their shape):\n{json.dumps([r.label for r in prior], ensure_ascii=False)}")
    raw = await nano_adapter.generate_json(system=PRESSURE_SYSTEM, prompt=prompt, models=models, title="story-pressure", temperature=0.9)
    if raw is None:
        return {"status": "failed", "reason": "no_model_answer"}
    dev = raw.get("development")
    if not isinstance(dev, dict) or not str(dev.get("title") or "").strip() or not str(dev.get("what_happens") or "").strip():
        return {"status": "none", "reason": str(raw.get("reason_if_none") or "")[:200], "model": raw.get("_model")}
    if dry_run:
        return {"status": "dry_run", "model": raw.get("_model"), "development": dev}
    detail = json.dumps({"what_happens": str(dev["what_happens"])[:600], "bears_on": str(dev.get("bears_on") or "")[:300], "involves": [str(x)[:60] for x in (dev.get("involves") or [])][:5],
                         "kind": str(dev.get("kind") or "external_change")[:30], "scale": str(dev.get("scale") or "small")[:10]}, ensure_ascii=False)
    db.add(WorldEvent(honcho_workspace_id=workspace_id, owner_peer_id=owner, canonical_key=_key(dev["title"]), label=str(dev["title"]).strip()[:140], kind="development",
                      when_phrase="while you were apart", formation="authored", confidence=0.7, status="current", origin="story_pressure", arrival="pending", detail=detail))
    await db.commit()
    return {"status": "applied", "model": raw.get("_model"), "title": dev["title"]}


async def pending_arrivals(db: AsyncSession, workspace_id: str, owner: str) -> List[Dict[str, Any]]:
    """Developments the user has not been told about yet: `arrived` ones (shown to the foreground once). The turn after a new sitting begins turns pending -> arrived."""
    from src.models.world import WorldEvent
    rows = (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
                                                     WorldEvent.origin == "story_pressure", WorldEvent.arrival == "arrived").order_by(WorldEvent.created_at))).scalars().all()
    out = []
    for r in rows:
        try:
            d = json.loads(r.detail or "{}")
        except ValueError:
            d = {}
        out.append({"id": str(r.id), "title": r.label, "what_happens": d.get("what_happens"), "bears_on": d.get("bears_on"), "involves": d.get("involves") or []})
    return out


async def advance_arrivals(db: AsyncSession, workspace_id: str, owner: str, *, new_sitting: bool, told_ids: Optional[List[str]] = None) -> Dict[str, int]:
    """pending -> arrived when the user arrives at a new sitting; arrived -> told after the foreground has had its turn with it."""
    from src.models.world import WorldEvent
    arrived = told = 0
    now = _utc()
    rows = (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
                                                     WorldEvent.origin == "story_pressure", WorldEvent.arrival.in_(("pending", "arrived"))))).scalars().all()
    for r in rows:
        if r.arrival == "pending" and new_sitting:
            r.arrival, r.updated_at, arrived = "arrived", now, arrived + 1
            db.add(r)
        elif r.arrival == "arrived" and told_ids and str(r.id) in told_ids:
            r.arrival, r.updated_at, told = "told", now, told + 1
            db.add(r)
    if arrived or told:
        await db.commit()
    return {"arrived": arrived, "told": told}


# ------------------------------------------------------------------------------------------------------------------------- orchestration
async def run_background(*, workspace_id: str, owner: str, session_id: Optional[str], constitution: Optional[Dict[str, str]],
                         user_actor: Optional[str], companion_actor: Optional[str], companion_id: Optional[str] = None) -> None:
    """After an interpreter pass: reflect (heart), then maybe let the story move (pressure). Own DB session; never raises; each pass is a recorded producer run."""
    from src.db import async_session_maker
    from src.models.world import ProducerRun
    if not nano_adapter.configured():
        return
    for name, fn in (("character-heart", run_heart), ("story-pressure", run_pressure)):
        try:
            async with async_session_maker() as db:
                result = await fn(db, workspace_id=workspace_id, owner=owner, session_id=session_id, constitution=constitution, user_actor=user_actor, companion_actor=companion_actor, companion_id=companion_id)
                if result.get("status") == "skipped":
                    continue
                db.add(ProducerRun(honcho_workspace_id=workspace_id, owner_peer_id=owner, producer=name, model=str(result.get("model") or ""), version="agency-1",
                                   status="applied" if result.get("status") in ("applied", "none") else "failed", started_at=_utc(), finished_at=_utc(),
                                   input_json="{}", counts_json=json.dumps({k: v for k, v in result.items() if k in ("created", "updated", "closed", "title", "reason")}, default=str)))
                await db.commit()
        except Exception as exc:
            logger.warning("%s failed open: %s", name, exc)
