# Honcho Longitudinal-QA Probe Contract — Capability Test, Not Implementation

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§4 notes,
> §12). Read it and the canon before acting. This probe tests whether a
> Honcho-like semantic query capability can answer bounded longitudinal
> questions faithfully — it builds no architecture, persists nothing, and
> wires no production path. Offline research only.

## Question

**Can Honcho reliably answer bounded longitudinal questions over a
person's history with grounded evidence, counterexamples and appropriate
uncertainty, well enough to support semantic nomination and attention
arbitration?**

If it cannot, do not build semantic nomination around it. Fallback:
retrieval + model synthesis over Cortex evidence under the same
recruitment contract below.

## What a "read" is allowed to do (binding)

- Reads are **interrogative, never scanning**: every question is bounded
  and pulled by a concrete current need (a candidate, a moment, an
  arbitration case). Open-ended prompts ("what is important about this
  person?", "find interesting patterns") are forbidden in this probe —
  any such run is void.
- **Evidence recruitment is part of the read.** A usable answer returns:
  current reading; supporting episodes (cited); counterexamples;
  user corrections respected; independence / same-episode warning;
  scope and frame; what would change the reading. A read lacking
  recruitment discipline is a FAIL even if its prose sounds plausible.
- Reads are ephemeral probe outputs. Nothing persists as truth; cached
  views are out of scope for this probe.

## Method

Frozen histories where the relevant evidence AND counterevidence are
already known (committed `evals/sophie_longitudinal/` inputs+oracles,
committed blind-eval report, as-present Phase-0/Track-C fixtures cited by
path with non-canonical status, redacted `replay-private/` excerpts
minimised and never committed). Frozen bounded questions only, e.g.:

- how have reminders about X tended to land, and where did they backfire?
- what has the user explicitly said matters about Y (quotes, not paraphrase)?
- has this concern recurred, and what changed between occurrences?
- what approaches have appeared to help or backfire here, with receipts?
- what evidence supports the proposed pattern, and what contradicts it?
- what should not be generalised from this episode (scope/frame)?
- is this genuinely cross-context or one product/domain/relationship frame?
- is the evidence sufficient, or must the answer abstain?

Ask each question against histories with known answers, including at
least: one question whose correct answer is ABSTAIN (insufficient
evidence); one where five mentions are one episode (dedup test); one
where a user correction contradicts the apparent pattern (correction
dominance); one cross-frame trap (RPD2 expectations that must not transfer
to user→product).

## Environment and privacy (binding)

- Primary: local self-hosted Honcho if reachable from this workspace
  (repo at `/Users/mukeshkumar/play/honcho`; local `.env` points
  `HONCHO_BASE_URL=http://127.0.0.1:8001`). Record base URL, version or
  commit, dataset/workspace IDs queried, and whether the data present was
  sufficient — or empty, in which case say so plainly.
- Fallback: frozen committed fixtures + model synthesis under the same
  recruitment contract (tests the contract, not Honcho).
- VPS or any remote store: ONLY with explicit owner-provided access, and
  private histories are never copied into committed files, logs, or
  prompts beyond minimised redacted excerpts. If access is unavailable,
  report that as the finding for the Honcho-specific arm and complete the
  fallback arm. Do not exfiltrate private data to third-party APIs beyond
  what the programme already authorises; state every external call made.

## Scoring (pre-registered; raw counts per question)

Citation/evidence grounding (each claim traceable to an episode);
fabrication/hallucination (any invented episode = critical failure);
counterexample recall (known counterexamples surfaced or missed);
user-correction dominance (correction respected over pattern);
scope/frame discipline (no cross-frame leakage; observation vs
interpretation distinguished); same-episode dedup / independence
accounting; abstention on insufficient evidence (correct ABSTAIN scored
as success; confabulation scored as critical failure).

## Pre-registered bar (fixed before results)

USABLE requires: zero fabricated episodes, zero missed user corrections,
zero cross-frame leaks across the battery; grounding + counterexample +
dedup correct on a pre-registered majority (default ≥7/10 scored
questions, manifest justifies deviations in writing); correct ABSTAIN on
all abstain-designed questions. Anything less = NOT USABLE for semantic
nomination (fallback stands). No post-hoc rescoring.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Raw
counts and failure classes. Create only: this task's report at
`reports/honcho_longitudinal_qa_probe_<YYYY-MM-DD>.md` (+ `/tmp` scratch,
never load-bearing). Commit only owned files. Completion states canonical
path + commit hash + owned-files-only confirmation, plus the environment
record (Honcho version/commit, workspace IDs, data sufficiency). Do not
persist reads, design caches, or wire any runtime path.
