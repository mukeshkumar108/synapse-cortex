from datetime import datetime, timezone

import pytest

from src.db import async_session_maker
from src.services.persistence import save_expectation_idempotent


@pytest.mark.asyncio
async def test_second_chance_grounding_uses_injected_turn_clock():
    data = {
        "honcho_workspace_id": "ws_second_chance",
        "honcho_session_id": "session_second_chance",
        "honcho_message_id": "message_second_chance",
        "owner_peer_id": "user_second_chance",
        "candidate_key": "candidate@model-v1",
        "extractor_version": "model-v1",
        "subject_peer_id": "user_second_chance",
        "expectation_type": "USER_COMMITMENT",
        "title": "Call mum",
        "summary": "Call mum tomorrow at 11am",
        "raw_temporal_phrase": "tomorrow at 11am",
        "anchor_timezone": "Europe/London",
        "expected_window_start": None,
        "expected_window_end": None,
        "hard_deadline_at": None,
        "extraction_confidence": 0.99,
        "reminder_requested": True,
    }
    turn_now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    async with async_session_maker() as session:
        expectation, created = await save_expectation_idempotent(
            session, data, grounding_now=turn_now
        )

    assert created is True
    assert expectation.expected_window_start == datetime(2026, 9, 2, 10, 0)
    assert expectation.expected_window_end == datetime(2026, 9, 2, 13, 59)
    assert '"start": "2026-09-02T10:00:00"' in expectation.reminder_windows_json
