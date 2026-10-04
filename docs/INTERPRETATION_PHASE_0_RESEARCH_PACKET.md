# Interpretation / Meaning — Phase 0 research packet

**Status:** offline representation experiment; no production semantics, schema,
runtime, prompts, or tables changed.

**Baseline inspected:** Cortex graduated baseline `9aadba5`, runtime baseline
`00e8364`, closeout/docs baseline `1d55e86`; current Cortex checkout was
`434ec01` on `main`. The worktree already contained unrelated changes, which
this tranche did not edit.

**Experiment:** nine provenance-labelled trajectories in
`evals/interpretation_phase0/cases.json`, validated by an isolated standard
library runner. Sophie and RPD2 cases cite frozen historical replay artefacts;
Bloom, worldview, and astrology-shaped cases are explicitly synthetic. This is
a representation test, not an extraction/model-quality test: hypotheses were
curated from the evidence. It demonstrates that a compact packet can preserve
meaning needed by bounded decisions; it does not demonstrate that a model can
reliably produce those packets.

**Result:** the sidecar changed the expected bounded decision in 9/9 cases.
That is directional evidence for the representation. It is not a performance
score, because the fixtures and expected decisions were authored together and
there is no blind judge.

## 1. What the current substrate already solves

Do not rebuild these capabilities in an interpretation layer:

- canonical raw evidence with provenance back to messages/spans/models;
- durable longitudinal identity across temporal session boundaries;
- bounded, retryable reconstruction with honest packing and semantic coverage;
- legal lifecycle transitions for expectations, loops, commitments,
  recurrences, and suppressions;
- ranked attention with pressure, fatigue, suppression dominance, and HOLD;
- action/withholding separation, delivery receipts, and version fencing;
- reaction outcomes that alter later attention (answered, ignored, dismissed,
  deferred, resolved), including revival by new evidence;
- isolation and idempotency.

The sidecar consumes evidence/state and emits interpretation. It must not become
a second evidence store, lifecycle engine, attention ranker, or action authority.

## 2. What information is currently lost

Concrete losses found in the selected trajectories:

- **Dentist:** repeated mentions and later elliptical commands are stored as
  multiple rows; the proposition “these utterances revise one intention” is
  absent.
- **Meeting:** add, move, and cancel facts survive, but “move/cancel transforms
  this event rather than creates another obligation” does not.
- **RPD2:** the opening scene is available, yet replay produced no durable
  representation of the injury: coldness/non-recognition and transfer of repair
  labour to the injured party. It also could not retain that “give space” was a
  tried strategy whose observed consequence was experienced abandonment.
- **Bloom baseline shift:** independent changes survive, but their convergence,
  competing explanations, and evidence that narrows them do not.
- **Bloom non-adherence:** misses are visible; the distinction among lost
  motivation, forgetfulness, burden, and environmental friction is not.
- **Bloom recovery:** observations survive independently; partial improvement
  followed by recurrence is not itself represented as trajectory meaning.
- **Transient affect:** a curt turn can harden into durable state because
  “temporary depleted bandwidth, contradicted by continued initiation” has no
  home.
- **Worldview:** `favourite_book = The Alchemist` loses what the user said they
  value, where a metaphor landed, and where applicability narrowed.
- **Oracle-shaped plurality:** a scalar can say neutral while losing two
  supporting public-work signals, one execution qualifier, and a separate
  private-life theme.

## 3. Minimum interpretation packet

The smallest representation that survived all nine cases is:

1. **Matter identity claim** — a short description of the evolving referent,
   product/domain scope, and evidence references. It is a hypothesis-bearing
   anchor, not a canonical entity or new row type.
2. **Hypothesis** — a falsifiable proposition plus product scope.
3. **Typed evidence relations** — references divided into `supports`,
   `qualifies`, and `contradicts`. Evidence is not copied or rewritten.
4. **Confidence** — only `low | medium | high`, always accompanied by a prose
   basis explaining independence, directness, and missing evidence. It is not
   derived by arithmetic.
