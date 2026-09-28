# Longitudinal Companion Cognition Blitz

> Research coordination document. Not a production architecture, implementation
> mandate, schema proposal, or reopening of the graduated operational substrate.
>
> **Relationship to prior work:** the Interpretation Research Blitz
> (`docs/INTERPRETATION_RESEARCH_BLITZ.md`) stands as **completed research**.
> Its findings are inherited here as construction constraints (§8), not
> reopened, superseded, or rewritten. The Phase 0 packet
> (`docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md`) remains a research and
> validation instrument; it is not the architecture of this programme.
> Synthesis V2 (`docs/INTERPRETATION_RESEARCH_SYNTHESIS_V2.md`) remains the
> record of what the interpretation blitz did and did not establish.
>
> **What this programme adds:** the interpretation blitz narrowed the mechanics
> of generic interpretation and killed several universal abstractions. This
> programme returns those findings to the original companion-level question:
> durable person/relationship understanding plus moment-level participation.

## Status and baseline

The Operational Longitudinal Cognition Substrate is graduated (baselines:
Cortex `9aadba5`, runtime `00e8364`, closeout/docs `1d55e86`). Nothing here
authorises changes to production code, schema, runtime semantics, live
prompts, or deployed behaviour. No track may create a production service,
migrate data, or wire a production path. Experiments remain offline, bounded,
removable, and clearly labelled as research.

Constitutional grounding: `docs/COMPANION_CANON.md` (objectives, principles,
failure modes, non-decisions) and `docs/COMPANION_NORTH_STAR.md` (product
ambition and magic standard). Per the canon's decision hierarchy, this
document and any agent-drafted proposal inside it are hypotheses and
experiment designs; objectives and principles change only by the programme
owner's hand, on evidence.

## 1. Objective (ratified programme direction)

**Understand the person increasingly well over time, help them move toward
the life, values and goals they choose, notice when their trajectory may be
diverging from those intentions, and support reflection and action without
taking authorship of their life away from them.**

This is direction, not a licence for the system to define what "better" means
on the user's behalf. "Better" is authored by the user's own values,
commitments, and chosen directions. The system may hold tensions between
stated values and observed behaviour; it must **never claim privileged access
to the user's "true" values**. Noticing contradiction is care; resolving it
against the user is paternalism.

## 2. Load-bearing separation (programme invariant)

**Understanding ≠ current relevance ≠ behaviour.**

- A durable understanding may be irrelevant right now.
- Something relevant now may only alter orientation.
- Orientation may influence judgement without becoming an instruction or an
  utterance.

This is the semantic analogue of the canon's structural invariant:

**Persistence ≠ attention ≠ execution** (`COMPANION_CANON.md` principle 14:
durable truth, live activation, attention, and action authority are separate;
a matter can remain true while deserving neither attention nor action).

Every track in this programme must preserve all three gaps. Any proposal that
collapses them — understanding auto-surfacing, relevance auto-instructing,
orientation auto-uttering — fails whatever its diagram says.

Core programme rule (S1→S2 evidence): **do not ask intelligence to
discover relevance from an unbounded life stream. First bound the decision
surface (deterministic candidates, eligibility facts, triggers); then use
intelligence only on the residue.** S1 at 40–59% false-steer vs S2 at
0–8.3% once candidates were bounded is the result that earns this rule:
the noise problem was room size, not model nature.

## 3. Epistemic dimensions (P0 reconciliation)

P0 (`reports/track_p_p0_separability_2026-09-28.md`) killed the original
tier ladder as a single truth hierarchy: judges can separate authored from
observed and policy-vetoes reliably, but **cannot** separate person-level
derived from relational from product-local on the interesting cases. The
ladder below is therefore replaced by four independent dimensions. Nothing
is a "level of truth."

- **SOURCE / PROVENANCE** — where it came from: user-authored statement,
  observed external event, system action/receipt, product-derived signal.
- **READING** — the inferred meaning, pattern, or trajectory. All inference
  lives here, however often repeated.
- **EPISTEMIC STATUS** — confidence + basis + contradiction + recheck. Always
  revisable and scoped for derived content.
