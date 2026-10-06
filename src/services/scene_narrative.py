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
REWRITE_EVERY_MESSAGES = 4     # the picture is rewritten once this many new messages are waiting (2 exchanges): always fewer than the raw tail the foreground reads, so nothing falls between
MAX_PENDING = 12

SYSTEM = """You keep the running picture of one ongoing conversation between a person and a companion character, so the character can speak as one continuous self.
You are given the PREVIOUS PICTURE (what was already known) and the LAST MESSAGES (verbatim). Write the picture as it stands NOW: 4 to 8 short plain sentences, no lists, no headings.
Cover, in whatever order reads naturally: what is actually happening and in what register; what is genuinely still open between them (questions not answered, decisions pending,
tension not settled); any decisions, promises, plans or commitments made; the texture (mood, humour, running jokes, tone) as observed, not as lasting unless it continues;
and what has already been used up so it is not needlessly repeated (questions asked, stories told, callbacks made, points settled), saying who did it.
Carry forward from the PREVIOUS PICTURE whatever still matters; drop what has resolved or no longer matters. Name people by the names given. Say only what the messages support.
Neutral description only: never an instruction, never a line for the character to say. The material may be fiction or explicit: describe it only as far as needed to track what is happening.
Output a JSON object: {"scene": "<the picture>"}"""


async def current(db: AsyncSession, workspace_id: str, session_id: str) -> Optional[SceneNarrative]:
    return (await db.execute(select(SceneNarrative).where(
        SceneNarrative.honcho_workspace_id == workspace_id, SceneNarrative.honcho_session_id == session_id))).scalars().first()


async def narrate(db: AsyncSession, *, adapter: Any, workspace_id: str, session_id: str, messages: List[Dict[str, str]], names: Dict[str, str],
                  model: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
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
    prompt = (f"PEOPLE: {names.get('user', 'the person')} (the person), {names.get('assistant', 'the companion')} (the companion character)\n\n"
              f"PREVIOUS PICTURE:\n{row.text or '(none yet)'}\n\nLAST MESSAGES:\n" + "\n".join(f"{who(m)}: {m['text']}" for m in pending[-TAIL - 2:]))
    model_id = model or SCENE_MODEL
    try:
        out = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"scene": "string"}, model_id=model_id, max_tokens=700,
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
    row.text, row.model, row.updated_at = text, model_id, utc_now()
    row.through_message_id = next((m.get("id") for m in reversed(pending) if m.get("id")), None)
    await db.commit()
    return {"text": text, "updated_at": row.updated_at.isoformat(), "model": model_id}
