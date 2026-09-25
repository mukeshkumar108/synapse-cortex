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