- **SCOPE / OWNER** — who may use it and where it applies: shared-person,
  shared-relationship, Bloom, RPD2, Sophie, etc. Scope is a tag on every
  derived understanding, never prose implication.

**Authored ≠ true.** Authorship establishes provenance and authority over
self-description, preferences, and boundaries — not automatic verification of
external-world claims. "Carlos still owes £2,100" tells us who asserted it;
only independent evidence (bank rows, receipts, invoices) settles whether it
holds. Authorship earns ready persistence of *what the user said*; it confers
no epistemic privilege about world state (canon principle 11: evidence,
reading, and confidence are three separate things).

**Relational learning** is derived understanding about user ↔ companion
interaction (what appeared to help, backfire, repair, deepen, frustrate),
kept visible as its own research subtype with obligatory
strategy + consequence + recheck lineage. It is not a separate persistence
primitive and never causal certainty from one receipt.

**Lifecycle stays operational.** "Paid," "cancelled," "deferred," "resolved,"
"changed mind" are lifecycle/receipt states owned by Cortex operational
state, not confidence states of a reading. The meaning layer reads
lifecycle; it does not recreate it in prose.

**Do not let repetition launder inference into fact.** This is the canon's
"uncertainty laundering" failure mode: frequency is not authority.
"Morning exercise stabilises him" and "approach X works for this person" are
derived however often repeated.

Promotion rules (evidence-based, no exceptions by feel):

- Authored-equivalent authority requires explicit user confirmation.
- Repeated occurrence alone is insufficient for any promotion.
- Stronger derived confidence may come from independent evidence paths,
  surviving rechecks, explicit correction/confirmation, and consistent
  outcomes.
- Relational learning requires repeated or strongly diagnostic consequences
  in comparable contexts and remains revisable. ("Strongly diagnostic" from
  a single consequence stays contested, not durable — see P0 ambiguous
  case 1.)
- Correlated or duplicated evidence must not count as independent
  corroboration.
- Confidence upgrades never imply surfacing permission: well-evidenced and
  durable can mean *never surface* (understanding ≠ relevance ≠ behaviour).

## 4. Target picture (hypothesis, not mandate)

```text
EVIDENCE SUBSTRATE (Cortex — factual, provenanced, graduated; owns lifecycle)
  authored claims / corrections / boundaries / receipts / closures
        ↓
CANDIDATE GENERATORS (two nomination paths, never open scans)
  A. OPERATIONAL NOMINATION (deterministic + product systems):
     deadlines / meetings / open loops / reminders / completions /
     opportunities / unresolved commitments
  B. SEMANTIC NOMINATION (longitudinal reads over history, §4 notes)
        ↓
ATTENTION CANDIDATES (bounded room: eligible matters + context)
        ↓
LLM ATTENTION ARBITER (triggers first; judgement over the room)
  HOLD / SUPPRESS / RELEASE / ATTEND (maybe PRIORITISE)
  eligible ≠ relevant now ≠ surface now
        ↓
PRODUCT LENS (domain expertise reads the arbitration + evidence)
        ↓
FOREGROUND TURN (chooses, expresses, acts/withholds — never puppeted)
        ↓
RECEIPTS + CONSEQUENCES → evidence; candidate learnings upward (gated, §5)
```

Notes:

- The product lens participates **before/during** moment interpretation, not
  only after it: the same shared understanding plus the same new evidence can
  mean different things through different expertise.
- The product lens also contributes **back upward**: domain-local readings may
  become candidate shared learnings, promoted only through Track P rules (§5).
- Steering modulates attention and latitude; it never rewrites character
  constitution (curation is lighting, not recasting).