5. **Revision state** — `live | contested | superseded`. Superseded readings
   remain inspectable rather than disappearing.
6. **Persistence bound plus recheck condition** — `turn | session |
   until_condition | durable`, and the concrete evidence that should reopen or
   revise the reading.
7. **Bounded implication plus guardrail** — one decision/posture consequence,
   explicitly constrained. This is advisory projection, never action authority.

No actor objects, claim nodes, sub-matter trees, numeric weights, free-standing
salience, or generic relationship edges were needed.

## 4. What failed or was unnecessary

- **Arbitrary scalar soup:** confidence, salience, persistence, urgency, valence,
  and impact as numbers encouraged fake precision and did not explain a decision.
- **Score averaging:** erased qualification and unrelated simultaneous domains.
- **Generic graph shape:** subject-predicate-object edges could encode every
  case but did not say which distinctions mattered downstream.
- **Emotion ontology:** labels such as hurt/angry/withdrawn were less useful than
  the concrete violated expectation and observed consequence. They also risked
  pretending access to internal state.
- **Universal lifecycle:** cancelled meeting, recurring symptom, relational
  injury, and interpretive theme do not share one honest state machine.
- **Durable-by-default hypotheses:** made transient affect and speculative
  explanations sticky. Most readings should expire by turn/session or an
  evidence condition.
- **Separate convergence score:** relation topology plus a confidence basis was
  sufficient for this tranche.
- **A second action field:** one advisory implication was enough; policy and
  runtime remain authoritative.

## 5. Convergence and contradiction

They deserve first-class representation as **typed evidence-to-hypothesis
relations**, not numeric aggregates.

Minimum useful semantics:

- `supports`: the observation increases plausibility;
- `qualifies`: it narrows domain, strength, timing, or applicability without
  opposing the core proposition;
- `contradicts`: it is evidence against the proposition;
- `superseded`: a status on the old hypothesis, not an evidence edge.

Why this matters: two independent changes from a personal baseline are not just
“+2”, and preserved social enjoyment is not “−1”. It qualifies breadth. In the
RPD2 case, the explicit request for space supports withdrawal literally, while
the user's immediate explanation contradicts withdrawal-as-care in this scene.
That tension must remain visible rather than average to uncertainty.

Independence itself was not encoded as a field. The confidence basis can state
whether signals are independent; add structure only if a later blind experiment
shows models routinely double-count the same source.

## 6. Matter hypothesis

**Verdict: useful as a bounded identity claim; too broad as a universal root
ontology.**

It helps most when the decision requires identity across change: dentist
references, an event being moved then cancelled, an issue improving then
recurring, or one rupture accumulating attempted repairs. It gives hypotheses a
stable subject without forcing evidence rows themselves to merge.

It becomes vague for a one-turn affect reading, a worldview resonance rule, or
simultaneous astrology domains. Calling all of these “things in the world” adds
little. For Phase 0, `matter` means only “the bounded referent this packet is
about.” It does not own actions, deadlines, actors, claims, sub-matters, or
lifecycle. If identity is not decision-relevant, a packet should be allowed to
use a transient subject rather than mint durable matter state.

## 7. Strategy learning

Yes, outcomes of the system's own behaviour fit the same abstraction.

The RPD2 packet represents:

`withdraw / give space` → explicit consequence (“repair burden returned to me;
this felt like abandonment”) → old strategy hypothesis superseded → new,
bounded hypothesis (“a small autonomous repair move may better address this
kind of injury”) → recheck on welcomed/rejected/redirected reaction.

This generalises to “reminder style X repeatedly increases disengagement.” The
representation must store the attempted strategy and reaction as evidence, not
as a behavioural script. The implication remains conditional and product-owned;
there is no rule such as “pursue three times.” Explicit boundaries always
dominate.

## 8. Bloom implications

Bloom should inherit from the shared substrate:

- provenance-bearing longitudinal evidence;
- identity and lifecycle where genuinely operational;
- suppression, receipts/outcomes, attention, and revision on new evidence;
- separation of durable truth, activation, attention, and action authority.

