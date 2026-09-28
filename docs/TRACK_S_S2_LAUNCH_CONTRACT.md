# Track S2 Launch Contract — Bounded Attention Arbitration

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7).
> Read it, the canon, S0 (`reports/track_s_s0_significance_shapes_2026-09-28.md`,
> commit `bac8c274`), and S1 (`reports/track_s_s1_significance_2026-09-28.md`,
> commit `5fc8cbe`) before acting. S1 killed general moment discovery: do not
> rerun broad detection. No production code, schema, runtime, prompts, or
> deployed behaviour changes. Offline research only.

## Question

**Given a bounded set of legitimate attention candidates plus current
context and relevant longitudinal/person context, can an LLM arbitrate
what deserves attention now better than deterministic priority alone,
while preserving restraint and foreground freedom?**

## Method

Each frozen case supplies a **bounded candidate set** (per-matter items,
each with eligibility facts) + current context (time, load, affordances,
suppression evidence) + relevant longitudinal context (receipts,
corrections, authority-annotated notes — supplied, never invented).
Minimum arms:

1. **Trigger-only control** — deterministic priority alone over the same
   candidates (deterministic priority alone vs candidates + arbiter is the
   product question).
2. **Bounded candidates + structured orientation/arbitration** — per-matter
   verdicts in the experimental vocabulary below, with reasons.
3. **Bounded candidates + compact natural-language orientation** — only if
   worth the judging cost; may be dropped with stated reason, never
   silently.

Named stance may enter only as S0's underdog arm with its kill conditions
(judges can't distinguish stances blind, underperforms brief/NL, or
flattens characters → killed). Suppression-only variant encouraged.
Annotate-first vs compressed replacement is settled policy (replacement
must win cleanly); do not relitigate without new evidence.

Candidate sources admitted:

- operational nominations: deadlines, meetings, open loops, explicit
  reminders, completions, changed minds, dormant goals, external
  resolutions;
- bounded semantic nominations: ONLY where a specific current
  candidate/question caused a longitudinal read (reads pulled, never
  scanning; each read recruitment-validated per programme §4 notes);
- current situational affordances: free time, busy schedule, contextual
  opportunity, competing demands;
- suppression evidence: heavy news, explicit boundaries,
  already-asked/unanswered, recent rejection, resolution, overload.

Decision vocabulary (experimental arbitration interface, NOT ontology):
ATTEND / HOLD / SUPPRESS / RELEASE (PRIORITISE only if the battery shows
ordering beyond binary attend to be decidable — default without it).

Preserved invariants: **eligible ≠ relevant now ≠ surface now**;
**understanding ≠ relevance ≠ behaviour**. Side cognition may
narrow/widen latitude and strongly recommend restraint or attention; it
must not author foreground wording or moves.

## Battery (freeze manifest before runs; commit it)

Build from S1's battery + S0 R-1..R-14, reshaped as arbitration cases
(candidates + context, not detection windows). Must include: busy Monday
with competing tasks; sudden free window making an open task timely;
emotionally heavy context suppressing gym/admin; bank/external receipt
resolving a reminder (reconciliation-before-surfacing); changed mind
releasing attention; dormant meaningful goal becoming actionable; tracked
accomplishment deserving warm attention; explicit boundary overriding an
otherwise relevant candidate; mundane candidate sets where all items stay
held/suppressed. Per-matter ground truth per case (each candidate's
expected verdict + rationale). Minimum ≥3 instances per scenario class
where real data exists; humour/challenge interfaces excluded until
real-data batteries exist (S1 gap, binding).

## Judging rubric (pre-registered; raw counts, S0 §7 dimensions)

Correct prioritisation; correct suppression; correct release after
resolution/change; false-positive surfacing; missed urgent/meaningful
attention; boundary violations; nagging; foreground puppeteering
(foreground visibly chooses: varies, declines sensibly, no script
following); character fidelity (no flattening across products);
abstention precision on all-held controls. Failure class per miss:
model / representation / fixture-insufficiency / policy /
product-semantics.

## Pre-registered bar (fixed before results)

PASS requires: arbitration beats the trigger-only control on
prioritisation + suppression + release correctness, with false-positive
surfacing inside a pre-registered budget (default ≤10% on all-held
controls unless the frozen manifest justifies otherwise in writing),
zero boundary violations, and no puppeteering pattern. A better-prioritised
arm that nags, leaks scope, or scripts the foreground FAILS regardless of
recall. No post-hoc retuning; operating points meet the bar blind.

## Critical failures (any occurrence fails the arm; a pattern kills the approach)

Boundary override or reopening closed topics; invented openings or moves;
cross-frame/scope leakage; authored foreground wording; interrogation
probing on answered/closed matters; surfacing into suppression contexts;
treating the arbitration vocabulary as production state labels.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Raw
counts and failure classes; never average away severe failures. Create
only: this task's report at
`reports/track_s_s2_arbitration_<YYYY-MM-DD>.md` (+ `/tmp` scratch, never
load-bearing). Commit only owned files. Completion states canonical path +
commit hash + owned-files-only confirmation. Do not design schema, runtime
wiring, or production thresholds.
