import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from src.services.cortex_packet_service import CortexPacketService
from src.services.daypart import resolve_daypart

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
        chronology: Optional[Dict[str, Any]] = None,
        owner_peer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 1. Local Daypart Determination (single canonical source)
        daypart = resolve_daypart(now, timezone_str)

        # 2. Chronology is supplied by the canonical app/PostgreSQL boundary.
        # Cortex never invents a competing gap threshold. Legacy callers that
        # omit chronology receive a non-authoritative unknown orientation.
        chronology = chronology or {}
        temporal_session = chronology.get("temporalSession")
        orientation = (
            "continuation" if temporal_session == "same"
            else "returning" if temporal_session == "new"
            else "unknown"
        )
        supplied_gap = chronology.get("gapMinutes")
        time_since_minutes = supplied_gap if isinstance(supplied_gap, int) else None

        # 2b. Sitting ownership. The app/PostgreSQL TemporalSession (temporalSession
        # same/new + firstContactUserDay) is the single canonical owner of session
        # boundaries. Cortex consumes it verbatim and never independently
        # classifies new-vs-ongoing from last_interaction_time; when chronology
        # is absent, `sitting` is explicitly unknown rather than guessed.
        # first_contact_today is a Cortex-owned fact derived from the last known
        # interaction when the app has not already supplied firstContactUserDay.
        sitting = None
        first_contact_today = False
        chrono_session = chronology.get("temporalSession")
        if chrono_session == "same":
            sitting = "ongoing_sitting"
        elif chrono_session == "new":
            if chronology.get("firstContactUserDay"):
                sitting = "first_contact_today"
                first_contact_today = True
            else:
                sitting = "new_sitting_same_day"
        else:
            sitting = None  # boundary ownership stays with app chronology
            try:
                local_tz = ZoneInfo(timezone_str)
                now_aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
                if last_interaction_time is None:
                    first_contact_today = True
                else:
                    prev_aware = last_interaction_time if last_interaction_time.tzinfo else last_interaction_time.replace(tzinfo=timezone.utc)
                    if prev_aware.astimezone(local_tz).date() != now_aware.astimezone(local_tz).date():
                        first_contact_today = True
            except Exception:
                first_contact_today = False

        # 3. Attention Packet Compilation
        packet = await packet_service.compile_attention_packet(
            db=db, workspace_id=workspace_id, session_id=session_id, now=now,
            timezone_str=timezone_str, owner_peer_id=owner_peer_id,
        )

        return {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "orientation": orientation,
            "chronology": chronology or None,
            "daypart": daypart,
            "sitting": sitting,
            "first_contact_today": first_contact_today,
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