Before substantial Bloom behaviour, it needs product-scoped ability to hold
competing, revisable explanations for baseline change; preserve trajectories;
distinguish contradiction from qualification; state what evidence would change
a reading; and choose ask/wait/notice without declaring an internal state.

What must not leak into generic Cortex: clinical concepts, symptom taxonomies,
diagnostic thresholds, treatment recommendations, escalation rules, adherence
labels, or health-risk policy. Those require a Bloom/clinical constitution and
appropriate safety ownership, which the current canon explicitly leaves open.
Phase 0 authorises no medical inference.

## 9. RPD2 implications

The missing unit is not “emotion detected.” It is relational meaning across a
trajectory: established expectation, perceived violation, injury as understood
by the user, attempted repair, whether the attempt addresses that injury, and
what the observed response teaches future posture. Current replay remembered
events but missed that non-pursuit repeated the exact injury of non-recognition
and transferred repair labour.

These hypotheses must stay RPD2-scoped. Pursuit, repair sufficiency, jealousy,
and character-specific expressions of love are product constitution, not shared
Cortex truth.

## 10. Sophie implications

Beyond factual memory and task follow-up, Sophie could:

- treat paraphrases and pronouns as revisions of one live matter;
- preserve an event's transformation instead of accumulating operation-shaped
  commitments;
- recognise when a preference suggests a communication style, then narrow it
  from feedback;
- learn that a reminder posture is counterproductive without treating a missed
  action as a character flaw;
- choose ask, wait, enrich, or attend based on what remains uncertain rather
  than on row count.

This does not yet authorise fixing reconciliation in production.

## 11. Oracle implications

What genuinely generalises is not astrology content. It is:

- multiple simultaneous hypotheses;
- domain-scoped signals;
- explicit support, qualification, and contradiction;
- convergence explained by independent evidence rather than score addition;
- projections that preserve tension instead of forcing one valence.

Signal definitions, interpretive traditions, reading style, and any predictive
claims remain Oracle-owned. No existing Oracle implementation or deterministic
signal fixture was found in this repository, so the experiment uses a labelled
synthetic astrology-shaped case and makes no claim about astrology validity.

## 12. Where this layer should live

**Recommended ownership split:**

- **Cortex:** canonical evidence/history, existing durable operational state,
  and retrieval by stable evidence reference. It should not own product meaning
  merely because it stores evidence.
- **Shared sidecar contract:** the minimal packet shape and validation rules,
  usable offline first. Shared means transport/inspection contract, not shared
  semantic authority.
- **Product-specific interpretation module:** creates and revises hypotheses,
  chooses product scope and persistence, and owns domain vocabulary. Sophie,
  Bloom, RPD2, and Oracle may use different prompts/models/rules behind the same
  small envelope.
- **Synapse/ContextAdapter:** selects and compresses currently relevant packet
  projections for the foreground. It should not derive durable meaning.
- **Runtime/product policy:** converts advisory implications into posture or
  action under permissions, safety, character, and foreground autonomy.

This split follows ownership evidence: shared provenance and revision mechanics;
product-specific meaning; runtime authority. It avoids relocating mature
components for diagram symmetry.

## 13. Smallest next implementation

The experiment succeeds narrowly enough to justify exactly one tranche:

**Build a read-only, offline model bakeoff that emits this packet for only the
two frozen Sophie trajectories (dentist and meeting), then blind-judge matter
identity, evidence-relation correctness, and bounded decision against distractor
cases.**

Constraints:

- live production paths, schemas, and tables remain unchanged;
- input is frozen transcript evidence plus current snapshot only;
- output is ephemeral JSON validated by the Phase-0 contract;
- include adversarial near-duplicates (two genuinely distinct dentist matters,
  two Sarah meetings) to measure over-merging;
- judge evidence links and decision effect, not prose;
- no RPD2/Bloom/Oracle implementation until the narrow identity test shows the
  packet can be produced reliably rather than merely hand-authored.

If that bakeoff cannot beat the current representation without unsafe merging,
discard the sidecar design and leave the graduated substrate unchanged.

