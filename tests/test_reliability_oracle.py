"""The reliability oracle must itself be trustworthy: it reports every fault
(nothing overwritten), has no vacuous checks, and accepts equivalent correct
end states. Pure functions; no network."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from eval_reliability import check_one, evaluate  # noqa: E402
from reliability_fixtures import FIXTURES  # noqa: E402


def row(title, status="open", date=None, detail="", timing="", kind="event"):
    return {"title": title, "status": status, "expected_date": date, "detail": detail, "timing": timing, "kind": kind,
            "question": "", "waiting_on": ""}


def _final(name, ledger):
    """Checks that apply to the END state (the same ledger is not a valid mid-run state)."""
    fix = FIXTURES[name]
    snaps = {sid: ledger for sid, _, _ in fix["sessions"]}
    last = fix["sessions"][-1][0]
    return [c for c in evaluate(fix, {"snapshots": snaps}) if c["at"] == last]


def test_closed_dentist_with_lost_time_reports_both_faults():
    bad = [row("Dentist appointment time confirmation", "done", "2026-10-22", "time not yet determined")]
    final = _final("dentist-lifecycle", bad)[-1]
    assert not final["pass"]
    joined = " ".join(final["notes"])
    assert "status not in ['open']" in joined and "nothing matches" in joined       # neither hides the other


def test_dentist_equivalent_correct_states_pass():
    for detail in ("Thursday 2026-10-22 at 2pm", "appointment 2:00 PM", "Thursday, 14:00"):
        ok = _final("dentist-lifecycle", [row("Dentist appointment", "open", "2026-10-22", detail, "Thursday")])
        assert all(c["pass"] for c in ok), (detail, ok)
    assert not all(c["pass"] for c in _final("dentist-lifecycle", [row("Dentist appointment", "waiting", "2026-10-22", "2pm Thursday")]))


def test_duplicate_or_missing_rows_fail_not_vacuously_pass():
    assert not all(c["pass"] for c in _final("dentist-lifecycle", []))
    two = [row("Dentist appointment", "open", "2026-10-22", "2pm"), row("Dentist time", "open", "2026-10-22", "2pm")]
    assert not all(c["pass"] for c in _final("dentist-lifecycle", two))


def test_vinesh_equivalent_end_states_pass_and_faults_fail():
    sep = [row("Send proposal to Vinesh", "done", "2026-10-22", "sent", kind="commitment"),
           row("Review with Vinesh", "open", "2026-10-23", "moved to Friday morning")]
    assert all(c["pass"] for c in _final("vinesh-reschedule", sep))
    # a separate review row whose detail merely mentions the proposal is not "the proposal" (observed false failure)
    sep2 = [row("Send proposal to Vinesh", "done", "2026-10-22", "promised by Thursday; review moved to Friday", kind="commitment"),
            row("Vinesh review", "open", "2026-10-23", "moved to Friday morning; the proposal was sent this morning", "Friday 2026-10-23 morning")]
    assert all(c["pass"] for c in _final("vinesh-reschedule", sep2))
    folded = [row("Send proposal to Vinesh", "done", "2026-10-23", "review moved to Friday; sent this morning", kind="commitment")]
    assert all(c["pass"] for c in _final("vinesh-reschedule", folded))
    junk = [row("Deliver proposal to Vinesh", "done", None, "x"), row("Vinesh proposal", "open"),
            row("The Vinesh proposal, closed with the quote", "open")]
    res = _final("vinesh-reschedule", junk)
    assert not all(c["pass"] for c in res)
    premature = FIXTURES["vinesh-reschedule"]
    snaps = {"vr1": [row("Send proposal to Vinesh", "open", "2026-10-22")],
             "vr2": [row("Send proposal to Vinesh", "done", "2026-10-22")],
             "vr3": [row("Send proposal to Vinesh", "done", "2026-10-22")]}
    r2 = {c["at"]: c for c in evaluate(premature, {"snapshots": snaps})}
    assert not r2["vr2"]["pass"]                                                      # a moved review must not close the proposal


def test_mixed_plate_checks_are_real():
    good = [row("Invoice from James", "done", kind="commitment"), row("Run a marathon", "open", kind="aspiration"),
            row("Call Mum at 6", "open", "2026-10-20", "tomorrow at 6", kind="reminder"), row("Pete SSH pings", "suppressed")]
    assert all(c["pass"] for c in _final("mixed-plate", good))
    wrong_day = [dict(r) for r in good]
    wrong_day[2]["expected_date"] = "2026-10-21"
    fix = FIXTURES["mixed-plate"]
    both = lambda led: evaluate(fix, {"snapshots": {"mp1": led, "mp2": led}})
    assert not all(c["pass"] for c in both(wrong_day))                    # tomorrow resolved against the wrong day
    assert not all(c["pass"] for c in both([r for r in good if "marathon" not in r["title"].lower()]))
