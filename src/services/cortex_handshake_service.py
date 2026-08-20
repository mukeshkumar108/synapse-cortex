import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from src.services.cortex_packet_service import CortexPacketService

logger = logging.getLogger(__name__)
packet_service = CortexPacketService()


class CortexHandshakeService:
    """
    Compiles deterministic Cortex Handshake payloads.
    Answers: "How should Sophie enter this interaction?"
    Calculated completely deterministically without LLM generation.
    """

    async def compile_handshake(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        now: datetime,
        timezone_str: str = "Europe/London",
        last_interaction_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        # 1. Local Daypart Determination
        try:
            local_tz = ZoneInfo(timezone_str)
            local_now = now.astimezone(local_tz) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(local_tz)
        except Exception:
            local_now = now

        hour = local_now.hour
        if 5 <= hour < 12:
            daypart = "morning"
        elif 12 <= hour < 17:
            daypart = "afternoon"
        elif 17 <= hour < 22:
            daypart = "evening"
        else:
            daypart = "night"

        # 2. Time Since Last Interaction
        time_since_minutes = None
        orientation = "fresh_start"
        if last_interaction_time:
            delta = now - (last_interaction_time if last_interaction_time.tzinfo else last_interaction_time.replace(tzinfo=timezone.utc))
            time_since_minutes = max(0, int(delta.total_seconds() // 60))
            if time_since_minutes < 120:
                orientation = "continuation"

        # 3. Attention Packet Compilation
        packet = await packet_service.compile_attention_packet(
            db=db, workspace_id=workspace_id, session_id=session_id, now=now, timezone_str=timezone_str
        )

        return {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "orientation": orientation,
            "daypart": daypart,
            "time_since_last_interaction_minutes": time_since_minutes,
            "live_threads": packet["open_loops"] + packet["active_expectations"],
            "followup_opportunities": packet["followups"],
            "recent_resolutions": packet["recent_resolutions"],
            "avoid_surface": packet["suppressed_targets"],
            "relevant_memory_refs": [
                {"honcho_message_id": message_id}
                for message_id in packet["relevant_honcho_message_ids"]
            ],
            "entry_constraints": {
                "night_context": daypart == "night",
                "suppressed_target_ids": [
                    item["id"] for item in packet["suppressed_targets"]
                ],
            },
            "continuity_context": packet["continuity_context"],
        }
