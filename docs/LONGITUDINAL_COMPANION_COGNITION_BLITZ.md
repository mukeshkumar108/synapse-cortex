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
        ↓
SHARED LONGITUDINAL MODEL (Track P — person + relationship, revisable)
  source/provenance × reading × epistemic status × scope/owner (§3)
        ↓
CURRENT EVIDENCE → PRODUCT LENS (domain expertise: health, relational,
  symbolic, operational, educational)
        ↓
MOMENT INTERPRETATION (what does this moment mean in the larger trajectory?)
        ↓
STEERING / ORIENTATION (Track S — ephemeral, advisory, stance-rung)
        ↓
PRODUCT POLICY + PERSONA (voice, allowances, judgement — product-owned)
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

**P1 — Loss analysis.** Replay battery (shared with Track S where useful):
for each candidate, what future turn or cross-product handoff degrades
without it? Rank by decision-effect. Only the residue past the
evidence+receipts+profile baseline earns inferred persistence. Likely
retained: explicit long-term goals, deeply meaningful aims, repeated
corrections of system behaviour. Likely not: transient affect, single
readings, raw metric values. Interesting candidates (e.g. "when feeling
controlled, disengages even when agreeing") require evidence, revision, and
correction pathways. P1 runs a real control arm attempting to recover
future-turn quality from operational evidence + receipts + authored user
knowledge + product-local context **without** the candidate derived
understanding; where the baseline recovers cheaply and reliably,
persistence loses. Battery includes relational-learning cases alongside
person-understanding cases, and the Alchemist resonance specimen
(authored favourite + observed reception + derived quest-metaphor resonance
rule with literalness boundary) as a cross-product promotion-path case.
Full launch contract: `docs/TRACK_P_P1_LAUNCH_CONTRACT.md`.

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
available window, e.g. free time appearing); suppression-by-context
(important matter correctly withheld under grief, overload, or bad timing);
mundane turns where nothing should happen. RPD2 is a
wind tunnel, not the aircraft: rupture-rich data must not optimise the whole
system around repair. These categories are **evaluation coverage, not runtime
ontology**: no proposal may turn battery labels (including any `SHP-*`
shape identifiers) into production classifier outputs or state labels merely
because the battery uses them.

**S0 — Candidate interfaces and trigger shapes. REPORT PENDING CANONICAL
LANDING.** The battery categories above and trigger shapes below stand as
the programme's planned evaluation coverage. S0's frozen shape inventory
and interface analysis must be landed canonically before S1 cites them;
until then S1 builds its manifest from the categories in this section and
committed fixtures only (see `docs/TRACK_S_S1_LAUNCH_CONTRACT.md`).
Candidate steering interfaces (§9) and meaningful trigger shapes
(asymmetric conversational debt + energy + open expectation; circling
structure; user frustration markers; accomplishment moments; recheck firing).
No canonical stance list. Output: frozen trigger/shape inventory plus the
frozen replay battery.

**S1 — Significance calibration.** Sliding-window runs over the frozen
battery, with operational/context inputs (deadlines, due items, calendar
load, time, prior reminders, available context signals) supplied as
deterministic facts alongside trajectory and person-model content. Primary
metric: precision/recall on user-marked frustration and
missed/deepened moments, plus opportunity-timing hits (right matter at a
genuinely affording moment) and correct suppressions (withheld under
grief/overload/closure); explicit user signals ("you're not understanding
me") are ground truth against which classifier ambition is measured. S1
does not classify every battery shape: it must beat cheap
deterministic/explicit-signal baselines (explicit correction/frustration,
explicit boundary, due/open commitment, deadline/recurrence facts, explicit
completion or change-of-mind, ABSTAIN) without unacceptable false-positive
steering, inside a pre-registered false-positive budget. If the LLM
judgement cannot beat deterministic/explicit triggers, ship the triggers.
Kill condition: false-positive rate that would produce rupture tunnel vision
(every turn damage-managed) fails the loop regardless of recall; symmetric
failure is chronic suppression of genuinely affording moments. Full launch
contract: `docs/TRACK_S_S1_LAUNCH_CONTRACT.md`.

**S2 — Interface comparison, blind-judged.** Same frozen sessions, at least
three arms: (1) named stance; (2) structured orientation brief (salient /
unresolved / relational posture / avoid / latitude); (3) compact
natural-language orientation — plus a raw-turns control. Judge downstream
trajectory on receipts-observables (resumed substance, user correction,
disengagement, repair yield, deepening). **The experiment may kill the stance
taxonomy entirely.** Also tested inside S2: annotate-first (keep turns, add
orientation) vs compressed replacement (logged, recoverable, attributed);
replacement must win cleanly to survive given its laundering risk.

**S3 — Rung discipline.** Stance by default; directive only under explicit
invitation, hard safety, or separately justified authority; script basically
never. Rung chosen by uncertainty × stakes. Steering delivers structure +
options, never moves to perform; repair steering must clear the "performed
chase" bar (chosenness available: waiting held as a live candidate).

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

## 9. Steering interface candidates (experimental, S2 decides)

1. Named stance (e.g. lead, hijack, curiosity, hold, repair-readiness —
   product-constituted, never canonical).
2. Structured orientation brief (salient / unresolved / relational posture /
   avoid / latitude).
3. Compact natural-language orientation.

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
(product-owned, later); S0's canonical shape inventory (report pending
landing — §7). Numeric promotion thresholds follow P1/S1 evidence, not preference.
