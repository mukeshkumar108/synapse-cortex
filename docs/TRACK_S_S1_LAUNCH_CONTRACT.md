# Track S1 Launch Contract — Moment-Significance Calibration

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7).
> Read it, the canon, and the S0 situation below before acting. No
> production code, schema, runtime, prompts, or deployed behaviour changes.
> Offline research only. You are calibrating detection, not building a
> runtime monitor.

## Question

**Can side cognition recognise what deserves attention now from the
combination of operational pressure, trajectory relevance, current context,
situational opportunity, suppression signals, and longitudinal
person/relationship understanding — while outperforming cheap
deterministic/explicit-signal baselines without excessive false-positive
steering?**

Moment significance is not trajectory-change detection alone. An open
matter with no new trajectory evidence may become surface-worthy when a
window opens (e.g. 40 free minutes appearing); an important goal may demand
suppression under upsetting news or severe overload. Preserved throughout:
**eligible ≠ relevant now ≠ surface now.** Do not reduce the target to
historical trajectory-change detection, and do not turn the inputs below
into a numeric formula or fixed ontology (calendar/time/load/weather are
examples of context inputs, never mandatory universal primitives).

Hybrid boundary for the experiment: deterministic/operational machinery
establishes facts and eligibility (deadlines, meetings, recurrence,
completion, prior reminders, calendar load, current time, available
context signals); person/relationship understanding supplies importance,
preferences, goals, receipts, help/backfire history; side cognition judges
relevance, opportunity, competing demands, timing, suppression, and
attentional latitude; foreground/product keeps behavioural authority.

## S0 status (canonical — cite it)

S0 report: `reports/track_s_s0_significance_shapes_2026-09-28.md`
(commit `bac8c274`). Its frozen shape inventory SHP-1..SHP-14 and concrete
source table (R-1..R-14) are the manifest basis for this track: build the
manifest from S0 §6, reconciled against the programme doc §7 categories
(which add situational opportunity, suppression-by-context, and
frame/boundary cross-cutting explicitly). Shapes remain evaluation
coverage, never runtime classifier outputs or state labels; the `SHP-*`
prohibition stands. Interface arms for later S2 are S0 §2 (stance
underdog, brief, NL, raw control); S1 calibrates significance detection
only and presumes no interface.

## Method

Sliding-window runs over the frozen manifest (§Manifest). Each window
supplies: operational/context facts as deterministic inputs (due/open
items, deadlines, recurrence state, completion, prior-reminder receipts,
calendar load, current time, available context signals — stated as facts,
never as interpretation); trajectory relevance and person/relationship
content as the longitudinal side; the live turn as the moment. Three arms
minimum:

- **Cheap-baseline arm:** explicit correction/frustration markers, explicit
  boundaries, due/open commitments, deadline/recurrence facts, explicit
  completion or change-of-mind, ABSTAIN. Deterministic or near-deterministic
  triggers only.
- **Significance-detector arm(s):** side-cognition readings combining all
  input classes above into attention judgements (attend / hold / suppress /
  surface-as-candidate / narrow-latitude). Frozen prompts/configs; no oracle
  leakage; no access to future turns beyond the window; no numeric scoring
  formulas — LLM judgement over stated facts, reported qualitatively and
  scored on outcomes.

Judge against user-marked ground truth: explicit user frustration /
correction, marked accomplishments, remembered-goal relevance points,
user-closed topics. Mundane turns and correct-silence cases are scored
controls, not filler.

## Manifest (freeze before runs; commit it with the report)

Build from S0 §6 (R-1..R-14 with concrete sources), reconciled against
programme-doc §7 categories. Cover: rupture/friction, successful
repair, circling, deepening, remembered goals, missed opportunities,
celebration/accomplishment, humour/shared repertoire, changed mind,
gradual personal change, correct silence, unwanted probing,
successful challenge, situational opportunity (open matter meets a newly
available window), suppression-by-context (important matter correctly
withheld under grief, overload, or bad timing), frame/boundary
cross-cutting (diegetic vs extradiegetic vs boundary; scope-leakage
control), mundane nothing-should-happen turns (≥30% of battery per S0 §6).
Sources, in preference order: committed `evals/sophie_longitudinal/` scenario inputs+oracles and
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
  accomplishment, deepening, missed opportunity, situational-opportunity
  timing) vs cheap baseline.
- Correct-suppression rate on suppression-by-context cases (withheld under
  grief/overload/closure where surfacing would be wrong), reported
  separately from recall: chronic failure to suppress is the symmetric
  failure to tunnel vision.
- False-steer rate on mundane + correct-silence controls (any steering
  output where ABSTAIN was correct).
- Latency/window metadata recorded (window sizes tested, no production
  latency claims).
- Failure class per miss/false-steer: model / representation /
  fixture-insufficiency / policy / product-semantics.

## Pre-registered bar and false-positive budget (fixed before results)

- PASS requires ALL of: (a) detector recall exceeds the cheap baseline on
  user-marked moments at (b) false-steer rate on mundane + correct-silence
  controls **≤10%**, and (c) correct-suppression rate on
  suppression-by-context cases reported with no systematic suppression
  blindness (eligible-but-withheld matters must not leak into surfacing).
  Exceeding recall while exceeding the FP budget is a FAIL (rupture tunnel
  vision fails the loop regardless of recall); systematic failure to
  suppress is the symmetric FAIL.
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
- Surfacing an eligible matter into a suppression context (active grief,
  acute overload, user-closed topic) where the oracle requires holding:
  eligible ≠ relevant now ≠ surface now, and relevance misjudged under
  suppression signals fails the arm.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Report
raw counts and failure classes; never hide severe failures inside averages.
Create only: this task's report at
`reports/track_s_s1_significance_<YYYY-MM-DD>.md` (+ `/tmp` scratch, never
load-bearing). Commit only owned files. Completion states canonical path +
commit hash + owned-files-only confirmation. Do not execute S2; do not
canonise any shape, stance, or interface.
