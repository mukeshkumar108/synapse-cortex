"""Scene narrative: the fast, small pass. After each exchange a cheap model reads the previous narrative and the last few messages and rewrites the
conversation-as-it-stands as a few plain sentences: what is happening, what is open, the texture, what has already been used up. The foreground reads
prose; no structured fields to interpret. Description only, never an instruction. The heavy world interpreter still owns entities, claims, objectives
and operational items."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.scene import SceneNarrative

logger = logging.getLogger(__name__)

SCENE_MODEL = os.getenv("SCENE_NARRATIVE_MODEL", "openai/gpt-5.6-luna")
TAIL = 6

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
                  model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Rewrite the picture from the previous picture plus the last messages. `messages` = [{id?, speaker: user|assistant, text}], oldest first."""
    tail = [m for m in messages if str(m.get("text") or "").strip()][-TAIL:]
    if not tail:
        return None
    row = await current(db, workspace_id, session_id)
    who = lambda m: names.get(m.get("speaker"), m.get("speaker"))
    prompt = (f"PEOPLE: {names.get('user', 'the person')} (the person), {names.get('assistant', 'the companion')} (the companion character)\n\n"
              f"PREVIOUS PICTURE:\n{(row.text if row else '') or '(none yet)'}\n\nLAST MESSAGES:\n" + "\n".join(f"{who(m)}: {m['text']}" for m in tail))
    model_id = model or SCENE_MODEL
    out = await adapter.generate_structured(system=SYSTEM, prompt=prompt, json_schema={"scene": "string"}, model_id=model_id, max_tokens=700,
                                            temperature=0.2, strict=False, timeout=45)
    text = str((out or {}).get("scene") or "").strip()
    if not text:
        return None
    through = next((m.get("id") for m in reversed(tail) if m.get("id")), None)
    if row is None:
        row = SceneNarrative(honcho_workspace_id=workspace_id, honcho_session_id=session_id, text=text, through_message_id=through, model=model_id)
        db.add(row)
    else:
        row.text, row.through_message_id, row.model = text, through, model_id
        from src.models.scene import utc_now
        row.updated_at = utc_now()
        db.add(row)
    await db.commit()
    return {"text": text, "updated_at": row.updated_at.isoformat(), "model": model_id}