- **Signals may be query-generated rather than event-extracted.** Many
  signals that matter do not exist inside any one event; they emerge from a
  read across history ("when feeling controlled, disengages"). The system
  therefore distinguishes event-local extraction (Cortex: user said X, task
  completed, boundary set — stable evidence) from **longitudinal reads**:
  a scoped question asked over the relevant history ("how do reminders land
  for this person? what is unresolved? where do stated goals and behaviour
  diverge?"), answered as an ephemeral interpretation, then validated by
  **evidence recruitment** (support, counterexamples, scope checks,
  same-episode dedup, user contradiction, supersession by newer evidence).
  Reads are recomputable from new angles; they are not trait records.
- P1 verdict recorded: **0/8 derived candidates earned durable shared
  persistence** (`reports/track_p_p1_loss_analysis_2026-09-28.md`, commit
  `1ce11ee`). What persists for years is authored + receipts + operational
  lifecycle; inference reconstructs on demand. This kills semantic
  authority-by-persistence, not efficiency caching: **revisable derived
  views may be materialised for retrieval/latency reasons** without becoming
  source-of-truth (cheap to regenerate, expiring, invalidated by recheck,
  contradiction, or correction).

## 5. Product lens boundary (bidirectional, gated)

Products **consume** the shared person/relationship model. Products may also
**propose** candidate shared learnings from domain-specific interpretation,
but they **cannot directly promote** them into shared truth.

Example:

- Bloom-local: "this pattern may reflect training overload."
- Possible shared candidate after validation: "when highly invested in a
  goal, the user may continue pushing despite recovery signals."

Promotion upward requires evidence, recheck survival, or user confirmation
under Track P rules (§3, §6). Domain expertise stays product-local unless the
cross-domain residue genuinely earns shared status. Character/relationship
content (e.g. RPD2 expectations, repair sufficiency) never auto-transfers
across frames: Kai→Yelena is not user→product.

**Scope promotion is an explicit, evidence-gated operation**
(`product-local → candidate → shared-person/shared-relationship`), recorded
with the evidence that justified it. A derived understanding cannot silently
escape its scope: breadth of prose is not promotion, and no reading becomes
shared merely because a model worded it generally.

## 6. Track P — Person & Relationship Model

**Research question (not "what can we store?"):**

**What understanding, if lost across products or after six months, would
materially degrade the companion's ability to understand and help this
person?**

Loss-analysis against that criterion — beating an evidence + receipts +
user-authored-profile baseline — is what earns persistence. "Looks
meaningful" earns nothing.

Preserve throughout the distinction between source, reading, epistemic
status, and scope/owner (§3) — not a six-column tier taxonomy. In
particular: factual evidence, user-authored self-understanding, derived
person-level understanding, relational learning (visible subtype, §3),
product/domain interpretation, and policy are separate dimensions, and
lifecycle is operational, not semantic.

**P0 — Separability. COMPLETE.**
Report: `reports/track_p_p0_separability_2026-09-28.md`. Findings applied:
tier ladder killed (§3 above); relational learning collapsed to derived +
strategy/consequence/recheck lineage with research visibility retained;
product interpretation collapsed to product-local reasoning + gated candidacy;
policy moved to the orthogonal truth/attention/action axis; lifecycle
confirmed operational. P0's load-bearing distinctions (evidence vs
interpretation vs confidence; boundary dominance; advisory-only
interpretation; transient vs durable with expiry + recheck; reading-relative
relations; transform-below-interpretation; scope tags) are carried forward.
P0's "two durable kinds + one ephemeral kind" is a candidate compression,
not architecture — P1 tests it, does not assume it.

**P1 — Loss analysis. COMPLETE.**
Report: `reports/track_p_p1_loss_analysis_2026-09-28.md`
(commit `1ce11ee`). Frozen battery C1–C8 with real control-arm
reconstructions 8/8 and strict independence counting (same-trajectory
repeats ≠ independent). **Result: 0/8 derived candidates earn durable
shared persistence.** Authored corrections/standing/boundaries persist as
authored (≥2 instances, scope + expiry preserved; moment-restraint never
globalised). C3 (RPD2 repair) and C6 (Bloom co-occurrence) survive only as
product-local contested-ephemeral with second-instance retest conditions.
C5 (Monday-subdued) is the deliberate-forgetting prototype: true,
well-evidenced, never-surface, surveillance-costly — dropped even backstage.
C7 promotion refused (scope escape + laundering). Claims capped at
SUPPORTED (reasoning experiment, pending-file dependencies as-present, no
blind bakeoff — P2 owns reliability). P2 stays narrow per P1 §7: C3/C6
retests only with second independent instances, blind precision, kill
clauses for boundary/paternalism/scope-escape/laundering failures; no
C5, no C7-shared, no C2-shared, no durable shared-derived store.

