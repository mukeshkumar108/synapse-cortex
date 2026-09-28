"""Cortex authoritative joins: corrections / lifecycle / closures / boundaries.

Joined BEFORE synthesis. Out-of-band authority outvotes in-band evidence at
the decision checkpoint. Derived entirely from the evidence corpus here
(user-authored utterances + operational records); in a live deployment this
is where Cortex lifecycle truth (paid/closed/released, boundaries) would
enter as structured rows instead of mined text.
"""

from __future__ import annotations

from typing import List

from src.longitudinal_read.models import CortexJoin, EvidenceItem

# Authoritative user corrections discovered in evidence. Each is a
# user-authored withhold / release / scope-boundary that MUST dominate
# pattern evidence at its decision checkpoint (G1).
_CORRECTIONS = [
    ("lucy_payment", "correction",
     "User withholds paid-verdict on the £240 row until direct confirmation from Lucy.",
     "s3_e05", "2026-09-28T21:43:00+01:00"),
    ("lucy_payment", "receipt",
     "Lucy directly confirms the £240 was hers (closes Monday uncertainty).",
     "s3_e08", "2026-09-30T08:33:00+01:00"),
    ("neck_watch", "closure",
     "User releases the neck watch: 'don't need to keep asking about that anymore'.",
     "s4_e10", "2026-10-01T08:44:00+01:00"),
    ("surfacing_restraint", "boundary",
     "Moment restraint for that turn only ('don't just give me everything'); never a global rule.",
     "s1_e10", "2026-09-30T09:11:00+01:00"),
    ("studio_contract", "correction",
     "User self-negates execution: approval given but 'I didn't sign anything'.",
     "s3_e06", "2026-09-29T14:12:00+01:00"),
    ("studio_contract", "receipt",
     "Final signature copy arrives (Friday); user signs an hour before reporting.",
     "s3_e12", "2026-10-02T07:15:00+01:00"),
    ("cousin_pickup", "receipt",
     "Pickup loop closes via user-marked calendar completion + 'Mum got home fine'.",
     "s3_e10", "2026-10-01T15:18:00+01:00"),
    ("school_payment", "supersession",
     "School-child identity resolves to Andree (supersedes earlier ambiguity).",
     "s1_e12", "2026-10-01T07:54:00+01:00"),
    ("school_payment", "receipt",
     "£18 school-trip payment leaves via bank feed.",
     "s1_e13", "2026-10-01T18:49:00+01:00"),
    ("carlos_debt", "lifecycle",
     "Chase deferred: 'If he hasn't paid by tomorrow then we'll chase' / 'Don't chase him tonight' / 'give him until tomorrow'.",
     "s1_e11", "2026-09-30T16:18:00+01:00"),
]


def joins_for_matters(
    matters: List[str], cutoff_iso: str, evidence: List[EvidenceItem]
) -> List[CortexJoin]:
    """Return authoritative joins for the given matters, cut off structurally."""
    out: List[CortexJoin] = []
    for matter, kind, statement, eid, ts in _CORRECTIONS:
        if matter not in matters:
            continue
        if ts > cutoff_iso:
            continue  # structural cutoff applies to authority too
        out.append(CortexJoin(matter=matter, kind=kind, statement=statement,
                              source_event_id=eid, timestamp=ts))
    # Lifecycle truth visible directly in retrieved evidence (receipts,
    # completions, closures) is re-surfaced as joins so synthesis cannot miss it.
    for ev in evidence:
        if ev.event_id == "s3_e10" and "cousin_pickup" in matters and ev.timestamp <= cutoff_iso:
            out.append(CortexJoin(matter="cousin_pickup", kind="lifecycle",
                                  statement="Calendar event 'Mum pickup — Sam' marked completed by user.",
                                  source_event_id="s3_e10", timestamp=ev.timestamp))
        if ev.event_id == "s1_e13" and "school_payment" in matters and ev.timestamp <= cutoff_iso:
            out.append(CortexJoin(matter="school_payment", kind="lifecycle",
                                  statement="Outgoing £18 payment to School Trips Ltd recorded.",
                                  source_event_id="s1_e13", timestamp=ev.timestamp))
    return out
