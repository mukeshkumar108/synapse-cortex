"""Scene narrative: the fast, small pass. After each exchange a cheap model reads the previous narrative and the last few messages and rewrites the
conversation-as-it-stands as a few plain sentences: what is happening, what is open, the texture, what has already been used up. The foreground reads
prose; no structured fields to interpret. Description only, never an instruction. The heavy world interpreter still owns entities, claims, objectives
and operational items."""
from __future__ import annotations

import json
import logging
import os
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

SYSTEM = """You keep the running picture of one ongoing conversation between a person and a companion character, so the character can speak as one continuous self.
You are given the PREVIOUS PICTURE (what was already known) and the LAST MESSAGES (verbatim). Write the picture as it stands NOW: 6 to 14 short plain sentences, no lists, no headings. BEGIN it with where the relationship stands and what has been built between them: moments of closeness, celebration, trust, vulnerability, affection or repair are the weightiest things in any conversation. Keep each such moment (a clause: what it was, how it landed) for as long as the scene lasts even when it is no longer the latest thing, and say how it should colour what follows. A later disagreement or strange turn is described against that background, as a rupture of it, never as if the bond did not exist; and when something a character says or does is out of keeping with that background, say that it is out of keeping.
Cover, in whatever order reads naturally: what is actually happening and in what register; what is genuinely still open between them (questions not answered, decisions pending,
tension not settled); any decisions, promises, plans or commitments made; the texture (mood, humour, running jokes, tone) as observed, not as lasting unless it continues;
and what has already been used up so it is not needlessly repeated (questions asked, stories told, callbacks made, points settled), saying who did it.
Carry forward from the PREVIOUS PICTURE whatever still matters. DROP mood and moment-to-moment texture that has passed, but KEEP, as short factual clauses, the concrete things that have happened in this scene and that anything later must stay consistent with: who did what to whom, what was sent, received, refused or accepted, where each person physically is and what they are waiting for, and what each said they did or did not do. A long scene must not lose its earlier events just because they are no longer the latest thing.
A character's own account of their hidden past or secret feelings, offered for the first time under questioning, is described as what they SAID ("she said ..."), never as a fact of the scene; if it contradicts something that already happened in the scene, say that it contradicts it, and keep the event. Name people by the names given. Say only what the messages support.
Neutral description only: never an instruction, never a line for the character to say. The material may be fiction or explicit: describe it only as far as needed to track what is happening.
STANDING REQUESTS are kept separately, NOT in the picture. Anything the person has asked of the character about how to talk or behave (a name not to use, a topic to avoid, less of something, a correction to what the character got wrong) goes in "standing_requests" as short plain statements in the person's own terms. You are given the PREVIOUS STANDING REQUESTS: return every one of them again unless the person has withdrawn or clearly changed it, plus any new one. Never drop one for space.
Output a JSON object: {"scene": "<the picture>", "standing_requests": ["<request>", ...]}"""


async def current(db: AsyncSession, workspace_id: str, session_id: str) -> Optional[SceneNarrative]:
    return (await db.execute(select(SceneNarrative).where(
        SceneNarrative.honcho_workspace_id == workspace_id, SceneNarrative.honcho_session_id == session_id))).scalars().first()


async def narrate(db: AsyncSession, *, adapter: Any, workspace_id: str, session_id: str, messages: List[Dict[str, str]], names: Dict[str, str],
                  model: Optional[str] = None, force: bool = False, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Hand in the newest exchange. The picture is rewritten (one cheap model call) only when enough has accrued to leave the raw tail (or `force`, for a
    significant moment); otherwise the exchange is just buffered. `messages` = [{id?, speaker: user|assistant, text}], oldest first."""
    fresh = [m for m in messages if str(m.get("text") or "").strip()]
    if not fresh:
        return None
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
    prompt = (f"PEOPLE: {names.get('user', 'the person')} (the person), {names.get('assistant', 'the companion')} (the companion character)\n\n"
              f"PREVIOUS PICTURE:\n{row.text or '(none yet)'}\n\nPREVIOUS STANDING REQUESTS:\n{previous_requests or '(none)'}\n\nLAST MESSAGES:\n" + "\n".join(f"{who(m)}: {m['text']}" for m in pending[-TAIL - 2:]))
    model_id = model or SCENE_MODEL
    try:
        out = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"scene": "string", "standing_requests": ["string"]}, model_id=model_id, max_tokens=700,
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
    row.through_message_id = next((m.get("id") for m in reversed(pending) if m.get("id")), None)
    await db.commit()
    return {"text": text, "updated_at": row.updated_at.isoformat(), "model": model_id, "standing_requests": await standing_requests.active(db, workspace_id, owner) if owner else []}
