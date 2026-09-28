# Track P1 Launch Contract — Loss Analysis for Durable Shared Persistence

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§6).
> Read it, the canon, and P0 before acting. P0 report:
> `reports/track_p_p0_separability_2026-09-28.md` (verify it is committed;
> if not, report the blocker and proceed on the file as present, citing path).
> No production code, schema, runtime, prompts, or deployed behaviour changes.
> No new production mechanisms. Offline research only.

## Question

**What derived understanding actually earns durable shared persistence
beyond operational evidence, receipts, explicit user-authored knowledge and
product-local context?**

"Looks meaningful" earns nothing. Persistence is residue past a harsh
baseline, or it is refused.

## Method

For each candidate derived understanding (person-level and relational,
§Battery):

1. Freeze the evidence set (manifest order, provenance per item).
2. **Control arm (mandatory, real, documented):** attempt to recover the
   future turn / cross-product handoff quality from the harsh baseline
   only — operational evidence + receipts + authored user knowledge +
   product-local context, **without** the candidate. Show the work: what the
   baseline recovers and where it fails, turn by turn.
3. Candidate arm: same future turn/handoff with the candidate available
   (scoped, recheck-bound, per §3 dimensions of the programme doc).
4. Judge degradation blindly where feasible (judge sees baseline-recovered
   vs candidate-supported handling without labels).
5. Verdict per candidate: PERSIST (shared-person / shared-relationship /
   product-local) with scope, expiry, and recheck — or CONTESTED-EPHEMERAL —
   or DROP. Scope promotion (`product-local → candidate → shared`) is an
   explicit evidence-gated operation, recorded with its justifying evidence.

## Battery (freeze manifest before judging; commit it with the report)

Minimum candidates (IDs stable in report):

- P1-C1 Alchemist resonance (cross-product specimen): authored favourite
  (w1) + literalness correction (w3) + ambition-context reception (w2) +
  bereavement inapplicability (w4). Tests the full
  authored → observed → derived promotion path and scope-narrowing.
- P1-C2 "When feeling controlled, disengages even when agreeing"
  (person-level inferred candidate from RPD2/Sophie trajectories).
- P1-C3 RPD2 bounded-repair hypothesis rh3 (relational learning,
  single-diagnostic-consequence case; stays contested per P0 ambiguous
  case 1 unless repeat evidence exists).
- P1-C4 Reminder-style-X / challenge-over-placation correction
  (relational learning from correction history).
- P1-C5 Monday-subdued pattern c9 (well-evidenced never-surface: does
  backstage-only persistence earn *anything*?).
- P1-C6 Headache+sleep co-occurrence c6 (temporal co-occurrence vs causal
  hint; third occurrence must not auto-promote).
- P1-C7 Training-overload (Bloom-local c2) → "pushes through recovery
  signals when highly invested" (shared candidate; tests scope promotion
  and the laundering boundary).
- P1-C8 Explicit long-term goal + meaningful aim + repeated system
  correction (expected-persist anchors; control-arm must confirm cheaply).

Relational-learning cases (C3, C4) are mandatory, not optional. Each entry
records source/provenance × reading × epistemic status × scope/owner
separately — never a single tier label.

## Evidence sources (frozen references; verify presence, report gaps)

- Committed: `evals/sophie_longitudinal/scenario_{1,2,3,4}_*_input.json` and
  `*_oracle.json`; `reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`.
- Pending landing (uncommitted at contract writing): P0 report;
  `evals/interpretation_phase0/{cases.json,track_c_bloom_cases.json}`;
  Track A/C reports. Use the files as present; cite paths; never treat
  pending files as canonical — re-verify at run time.
- Private (gitignored, never committed): `replay-private/` corpora.
  Minimise excerpts; never copy full trajectories into the report.

## Judging rubric (pre-registered; raw counts, no aggregate score)

Per candidate: (a) baseline recovery — FULL / PARTIAL (what exactly is
missing, quoted) / FAILED; (b) degradation cases — count of independent
future-turn/handoff instances that degrade without the candidate, with
session/product IDs; (c) scope verdict and promotion evidence; (d) expiry +
recheck condition; (e) failure class if refused (model / representation /
fixture-insufficiency / policy / product-semantics).

## Pre-registered persistence bar (fixed before results; not negotiable after)

- DURABLE SHARED persistence requires degradation demonstrated in **≥2
  independent instances across sessions or products**, OR **1 instance +
  explicit user confirmation**. Anything less → contested-ephemeral at best.
- Single-instance inferred candidates ( however diagnostic) stay
  contested-ephemeral. One receipt is never durable truth.
- Backstage-only (never-surface) persistence must additionally pass P3-style
  harm clearance in miniature: surveillance texture, user-endorsement, and
  removability stated, or it is DROPPED even if decision-effect is shown.

## Critical failures (any occurrence kills the candidate; a pattern kills the tier)

- Persisting or surfacing against an explicit user boundary or correction.
- Claiming privileged access to the user's "true" values over their stated
  values (paternalism).
- Silent scope escape (product-local content presented as shared-person).
- Repetition counted as independent corroboration.
- Inventing a numeric threshold, score, or lifecycle state.
- Treating a lifecycle transition ("paid", "resolved", "deferred") as a
  confidence upgrade.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Report
raw counts and failure classes. Create only: this task's report at
`reports/track_p_p1_loss_analysis_<YYYY-MM-DD>.md` (+ `/tmp` scratch, never
load-bearing). Commit only owned files. Completion states canonical path +
commit hash + owned-files-only confirmation. Do not execute P2/P3; do not
design schema.
