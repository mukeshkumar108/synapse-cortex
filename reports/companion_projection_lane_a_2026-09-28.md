# Thin Slice Lane A — Companion Projection Builder (research, offline, no production)

> Date: 2026-09-28. Owner: Lane A agent. No production code, schema, runtime,
> prompts, or deployed behaviour changed. No runtime consumer built. No
> Companion Runtime integration. No attention governor. No behavioural commands.
> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§10–§12).
> Spec: `docs/COMPANION_PROJECTION_SPEC.md`. Read contract:
> `docs/LONGITUDINAL_READ_CONTRACT.md` (JIT hints only — no read executed here).
> Canon lineage: P0 (`49fa0a0`), P1 (`1ce11ee`, 0/8 shared-durable),
> S1 (`5fc8cbe`, broad detection fails), S2 (`cb8e0f8`, control wins, stance
> killed), S3 (`b5b9591`, exception tier killed on E1d), Honcho rerun
> (`b7dabcb`, stored conclusions unsafe).
>
> Bootstrap: `docs/AGENT_BOOTSTRAP.md` read; branch `main`; HEAD `7cc750d`;
> `6ae9df9` verified ancestor of HEAD before work. Private corpora untouched
> (`replay-private/` never opened). Only committed fixtures + labelled
> synthetic constructions used. Scratch (never load-bearing): `/tmp/lane_a_*.json`
> (result snapshots, example projections). Touch-only-own-files discipline held:
> every committed path below is new and owned by this lane.

## 0. Canonical files created (nothing changed)

- `evals/companion_projection/builder.py` — offline deterministic projection
  builder (pure function of events + session-start timestamp; no DB, no
  network, no model calls, no semantic scanning).
- `evals/companion_projection/corpus.json` — frozen 12-day evaluation corpus
  (`lane-a-eval-v1`, pinned to `sophie-longitudinal-1.0.0` + 2 inline
  synthetic days).
- `evals/companion_projection/score.py` — deterministic scorer + naive flat
  baseline. Run: `python3 evals/companion_projection/score.py [--out FILE]`
  (~0.3s).
- `tests/test_companion_projection_lane_a.py` — canonical bar test (2 tests,
  pre-registered assertions over all 12 days + baseline contrast).
- This report.

## 1. Question

**Can Cortex prepare a small, faithful, disposable model of the user's current
world that gives Companion Runtime enough context to be intelligent without
trying to be the companion itself?**

On the frozen 12-day battery, with this builder: **yes for preparation —
with stated residue.** The projection carries the bounded context Runtime
would need (31/31 required items), preserves every hard constraint with its
verbatim quote and scope (4/4), leaks zero closed matters as active, keeps
relational and operational channels separate on all E1-shaped days, and emits
zero behavioural commands (12/12 self-audits pass). It does not decide, rank,
or script anything.

## 2. Exact projection representation implemented and tested

One JSON object per session-start, sections per `COMPANION_PROJECTION_SPEC.md`:

```text
meta                  builder version, built_at (= session start), session_id,
                      fixture version, horizon basis, source event ids,
                      rebuild_on list, provenance rule, command_audit, counts
current_world         time_constraints (calendar + explicit external deadlines)
                      active_commitments (outstanding reminder requests)
                      task_lifecycle (every matter: open/closed/reference/person + stems)
                      recent_closures, recent_external_events
continuity            session_handoff (verbatim last assistant turn, no summary)
                      open_threads, companion_promises ("I'll…" statements),
                      user_concerns (quoted), corrections (quoted, superseding)
hard_constraints      boundaries, deferrals, required_reminders (all quoted,
                      scope: moment | durable-until-reopened),
                      verified_closures, revalidation_requirements
soft_candidates       active_goals (possible_goal, tentative wording only),
                      unresolved_topics, recent_significant_events,
                      opportunities (open matter × uncongested time, max 1 note)
relational_context    person-context items (relational channel only, quoted)
horizons              now / today / week id-buckets over all items
jit_hints             bounded questions for recurring open threads only,
                      each with trigger + event list, never a conclusion
```

