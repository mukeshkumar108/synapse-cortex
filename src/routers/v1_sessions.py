"""Session lifecycle endpoints (Cortex side).

Cortex owns NO session lifecycle: the app/runtime owns open/close and calls
this boundary with the completed transcript. Consolidation runs in SHADOW
mode — validated proposal + would-apply report, no interpreted-state
mutation — so callers may invoke it at session end, scene rollover, idle,
or as a daily catch-up retry. Raw evidence stays canonical; a later pass
can always retry.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.services.session_consolidation import (
    SessionTurn,
    StartSnapshot,
    SnapshotMatter,
    consolidate_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


class TranscriptTurn(BaseModel):
    message_id: str
    speaker: str = "user"
    text: str = ""


class SnapshotMatterIn(BaseModel):
    id: str
    kind: str = "open_loop"
    title: str = ""
    status: str = ""
    owner: str = ""


class StartSnapshotIn(BaseModel):
    matters: List[SnapshotMatterIn] = Field(default_factory=list)
    attentions: List[str] = Field(default_factory=list)
    suppressions: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)


class ConsolidateRequest(BaseModel):
    workspace_id: str
    session_id: str
    transcript: List[TranscriptTurn] = Field(default_factory=list)
    start_snapshot: Optional[StartSnapshotIn] = None


@router.post("/consolidate", status_code=status.HTTP_200_OK)
async def consolidate(
    payload: ConsolidateRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Propose the session's longitudinal delta (shadow: never mutates)."""
    snapshot: Optional[StartSnapshot] = None
    if payload.start_snapshot is not None:
        snapshot = StartSnapshot(
            matters=[SnapshotMatter(
                id=m.id, kind=m.kind, title=m.title,
                status=m.status, owner=m.owner)
                for m in payload.start_snapshot.matters],
            attentions=list(payload.start_snapshot.attentions),
            suppressions=list(payload.start_snapshot.suppressions),
            people=list(payload.start_snapshot.people),
        )
    result = await consolidate_session(
        db, workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        transcript=[SessionTurn(message_id=t.message_id, speaker=t.speaker,
                                text=t.text) for t in payload.transcript],
        start_snapshot=snapshot,
    )
    return {
        "status": "shadow",
        "summary": result.summary,
        "error": result.error,
        "prompt_chars": result.prompt_chars,
        "accepted": [{"op": o.op, "data": o.data, "confidence": o.confidence,
                      "rationale": o.rationale} for o in result.accepted],
        "rejected": result.rejected,
        "would_apply": result.would_apply,
    }
