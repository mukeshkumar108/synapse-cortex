"""Scene narrative: the fast, small pass. After each exchange a cheap model reads the previous narrative and the last few messages and rewrites the
conversation-as-it-stands as a few plain sentences: what is happening, what is open, the texture, what has already been used up. The foreground reads
prose; no structured fields to interpret. Description only, never an instruction. The heavy world interpreter still owns entities, claims, objectives
and operational items."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.scene import SceneNarrative

logger = logging.getLogger(__name__)

SCENE_MODEL = os.getenv("SCENE_NARRATIVE_MODEL", "openai/gpt-5.6-luna")
TAIL = 6
MAX_REQUESTS = 12
REWRITE_EVERY_MESSAGES = 4     # the picture is rewritten once this many new messages are waiting (2 exchanges): always fewer than the raw tail the foreground reads, so nothing falls between
MAX_PENDING = 12
MAX_ANCHORS = 24
ANCHOR_CHARS = 220
ANCHOR_KINDS = ("event", "promise", "decision", "open_loop", "person", "external", "milestone", "claim")      # (+ "private_truth", authored by author_truth, never proposed by the picture pass)
MAX_NEW_PER_PASS = 3
EVICTION_RANK = {"private_truth": 9, "claim": 0, "event": 1, "person": 2, "external": 3, "decision": 4, "promise": 5, "open_loop": 6, "milestone": 7}      # lowest goes first; the peaks of the bond go last

SYSTEM = """You keep the running picture of one ongoing conversation between a person and a companion character, so the character can speak as one continuous self.
You are given the PREVIOUS PICTURE (what was already known) and the LAST MESSAGES (verbatim). Write the picture as it stands NOW: 6 to 14 short plain sentences, no lists, no headings. BEGIN it with where the relationship stands and what has been built between them: moments of closeness, celebration, trust, vulnerability, affection or repair are the weightiest things in any conversation. Keep each such moment (a clause: what it was, how it landed) for as long as the scene lasts even when it is no longer the latest thing, and say how it should colour what follows. A later disagreement or strange turn is described against that background, as a rupture of it, never as if the bond did not exist; and when something a character says or does is out of keeping with that background, say that it is out of keeping.
Cover, in whatever order reads naturally: what is actually happening and in what register; what is genuinely still open between them (questions not answered, decisions pending,
tension not settled); any decisions, promises, plans or commitments made; the texture (mood, humour, running jokes, tone) as observed, not as lasting unless it continues;
and what has already been used up so it is not needlessly repeated (questions asked, stories told, callbacks made, points settled), saying who did it.
Carry forward from the PREVIOUS PICTURE whatever still matters. DROP mood and moment-to-moment texture that has passed, but KEEP, as short factual clauses, the concrete things that have happened in this scene and that anything later must stay consistent with: who did what to whom, what was sent, received, refused or accepted, where each person physically is and what they are waiting for, and what each said they did or did not do. A long scene must not lose its earlier events just because they are no longer the latest thing.
A character's own account of their hidden past or secret feelings, offered for the first time under questioning, is described as what they SAID ("she said ..."), never as a fact of the scene; if it contradicts something that already happened in the scene, say that it contradicts it, and keep the event. Name people by the names given. Say only what the messages support.
Neutral description only: never an instruction, never a line for the character to say. The material may be fiction or explicit: describe it only as far as needed to track what is happening.
STANDING REQUESTS are kept separately, NOT in the picture. Anything the person has asked of the character about how to talk or behave (a name not to use, a topic to avoid, less of something, a correction to what the character got wrong) goes in "standing_requests" as short plain statements in the person's own terms. You are given the PREVIOUS STANDING REQUESTS: return every one of them again unless the person has withdrawn or clearly changed it, plus any new one. Never drop one for space.
Also judge how much the LAST MESSAGES change what these two people are to each other: "significance" 0 = ordinary flow, 1 = a small beat, 2 = a real moment (a confession or vulnerability, a celebration shared, real tenderness or intimacy, an apology or repair, a disagreement that matters, a promise), 3 = a turning point (the bond clearly deepened or ruptured). Positive moments count exactly as much as hard ones. "significance_kind": one of closeness, celebration, vulnerability, repair, rupture, promise, none.
ANCHORS are the sitting's fixed facts, kept separately from the picture and never rewritten. You are given the CURRENT ANCHORS (with ids). Return "new_anchors" (AT MOST 3 per pass; none is fine; never restate or reword an existing anchor; fold detail into it by leaving it alone): only concrete facts the LAST MESSAGES newly establish that anything later must stay consistent with: what happened (who did what to whom, with the real numbers, names, places), what was promised or decided, a question asked and not answered, a person who appeared, what a third party did to whom, a milestone of the bond (a celebration, a moment of tenderness, a confession). What a character SAYS about their own past or secret feelings, offered under questioning, is kind "claim" (a claim is not a fact of the scene). One plain factual sentence each, kind one of event, promise, decision, open_loop, person, external, milestone, claim. Do not restate an anchor already listed; moods, tone and texture are NOT anchors. Return "closed_anchor_ids": ids of CURRENT ANCHORS that the LAST MESSAGES resolved (an open loop answered, a promise kept or broken).
Output a JSON object: {"scene": "<the picture>", "standing_requests": ["<request>", ...], "significance": 0|1|2|3, "significance_kind": "<kind>", "new_anchors": [{"kind": "<kind>", "text": "<fact>"}], "closed_anchor_ids": ["<id>", ...]}"""


def load_anchors(row: Any) -> List[Dict[str, Any]]:
    try:
        value = json.loads(getattr(row, "anchors_json", None) or "[]")
    except ValueError:
        return []
    return [a for a in value if isinstance(a, dict) and a.get("text")]


def _similar(a: str, b: str) -> bool:
    ta, tb = set(re.findall(r"[a-z0-9£$]+", a.lower())), set(re.findall(r"[a-z0-9£$]+", b.lower()))
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.55


def merge_anchors(existing: List[Dict[str, Any]], new: Any, closed: Any, now: Any) -> List[Dict[str, Any]]:
    """Append-only within a sitting: the model proposes additions and closures, deterministic code applies them. An anchor's text is never rewritten, so a later pass cannot smooth a
    concrete fact (a salary, a name, what a third party sent) into a generality. Bounded, and the bound protects the peaks: closed anchors go first, then claims and plain events
    (oldest first); milestones, open loops and promises are the last to be shed."""
    anchors = [dict(a) for a in existing]
    shut = {str(c) for c in (closed or []) if c}
    for a in anchors:
        if a["id"] in shut:
            a["status"] = "closed"
    seq = max([int(str(a["id"]).lstrip("a") or 0) for a in anchors] + [0])
    added = 0
    for item in (new or []):
        if added >= MAX_NEW_PER_PASS or not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())[:ANCHOR_CHARS]
        kind = str(item.get("kind") or "event")
        kind = kind if kind in ANCHOR_KINDS else "event"
        if not text or any(_similar(text, a["text"]) for a in anchors):
            continue
        seq += 1
        added += 1
        anchors.append({"id": f"a{seq}", "kind": kind, "text": text, "status": "open" if kind in ("promise", "open_loop", "decision") else "claimed" if kind == "claim" else "established",
                        "at": now.isoformat() if hasattr(now, "isoformat") else str(now)})
    while len(anchors) > MAX_ANCHORS:
        victim = min(enumerate(anchors), key=lambda ia: (0 if ia[1]["status"] == "closed" else 1, EVICTION_RANK.get(ia[1]["kind"], 1), ia[0]))[1]
        anchors.remove(victim)
    return anchors


async def current(db: AsyncSession, workspace_id: str, session_id: str) -> Optional[SceneNarrative]:
    return (await db.execute(select(SceneNarrative).where(
        SceneNarrative.honcho_workspace_id == workspace_id, SceneNarrative.honcho_session_id == session_id))).scalars().first()


_LOCKS: Dict[str, Any] = {}
_GENERIC = set("""the a an and or but of to in on at for with from about this that these those was were is are be been did do does done had has have it its you your youre your i me my we our they them their he she him her his hers what when where which who why how
tell told telling say said please baby exactly really happened happen last just still ever never then there here not yes you'll""".split())