**P2 — Construction reliability.** Blinded emission of tiered entries from
frozen evidence, Track A replication methodology (frozen prompts, sealed
oracle, disagreement analysis, raw counts). Headline metric: precision on
inferred tensions/trajectories — a fabricated "stuck trajectory" is the
failure that matters, not recall. Tier-confusion (derived stated as
observed) is scored as failure. Kill condition: pre-registered fabrication or
tier-confusion rate above bar kills the inferred tier while leaving
authored/observed intact.

**P3 — Harm clearance.** Correctability without dossier: every derived
understanding inspectable, challengeable, supersedable, removable when
surfaced or requested — with no assumption of a user-facing dashboard per
inference (no creepy settings rows; product owns any eventual "what I
understand about you" surface). Probes: cross-frame leakage, surveillance
texture on well-evidenced never-surface patterns, over-governance (does the
layer deny the foreground its chance?), user-endorsement rendering. Gates any
persistence.

**Trajectory rule (central):** trajectory is revisable/supersedable derived
understanding grounded in stable historical evidence. Supersede readings;
never rewrite history to fit the latest interpretation. Intervention logs are
derived state: what was assumed, injected, hidden — attributed, timestamped,
recoverable.

## 7. Track S — Moment significance / steering

**Core question:**

**Can side cognition recognise what deserves attention now from the
combination of operational pressure, trajectory relevance, current context,
situational opportunity, suppression signals, and longitudinal
person/relationship understanding — while outperforming cheap
deterministic/explicit-signal baselines without excessive false-positive
steering?**

Moment significance is not trajectory-change detection alone. It includes
current situational affordance: an open dentist task with no new trajectory
evidence may become surface-worthy the moment the user has 40 free minutes;
an important gym goal may demand suppression on receipt of upsetting family
news or a severely overloaded day. No new trajectory evidence need exist in
either case.

The hybrid boundary (not a formula, not an ontology — context inputs such
as calendar, time, load, weather are examples, never mandatory universal
primitives):

- deterministic/operational machinery establishes facts and eligibility:
  deadlines, meetings, recurrence, completion, prior reminders, calendar
  load, current time, external/context signals where available;
- longitudinal person/relationship understanding supplies importance,
  preferences, goals, previous receipts, what tends to help or backfire;
- side cognition exercises LLM judgement over the current moment:
  relevance, opportunity, competing demands, timing, suppression, and
  attentional latitude;
- foreground/product retains behavioural and expression authority.

Preserved throughout: **eligible ≠ relevant now ≠ surface now.** An owed,
uncompleted matter is eligible; only the moment decides relevance; only
relevance plus legitimacy decides surfacing. Suppression on contextual
grounds (grief, overload, closed topics) is a first-class correct output,
scored alongside timely surfacing.

Rupture/frustration is one subclass, not the organising purpose. The loop
serves significance, opportunity, deepening, and timely silence at least as
much as repair.

**Replay battery (frozen, shared where useful with Track P):** rupture and
friction; successful repair; circling; deepening; remembered goals; missed
opportunities; celebration and accomplishment; humour and shared repertoire;
changed mind; gradual personal change; correct silence; unwanted probing;
successful challenge; situational opportunity (open matter meets a newly
available window, e.g. free time appearing — SHP-5); suppression-by-context
(important matter correctly withheld under grief, overload, or bad timing);
frame/boundary cross-cutting (diegetic vs extradiegetic vs boundary —
S0 R-14; scope-leakage control for every steering output); mundane turns
where nothing should happen. RPD2 is a
wind tunnel, not the aircraft: rupture-rich data must not optimise the whole
system around repair. These categories are **evaluation coverage, not runtime
ontology**: no proposal may turn battery labels (including any `SHP-*`
shape identifiers) into production classifier outputs or state labels merely
because the battery uses them.

**S0 — Candidate interfaces and trigger shapes. COMPLETE.**
Report: `reports/track_s_s0_significance_shapes_2026-09-28.md`
(commit `bac8c274`). Findings applied: frozen shape inventory SHP-1..SHP-14
adopted as the evaluation-coverage battery (shapes are temporal + evidential
+ relational structures, never runtime classifier labels or state — the
`SHP-*` prohibition in §7 stands); three S2 interface arms confirmed
(named stance as underdog, structured orientation brief, compact NL
orientation, plus raw-turns control) with annotate-first vs replacement and
a suppression-only variant as orthogonal S2 choices; per-shape suppression
conditions and failure modes carried into S1/S2 judging; blind-judging
dimensions (continuity-without-nagging, restraint/timing, repair yield,
deepening, character fidelity, non-puppeteering/foreground-room,
abstention precision) reserved for S2. Corrections applied back to this
document: "stance-rung" demoted as organising noun (neutral term is
*orientation* until S2 evidence lands — see diagram, §9, S3 below);
jargon trigger starter list replaced by the frozen shape inventory, each
shape defined by observable evidence + recheck; rung discipline made
arm-agnostic. Two notes: S0 §4's reservation of "whether to act at all"
entirely to foreground is superseded by §10's attentional-powers boundary
(strong hold/attend/avoid recommendations permitted; move authorship
forbidden); S0 §8.7 (no persistent intervention log as infrastructure
before S4) is adopted as discipline. No canonical stance list. SHP-5
(remembered goal + current context has room) is the programme's
situational-affordance carrier.

**S1 — Significance calibration. COMPLETE.**
Report: `reports/track_s_s1_significance_2026-09-28.md`
(commit `5fc8cbe`). Frozen 69-window battery (47 real + 22 synth,
manifest sha `bbd1ca21`), three arms (deterministic cheap triggers,
restraint-prior LLM, opportunity-prior LLM), pre-registered bar.
**Verdict: FAIL on frozen numbers, all arms.** Detector recall ties cheap
explicit triggers on user-marked moments (24/29 both) and loses on the open
arm; all arms including the cheap baseline exceed the 10% false-steer
budget by multiples (cheap 45.5%, strict 40.9%, open 59.1%; repaired
27.3%/50% — still failing); rupture recall 1/3 everywhere; humour and
successful-challenge have zero real-data windows. **Killed:** general LLM
moment discovery beating cheap triggers; opportunity-prior operating
point; restraint-prior rupture detection. **Supported (representation, not
reliability):** the hold/suppress/release vocabulary carries decision
value cheap triggers structurally lack (strict +7 entirely from HOLD +6 /
SUPPRESS +1: Lucy withhold, neck restraint, never-surface Monday,
changed-mind releases, boundary honoured) — currently drowned in
over-attending noise (attend on 14/20 HOLD windows). Prescribed for S2:
compare interfaces on hold/suppress/release quality with a trigger-only
control; per-matter judgments (single-label verdicts conflate
attend-to-person with suppress-routine); authority-annotated person notes
supplied, not invented; reconciliation-before-surfacing gate; repaired CF
scanner and mark-release class; no humour/challenge interfaces without
real-data batteries; operating points meet the bar blind, never by
post-hoc retuning.

**S2 — Attention arbitration over bounded candidates. COMPLETE.**
Report: `reports/track_s_s2_arbitration_2026-09-28.md`
(commit `cb8e0f8`). 30 frozen cases / 84 per-matter verdicts, five arms
(trigger-only control, structured brief, suppression-only, NL orientation,
named stance), arm-blind judging with audited leniency. **Verdict: FAIL
for arbitration-as-replacement.** Control 67/84 beats brief 60/84
deterministic (judge +5 for brief sits inside audited leniency/noise);
all verdict arms inside the FP budget here (control 0%, brief 8.3%,
supponly 0%) — bounded candidates fixed S1's FP blowup, leaving recall
of the judgement-shaped residue as the gap. **Killed:** named-stance
interface (K-b fires: 22 wrong vs brief 7; K-c supported; 1 format
failure); suppression-only as standalone arbiter (0/15 ATTEND);
NL as arbitration record (29/84 unclear); generic priority ranking
(undemonstrated). **Supported:** per-matter verdicts as the validatable
unit; hold/suppress/release vocabulary where triggers structurally lack
it. Control misses (17) are exactly the judgement-shaped residue
(receipt beats, named injury, accomplishment marking, restraint-scope).
E1-class heavy-context receipt-beat cases defeat ALL arms — needs a
dedicated family before any suppression claim there. Prescribed:
triggers-first substrate + suppression-posture default + strictly-gated
brief exception tier. Programme direction adopted: **LLM by exception,
not by default** — deterministic default + contextual exception
judgement = current attention posture.

**S3 — Exception-tier test (narrowed per S2 §9.3).** Test ONLY whether
brief-format arbitration gated to flagged judgement-shaped cases recovers
those exact control-miss classes: dormant-goal affordance (F3-class),
named-injury attention-with-pursuit-suppressed (Z3-class), restraint-scope
answers (B2/florist-class), receipt beats (E1/matt-class) — plus the
**mandatory E1 heavy-context dual-judgement family**: suppress the routine
candidate while simultaneously recognising the person may deserve
attention (per-task SUPPRESS + relational ATTEND are different outputs;
warm-packet task lists with suppression metadata alone would lose the
second). Bar, brutal and pre-registered: recover those classes at FP 0%
on all-held controls, or kill the exception tier too and run deterministic
triggers/context rules until better evidence exists. Full launch contract:
`docs/TRACK_S_S3_LAUNCH_CONTRACT.md`.

**S3 — Rung and authority discipline (arm-agnostic).** Orientation brief
or compact NL orientation by default; named stance is one S2 candidate,
not the presumption. Directives only under explicit invitation, hard
safety, or separately justified authority; script basically never. Rung
chosen by uncertainty × stakes. Steering delivers structure +
options, never moves to perform; repair steering must clear the "performed
chase" bar (chosenness available: waiting held as a live candidate).

**Honcho longitudinal-QA probe (gates semantic nomination).** Semantic
nomination (diagram path B) depends on an untested capability claim: that
a Honcho-like semantic query layer answers bounded longitudinal questions
faithfully. Probe contract: `docs/HONCHO_PROBE_LAUNCH_CONTRACT.md`
(interrogative-only questions; recruitment discipline scored per read;
pre-registered usability bar). **First run COMPLETE, capability still
OPEN.** Report: `reports/honcho_longitudinal_qa_probe_2026-09-28.md`
(commit `85942ef`): local workspaces contain no usable longitudinal data
(PROVEN, 4 workspaces enumerated); `conclusions/query` 422s on
schema-valid bodies (PROVEN — file upstream); stored deductive conclusions
overstate thin chatter (caution for any reliance). Fallback arm:
retrieval-only 2/10 vs retrieval + recruited synthesis 10/10 with zero
fabrication/missed-corrections/leaks (SUPPORTED, author-performed cap —
validates the recruitment contract, not a pipeline). Rerun prescribed:
isolated probe workspace (fixture ingestion, never production or
real-user mining without explicit consent rules) + fixed query endpoint +
frozen F1–F10 blind. VPS hosts a live Honcho stack (api/postgres/deriver
containers present; access verified read-only) — rerun agent may target it
with owner authorisation under the probe contract's privacy rules.
Fallback if unusable: retrieval + model synthesis over Cortex evidence
under the same recruitment contract. Stored Honcho conclusions are NOT
trusted semantic state (probe: deductive conclusions drawn from single
throwaway remarks) — at most retrieval hints until separately validated,
and explicitly excluded from any scored semantic-read path. Data posture
for the rerun: the operator is the sole user and the VPS histories are
deliberate test data, so the constraint is methodological cleanliness
(frozen corpus, isolated probe workspace preferred, no contamination of
the scored path), not privacy theatre. P2 stays narrow per P1 §7 and runs
separate from both tracks.

**S4 — Repair and follow-up loop.** Intervention log format; session-level
judging on pre-registered observable criteria (not vibes); follow-up
candidates re-authorised against live state at send time, never merely
scheduled (earlier truth ≠ present permission; product policy owns cadence).

## 8. Inherited construction constraints (from the completed Interpretation Blitz — not reopened)

- Abstention / no-packet is success; "no conclusion supported" is legitimate.
- No universal Matter ontology; bounded optional subject references only.
- No shared expectation state machine; expectations product-scoped, optional.
- No numeric certainty, score averaging, or convergence scores.
- No universal emotion/domain taxonomy in shared machinery.
- No durable-by-default interpretation; expiry + recheck discipline.
- Interpretation does not command behaviour; advisory-only, guardrailed.
- Explicit boundaries and user correction dominate inferred strategy.
- Packet validity does not imply semantic correctness.
- Models may legitimately refuse conclusions the evidence cannot establish;
  never punish honest holds or abstentions.

The Phase 0 packet shape is available as research/validation machinery
(validators, blind-judging harness, ABSTAIN scoring). It is not the new
architecture and must not be forced into that role.

## 9. Steering interface candidates (experimental, S2 decides; S0 §2)

1. Named stance (e.g. hold, curiosity, lead, repair-readiness —
   product-constituted, never canonical; underdog — S2 tests whether it
   can be killed).
2. Structured orientation brief (salient / unresolved / relational posture /
   avoid / latitude + recheck + abstain-reason; ≤5 lines, ≤3 items).
3. Compact natural-language orientation (1–2 sentences of trajectory-aware
   context).

Plus a raw-turns control (no side cognition — every arm must earn its keep
against evidence + receipts). Orthogonal S2 choices: annotate-first vs
compressed replacement (replacement must win cleanly); suppression-only
variant (only `avoid` / hold-quietly populated).

Every candidate carries its suppression condition and characteristic failure
(hijack↔heavy moments/boundaries; curiosity↔interrogation; lead↔dragging;
repair-readiness↔performed pursuit). Stances modulate attention and salience,
never rewrite constitution. Moves must ground in actual conversation, never
invented openings; reasoning runs through character judgement, not generic
judges with voice applied after.

## 10. Authority (preserved)

- Side proposes; foreground disposes; user overrules; evidence/log remembers.
- Product/runtime policy retains authority over action, tools, escalation,
  pursuit/restraint, and foreground behaviour.
- Side cognition may use attentional powers — `attend`, `hold`, `suppress`,
  `surface-as-candidate`, `narrow-latitude` — including strong
  recommendations to hold, attend, or avoid. It must not author behavioural
  moves — `say`, `ask`, `apologise`, `pursue` — nor override product/safety
  authority. Foreground keeps final expressive choice; a shape that strongly
  favours restraint constrains latitude instead of scripting silence.
- Scripts basically never; directives only under explicit invitation, hard
  safety, or another separately justified authority path.
- Silence/hold is always available, with recheck and expiry; unanswered
  outreach caps repetition rather than licensing it.
- Follow-up is re-authorised against current state at send time.
- Trajectory edits are contested supersessions, logged and recoverable —
  never silent replacement.

## 11. Replay and experiment discipline

Frozen inputs with manifests and provenance; blinded comparisons where
judgement is scored; negative controls for every attractive capability
(including mundane nothing-should-happen turns and user-closed topics with
continuing evidence); raw counts and failure classes reported, never bare
aggregate scores; graduate / narrow / kill decisions per tier and per
interface. No production schemas or runtime mechanisms until a track's gate
criteria are met and the graduated substrate's owners agree. Per canon
principle 16, anything that has not earned its keep is removed or absorbed,
not accumulated.

## 12. Open decisions (explicitly NOT decided here)

Whether trajectory resolves to one object or per-product views; exact
monitor trigger mechanism (on-due query vs ambient intersect); the winning
steering interface; session-close durability owner; watch-list
implementation; timers and cadence values; which product goes first in
shadow mode; any user-facing surface for shared understanding
(product-owned, later). Open research questions, not decisions: whether
cached derived views materially improve retrieval/latency/quality over
reconstruction at realistic history scale (systems experiment, with
invalidation rules — never a semantic-persistence claim); whether a
Honcho-like semantic query capability answers longitudinal questions
faithfully with citations and counterexamples (probe before relying);
one trajectory object vs per-product views (P1 evidence favours
per-product + thin shared transport, not canonised). Next architecture
artifact when evidence justifies it: warm projection / companion packet
spec (what is prepared at what horizons, what is deterministic, what is
cached with what invalidation, what is JIT-only, how runtime requests
missing context — the packet is a projection, never truth). Numeric promotion
thresholds follow evidence, not preference.
