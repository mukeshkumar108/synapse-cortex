"""The continuing account is read on later days (Monday 2 Nov: a Friday lunch written into the account without its day read as today, and Sophie's own questions were stored as the person's non-answers).
The fix is general: the writer is told to date events and to leave Sophie's own questions out, and the served account says when it was last written. No phrase matching."""
from src.services import memory_pipeline


def test_the_writer_is_told_to_date_events_and_to_leave_sophies_questions_out():
    p = memory_pipeline.ARC_UPDATE_PROMPT
    assert "read on LATER days" in p and "give every event the day it happened" in p
    assert "left out of the account entirely" in p and "not a fact about the person and not a debt" in p


def test_the_session_day_is_named_for_the_writer():
    assert memory_pipeline._day_name("2026-10-30") == "Friday 30 October 2026"