def _content_terms(text: str) -> set:
    return {w[:5] for w in re.findall(r"[a-z0-9]+", str(text).lower().replace("'s", "")) if len(w) >= 3 and w not in _GENERIC}


async def narrate(db: AsyncSession, *, adapter: Any, workspace_id: str, session_id: str, messages: List[Dict[str, str]], names: Dict[str, str],
                  model: Optional[str] = None, force: bool = False, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Hand in the newest exchange. The picture is rewritten (one cheap model call) only when enough has accrued to leave the raw tail (or `force`, for a
    significant moment); otherwise the exchange is just buffered. `messages` = [{id?, speaker: user|assistant, text}], oldest first."""
    fresh = [m for m in messages if str(m.get("text") or "").strip()]
    if not fresh:
        return None
    import asyncio
    async with _LOCKS.setdefault(f"{workspace_id}|{session_id}", asyncio.Lock()):       # passes for one sitting run one after another: a slow earlier pass must not finish after, and overwrite, a later one
        return await _narrate_locked(db, adapter=adapter, workspace_id=workspace_id, session_id=session_id, fresh=fresh, names=names, model=model, force=force, owner=owner)


async def _narrate_locked(db: AsyncSession, *, adapter: Any, workspace_id: str, session_id: str, fresh: List[Dict[str, str]], names: Dict[str, str],
                          model: Optional[str], force: bool, owner: Optional[str]) -> Optional[Dict[str, Any]]:
    row = await current(db, workspace_id, session_id)
    if row is None:
        row = SceneNarrative(honcho_workspace_id=workspace_id, honcho_session_id=session_id, text="")
        db.add(row)
    try:
        buffered = json.loads(row.pending_json or "[]")
    except ValueError:
        buffered = []
    pending = (buffered + fresh)[-MAX_PENDING:]
    if not force and len(pending) < REWRITE_EVERY_MESSAGES:
        row.pending_json = json.dumps(pending, ensure_ascii=False)
        await db.commit()
        return {"status": "buffered", "pending": len(pending)}
    who = lambda m: names.get(m.get("speaker"), m.get("speaker"))
    from src.services import standing_requests
    held = await standing_requests.active(db, workspace_id, owner) if owner else []
    previous_requests = "\n".join(f"- {x}" for x in held)
    anchors = load_anchors(row)
    anchor_lines = "\n".join(f"[{a['id']}] ({a['status']}) {a['text']}" for a in anchors if a.get("kind") != "private_truth")      # the authored truth stays out of the picture's prose: the person has not been told it
    prompt = (f"PEOPLE: {names.get('user', 'the person')} (the person), {names.get('assistant', 'the companion')} (the companion character)\n\n"
              f"PREVIOUS PICTURE:\n{row.text or '(none yet)'}\n\nPREVIOUS STANDING REQUESTS:\n{previous_requests or '(none)'}\n\nCURRENT ANCHORS:\n{anchor_lines or '(none yet)'}\n\nLAST MESSAGES:\n" + "\n".join(f"{who(m)}: {m['text']}" for m in pending[-TAIL - 2:]))
    model_id = model or SCENE_MODEL
    try:
        out = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"scene": "string", "standing_requests": ["string"], "significance": "integer", "significance_kind": "string", "new_anchors": [{"kind": "string", "text": "string"}], "closed_anchor_ids": ["string"]}, model_id=model_id, max_tokens=700,
                                                temperature=0.2, strict=False, timeout=45)
    except Exception:
        row.pending_json = json.dumps(pending, ensure_ascii=False)       # keep the exchanges: the next pass covers them
        await db.commit()
        raise
    text = str((out or {}).get("scene") or "").strip()
    row.pending_json = json.dumps(pending if not text else [], ensure_ascii=False)
    if not text:
        await db.commit()
        return None
    from src.models.scene import utc_now
    returned = (out or {}).get("standing_requests")
    if owner and isinstance(returned, list):        # a pass that omits the field changes nothing; only an explicit list (possibly empty = all withdrawn) is applied
        await standing_requests.sync(db, workspace_id, owner, [str(x) for x in returned], source="scene_pass")
    row.text, row.model, row.updated_at = text, model_id, utc_now()
    anchors = merge_anchors(anchors, (out or {}).get("new_anchors"), (out or {}).get("closed_anchor_ids"), row.updated_at)
    row.anchors_json = json.dumps(anchors, ensure_ascii=False)
    row.through_message_id = next((m.get("id") for m in reversed(pending) if m.get("id")), None)
    await db.commit()
    try:
        significance = max(0, min(3, int((out or {}).get("significance") or 0)))
    except (TypeError, ValueError):
        significance = 0
    return {"text": text, "updated_at": row.updated_at.isoformat(), "model": model_id, "anchors": anchors, "significance": significance, "significance_kind": str((out or {}).get("significance_kind") or "none"), "standing_requests": await standing_requests.active(db, workspace_id, owner) if owner else []}


TRUTH_SYSTEM = """You are the keeper of the story's ground truth. The person has asked the character, directly, about something in the PAST that the character knows and the story has NOT established (what happened at a party last year, where she was, whether she kissed someone). The character cannot answer consistently about a fact that does not exist: left alone, the answer changes from reply to reply, or the character stalls for ever.
You are given the EXISTING PRIVATE TRUTHS: each is ONE hidden event the story already has an answer for. Questions about the same underlying event (what happened at Lila's, did you kiss him, did you sleep with him, who was there, what exactly happened) are all questions about that one event and must resolve against it, never against a new one.
Choose ONE action:
- "none": the question is already answered by an existing private truth or by the established facts, or it is not a direct question about the past (what happens next in the scene, a pending decision or plan, whether someone will do something, a feeling, a request, anything the person has not asked about, the person's own real life). When unsure, "none". Never decide the future of the scene.
- "extend": the question concerns an event an existing private truth already covers but asks about an aspect it leaves open. Give `target_id` and, in `truth`, ONLY the additional facts (1 to 3 plain sentences) that settle that aspect, consistent with everything already true.
- "new": the question concerns a different past event that has no private truth. Write 2 to 4 plain, concrete sentences of neutral fact (who did what, where, when, how it ended, why it was kept back), consistent with EVERY established fact, the character's constitution and the register of the story so far. Specific, plausible, and no more extreme than the story's own register.
Never dialogue, never a script, never a plan for how to reveal it: only what happened. Explicit or painful material is described only as far as needed to fix what happened.
Output a JSON object: {"action": "none"|"extend"|"new", "target_id": "<id of the private truth, for extend>", "topic": "<what the question was about, a few words>", "truth": "<what actually happened / the additional facts>"}"""


async def author_truth(db: AsyncSession, *, adapter: Any, workspace_id: str, session_id: str, question_anchor_id: Optional[str], question: str, picture: str, recent: List[Dict[str, str]],
                       character: str, constitution: str, names: Dict[str, str], model: Optional[str] = None) -> Dict[str, Any]:
    """Author the hidden truth behind an unanswered question ONCE, as a sitting anchor of kind private_truth (append-only, so every later reply and regeneration has the same
    answer). The system owns what happened; the foreground owns how the character tells it. Marks the question anchor so it is never authored twice, whatever the verdict."""
    row = await current(db, workspace_id, session_id)
    if row is None:
        return {"needed": False, "reason": "no_sitting"}
    anchors = load_anchors(row)
    target = next((a for a in anchors if a.get("id") == question_anchor_id), None) if question_anchor_id else None
    if target is not None and target.get("authored"):
        return {"needed": False, "reason": "already_authored", "anchors": anchors}
    who = lambda m: names.get(m.get("speaker"), m.get("speaker"))
    truths = [a for a in anchors if a.get("kind") == "private_truth"]
    established = "\n".join(f"- ({a['kind']}) {a['text']}" for a in anchors if a.get("status") != "closed" and a.get("kind") != "private_truth")
    existing = "\n".join(f"[{a['id']}] ({a.get('topic') or 'event'}) {a['text']}" for a in truths)
    prompt = (f"CHARACTER: {character}\nCONSTITUTION: {constitution or '(none given)'}\n\nTHE QUESTION THE PERSON IS ASKING: {question}\n\nEXISTING PRIVATE TRUTHS:\n{existing or '(none)'}\n\n"
              f"PICTURE OF THE STORY SO FAR:\n{picture or row.text or '(none)'}\n\nESTABLISHED FACTS:\n{established or '(none)'}\n\nRECENT MESSAGES:\n" + "\n".join(f"{who(m)}: {m['text']}" for m in recent[-8:]))
    out = await adapter.generate_structured(system=TRUTH_SYSTEM, prompt=prompt, json_schema={"action": "string", "target_id": "string", "topic": "string", "truth": "string"}, model_id=model or SCENE_MODEL,
                                            max_tokens=400, temperature=0.7, strict=False, timeout=30)
    action = str((out or {}).get("action") or "none").lower()
    truth = " ".join(str((out or {}).get("truth") or "").split())[:600]
    if target is not None:
        target["authored"] = True
    verdict: Dict[str, Any] = {"needed": False}
    from src.models.scene import utc_now
    if action == "new" and truth and truths:
        # Identity is decided here, not left to the model's mood: a question that shares a content word with a hidden event already authored (the party, Lila's, Marco, the kiss) is about
        # THAT event; only a question that touches none of them can open another, and a sitting holds at most two.
        asked = _content_terms(question + " " + str((out or {}).get("topic") or ""))
        best = max(truths, key=lambda a: len(asked & _content_terms(a["text"] + " " + str(a.get("topic") or ""))))
        if asked & _content_terms(best["text"] + " " + str(best.get("topic") or "")):
            action, out = "extend", {**(out or {}), "target_id": best["id"]}
        elif len(truths) >= 2:
            action = "none"
    if action == "extend" and truth:
        base = next((a for a in truths if a.get("id") == (out or {}).get("target_id")), None) or (truths[-1] if truths else None)
        if base is not None:
            if truth.lower() not in base["text"].lower():
                base["text"] = (base["text"].rstrip() + " " + truth)[:1000]            # same event, same anchor: one identity, grown, never a second version
                base["extended_at"] = utc_now().isoformat()
            verdict = {"needed": True, "extended": base["id"], "topic": str(base.get("topic") or "")}
        else:
            action = "new"
    if action == "new" and truth:
        seq = max([int(str(a["id"]).lstrip("a") or 0) for a in anchors] + [0]) + 1
        anchors.append({"id": f"a{seq}", "kind": "private_truth", "text": truth, "topic": str((out or {}).get("topic") or "")[:80], "status": "established", "at": utc_now().isoformat()})
        while len(anchors) > MAX_ANCHORS:
            victim = min(enumerate(anchors), key=lambda ia: (0 if ia[1]["status"] == "closed" else 1, EVICTION_RANK.get(ia[1]["kind"], 1), ia[0]))[1]
            anchors.remove(victim)
        verdict = {"needed": True, "topic": str((out or {}).get("topic") or "")}
    row.anchors_json = json.dumps(anchors, ensure_ascii=False)
    await db.commit()
    return {**verdict, "anchors": anchors, "updated_at": row.updated_at.isoformat() if row.updated_at else None, "text": row.text}
