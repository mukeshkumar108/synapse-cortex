from src.replay.historical import (
    HistoricalTurn, _rpd2_text, lexical_future_references, split_on_idle,
)


def test_rpd2_scenes_split_only_on_observed_idle_gap():
    turns = [
        HistoricalTurn("1", "user", "one", "2026-09-01T10:00:00"),
        HistoricalTurn("2", "assistant", "two", "2026-09-01T10:05:00"),
        HistoricalTurn("3", "user", "three", "2026-09-01T10:35:00"),
    ]
    scenes = split_on_idle(turns, idle_minutes=30, prefix="chat:scene")
    assert [len(s.turns) for s in scenes] == [2, 1]
    assert scenes[1].source_session_id == "chat:scene:2"
    assert scenes[1].boundary == "observed_idle_gap_30m"


def test_future_references_are_explicitly_lexical_and_bounded():
    refs = lexical_future_references(
        ["Waiting for Carlos invoice", "General thing"],
        "Two days later Carlos finally sent the corrected paperwork.")
    assert refs == [{"title": "Waiting for Carlos invoice",
                     "matched_terms": ["carlos"]}]


def test_rpd2_json_column_may_arrive_as_encoded_text():
    assert _rpd2_text('[{"type":"step-start"},{"type":"text","text":"hello"}]') == "hello"
