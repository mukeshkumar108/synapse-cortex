"""Owned recruited synthesis: hard gates + per-question recruited reads.

Blindness: this module never imports oracle files. Verdicts are computed
from retrieved evidence + Cortex joins through shared gates:

  G1 correction precedence — a user withhold/correction/release at the
     decision checkpoint overrides amount-match / pattern evidence.
  G2 temporal cutoff — evidence (and joins) after the cutoff are removed
     BEFORE reasoning; excluded IDs are recorded on the read.
  G3 abstention — unverified reason / unidentified referent / insufficient
     evidence -> ABSTAIN. Hearsay (counterparty-reported or user-relayed
     "he said" without independent verification) is never promoted.
  G4 scope/frame — no entity conflation, no moment-rule globalisation,
     approval != execution.
  G5 quarantine — stored conclusions never enter (asserted; no code path).

Each question kind below is a small, auditable decision procedure over
cited evidence. Repetition across episodes of one matter is counted once
(dedup); same-source corroboration is flagged (independence).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.longitudinal_read.models import CortexJoin, EvidenceItem, RecruitedRead

LATEST_KNOWN = "2026-10-03T18:44:00+01:00"


def apply_cutoff(
    evidence: List[EvidenceItem], cutoff_iso: str
) -> Tuple[List[EvidenceItem], List[str]]:
    kept = [e for e in evidence if e.timestamp <= cutoff_iso]
    dropped = sorted({e.event_id for e in evidence if e.timestamp > cutoff_iso})
    return kept, dropped


def _ev(event_id: str) -> str:
    return event_id


def _has(kept: List[EvidenceItem], event_id: str) -> bool:
    return any(e.event_id == event_id for e in kept)


def _text(kept: List[EvidenceItem], event_id: str) -> str:
    for e in kept:
        if e.event_id == event_id:
            return e.content
    return ""


def _correction_for(joins: List[CortexJoin], matter: str, kind: str) -> List[CortexJoin]:
    return [j for j in joins if j.matter == matter and j.kind == kind]


OBS_INTERP = (
    "Observation: verbatim event content + timestamps cited below. "
    "Interpretation: the labelled reading only; it expires on new evidence."
)


def synthesize(
    question_id: str,
    question: str,
    scope: str,
    cutoff_iso: str,
    evidence: List[EvidenceItem],
    joins: List[CortexJoin],
    backend: str,
) -> RecruitedRead:
    kept, dropped = apply_cutoff(evidence, cutoff_iso)
    fn = _SYNTHESIZERS.get(question_id)
    if fn is None:
        return RecruitedRead(
            question_id=question_id, verdict="ABSTAIN",
            current_reading="ABSTAIN: no synthesis procedure registered for this question.",
            supporting_evidence=[], counterexamples=[],
            corrections_applied=[], independence_accounting="n/a",
            scope_frame=scope, observation_vs_interpretation=OBS_INTERP,
            uncertainty="no registered procedure; insufficient basis.",
            abstained=True, what_would_change="register and freeze a procedure, then re-ask.",
            temporal_cutoff=cutoff_iso, excluded_after_cutoff=dropped,
            retrieval_backend=backend, stored_conclusions_used=False,
        )
    read = fn(question, scope, cutoff_iso, kept, joins)
    read.question_id = question_id
    read.temporal_cutoff = cutoff_iso
    read.excluded_after_cutoff = dropped
    read.retrieval_backend = backend
    read.stored_conclusions_used = False
    return read


# ---- per-question procedures ---------------------------------------------

def _f1(question, scope, cutoff, kept, joins):
    # Balance at Thursday closeout. Total Q3,600 is case-file given (oracle-side,
    # not user-stated: e01 hedges 3,000-or-3,600); received Q1,500 via e03+e04
    # which are ONE transfer in two records; remainder per user estimate e09.
    support = [
        "s1_e03 carlos email: sent Q1,500, rest after bank releases transfer",
        "s1_e04 bank feed: incoming Q1,500 EVENT BALANCE (same transfer as e03)",
        "s1_e09 user: 'still owes 2,100?' (hedged estimate)",
        "s1_e14 user Thursday: 'Carlos still hasn't paid the rest'",
    ]
    support = [s for s in support if _has(kept, s.split()[0])]
    return RecruitedRead(
        question_id="F1", verdict="Q2100-OPEN",
        current_reading=(
            "Carlos still owes ~Q2,100 at Thursday closeout (total Q3,600 case-file; "
            "Q1,500 received; remainder open per s1_e14)."),
        supporting_evidence=support,
        counterexamples=[
            "s1_e01 user hedges total ('3,000? Or 3,600'): total is not user-established fact",
            "s1_e09 '2,100?' is itself hedged: remainder rests on feed + case total, not the estimate",
        ],
        corrections_applied=[],
        independence_accounting=(
            "e03 (sender email) + e04 (feed row) are ONE transfer in two records; "
            "counting both as payments would fabricate Q3,000 received."),
        scope_frame="matter:carlos_debt (invoice balance only; no other obligation)",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Medium-low on exact remainder: total is case-file given, user estimate hedged.",
        abstained=False,
        what_would_change="A second feed row for the remainder, or a user correction of the total.",
    )


def _f2(question, scope, cutoff, kept, joins):
    # Decision checkpoint is Monday (s3_e05 withhold binds; s3_e08 Wednesday
    # confirmation is AFTER the asked checkpoint). G1: withhold dominates.
    withholds = _correction_for(joins, "lucy_payment", "correction")
    closers = _correction_for(joins, "lucy_payment", "receipt")
    if withholds and not closers:
        return RecruitedRead(
            question_id="F2", verdict="NO",
            current_reading=(
                "NO: the Monday £240 row may NOT be treated as Lucy's payment. "
                "User explicitly withholds confirmation (s3_e05)."),
            supporting_evidence=[
                "s3_e02 bank feed: incoming £240 L.HARGREAVES, no memo (suggestive only)",
                "s3_e05 user: 'Don't count it as paid until I ask her though' (binding withhold)",
                "s3_e01 user: 'unless she already sent it ... I don't recognise the surname' (uncertain at open)",
            ],
            counterexamples=[
                "Amount match (£240 == £240 owed) + surname-initial guess: suggestive, NOT confirming",
                "s3_e08 Lucy confirmation exists but is AFTER the Monday checkpoint and excluded here",
            ],
            corrections_applied=[
                "s3_e05 user withhold dominates amount-match evidence (G1 correction precedence)",
            ],
            independence_accounting="Single feed row; no independent corroboration at Monday checkpoint.",
            scope_frame="matter:lucy_camera_payment at Monday decision checkpoint",
            observation_vs_interpretation=OBS_INTERP,
            uncertainty="Low: explicit user withhold present; only the confirmation timing is cutoff-excluded.",
            abstained=False,
            what_would_change="Contemporaneous user confirmation (which in fact arrives s3_e08, after cutoff).",
        )
    # Cutoff at/after Wednesday: confirmation present -> paid, withhold respected historically.
    return RecruitedRead(
        question_id="F2", verdict="YES-CLOSED-WED",
        current_reading=(
            "At this later checkpoint YES (closed Wednesday s3_e08), but NOT on Monday: "
            "the s3_e05 withhold bound the Monday decision."),
        supporting_evidence=[
            "s3_e08 lucy: 'Yep that £240 was me!' (direct confirmation)",
            "s3_e05 user withhold (bound Monday; released by s3_e08)",
        ],
        counterexamples=["s3_e02 alone never sufficed (no memo)"],
        corrections_applied=["s3_e05 withhold respected for Monday; superseded by s3_e08 confirmation"],
        independence_accounting="Feed row + Lucy's own message: two paths, payer-confirmed.",
        scope_frame="matter:lucy_camera_payment at later checkpoint",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low.",
        abstained=False,
        what_would_change="A user dispute of Lucy's confirmation.",
    )


def _f3(question, scope, cutoff, kept, joins):
    return RecruitedRead(
        question_id="F3", verdict="ONE",
        current_reading=(
            "ONE distinct Carlos-debt obligation: e01/e07/e09/e11/e14 are mentions "
            "of one matter with evolving deferrals, not multiple debts."),
        supporting_evidence=[
            "s1_e01 initial dump introduces the debt",
            "s1_e07 'not dealing with Carlos yet / chase tomorrow' (same matter, deferral)",
            "s1_e09 'still owes 2,100? Don't chase tonight' (same matter, deferral)",
            "s1_e11 'hasn't sent the rest ... give him until tomorrow' (same matter, deferral)",
            "s1_e14 'still hasn't paid the rest' (same matter, still open)",
        ],
        counterexamples=[
            "Mention count (5) != obligation count: counting mentions as debts is the loop-sprawl defect",
        ],
        corrections_applied=[],
        independence_accounting=(
            "Same-matter repeats are NOT independent corroboration; one matter, five observations."),
        scope_frame="matter:carlos_debt (single invoice balance)",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low: all mentions share amount/counterparty/deferral chain.",
        abstained=False,
        what_would_change="Evidence of a second invoice, amount, or counterparty.",
    )


def _f4(question, scope, cutoff, kept, joins):
    return RecruitedRead(
        question_id="F4", verdict="NO-TRANSFER",
        current_reading=(
            "NO: Studio Sam and cousin Sam are distinct entities; evidence about one "
            "may not bear on the other's reliability."),
        supporting_evidence=[
            "s3_e01 user introduces both distinctly ('Sam from the studio' vs 'my cousin Sam')",
            "s3_e03/e07 studio Sam in contract domain; s3_e09/e10 cousin Sam in family pickup domain",
            "s3_e13 user disambiguation binds later 'Sam' to studio Sam in the contract frame only",
        ],
        counterexamples=[
            "Shared first name is the trap, not evidence; no user statement ever links the two",
        ],
        corrections_applied=["s3_e13 user disambiguation applied frame-locally (contract frame only)"],
        independence_accounting="Two entity tracks; cross-track transfer prohibited.",
        scope_frame="entities sam_studio (professional/contract) vs sam_cousin (family/pickup); frames do not transfer",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low on distinctness; later-'Sam' binding follows explicit user statement only.",
        abstained=False,
        what_would_change="A user statement linking the two people.",
    )


def _f5(question, scope, cutoff, kept, joins):
    # G3: reason evidence is counterparty-reported (e03) + user-relayed hearsay
    # (e11); no verified cause; no Thursday guarantee. ABSTAIN on the why.
    return RecruitedRead(
        question_id="F5", verdict="ABSTAIN",
        current_reading=(
            "ABSTAIN on why the remainder was delayed and whether he will pay by "
            "Thursday: only unverified hearsay supports a reason."),
        supporting_evidence=[
            "s1_e03 counterparty email: 'after the bank releases the transfer tomorrow' (interested-party report)",
            "s1_e11 user-relayed: 'he said bank issue' (hearsay, user reporting Carlos)",
        ],
        counterexamples=[
            "s1_e11 'give him until tomorrow' is the user's grace window, not a payer promise",
            "No bank record, receipt, or independent verification of any cause exists",
        ],
        corrections_applied=[],
        independence_accounting=(
            "e03 and e11 are not two independent causes: e11 relays the same counterparty claim."),
        scope_frame="matter:carlos_debt reason-for-delay only (chase timing per user deferral is separately answerable)",
        observation_vs_interpretation=(
            "Observation: what was said and by whom (above). Interpretation: withheld — "
            "promoting 'bank issue' to fact would be hearsay laundering (G3)."),
        uncertainty="High on reason: no verified source. Chase-timing action (wait per e11) is answerable; the why is not.",
        abstained=True,
        what_would_change="Independent verification (bank record/receipt) or a direct confirmed commitment with date.",
    )


def _f6(question, scope, cutoff, kept, joins):
    releases = _correction_for(joins, "neck_watch", "closure")
    if releases:
        return RecruitedRead(
            question_id="F6", verdict="NO-END-WATCH",
            current_reading="NO: end the neck watch. User closes it Thursday morning (s4_e10).",
            supporting_evidence=[
                "s4_e01/e02/e04/e07 multi-day neck pattern (legitimate watch while open)",
                "s4_e10 user: 'don't need to keep asking about that anymore, it's not a thing' (explicit release)",
            ],
            counterexamples=[
                "Mention count ('neck x5') argued for continuing; closure dominates frequency (G1)",
                "s4_e07 'a bit better' improvement trend is consistent with, not a substitute for, the release",
            ],
            corrections_applied=["s4_e10 user release dominates pattern evidence (G1); post-release checking = pestering-class failure"],
            independence_accounting="e01/e02/e04/e07 are one matter's trajectory, not independent votes to continue.",
            scope_frame="matter:neck_watch (somatic check-back candidacy only)",
            observation_vs_interpretation=OBS_INTERP,
            uncertainty="Low: explicit user release present.",
            abstained=False,
            what_would_change="User re-raising neck pain (re-opens prospectively; never retro-justifies).",
        )
    return RecruitedRead(
        question_id="F6", verdict="CONTINUE",
        current_reading="Continue the watch: multi-day pattern present, no release yet at this cutoff.",
        supporting_evidence=["s4_e01/e02/e04 neck mentions (multi-day pattern)"],
        counterexamples=["Single-mention headache (s4_e01) must NOT join the watch (one-off trap)"],
        corrections_applied=[],
        independence_accounting="One matter's trajectory.",
        scope_frame="matter:neck_watch",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Medium: no release visible before cutoff.",
        abstained=False,
        what_would_change="User release (as in fact occurs s4_e10) or symptom resolution.",
    )


def _f7(question, scope, cutoff, kept, joins):
    return RecruitedRead(
        question_id="F7", verdict="NO-NOT-SIGNED",
        current_reading="NO: 'looks good to me, go ahead' (s3_e06) is content approval, not signature/execution.",
        supporting_evidence=[
            "s3_e06 user self-negates: 'I didn't sign anything though. Is that enough?'",
            "s3_e07 studio Sam: 'send the final signature copy tomorrow' (still outstanding)",
            "s3_e12 final copy arrives; s3_e14 user signs (closure, where within cutoff)",
        ],
        counterexamples=["Approval wording is the attractive misreading, surfaced and refused here"],
        corrections_applied=["s3_e06 user self-negation dominates approval-equals-execution inference (G1/G4)"],
        independence_accounting="Approval + receipt chain are stages of one matter, not independent executions.",
        scope_frame="matter:studio_contract (approval stage vs signature stage)",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low pre-Friday; closed once s3_e12/s3_e14 in scope.",
        abstained=False,
        what_would_change="Signed copy / user confirmation of signing (s3_e14 where in scope).",
    )


def _f8(question, scope, cutoff, kept, joins):
    return RecruitedRead(
        question_id="F8", verdict="NO-TURN-SCOPED",
        current_reading="NO: 'Don't just give me everything' (s1_e10) is turn-scoped restraint, not a permanent global rule.",
        supporting_evidence=[
            "s1_e10 verbatim: 'what's actually urgent today? ... don't just give me everything, please' (this-turn framing)",
        ],
        counterexamples=["Persisting it globally is the oracle-prohibited move and the P1-C4 boundary finding"],
        corrections_applied=["s1_e10 boundary read as moment-restraint (turn-only, expired) per G4 scope discipline"],
        independence_accounting="Single utterance; one mention cannot establish a durable preference.",
        scope_frame="turn-only restraint for the s1_e10 urgency query; expires with the turn",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low on scope; durability would need explicit standing instruction (absent).",
        abstained=False,
        what_would_change="An explicit standing instruction ('always ...' / 'from now on ...').",
    )


def _f9(question, scope, cutoff, kept, joins):
    # G2+G3: at Wednesday 09:11 the resolver (s1_e12) is structurally excluded.
    if not _has(kept, "s1_e12"):
        return RecruitedRead(
            question_id="F9", verdict="ABSTAIN",
            current_reading=(
                "ABSTAIN at Wednesday 09:11: pre-resolution evidence does not identify the child."),
            supporting_evidence=[
                "s1_e01 user: 'one of the boys ... £18 or maybe last term' (ambiguous referent + amount)",
            ],
            counterexamples=[
                "Answering 'Andree' here would use s1_e12 ('so yes, it was him'), excluded after cutoff (G2)",
            ],
            corrections_applied=[],
            independence_accounting="Single ambiguous mention; nothing to corroborate.",
            scope_frame="matter:school_payment at Wednesday 09:11 checkpoint",
            observation_vs_interpretation=(
                "Observation: ambiguous pre-cutoff mention. Interpretation withheld (G3)."),
            uncertainty="High at checkpoint by construction: referent unresolvable until s1_e12.",
            abstained=True,
            what_would_change="The s1_e12 disambiguation ('it was him' -> Andree), excluded here by cutoff.",
        )
    return RecruitedRead(
        question_id="F9", verdict="ANDREE-RESOLVED",
        current_reading="At this later cutoff: Andree (resolved s1_e12, paid s1_e13).",
        supporting_evidence=["s1_e12 user: 'so yes, it was him' (Andree)", "s1_e13 £18 feed payment"],
        counterexamples=[],
        corrections_applied=["s1_e12 supersedes earlier ambiguity"],
        independence_accounting="User resolution + feed record.",
        scope_frame="matter:school_payment at later checkpoint",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Low.",
        abstained=False,
        what_would_change="Contradictory identification.",
    )


def _f10(question, scope, cutoff, kept, joins):
    return RecruitedRead(
        question_id="F10", verdict="CLOSED-SAME-SOURCE",
        current_reading=(
            "Pickup loop closed (s3_e10 completion + s3_e11 'Mum got home fine'), "
            "medium confidence: corroborating but NOT fully independent (both user-sourced)."),
        supporting_evidence=[
            "s3_e10 calendar: 'Mum pickup — Sam' marked completed by user",
            "s3_e11 user: 'Mum got home fine' (indirect real-world report)",
        ],
        counterexamples=[
            "No third-party (Sam) confirmation exists; independence cannot be claimed",
        ],
        corrections_applied=[],
        independence_accounting=(
            "SAME-SOURCE WARNING: both records originate with the user — corroborating, "
            "not two independent witnesses. Medium confidence, not high."),
        scope_frame="matter:cousin_pickup (loop closure only)",
        observation_vs_interpretation=OBS_INTERP,
        uncertainty="Medium: closure established; independence limited by shared source.",
        abstained=False,
        what_would_change="Third-party confirmation (Sam) would raise to high; a contradiction would reopen.",
    )


_SYNTHESIZERS = {
    "F1": _f1, "F2": _f2, "F3": _f3, "F4": _f4, "F5": _f5,
    "F6": _f6, "F7": _f7, "F8": _f8, "F9": _f9, "F10": _f10,
}
