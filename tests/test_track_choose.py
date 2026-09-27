"""track->choose: ranked optional judgement must reach handover.available,
and proactive eligibility must speak the agenda's status vocabulary."""
from src.services.handover_service import compile_handover
from src.services.initiative_service import _high_pressure_items


def _packet():
    return {
        "intelligence_brief": {"daypart": "morning", "user_day": "2026-09-28"},
        "sophie_attention": [],
        "open_loops": [
            {"id": "loop-low", "candidate_id": "open_loop:loop-low",
             "candidate_version": "v1", "honcho_message_id": "m1",
             "title": "Low value thread", "summary": "low",
             "expectation_id": None, "explicitly_invited": False},
            {"id": "loop-matt", "candidate_id": "open_loop:loop-matt",
             "candidate_version": "v2", "honcho_message_id": "m2",
             "title": "Update on Matt's condition", "summary": "waiting",
             "expectation_id": None, "explicitly_invited": False},
        ],
        "suppressed_targets": [],
        "recurring_intentions": [],
        "clarifications": [],
    }


def test_available_follows_ranked_optional_not_packet_order():
    packet = _packet()
    # Ranked admission optional (agenda order preserved): Matt first despite
    # being second in raw packet order.
    optional = [
        {"what": "Update on Matt's condition", "pressure": 0.45,
         "followup_state": "optional_background",
         "why": "unresolved 42h", "next_move": "check back naturally",
         "item_key": "loop:loop-matt", "horizon": "day"},
        {"what": "Low value thread", "pressure": 0.27,
         "followup_state": "optional_background",
         "why": "open thread", "next_move": "return naturally",
         "item_key": "loop:loop-low", "horizon": "day"},
    ]
    h = compile_handover(packet, admission={"owed": [], "optional": optional,
                                            "scene": {}})
    assert len(h["available"]) == 1
    avail = h["available"][0]
    assert avail["what"] == "Update on Matt's condition"
    assert avail["pressure"] == 0.45
    assert avail["why"] == "unresolved 42h"
    assert avail["next_move"] == "check back naturally"
    assert avail["candidate_id"] == "open_loop:loop-matt"
    assert avail["evidence_refs"] == ["m2"]


def test_available_skips_terminal_optionals():
    packet = _packet()
    optional = [
        {"what": "Done thing", "pressure": 0.1,
         "followup_state": "resolved", "why": "done",
         "next_move": "", "item_key": "loop:loop-low", "horizon": "day"},
        {"what": "Update on Matt's condition", "pressure": 0.45,
         "followup_state": "optional_background",
         "why": "unresolved 42h", "next_move": "check back naturally",
         "item_key": "loop:loop-matt", "horizon": "day"},
    ]
    h = compile_handover(packet, admission={"owed": [], "optional": optional,
                                            "scene": {}})
    assert h["available"][0]["what"] == "Update on Matt's condition"


def test_available_falls_back_to_legacy_packet_row():
    packet = _packet()
    h = compile_handover(packet, admission={"owed": [], "optional": [],
                                            "scene": {}})
    # legacy: first packet row (sophie_attention empty -> first open_loop)
    assert h["available"][0]["what"] == "Low value thread"
    assert "why" not in h["available"][0]


def test_initiative_sees_live_agenda_statuses():
    items = [
        {"what": "overdue task", "pressure": 0.85, "status": "outstanding"},
        {"what": "waiting thread", "pressure": 0.7, "status": "waiting_event"},
        {"what": "plain thread", "pressure": 0.7, "status": "unresolved"},
        {"what": "settled", "pressure": 0.9, "status": "resolved"},
        {"what": "later", "pressure": 0.9, "status": "scheduled_for_later"},
    ]
    got = _high_pressure_items(items, 0.6)
    assert {i["what"] for i in got} == {"overdue task", "waiting thread",
                                        "plain thread"}
