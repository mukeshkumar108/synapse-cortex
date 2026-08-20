from datetime import datetime, timezone
from src.services.temporal_grounding import TemporalGrounding

grounder = TemporalGrounding()


def test_dst_spring_forward_grounding():
    # Spring forward in Europe/London happens last Sunday of March (e.g., March 29, 2026)
    # At 2026-03-28 12:00:00 UTC (GMT = UTC+0)
    now = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
    
    # "tomorrow" is March 29, when DST switches from GMT (UTC+0) to BST (UTC+1)
    start, end, _ = grounder.ground_expression("tomorrow", now, "Europe/London")
    assert start is not None
    assert end is not None


def test_dst_autumn_fallback_grounding():
    # Autumn fallback in Europe/London happens last Sunday of October (e.g., October 25, 2026)
    # At 2026-10-24 12:00:00 UTC (BST = UTC+1)
    now = datetime(2026, 10, 24, 11, 0, 0, tzinfo=timezone.utc)
    
    start, end, _ = grounder.ground_expression("tomorrow", now, "Europe/London")
    assert start is not None
    assert end is not None
