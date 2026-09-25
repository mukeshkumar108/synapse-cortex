"""Phase-A shadow acceptance tests — SHADOW ONLY.

- No DB, no prod imports, no foreground behaviour change.
- test_shadow_has_no_prod_imports guards the hard constraint mechanically.
- Remaining tests pin the 9 acceptance cases against the shadow pipeline.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def _result(case_id):
    from shadow_a.cases import build_cases
    from shadow_a.pipeline import run_case
    spec = next(s for s in build_cases() if s["case_id"] == case_id)
    return run_case(spec["case_id"], spec["events"],
                    spec.get("observed_sources", []),
                    spec.get("user_tracking_ok", True),
                    spec.get("absence_probes")), spec


def test_shadow_has_no_prod_imports():
    import re
    pkg = Path("src/shadow_a")
    assert pkg.is_dir()
    for f in list(pkg.glob("*.py")) + [Path("scripts/run_shadow_phase_a.py")]:
        for line in f.read_text().splitlines():
            s = line.strip()
            if not s.startswith(("import ", "from ")):
                continue
            for banned in ("src.models", "src.services", "src.routers", "src.db",
                           "from src.", "import src."):
                assert banned not in s, f"{f} imports prod code: {s!r}"


def test_relation_vocab_bounded():
    from shadow_a.schema import RELATION_VOCAB
    required = {"same_as", "refines", "contradicts", "supersedes", "depends_on",
                "part_of", "conditioned_on", "fulfils", "partially_fulfils",
                "resolves", "reopens", "enables", "blocks"}
    assert required <= set(RELATION_VOCAB)


def test_telemetry_vocab():
    from shadow_a.schema import TELEMETRY
    assert set(TELEMETRY) == {"NO_MOVE_WARRANTED", "MOVE_HELD", "MOVE_ELIGIBLE",
                              "UNRESOLVED_SEMANTICS", "UNREPRESENTED_SCHEMA_GAP"}


def test_c1_partial_payment_relation_and_ownership():
    res, _ = _result("c1_carlos_partial")
    rels = {(r.rel_type, ) for r in res.relations}
    assert any(r.rel_type == "partially_fulfils" for r in res.relations)
    owners = {(o.obligor) for o in res.obligations}
    assert "carlos" in owners  # debt stays with Carlos, not the user
    # underlying matter link present on every move; expiry never implied
    for m in res.moves:
        assert m.matter_id in res.roles


def test_c2_supersession_chain():
    res, _ = _result("c2_freepik_reschedule")
    assert sum(1 for r in res.relations if r.rel_type == "supersedes") >= 2
    # completion record must not spawn an ACT
    for m in res.moves:
        assert "cancelled freepik themselves" not in _claim(res, m.matter_id).lower()


def _claim(res, cid):
    return next(c.content for c in res.claims if c.claim_id == cid)


def test_c3_pact_terms_survive_with_part_of():
    res, _ = _result("c3_isa_pact")
    part_of = [r for r in res.relations if r.rel_type == "part_of"]
    assert len(part_of) >= 3  # terms + wrapper linked into the pact
    contents = " ".join(c.content for c in res.claims)
    assert "school-run" in contents and "mornings" in contents


def test_c4_no_sam_merge():
    res, _ = _result("c4_two_sams")
    assert not any(r.rel_type == "same_as" for r in res.relations)
    assert any(r.rel_type == "blocks" for r in res.relations)


def test_c5_restraint_without_suppression():
    res, _ = _result("c5_neck_elif")
    sms = [a for a in res.assessments if a.telemetry == "NO_MOVE_WARRANTED"]
    assert len(sms) >= 3  # somatic claims retained, no move, no suppression object


def test_c5_elif_self_resolution_invalidates_followup():
    # A.5: s4_e10 "I finally messaged Elif" resolves the e04 regret.
    # The Phase-A user-facing Elif FOLLOW_UP was a genuine false positive.
    res, _ = _result("c5_neck_elif")
    assert any(r.rel_type == "resolves" and "elif" in _c(res, r.from_id).lower()
               for r in res.relations)
    for m in res.moves:
        assert "elif" not in _c(res, m.matter_id).lower() or not m.user_facing


def _c(res, cid):
    return next(c.content for c in res.claims if c.claim_id == cid)


def test_c6_context_modulates_without_hardcode():
    res, _ = _result("c6_surgery_context")
    assert res.t2 is not None and res.t2.context_labels != ["grief-dominant"]
    assert res.t2.context_weight >= 0  # inferred, never asserted


def test_c7_third_party_never_self_debt():
    res, _ = _result("c7_third_party")
    assert not res.views.companion_obligation  # no self-accounting debt
    assert any(m.kind == "WATCH" and not m.user_facing for m in res.moves)


def test_c8_vocab_bridge_closes_loop():
    res, _ = _result("c8_stale_loop_vocab")
    assert any(r.rel_type == "refines" for r in res.relations)
    assert all(m.kind != "QUESTION" for m in res.moves)  # no re-ask


def test_c9_observability_gate():
    res, _ = _result("c9_observability")
    assert any(f["finding"] == "expected_but_missing" for f in res.expected_but_missing)
    assert any(f["finding"] == "UNKNOWN" for f in res.unknowns)


# ---------------- Phase A.5: real-evidence precision ----------------

def _a5(case_id):
    from shadow_a.cases import build_cases
    from shadow_a.pipeline import run_case
    spec = next(s for s in build_cases() if s["case_id"] == case_id)
    return run_case(spec["case_id"], spec["events"],
                    spec.get("observed_sources", []),
                    spec.get("user_tracking_ok", True)), spec


def test_a5_same_as_positive_and_negative():
    res, _ = _a5("a5_s1_full")
    by_content = {c.content: c for c in res.claims}
    pairs = {(r.from_id, r.to_id) for r in res.relations if r.rel_type == "same_as"}
    assert pairs, "no positive same_as on real S1 evidence"
    id_of = {v.claim_id: k for k, v in by_content.items()}
    merged = {(id_of[a][:30], id_of[b][:30]) for a, b in pairs}
    assert any("matias" in a and "matias" in b for a, b in merged)
    assert any("yoshi" in a and "yoshi" in b for a, b in merged)
    # no cross-kid merge: every same_as pair shares its non-user subject token
    for a, b in merged:
        assert ("yoshi" in a) == ("yoshi" in b)
        assert ("matias" in a) == ("matias" in b)
    res4, _ = _result("c4_two_sams")
    assert not any(r.rel_type == "same_as" for r in res4.relations)
    assert any(r.rel_type == "blocks" for r in res4.relations)


def test_a5_chairs_reopen_answered_from_history():
    res, _ = _a5("a5_s1_full")
    assert any(r.rel_type == "reopens" for r in res.relations)
    reasks = [c for c in res.claims if "re-asks" in c.content]
    assert reasks
    for c in reasks:
        a = next(x for x in res.assessments if x.matter_id == c.claim_id)
        assert a.telemetry == "NO_MOVE_WARRANTED" and not a.moves


def test_a5_sequential_revision_preserves_evidence():
    from shadow_a.pipeline import replay_sequential
    res, spec = _a5("a5_s1_full")
    snaps = replay_sequential(spec["case_id"], spec["events"],
                              spec.get("observed_sources", []), True)
    assert len(snaps) == len(spec["events"])
    # partially_fulfils appears at the email, gains the feed as evidence,
    # never loses the original ref.
    seen_with, seen_grown = False, False
    for sn in snaps:
        for r in sn.relations:
            if r.rel_type != "partially_fulfils":
                continue
            refs = set(r.evidence_refs)
            if "s1_e03" in refs:
                seen_with = True
            if {"s1_e03", "s1_e04"} <= refs:
                seen_grown = True
    assert seen_with and seen_grown


def test_a5_neck_watch_earns_then_retires():
    from shadow_a.pipeline import replay_sequential
    res, spec = _a5("a5_s4_full")
    snaps = replay_sequential(spec["case_id"], spec["events"],
                              spec.get("observed_sources", []),
                              spec.get("user_tracking_ok", True))
    by_event = dict(zip([e["id"] for e in spec["events"]], snaps))
    mid = by_event["s4_e04"]
    assert any(m.kind == "WATCH" and not m.user_facing
               and "neck" in _c(mid, m.matter_id).lower() for m in mid.moves)
    final = snaps[-1]
    assert not any("neck" in _c(final, m.matter_id).lower() for m in final.moves)


def test_a5_elena_fragment_owned_by_elena():
    res, _ = _a5("a5_elena_fragment")
    assert len(res.obligations) == 1
    o = res.obligations[0]
    assert (o.obligor, o.beneficiary) == ("elena", "kai")
    assert not res.views.companion_obligation
    assert all(not m.user_facing for m in res.moves)


def test_a5_sophie_promise_is_self_accounting():
    res, _ = _a5("a5_s4_full")
    acts = [m for m in res.moves if m.kind == "ACT"]
    assert any("sophie will come back" in _c(res, m.matter_id).lower()
               and not m.user_facing for m in acts)


def test_a5_school_money_reconciled_across_sources():
    res, _ = _a5("a5_s1_full")
    assert any(r.rel_type == "fulfils" and "school trip 18 paid" in _c(res, r.from_id).lower()
               for r in res.relations)