Every item carries `id, kind, topic (extractive slug), text (template-neutral,
no imperatives), quote (verbatim or null), sources (event ids), provenance
(hard|soft), status, horizon`. Lifecycle rows additionally carry `stems`
(explicit content footprint). Builder version `projection-lane-a-v1.0.0`.

### How it is populated (the entire "intelligence", all frozen in code)

1. **Sentence-level matter clustering** over the bounded window: join on ≥2
   shared significant stems (light plural/ed/ing stemming + irregulars +
   florist→flower), or shared name + ≥1 stem; same-turn adjacency lowers the
   bar to 1 stem; pronoun continuation (`he/she/they/it/that…` with
   determiner guard) outranks weak lexical join; weak proportional join
   (≥50% shared) outranks bare positional ellipsis; thin fragments attach to
   neighbours. External records (email/sms/payment/calendar) are NEVER
   absorbed — they stand as their own matters.
2. **Lifecycle classification** from frozen generic-English patterns only
   (first-person completions, don't/stop/leave-alone boundaries, till/push/
   weekend deferrals, remind-me requests, structured corrections with an
   epistemic-hedge guard, concern/accomplishment/half-intention wordings).
   Latest decisive signal wins; explicit drops ("decided not to", "can die
   now") close; outgoing payments close amount-matching matters
   (cross-cluster reconciliation — incoming part-payments do not).
3. **Supersession/reference folding**: closures retire earlier fragments of
   the same matter (even deferral-rested ones), standing
   boundary/deferral/reminder quotes are CARRIED into the surviving cluster
   (closure retires the matter, not the user's terms); external records are
   superseded to `reference` on later overlapping closure, never deleted.
4. **Channel routing**: person threads (no lifecycle movement, no amounts,
   person+affect presence) skip the actionable working set
   (unresolved/active) and live in continuity + relational only; calendar and
   explicit external deadlines are hard time constraints; opportunities need
   an open matter (a person is never an "opportunity").
5. **Horizons** from explicit anchors only (today/tonight words, weekday ==
   session weekday, future markers → week, else recency fallback).
6. **Self-audit**: every non-quote string scanned for ATTEND / SUPPRESS /
   SURFACE / ask-about / mention / bring-up / check-in-on / remind-the-user /
   circle-back / prioritise / nudge / follow-up-with. Templates are
   constructed to avoid the whole list.

## 3. Example projection (representative day d04-boundary, Wed 16:30)

Window s1_e01–s1_e11. Abridged (full: `/tmp/lane_a_example_d04.json`):

```text
HARD (authoritative, quoted, scoped):
- boundary  carlo-chase-owe   [moment]              "Don't chase him tonight."
- boundary  carlo-chase-owe   [durable-until-reopened] "Don't message him though, he said bank issue."
- deferral  carlo-chase-owe   [durable-until-reopened] "I'll give him until tomorrow."
- boundary  feel-forgotten-give [moment]            "And don't just give me everything, please."
- reminder  cake (no explicit time)                 "remind me not to forget the cake lady…"
- reminder  urgency query (today)                   "Can you remind me what's actually urgent today?"
- closure   chairs ✓ "I told the venue yes, 120 chairs, so that's done."
- closure   florist ✓ "I sent her that just now." (+ standing "not today" terms preserved)
- closure   mat-form ✓ "I signed Matías's form at 4:10…" (+ revalidation flag: tentative wording)
SOFT (context, never instruction):
- open threads: carlos-debt, school-money, yoshi-activity, consent-form, cake…
- dormant: none here (cf. d07: course/CV/running as possible_goal)
- opportunity: none (day has calendar load)
- person channel: (none this day; cf. d11 below)
JIT (hint, not answer):
- "Thread 'carlo-chase-owe' spans 5 events; if it becomes live, a longitudinal
   read over s1_e01,s1_e05,s1_e07,s1_e09,s1_e11 may help."
```

E1 contrast (d11): relational channel holds four quoted Matt items
(hospital worry → waiting → surgery update → relief) while the operational
working set holds only the Saturday food-shop routine and open health
threads — `matt`/`surgery` appear in zero unresolved/active/opportunity
items.

## 4. Evaluation corpus and method

Frozen `corpus.json` (12 days, all pre-registered before scoring):

| day | shape | window |
|---|---|---|
| d01 | busy Monday, constrained | s1 ≤ e01 |
| d02 | free-window opportunity | s2 ≤ e07 |
| d03 | task due later today + moment restraint | s1 ≤ e10 |
| d04 | explicit boundary + late closure | s1 ≤ e11 |
| d05 | recently resolved (£18 feed) | s1 ≤ e13 |
| d06 | changed mind + dismissal | s2 ≤ e05 |
| d07 | dormant goals (half-intentions) | s2 e01 |
| d08 | recent accomplishment (self-completed) | s2 ≤ e10 |
| d09 | emotionally significant personal context | s4 e01 |
| d10 | mundane day (synthetic, phatic only) | synthetic |
| d11 | E1 dual (routine + person relief) | s4 ≤ e09 |
| d12 | E1d overload shape (synthetic) | synthetic |

Nine scored dimensions, all exact matching (token/stem/quote substring,
horizon equality, audit result): required-context recall, irrelevant-context
inclusion, stale/closed leakage, explicit-boundary preservation (quote +
scope), hard/soft distinction, horizon correctness, relational/operational
separation, provenance/invalidation availability, command-leakage audit.
Plus mundane caps (unresolved ≤1, opportunities ≤1, hard = 0, relational = 0)
and a deterministic baseline: flat recency-ranked imperative packet
("Priority N: Ask about 'X'… Mention this… remind the user to act").

## 5. Raw evaluation findings

Projection (12/12 days, ~0.3s total):

```text
day | recall | irrel | stale | bound | hardsoft | horiz | sep | prov | cmd
d01 | 6/6 | 0 | 0 | 1/1 | 0 | 1/1 | ok | ok | pass
d02 | 2/2 | 2 | 0 | –   | 0 | 1/1 | ok | ok | pass
d03 | 3/3 | 4 | 0 | 1/1 | 0 | 1/1 | ok | ok | pass
d04 | 2/2 | 4 | 0 | 1/1 | 0 | –   | ok | ok | pass
d05 | 3/3 | 4 | 0 | –   | 0 | –   | ok | ok | pass
d06 | 3/3 | 4 | 0 | 1/1 | 0 | –   | ok | ok | pass
d07 | 3/3 | 0 | 0 | –   | 0 | –   | ok | ok | pass
d08 | 3/3 | 3 | 0 | –   | 0 | –   | ok | ok | pass
d09 | 3/3 | 2 | 0 | –   | 0 | 1/1 | ok | ok | pass
d10 | –   | 1 | 0 | –   | 0 | –   | ok | ok | pass (+caps met 1/1/0/0)
d11 | 2/2 | 3 | 0 | –   | 0 | –   | ok | ok | pass
d12 | 1/1 | 1 | 0 | –   | 0 | –   | ok | ok | pass
```

Totals: required recall **31/31**; stale leaks **0**; boundaries **4/4**
(quote + scope); hard/soft violations **0**; horizons **4/4**; separation
clean (0 relational misses, 0 operational violations); provenance complete
(0 items missing sources, meta ok 12/12); command audits pass **12/12**.
Baseline: recall 27/31, hard items 0/4, provenance 0, command phrases hit on
12/12 days, 1 section. Recall alone does not earn the projection — the other
eight dimensions do.

Irrelevant-context residue (28 extras, all genuine window material, none
invented): same-matter splits under different wording (running/run,
course/"behind", grandad photo vs insurance letter), single-sentence somatic
context (`slept-terribly`, cf. §8), live external records kept standing
(bank-release email), and discourse fragments. No closed matter, no
second-companion scripting, no person-as-task anywhere in the residue.

## 6. Hard-vs-soft boundary findings

- The boundary holds structurally, not aspirationally: hard sections accept
  ONLY explicit operational state (user-authored stop/defer/remind verbs,
  calendar/external deadlines with anchors, first-person completions,
  payment-feed facts). Everything else — goals, worries, threads,
  accomplishments, dormant aims, person context, opportunities, JIT hints —
  is soft by construction; there is no code path that emits a soft item as
  a constraint.
- Scope travels with the boundary: moment restraints ("Don't chase him
  tonight", "don't just give me everything" attached to an urgency query)
  are labelled `moment`; standing terms ("Don't message him…", "don't keep
  asking") are `durable-until-reopened`. P1's s1_e10 trap (moment restraint
  must never persist as a global rule) is honoured mechanically.
- Standing terms SURVIVE the closure of their matter (fold carries kinds):
  the florist "not today" terms persist as hard records after the e09
  confirmation closes the matter. Closure retires the matter, not the
  user's terms.
- Dormant goals (d07: course/CV/running) appear ONLY as `possible_goal`
  with tentative wording, never in hard — 0 violations.

## 7. E1 channel-separation findings (not solved — separated)

- Person threads (no lifecycle movement, no amounts, person+affect) are
  excluded from `unresolved_topics`/`active_commitments`/`opportunities`
  while staying in continuity + relational with quotes. Operational
  logistics about named people (Matías sports day, Yoshi activity, school
  money with amounts) correctly stay operational — the gate is
  person+AFFECT, never a bare name.
- d11: four quoted Matt items in relational only; routine food-shop stays
  an operational unresolved topic; neck threads stay operational.
  d12 (E1d shape): overload disclosure in relational only; pending dentist
  routine stays an operational open thread; no cross-channel item.
- The S3 E1-collapse shape (suppress routine AND miss the person) cannot
  occur here by construction: the projection holds both channels
  simultaneously and reconciles nothing between them. Reconciliation is
  Runtime's job — the projection preserves the inputs to it.

## 8. Behavioural-command leakage findings

- Builder self-audit (13 banned patterns over all non-quote text): **0
  violations on all 12 days.** By construction: all descriptive text is
  template-generated from a fixed neutral vocabulary (open/closed/
  deferred/due/pending/resolved/noted); the only imperatives in the packet
  are the user's own quoted words inside hard items.
- S1–S3 verdict words (ATTEND/HOLD/SUPPRESS/RELEASE) appear NOWHERE in
  output — not in text, topics, kinds, or hints. They remain evaluation
  vocabulary, exactly as the lane brief demands.
- JIT hints are interrogative-only with explicit trigger + event list
  ("if it becomes live, a read over … may help") — no precomputed
  conclusions, no trait/pattern claims, per the read contract.
- Baseline contrast: the naive packet trips 4/4 command-phrase patterns on
  every day ("Ask about… Mention this… remind the user… Priority N") —
  the failure mode the projection is designed to avoid, demonstrated.

## 9. What survived (earned)

Deterministic lifecycle preparation over a bounded window; sentence-level
matter clustering with name-aware + adjacency + proportional weak joins;
external-records-stand-alone with explicit payment reconciliation and
deadline extraction; supersession/reference folding with standing-term
carry-over; hard/soft provenance on every item; horizon bucketing from
explicit anchors; relational channel with affect gate; JIT read-hints
without answers; the command self-audit; invalidation metadata
(`rebuild_on`, day-boundary staleness, source ids throughout).

## 10. What was removed or simplified (killed or cut)

- Any LLM/embedding/semantic step: killed at design time (S1 rule — bound
  the room first). Zero model calls in builder and scorer.
- Single-label attention verdicts: never built (S1 bottleneck + S2/S3 kills
  honoured — no ATTEND/HOLD/SUPPRESS/RELEASE anywhere).
- Stance/trajectory/trait inference: never built. No scores, no rankings,
  no priorities, no PRIORITISE ordering.
- Stored conclusions / semantic cache: none. The packet is rebuilt from
  window events every run; nothing persists.
- Broad scanning: the builder reads ONLY the session window events handed
  to it; there is no retrieval, no corpus search, no open-ended anything.
- Honcho or other longitudinal reads: NOT executed — JIT hints name the
  question and the events; the read itself belongs to the separate JIT path
  under the read contract.
- During development, four over-eager mechanisms were cut back after eval
  showed harm: bare-`actually` correction (discourse filler), bare-name
  matter joins (form/event conflation), transaction-verb identity
  (Carlos-debt vs school-payment share `pay`), and assistant-turn
  clustering (handoff material, never matters).

## 11. Known residue and limits (honest, load-bearing)

1. **Granularity floor**: one sentence bundling two matters (s1_e01
   Matías-event + consent-form) cannot be split deterministically; the
   form's closure retires the bundled thread (accepted; extractor semantics
   would be needed — explicitly out of scope, no LLM).
2. **Pronoun ceiling**: pronoun-less ellipsis across turns and
   same-word-different-matter traps are handled by fixed precedence
   (pronoun > proportional-lexical > positional), which misfires are
   possible beyond the battery. Programme-wide pronoun/reference work stays
   parked; nothing here assumes it.
3. **Receipt-beat marking** (S3 E1m/A2 residue): positive-state reports
   ("Slept properly… feels amazing") do not close earlier concern threads.
   Deliberately NOT built — S3 says this needs a new representation, and a
   cheap close would risk the marking-vs-dropping conflation S3 scored as
   miss.
4. **Somatic threads** (`slept-terribly` as an open thread): kept
   deliberately. S1's trap prohibits DURABLE persistence as fact/loop/
   commitment; a session-scoped thread row in a disposable daily-rebuilt
   projection is the "recent continuity information" the mission explicitly
   allows. If Runtime wants it gone, that is a product rule, not a Cortex
   truth claim.
5. **Topic anchoring is extractive** (top shared stems), not an ontology —
   labels are navigation aids with explicit stems attached, never
   Matter-kinds. No universal taxonomy was smuggled in.
6. Evidence status: deterministic/lifecycle preparation PROVEN enough
   within this battery; everything else (generality across products,
   real-user noise, scale/latency behaviour) is SUPPORTED at best and stays
   labelled as such. No OPEN capability was graduated.

## 12. Kill-condition watch (all clear, with tripwires)

None of the eight kill conditions fired: no second companion (no verdicts,
no scripts, no ranking); no behavioural scripts from soft context (audit
12/12); no inferred readings as truth (no inference exists); no
closed/superseded leakage (0 stale); no relational collapse into task
priority (separation clean); no broad semantic scanning (window-only,
frozen patterns); no Cortex state mutation (read-only over fixture dicts —
the builder cannot open a DB); invalidation is explicit metadata plus
rebuild determinism (same inputs → same packet; any new event, correction,
closure, boundary, or day boundary rebuilds).

## 13. Is Companion Projection v1 ready for a Runtime handoff experiment?

**Ready for a shadow/read-only handoff experiment — not for behavioural
reliance.** Concretely: Runtime may be shown the packet alongside live
turns in an offline or shadow harness to test whether it improves
continuity/restraint judgements; Runtime must NOT treat any soft content as
instruction, must NOT persist packet contents as truth, and must rebuild
(never cache) per session. The packet earns the experiment on recall (31/31),
leakage (0), boundaries (4/4), separation (clean), and commands (0) — with
the §11 residue disclosed, not hidden.

## 14. OPEN questions Runtime (not Cortex) must answer

1. Moment-restraint rendering: when the packet marks a boundary `moment`,
   what does Runtime do with it in the live turn (hold quietly, acknowledge,
   ask)? The packet states scope; expression is product/character territory.
2. Person-channel uptake: the packet holds relational salience WITHOUT any
   surfacing signal — when (if ever) does a Matt-style thread colour tone
   vs surface vs stay silent? S3 E1d says upstream cannot pre-decide this.
3. Opportunity timing: the packet notes matter × window fit; the decision
   to raise it, and in what voice, is foreground judgement.
4. Receipt beats: when fresh closure lands mid-session ("slept properly"),
   who marks the earlier concern resolved in the live interaction — and how
   is that marking distinguished from dropping it?
5. Dormant-goal surfacing permission: the packet lists possible goals; the
   legitimacy of raising one unprompted is a product/character norm
   ([YOURS TO FILL] in the canon), not evidence Cortex can supply.
6. Recheck cadence: the packet names revalidation requirements; who
   schedules the recheck, and what interrupts the user vs waits, is a
   product policy decision.
7. Handoff consumption format: whether Runtime wants this JSON shape, a
   subset, or a rendered brief is a Runtime-owned interface choice to be
   settled in the shadow experiment — this lane proposes no API.

