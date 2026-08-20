from datetime import datetime, timezone
from src.services.temporal_grounding import TemporalGrounding

grounder = TemporalGrounding()


def test_grounding_tonight():
    # 2026-08-11 15:00:00 in Europe/London (UTC+1)
    now = datetime(2026, 8, 11, 14, 0, 0, tzinfo=timezone.utc)
    tz_str = "Europe/London"

    start, end, deadline = grounder.ground_expression("tonight", now, tz_str)

    # 18:00 local today = 17:00 UTC
    # 23:59:59 local today = 22:59:59 UTC
    assert start == datetime(2026, 8, 11, 17, 0, 0)
    assert end == datetime(2026, 8, 11, 22, 59, 59)
    assert deadline is None


def test_grounding_hard_deadline_by_5pm_friday():
    # Tuesday 2026-08-11 15:00:00 Europe/London
    now = datetime(2026, 8, 11, 14, 0, 0, tzinfo=timezone.utc)
    tz_str = "Europe/London"

    start, end, deadline = grounder.ground_expression("by 5pm Friday", now, tz_str)

    # Friday 2026-08-14 17:00 local = 16:00 UTC
    assert deadline == datetime(2026, 8, 14, 16, 0, 0)
    assert end == datetime(2026, 8, 14, 16, 0, 0)
    # Friday 00:00:00 BST (UTC+1) -> Thursday 23:00:00 UTC
    assert start == datetime(2026, 8, 13, 23, 0, 0)


def test_grounding_ambiguous_relational_phrases():
    now = datetime(2026, 8, 11, 14, 0, 0, tzinfo=timezone.utc)
    
    phrases = [
        "after the Miami trip",
        "when Ashley gets back",
        "once I finish the architecture",
    ]

    for phrase in phrases:
        start, end, deadline = grounder.ground_expression(phrase, now, "Europe/London")
        assert start is None, f"Failed for phrase: {phrase}"
        assert end is None, f"Failed for phrase: {phrase}"
        assert deadline is None, f"Failed for phrase: {phrase}"


def test_timezone_boundary_midnight():
    # 2026-08-11 23:30:00 UTC -> 2026-08-12 00:30:00 BST in Europe/London
    now = datetime(2026, 8, 11, 23, 30, 0, tzinfo=timezone.utc)
    
    start_london, end_london, _ = grounder.ground_expression("today", now, "Europe/London")
    # In London it is already Aug 12!
    assert start_london.day == 11 and start_london.hour == 23  # 00:00 Aug 12 BST = 23:00 Aug 11 UTC

    start_ny, end_ny, _ = grounder.ground_expression("today", now, "America/New_York")
    # In New York (UTC-4) it is 19:30 Aug 11!
    assert start_ny.day == 11 and start_ny.hour == 4  # 00:00 Aug 11 EDT = 04:00 Aug 11 UTC
