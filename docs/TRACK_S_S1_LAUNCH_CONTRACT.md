# Track S1 Launch Contract — Moment-Significance Calibration

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7).
> Read it, the canon, and the S0 situation below before acting. No
> production code, schema, runtime, prompts, or deployed behaviour changes.
> Offline research only. You are calibrating detection, not building a
> runtime monitor.

## Question

**Can side cognition detect moment significance / trajectory relevance well
enough to outperform cheap explicit-signal baselines without introducing
unacceptable false-positive steering?**

S1 does NOT classify every battery shape. Per-shape accuracy is explicitly
not the metric. Rupture/frustration is one subclass; significance,
opportunity, deepening, and timely silence matter equally.

## S0 status (binding constraint on this track)

The S0 report is **not canonically landed** at contract writing. Do not
cite S0 shape identifiers (`SHP-*`) or S0 findings as prior work. Build the
manifest from the battery categories in the programme doc §7 and committed
fixtures only. If S0 lands mid-run, reconcile differences explicitly; do
not silently adopt its taxonomy. Battery labels must never become
classifier outputs or state labels in any proposal.

## Method

Sliding-window runs over the frozen manifest (§Manifest). Two arms minimum:

- **Cheap-baseline arm:** explicit correction/frustration markers, explicit
  boundaries, due/open commitments, explicit completion or change-of-mind,
  ABSTAIN. Deterministic or near-deterministic triggers only.
- **Significance-detector arm(s):** side-cognition readings of moment
  significance (opportunity, circling, deepening, accomplishment, drift,
  recheck firing, rupture risk). Frozen prompts/configs; no oracle leakage;
  no access to future turns beyond the window.

Judge against user-marked ground truth: explicit user frustration /
correction, marked accomplishments, remembered-goal relevance points,
user-closed topics. Mundane turns and correct-silence cases are scored
controls, not filler.

## Manifest (freeze before runs; commit it with the report)

Cover all programme-doc §7 categories: rupture/friction, successful
repair, circling, deepening, remembered goals, missed opportunities,
celebration/accomplishment, humour/shared repertoire, changed mind,
gradual personal change, correct silence, unwanted probing, successful
challenge, mundane nothing-should-happen turns. Sources, in preference
order: committed `evals/sophie_longitudinal/` scenario inputs+oracles and
the committed blind-eval report; redacted excerpts of `replay-private/`
corpora (gitignored — minimise, never commit full trajectories); synthetic
Bloom/Phase-0 cases only where real coverage is absent (labelled as such,
never as significance evidence). Minimum: ≥3 instances per category where
real data exists; every mundane/correct-silence control documented with
why nothing should fire.

## Judging rubric (pre-registered; raw counts, no aggregate score)

- Recall on user-marked rupture moments vs cheap-baseline recall (same
  windows, reported separately).
- Recall on non-rupture significance (remembered-goal relevance,
  accomplishment, deepening, missed opportunity) vs cheap baseline.
- False-steer rate on mundane + correct-silence controls (any steering
  output where ABSTAIN was correct).
- Latency/window metadata recorded (window sizes tested, no production
  latency claims).
- Failure class per miss/false-steer: model / representation /
  fixture-insufficiency / policy / product-semantics.

## Pre-registered bar and false-positive budget (fixed before results)

- PASS requires BOTH: (a) detector recall exceeds the cheap baseline on
  user-marked moments at (b) false-steer rate on mundane + correct-silence
  controls **≤10%**. Exceeding recall while exceeding the FP budget is a
  FAIL (rupture tunnel vision fails the loop regardless of recall).
- Non-rupture significance recall must be reported separately; a detector
  that only fires on frustration is a FAIL of scope even if it passes on
  rupture (wind tunnel, not aircraft).
- No threshold may be tuned after seeing results. Report the operating
  point frozen before scoring.

## Critical failures (any occurrence fails the run for that arm; a pattern kills the detector)

- Steering that overrides, reopens, or surfaces past an explicit user
  boundary or topic-close.
- Invented openings (resurfacing nothing real; café-invention).
- Cross-frame/scope leakage (e.g. RPD2 relational norms steering
  Sophie/Bloom handling, or character-frame expectations applied to
  user→product).
- Authored behavioural moves (`say` / `ask` / `apologise` / `pursue`) or
  scripted utterances in steering output.
- Steering that fires interrogation-style probing on an already-answered
  or explicitly closed matter.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Report
raw counts and failure classes; never hide severe failures inside averages.
Create only: this task's report at
`reports/track_s_s1_significance_<YYYY-MM-DD>.md` (+ `/tmp` scratch, never
load-bearing). Commit only owned files. Completion states canonical path +
commit hash + owned-files-only confirmation. Do not execute S2; do not
canonise any shape, stance, or interface.
