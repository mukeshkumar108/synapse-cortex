from datetime import datetime, timedelta, timezone

import pytest

from src.db import async_session_maker
from src.models.operational_state import TurnStamp
from src.services.initiative_service import evaluate_initiative


@pytest.mark.asyncio
async def test_recent_activity_is_scoped_to_owner_and_injected_clock():
    now = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        db.add_all([
            TurnStamp(
                honcho_workspace_id="shared",
                owner_peer_id="other-user",
                honcho_message_id="other",
                turn_at=now.replace(tzinfo=None) - timedelta(minutes=1),
            ),
            TurnStamp(
                honcho_workspace_id="shared",
                owner_peer_id="target-user",
                honcho_message_id="future-replay",
                turn_at=now.replace(tzinfo=None) + timedelta(minutes=1),
            ),
        ])
        await db.commit()

        result = await evaluate_initiative(
            db,
            workspace_id="shared",
            owner_peer_id="target-user",
            agenda=[{
                "what": "daily walk",
                "pressure": 0.8,
                "status": "unresolved",
                "severity": "normal",
            }],
            now=now,
            timezone_str="Europe/London",
        )

    assert result["should_appear"] is True
    assert result["reason"] == "high-pressure agenda item reserved for follow-up"
