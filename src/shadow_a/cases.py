"""Acceptance-case definitions — fixture-backed slices + labelled reconstructions.

Fixture-backed cases read the real Sophie longitudinal inputs (never the
oracles for behaviour). RPD2 arcs absent from the repo (Isa pact, Elena
rupture, Dad surgery, Marko, stale-loop paraphrase, Sam-promise
observability pair) are provided as minimal reconstructed probes, clearly
labelled RECONSTRUCTED, derived from the failure descriptions in the task —
not easier replacements: each preserves the load-bearing difficulty
(paraphrase closure, wrapper-vs-terms, ownership split, observed-vs-
unobserved absence).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "evals" / "sophie_longitudinal"


def _load(name: str) -> List[Dict]:
    d = json.loads((FIX / name).read_text())
    return d["events"]


def _ev(eid: str, content: str, source_type: str = "conversation",
        role: str = "user", sender: str = "ashley",
        ts: str = "2026-09-28T08:00:00+01:00") -> Dict:
    return {"id": eid, "content": content, "source_type": source_type,
            "role": role, "sender": sender, "timestamp": ts}


def build_cases() -> List[Dict]:
    s1 = _load("scenario_1_ashley_event_ops_input.json")
    s2 = _load("scenario_2_ordinary_sophie_plans_input.json")
    s3 = _load("scenario_3_multisource_conflict_input.json")
    s4 = _load("scenario_4_health_worry_texture_input.json")
    by_id = {e["id"]: e for e in s1 + s2 + s3 + s4}

    cases: List[Dict] = [
        dict(case_id="c1_carlos_partial",
             title="Carlos partial payment / delayed chase",
             events=[by_id[i] for i in ("s1_e01", "s1_e03", "s1_e04", "s1_e07", "s1_e09")],
             observed_sources=["bank_feed", "email"],
             user_tracking_ok=True),
        dict(case_id="c2_freepik_reschedule",
             title="Freepik cancellation + reschedule",
             events=[by_id[i] for i in ("s2_e03", "s2_e07", "s2_e09", "s2_e10")],
             observed_sources=["conversation"],
             user_tracking_ok=True),
        dict(case_id="c3_isa_pact",
             title="Isa multi-turn pact (RECONSTRUCTED from failure description)",
             events=[
                 _ev("isa_e01", "Isa and I talked late. The romantic part was lovely but we actually agreed terms: I handle mornings, they handle the school run, and we revisit Sunday."),
                 _ev("isa_e02", "Isa confirmed mornings are mine. Romantic wrapper aside, the school-run split stands.", sender="isa"),
                 _ev("isa_e03", "So the pact still holds? Mornings me, school run Isa, review Sunday?", ts="2026-09-29T08:00:00+01:00"),
             ],
             observed_sources=["conversation"],
             user_tracking_ok=True),
        dict(case_id="c4_two_sams",
             title="Studio Sam vs Cousin Sam",
             events=[by_id[i] for i in ("s3_e01", "s3_e05", "s3_e06", "s3_e08", "s3_e09", "s3_e10")],
             observed_sources=["sms", "calendar", "email"],
             user_tracking_ok=True),
        dict(case_id="c5_neck_elif",
             title="Neck vs headache vs Elif restraint",
             events=[by_id[i] for i in ("s4_e01", "s4_e02", "s4_e04", "s4_e07", "s4_e10")],
             observed_sources=["conversation"],
             user_tracking_ok=False),
        dict(case_id="c6_surgery_context",
             title="Dad/Matt surgery contextual modulation (fixture Matt + RECONSTRUCTED Dad probe)",
             events=[by_id[i] for i in ("s4_e07", "s4_e09", "s4_e10")] + [
                 _ev("dad_e01", "Dad's surgery is Tuesday. I'm barely holding it together; routine stuff can wait.", ts="2026-09-30T08:00:00+01:00"),
             ],
             observed_sources=["conversation"],
             user_tracking_ok=True),
        dict(case_id="c7_third_party",
             title="Ashley/Marko third-party ownership (RECONSTRUCTED Marko + fixture Ashley/Carlos)",
             events=[by_id["s1_e03"]] + [
                 _ev("mk_e01", "Marko said in roleplay he'll cover Isa's shift Thursday. That's his promise to Isa, not mine.", sender="ashley"),
                 _ev("mk_e02", "Ashley says she'll send the venue numbers tonight. Her task, keep me posted only.", sender="ashley"),
             ],
             observed_sources=["email", "conversation"],
             user_tracking_ok=True),
        dict(case_id="c8_stale_loop_vocab",
             title="Stale Open Loop resolved by different vocabulary (RECONSTRUCTED bridge on s2 pattern)",
             events=[by_id[i] for i in ("s2_e06", "s2_e07", "s2_e10")] + [
                 _ev("sl_e01", "That photo thing for Auntie — found the original in the loft and sent it over. Different words, same matter: grandad letter done.", ts="2026-10-03T10:00:00+01:00"),
             ],
             observed_sources=["conversation"],
             user_tracking_ok=True,
             extra_claims=[
                 {"content": "open matter: grandad original letter for auntie", "refs": ["s2_e06"]},
             ]),
        dict(case_id="c9_observability",
             title="Expected external event absent: observed vs unobserved",
             events=[
                 _ev("ob_e01", "Sam said he'd send it Friday.", ts="2026-10-02T09:00:00+01:00"),
             ],
             observed_sources=["inbox"],
             user_tracking_ok=False,
             absence_probes=[
                 {"label": "friday receipt, inbox observed all friday",
                  "expected": "sam sends it friday",
                  "observability": {"source": "inbox", "window": "friday 00:00-23:59",
                                    "observed": True, "last_observed_at": "2026-10-03T00:00:00+01:00"}},
                 {"label": "friday receipt, inbox never checked",
                  "expected": "sam sends it friday",
                  "observability": {"source": "inbox", "window": "friday 00:00-23:59",
                                    "observed": False, "last_observed_at": None}},
             ]),
        # --- A.5: full messy replays (all fixture events, in order) + RPD2 fragment
        dict(case_id="a5_s1_full",
             title="A.5 full Scenario 1 replay (14 events, sequential)",
             events=list(s1),
             observed_sources=["bank_feed", "email", "calendar"],
             user_tracking_ok=True,
             sequential=True),
        dict(case_id="a5_s4_full",
             title="A.5 full Scenario 4 replay (15 events, sequential)",
             events=list(s4),
             observed_sources=["conversation"],
             user_tracking_ok=False,
             sequential=True),
        dict(case_id="a5_elena_fragment",
             title="A.5 Elena msg-17 fragment (real RPD2 verbatim from tests/test_bilateral_state.py)",
             events=[
                 _ev("elena_m17", "I'll give you space. I'll be here.", role="assistant",
                     sender="elena", ts="2026-09-22T02:21:19+01:00"),
             ],
             observed_sources=["conversation"],
             user_tracking_ok=True),
    ]
    return cases
