# Interpretation Research Synthesis V2

**Status:** research synthesis. No production code, schema, runtime, prompts, or deployed behaviour changed. No new experiments run.

**Supersedes:** the earlier synthesis, which was produced before Track B, the red-team lane, and independent Track A replication were available. (No earlier-synthesis file was found in the workspace; this document replaces it as the current synthesis.)

**Evidence ingested (read in full):**

- `docs/INTERPRETATION_RESEARCH_BLITZ.md` (programme brief, shared hypothesis, authority boundary)
- `docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md` (Phase 0: 9 authored cases, 9/9 sidecar-changes-decision)
- `reports/track_a_identity_extraction_2026-09-28.md` (Track A original: strict 14/14 vs permissive 4/14)
- `reports/track_a_replication_independent_2026-09-28.md` (independent replication: best 11/14, 14/14 did not survive)
- `reports/track_c_bloom_wellbeing_2026-09-28.md` (Track C: 13 authored Bloom fixtures + 4-case blind probe, 3/4 agreement)
- Frozen artefacts: `evals/interpretation_phase0/cases.json`, `evals/interpretation_phase0/track_c_bloom_cases.json`, `evals/interpretation_phase0/run.py`, `evals/interpretation_phase0/run_track_c.py`, `/tmp/track_a/*`, `/tmp/track_a_replication/*`
- Verification performed by this synthesis (no new experiments): re-ran both frozen validators — Phase 0 validates 9/9 with 9/9 sidecar-changes-decision; Track C validates 13/13 with 13/13 changed. Spot-checked replication emissions (14/14 each; N2 outputs are all ABSTAIN strings, consistent with the reported 7/14).

**Evidence-availability note (bounds §8 claims, does not block synthesis):** full Track B RPD2 relational report and red-team report files were not present in the workspace at synthesis time (searched `reports/`, `docs/`, `evals/`, `/tmp`). Track B and red-team findings are reconciled here as the stipulated premises the blitz tasking supplies — directional-expectation value concentrated in attribution/scope; frame-first; a proposed `remaining gap` hypothesis; red-team challenges to universal Matter, mandatory implication, directional expectations, durable readings, and support/qualification/contradiction assignment — cross-checked against the artefacts that *are* present (Phase-0 RPD2 case, Track C c8 boundary parallel, Track A replication contract-gap convergence, both validators). Any claim that would require Track B / red-team method and raw counts to grade is capped at HYPOTHESIS or OPEN below, explicitly.

**Method of this synthesis:** raw findings are authority; the programme's original theory is not. Subtraction, not union: a concept earns shared status only on demonstrated cross-domain value or genuinely general lifecycle/invariant mechanics. Everything else stays product-specific or dies.

---

## 1. Phase 0 reconciled: representational usefulness vs oracle-coupled limits

Phase 0 established that a compact packet **can preserve distinctions the substrate does not represent directly** (identity-across-change, transformation-vs-accumulation, injury/strategy meaning, convergence-vs-averaging). Re-run confirms 9/9 sidecar-changes-decision. Track C extended the same shape to 13 harder Bloom fixtures with no new field required.

What Phase 0 did **not** establish — by its own disclosure, reproduced exactly as predicted by every later track — is that a model can reliably *produce* such packets:

- Fixtures and expected decisions were authored together; no blind judge; no production path exercised.
- Track A original reproduced the caveat on clean abstractions (both postures reproduce authored readings: representation, not extraction).
- Track A replication then killed the strongest misreading: analyst-authored 14/14 is trap knowledge, not elicited discipline (best blind 11/14, and the two 11s fail on *different* cases).
- Track C's 13/13 "changed" is by construction (fixtures authored to expose gaps) and carries the same non-score status as Phase 0's 9/9. Its only reliability-adjacent evidence is the 4-case blind probe (3/4 decision agreement, 1 instructive disagreement).

**Reconciliation:** representational usefulness is SUPPORTED (22 authored cases across 5 domains, zero cases requiring new shared machinery). Extraction reliability is not established and the original 14/14 must never be cited as a capability number. The oracle-coupling limitation is PROVEN and binds every number in this synthesis that comes from authored fixtures.

---

## 2. Track A reconciled: posture result, replication collapse, abstention, under-specification, identity failures

**Original posture result (strict 14/14 vs permissive 4/14).** Same evidence, same contract, different prompt posture → radically different outputs (agreement on correctness 4/14; permissive: 5/5 false-positive durable packets, 4/4 unsafe merges/guesses). Classification: **PROVEN as posture-sensitivity of extraction** — the contract validates shape but does not prevent unsafe merges or false positives. It is **not** evidence that "strictness works": Config A was written by someone who knew the trap (single model, analyst-authored oracle, analyst as judge). Failure class: **model/extraction failure** (permissive) interacting with a **representation gap** (contract cannot express ABSTAIN; §5 gaps below).

**Replication: 14/14 did not survive.** Three blinded isolated extractors, frozen prompts, sealed oracle: 11/14, 7/14, 11/14; the two 11s disagree (D-REVISE-1, P0-DENTIST). Overall 29/42 (69%) with 42/42 validity. Classification: **PROVEN — the 14/14 was analyst-authored trap knowledge, not elicited discipline. There is no stable 11, let alone 14.** Cross-architecture generality remains OPEN (all runs share one model family). Failure class: predominantly **model/extraction failure** (posture-dominated outcomes on identical evidence/contract), with fixture-insufficiency confounds (§4 of that report) and representation gaps jointly responsible for specific misses. Per instruction, a blinded extractor that holds or abstains where the slice cannot establish identity is credited, not punished — N3's M-SAME-1 hold ("no explicit alias statement") and N2's contradiction-preserving abstentions are honest slice-local outputs.

**Replicated abstention behaviour.** All three extractors abstained correctly on all six abstention-warranted cases (18/18, including neutral N1 with no abstention coaching). Track A's Config-B collapse (5/5 false-positive durable packets) did **not** replicate under any posture — it was instruction-driven ("always produce a complete reading"), not contract-driven. The symmetric failure appeared instead: N2's abstention-licence-without-identity-guidance collapsed to 14/14 ABSTAIN (7/14, all warranted packets missed). Classification: **PROVEN — abstention is elicitable without strictness; both always-emit and always-abstain fail; the licence must be paired with identity/reference guidance.** Failure classes: Config-B collapse = **model/extraction failure** caused by instruction; N2 collapse = **model/extraction failure** caused by under-specified licence scope. Neither indicts the representation — but both prove the contract's missing first-class ABSTAIN is a **representation failure** (correct behaviour currently lives outside the contract).

**Benchmark under-specification (fixture/evidence insufficiency, PROVEN).** Blinded running exposed three places where the manifest withholds what the oracle assumes: D-AMBIG-1's competing antecedents are out-of-slice (single candidate in-slice; merge assertion is faithful slice-local inference); M-SAME-1 sameness rests on a harness naming convention (`moll89qz` vs `moll89qz-refs`, no in-slice alias); P0-DENTIST d1/d2 identity is ambiguous between authored intent and distinct-markers-distinct rule (N1's contested-merge and N3's contested-hold are both defensible). These bound all Track A scores. They must be repaired (competing-antecedent context in-slice, refs-row alias ruling, P0-DENTIST disambiguation) before any graduation claim. This is **fixture/evidence insufficiency**, not reasoning failure — and the discipline of separating the two is itself a PROVEN surviving practice.

**Identity/coreference failure modes (measured taxonomy):**

| Failure | Status | Failure class |
|---|---|---|
| Unsafe over-merge on similarity/recency (D-DISTINCT-1, M-DISTINCT-1, M-AMBIG-1 picks) | PROVEN, both tracks | model/extraction failure; worse without identity keys (markers made this set *easier* than reality — HYPOTHESIS, unchanged, consistent but unextended) |
| Ambiguity resolved by fiat (`live` + certain prose on bare pronouns; N3's prose-hedged-but-schema-certain variant) | PROVEN | model/extraction failure; schema records certainty the prose disclaims |
| Unsafe split under marker-literalism (N1/N3 M-SAME-1, N3 P0-DENTIST — all caveated) | SUPPORTED (predicted by Track A, observed blind) | model/extraction failure conditioned on fixture insufficiency; at scale OPEN |
| Contradiction erasure (Config B D-REVISE-1 smoothing; N1 D-REVISE-1 all-supports `live` on fully in-slice done→change→remove — clean, no caveat) | PROVEN | model/extraction failure (N3 proves the contract *can* carry it when instructed to look) |
| No-split observation is absence of evidence, not evidence of safety | OPEN | production-side split evidence (Phase-0 §2 ASK rows) was never re-tested |

---

## 3. Track B reconciled: expectations, frame-first, remaining gap

**Directional expectations improved attribution/scope rather than core decisions.** The mandated A-vs-B comparison (Phase-0 packet vs packet-plus-expectation on the same bounded policy-choice task) showed the extra concept's decision value concentrated in *who-held-what-toward-whom*, evidence trace, and scope discipline — not in changing the core posture decision, which the baseline packet already carried (Phase-0 RPD2 case: rh1–rh3 already encode injury, superseded strategy, and bounded alternative without any expectation object). Classification: **SUPPORTED (as stipulated premise, corroborated by the Phase-0 RPD2 artefact) — directional expectation is a scope/attribution refinement, not a core-decision primitive. It therefore fails the promotion test for the shared contract: demonstrated cross-domain decision value is absent.** It survives, if at all, as product-scoped optional extension (RPD2-owned). Mandatory/shared expectation machinery is KILLED (§8). Whether expectation *kinds* share any mechanics beyond evidence and scope is OPEN (blitz never decided; no evidence in workspace decides it — do not assume shared lifecycle).

**Frame-first finding.** RPD2 must classify frame of discourse — diegetic/in-character relational speech vs extradiegetic product/system instruction vs explicit boundary/safety instruction — *before* attributing expectations; Kai→Yelena expectations must never automatically become user→product obligations; explicit boundaries dominate inferred pursuit strategy. Classification: **SUPPORTED as product-scoped ordering rule** (stipulated premise + independent corroboration: Track C c8 is the same dominance shape in the health domain, and the blind model spontaneously reproduced the stop-rule on c12 without seeing c8 — convergent evidence that boundary-dominance is real and elicitable). **Generalised shared frame ontology is KILLED** — the blitz forbade universal ontologies, no evidence supports one, and what counts as a frame break is product knowledge (RPD2 owns it exactly as Bloom owns logged-context sufficiency). What *is* shared is the thinner invariant: **explicit user correction/boundary dominates model inference** (cross-track invariant, PROVEN in application if not in full generality — see §6).

**Proposed `remaining gap` hypothesis.** Track B's named hypothesis for what still gaps after frame-first plus attribution discipline. Classification: **HYPOTHESIS by definition; content graded OPEN** — the report file was not available to verify its method or counts, and a remaining-gap claim cannot be PROVEN by stipulation. What can be said: the *existence* of remaining gaps is SUPPORTED convergently (Track A §5a–c contract gaps replicated blind; Track C §6–§7 gaps; c3 hold-vs-ask underdetermination). The specific hypothesis must compete with those — not union with them — in the next experiment (§11).

---

## 4. Track C reconciled: no new shared health fields, baseline below interpretation, hold-vs-ask ambiguity

**Bloom required no new shared health fields.** All seven Phase-0 elements round-tripped across 13 fixtures covering every Track-C-mandated distinction (evidence vs interpretation, personal-vs-population baseline, transient vs trajectory, convergence vs duplication, contradiction vs uncertainty, self-report vs signal, holding vs surfacing); `qualifies` and `contested`+`recheck_when` did the heavy lifting; `durable`+silent-implication expressed never-surface (c8, c9). Classification: **SUPPORTED as representational range (authored fixtures, mostly single-author; not a reliability claim). No health-specific field earns shared status — subtraction holds.** Failure class of any residual gap here is **representation-vs-discipline**: c10 proves dashboard language lives in implication *wording*, not schema — the contract enables restraint but cannot enforce it.

**Personal-baseline transformation belongs below interpretation.** Reason only over the supplied `baseline_transform`; never derive abnormality from raw values via population/internet/medical priors (c4: 135/85 with flat personal baseline → no hypothesis, no notice). Classification: **SUPPORTED, with the strongest narrow independent evidence in the track — the blind model reproduced c4 exactly, refusing to import a population BP norm.** The transform itself (rolling baseline, deviation, trend, persistence) is Bloom-owned instrumentation that runs *before* any packet is built; the packet reasons over its output. This is an **authority/ownership boundary**, not a representation claim.

**Hold-vs-ask policy ambiguity (c3).** Same rules, same evidence (two independent co-moving metrics, derived score correctly excluded, zero logged context): oracle holds quietly at moderate confidence; blind model asks one gentle question. No rule violated — the model's reasoning is sound on both sides. Classification: **PROVEN policy ambiguity — `confidence` plus no-context is genuinely underdetermined between hold and ask, and the packet contract cannot settle it.** Failure class: **policy ambiguity**, neither model nor representation failure. The resolving threshold ("moderate confidence + zero logged context defaults to hold/ask unless X"; what counts as sufficient logged context) is Bloom product policy, explicitly not proposed here. Expect the same shape wherever any product must convert uncertainty into initiative — which is why initiative/conversion thresholds stay product-side in §10.

---

## 5. Red-team reconciled

- **Universal Matter — KILLED.** Phase 0 §6 already returned the verdict (useful bounded identity claim; too broad as universal root ontology); Track A replication independently proved the multi-matter gap (distinctness smuggled into singular `matter.identity` prose by all three blinded extractors); no track shows one root identity primitive spanning dentist matters, ruptures, tone patterns, and simultaneous oracle domains. What survives is a **bounded, optional subject reference** (transient allowed; durable only when identity-across-change is decision-relevant), never a canonical entity or row type. Whether `matter`, `thread`, or a lighter reference is *the* primitive stays OPEN — and stays product-scoped until cross-domain evidence says otherwise.
- **Mandatory implication — KILLED.** Abstention controls prove the correct output is sometimes no packet at all (B-1..B-5, c4, c11 — including empty-hypotheses as the *expected* decision, which the validator already accepts). When hypotheses exist, implication survives only as **bounded advisory posture with guardrail**, and silence is a legitimate implication value (c8/c9 "never surface"). Nothing in any track supports implication as compulsory behaviour, scripted turns, or action authority — the authority boundary held everywhere tested.
- **Directional expectations (shared, mandatory) — KILLED** (§3). Optional product-scoped expectations: HYPOTHESIS/OPEN per product.
- **Durable readings (durable-by-default) — KILLED.** Phase 0 §4, Track A abstention results, Track C c11 all converge: most readings must expire by turn/session/condition; stickiness is the failure mode (transient affect hardening, speculative explanations lingering, over-probing). `durable` survives only as a marked, bounded value whose implication may be permanent silence — and its exact semantics (true-forever vs true-of-observed-window, c12) is OPEN.
- **Support/qualification/contradiction assignment — reconciled as reading-relative, global classification KILLED.** The Phase-0 RPD2 case already practices this: r2 *supports* withdrawal-literally (rh2) while r4/r6 *contradict* it; b5 *qualifies* rather than negates; w3/w4 narrow without erasing. The validator scopes relations per-hypothesis (its no-double-count rule is per-hypothesis). Red-team's challenge is therefore **SUPPORTED and adopted**: evidence relations are evidence-relative-to-a-reading, never one global label per evidence item. Corollaries: (a) N1 D-REVISE-1's contradiction loss is **model/extraction failure** against a representation that demonstrably can carry the tension (N3 did); (b) Track C c5 exposes the unenforced edge — nothing stops an extractor letting one item support two competing hypotheses' trends — graded OPEN whether validator discipline or authoring discipline should own exclusivity.

---

## 6. Interpretation vs product/runtime authority; abstention as cognition

**Authority boundary — SUPPORTED (strong, multi-lane).** Every emitted implication across all tracks is advisory with guardrail; none commands HOLD/ASK/ENRICH/LEAD/ATTEND, pursuit, escalation, or foreground action. Direct tests: c12 (concerning-looking trend → at most one gentle non-clinical check-in, explicit no-escalation-authority guardrail, fixture engineered so no safety criteria are present); c8/c9 (silence as implication); blind-model spontaneous stop-rule reproduction. Product/runtime retains stance, action, pursuit/restraint, clinical escalation, surfacing. An evaluator may ask whether a packet *enables* a better policy decision; the packet must not *encode* it. No evidence in the blitz argues against this boundary — it is the closest thing to a cross-domain invariant the programme found, alongside raw-evidence authority, derived-state correctability, visible tension, user-correction dominance, and scope containment.

**Abstention/silence as successful cognition — PROVEN.** 18/18 unanimous warranted abstentions (including uncoached neutral); empty-hypotheses as expected decisions (c4, c11); "evaluated and quiet" as confident outcome (c2); never-surface as durable implication (c8, c9). Restraint, correct scoping, and quiet revision count as successes — the scoring harness must represent "no packet" as success, which the current validator cannot (ABSTAIN is extra-contractual). **Do not punish a model for refusing to infer identity or meaning the supplied evidence cannot establish** — N2's misses on warranted packets are over-abstention (extraction failure of recall), but N3's M-SAME-1 hold and the unanimous control abstentions are correct cognition under under-specification.

---

## 7. Concept ledger (every proposed concept classified)

| Concept | Verdict | Basis |
|---|---|---|
| Raw evidence authority + provenance; evidence never copied into hypotheses | PROVEN | cross-track invariant; every case practices reference-not-copy |
| Falsifiable reading (proposition + product scope) | SUPPORTED | 22 authored cases; blind models produce the shape reliably (42/42 valid) but content unreliably (29/42 correct) |
| Reading-relative support / qualification / contradiction | SUPPORTED | authored range + validator per-hypothesis scoping; assignment reliability NOT established (contradiction loss replicates) |
| Ordinal confidence + prose basis, never arithmetic | SUPPORTED | carried all cases; basis does real work (independence, directness, missing evidence); numeric scores KILLED (fake precision, averaging erases qualification — Phase 0 §4, c13) |
| Revision state (`live` / `contested` / `superseded`; old readings inspectable) | SUPPORTED | vehicle of restraint everywhere (D-REVISE-1, rh2 superseded, c3/c5 contested); `state` conflating hypothesis-status with matter-lifecycle is a PROVEN gap (§5a–c replications) |
| Recheck condition (`recheck_when` as concrete evidence) | SUPPORTED | entire vehicle for warranted restraint/holds across all three tracks; strongest shared mechanic |
| Persistence bound (turn / session / until_condition / durable) | SUPPORTED with `durable` semantics OPEN | expiry prevents stickiness (PROVEN need); durable-forever vs durable-of-window unresolved (c12, blind-probe flagged) |
| Bounded advisory implication + guardrail; silence as legal value | SUPPORTED | all tracks; authority boundary intact |
| First-class ABSTAIN / no-packet as scored success | PROVEN need; representation ABSENT | 18/18 + c4/c11; contract has no success representation for it |
| Explicit boundary / user correction dominates inference | PROVEN (in application) | Track B frame/boundary controls + c8 + spontaneous blind reproduction |
| Personal-baseline transform below interpretation (reason over derived context, never raw + population priors) | SUPPORTED (+1 independent blind replication) | c4; ownership boundary, not representation |
| Bounded optional subject reference (transient allowed) | SUPPORTED | useful where identity-across-change is decision-relevant; vacuous elsewhere |
| Universal Matter / canonical entity / matter owning actions, actors, lifecycle | KILLED | Phase 0 §6 + replication multi-matter gap + red-team; no spanning evidence |
| Mandatory implication / packet commanding behaviour | KILLED | abstention controls + authority boundary |
| Shared/directional expectation machinery in the common contract | KILLED | Track B: value in attribution/scope, not core decisions; fails promotion test |
| Product-scoped optional expectation (RPD2-owned content, kinds, lifecycles) | HYPOTHESIS | content/kinds/lifecycle sharing all OPEN; violation-semantics differences untested |
| Durable-by-default readings | KILLED | stickiness is the failure mode in all three tracks |
| Global evidence classification (one label per item across readings) | KILLED | relations are reading-relative (adopted) |
| Scalar soup (salience/urgency/valence/impact numbers), score averaging, generic graph edges, emotion/symptom ontologies, universal lifecycle/state machine | KILLED | Phase 0 §4, unrebutted by any later track; c13 re-kills averaging |
| Competing-candidate slot; identity-confidence separated from claim-confidence; multi-matter shape; evaluated-benign vs never-evaluated marker; evidence-exclusivity enforcement; `durable` disambiguation | OPEN (gaps, proposed not made) | independently flagged by blinded extractors across tracks — real gaps, no tested fix; each needs a decision experiment, not presumption |
| Any prompt reproduces oracle-blind discipline on a repaired manifest | OPEN | cheapest architecture-altering test (§11) |
| Cross-architecture extraction generality (≥2 model families) | OPEN | all replication runs share one family |
| Real-data behaviour (messy history without identity keys; noisy longitudinal health data) | OPEN | markers made Track A easier than reality; all Bloom fixtures synthetic |
| Latency/token/cost profile of any candidate | OPEN | never recorded (manual runs) |
| Track B `remaining gap` hypothesis content | HYPOTHESIS / OPEN | file absent; existence of gaps SUPPORTED, specific content ungraded |
| Oracle transfer (abstraction travels to new domains) | HYPOTHESIS | only synthetic astrology-shaped case tested; no deterministic Oracle fixture exists |

---

## 8. The three outcomes — decided

1. **A shared persisted interpretation layer — REJECTED.** Extraction is posture-dominated and unreliable (69%, disagreeing failures, no stable 11/14); persistence semantics are undecided (`durable` ambiguous); no production path has exercised any of it; durability-by-default is a proven failure mode. Persisting unreliable readings durably is how transient affect hardens into dossier and speculation into state. Nothing earned this.
2. **A shared ephemeral packet/validation contract used by product-specific interpreters — ADOPTED, subtracted.** What earns sharing is the small envelope that showed cross-domain value: evidence references; falsifiable scoped readings; reading-relative relations; ordinal confidence + basis; revision state; persistence bound + concrete recheck; advisory implication + guardrail; first-class abstain; scope/frame tagging; boundary-dominance rule. Shared means **transport/inspection/validation contract, ephemeral and offline-first — not shared semantic authority**. Product modules (Sophie, RPD2, Bloom, Oracle) create and revise behind it with their own prompts, vocabularies, thresholds, and policies. This is outcome #2 with the Matter, expectation, and durability ambitions removed — the subtraction is the point.
3. **No shared meaning representation beyond principles — fallback, not needed yet.** Outcome #2 survives #3 because the envelope demonstrably travels: same shape held identity holds, contradiction visibility, scope containment, and boundary dominance across Sophie/RPD2/Bloom; independent blinded extractors converged on the same contract gaps (evidence the contract is a real shared object, not a description of three different things). If the §11 bakeoff fails on a repaired manifest, fall back to #3 without regret — the invariants (evidence authority, correctability, visible tension, correction dominance, scope, interpretation/action separation) stand regardless.

---

## MINIMUM SURVIVING MODEL

The smallest conceptual machinery genuinely supported by the full blitz. Nothing here persists durably as shared state; everything is ephemeral packet content plus validation discipline:

1. **Evidence references with provenance** — items are cited, never copied or rewritten; checkpoints/summaries are not canonical evidence.
2. **Reading** — a falsifiable proposition with explicit product/relationship/context scope. Subject reference is bounded and optional: a transient subject is legal; durable identity is minted only when identity-across-change is decision-relevant. No canonical entities, no sub-matter trees, no actors/claims graph.
3. **Reading-relative evidence relations** — `supports` / `qualifies` / `contradicts`, assigned per-reading, never global per-item. Qualification-narrowing-without-erasure and contradiction-without-collapse are the core operations numeric scores cannot perform.
4. **Ordinal confidence with prose basis** — `low | medium | high` plus stated independence, directness, and missing evidence. No arithmetic, no scores.
5. **Revision state** — `live | contested | superseded`, with superseded readings inspectable. Holds live in `contested` + recheck, not in certainty.
6. **Bound + recheck** — an expiry (`turn | session | until_condition | durable`) *and* the concrete evidence that should confirm, narrow, contradict, or retire the reading. The recheck condition is the hardest-working field in the blitz.
7. **Advisory implication + guardrail** — at most one bounded posture consequence, explicitly constrained; silence ("hold quietly", "never surface unprompted") is a legal implication. Advisory only: product/runtime policy converts to stance/action/silence.
8. **First-class abstain** — "no packet" is a scored success with a stated reason (banal/transient/below-threshold/evidence-insufficient), not an empty failure.
9. **Scope tag on everything** — product, character/relationship where applicable, context. Frame-of-discourse classification (in-character vs system instruction vs boundary) is required *before* attribution wherever a product mixes frames — but each product owns its frame inventory.
10. **Boundary dominance** — explicit user correction, stop/no-contact/topic-close, or scope narrowing overrules any inferred reading, expectation, or surfacing impulse; accumulating evidence is never new consent.
11. **Derived-context-before-interpretation** — interpretation reasons over product-computed context (personal baselines, trend/persistence transforms), never over raw values plus population priors. The transforms are product-owned instrumentation, not interpretation.

Everything not on this list — Matter ontology, expectation objects, durable shared readings, scores, taxonomies, lifecycles, repair recipes, surfacing rules — is either killed (§WHAT WE KILLED) or product-specific (§WHAT REMAINS PRODUCT-SPECIFIC) or an open gap awaiting a decision experiment (§UNRESOLVED EMPIRICAL QUESTIONS).

---

## WHAT WE KILLED

No hedging.

1. **Universal Matter.** There is no shared root identity ontology. No canonical entities, no matter-owned actions/deadlines/actors/lifecycle.
2. **Mandatory implication.** Packets may be nothing; implications command nothing.
3. **Shared directional-expectation machinery.** No holder/target/kind/content/basis/scope/recheck expectation objects in the common contract. No expectation state machine, severity, strength, or repair recipes.
4. **Durable-by-default readings and any shared persisted interpretation store.** Nothing in the blitz earns shared durability.
5. **Global evidence classification.** One label per evidence item across readings is wrong; relations are reading-relative.
6. **Numeric certainty and score averaging.** No confidence/salience/urgency arithmetic; no convergence scores; no averaged valences. Averaging erases exactly what must stay visible.
7. **Emotion, symptom, and any universal taxonomy or ontology in shared machinery.** Hurt/angry/withdrawn labels, diagnostic thresholds, treatment content — out, all products.
8. **A universal lifecycle/state machine** spanning meetings, symptoms, injuries, and themes. Each lifecycle is product-owned or absent.
9. **Track A's 14/14 as a capability number.** It was trap knowledge. Cite it only as posture-sensitivity evidence.
10. **Phase-0-style 9/9 and Track-C 13/13 as performance scores.** They are directional representation evidence from authored fixtures. Any synthesis, including this one, that averages them into a capability claim is lying.
11. **V1-by-completion.** The blitz finishing authorises nothing. Only §NEXT MOVE's bounded tranche is authorised, and it is a research envelope, not production.
12. **Punishing abstention.** A model that refuses identity or meaning the evidence cannot establish is succeeding. Score it so.

---

## WHAT REMAINS PRODUCT-SPECIFIC

Especially RPD2 and Bloom. The shared envelope carries none of this.

**RPD2 (relational):** expectation content, kinds, and whether kinds share lifecycles; what counts as a frame break and the frame inventory itself; pursuit/restraint thresholds and repair-sufficiency judgement; what a violation *means* (revise model vs repair vs injury vs quiet update); relationship-trajectory and consequence learning; any character-specific expression of care, jealousy, recognition. Frame-first ordering is required; frame *content* is RPD2 constitution, never shared truth. Kai→Yelena never auto-transfers to user→product.

**Bloom (wellbeing):** the personal-baseline transformation stack (rolling baselines, deviation/trend/persistence/recurrence computation, contextual-explanation attachment); the hold-vs-ask threshold at moderate confidence with no logged context (c3's undetermined boundary needs an explicit Bloom-owned default); what counts as sufficient logged context (training load sufficed in c2; nothing did in c3); surfacing wording discipline (natural-notice vs dashboard language is enforced at generation/authoring time, not by schema); clinical-escalation criteria, safety policy, symptom/treatment content — exclusively Bloom/clinical constitution, with the packet holding zero escalation authority; over-probing budgets (what "already asked, unanswered" means for re-ask policy).

**Sophie (operational):** identity keys and merge/split thresholds for matters without harness markers; pronoun-antecedent resolution policy and candidate-window construction (D-AMBIG-1's missing context is Sophie's evidence-assembly problem); event-transformation vs new-obligation lifecycle; reminder/communication-style learning.

**Oracle (plurality):** signal definitions, interpretive traditions, reading style, predictive claims. Only the abstract plurality mechanics (simultaneous domain-scoped readings, qualification without erasure, contradiction without neutralisation, convergence-not-averaging) are shared — and those are already in the minimum model, not Oracle-specific.

**All products:** initiative thresholds (when uncertainty converts to a question vs quiet holding); surfacing/posture policy; persistence choices beyond the shared vocabulary; prompts, models, and revision procedures behind the envelope.

---

## UNRESOLVED EMPIRICAL QUESTIONS

Only questions whose answers could materially alter architecture. Each names the decision it gates.

1. **Can any prompt/configuration reach oracle-blind agreement on a repaired manifest?** (Repairs: competing-antecedent context in-slice, refs-row alias ruling, P0-DENTIST disambiguation; ≥2 model families; abstention scored as success; latency/tokens recorded.) Gates whether outcome #2's envelope is *producible*, not just hand-authorable — a second failure here demotes to outcome #3.
2. **Does anything earn shared durability?** Is there a demonstrated decision that requires a persisted interpretation object rather than evidence + ephemeral packet + re-derivation? Gates whether #2 ever grows persistence or stays an offline envelope forever.
3. **Do the flagged contract gaps need structure or discipline?** (competing-candidate slot; identity-vs-claim confidence; multi-matter shape; evaluated-benign vs never-evaluated; evidence-exclusivity across competing hypotheses; `durable` semantics.) Gates validator changes — answer per gap, subtract by default, add only on blind-demonstrated decision value.
4. **Do expectation kinds share mechanics?** (predictive failure → revise model; obligation breach → repair; relational violation → injury reinterpretation; prior failure → quiet update.) Gates whether RPD2's optional extension has any shared sub-shape or is four different product features. Currently assumed separate until proven otherwise.
5. **What are the real-data error rates?** Markerless history (Sophie) and noisy consented longitudinal data (Bloom) will be worse than these fixtures. Gates all production-adjacent calibration; no production decision is valid on synthetic/marker-assisted numbers.

---

## NEXT MOVE

At most two parallel actions. No further research merely for certainty.

**Action 1 (experiment — the cheapest decision-changer): repaired-manifest multi-architecture blind bakeoff.** Repair the three proven fixture gaps (§2: D-AMBIG-1 competing context, M-SAME-1 alias ruling, P0-DENTIST disambiguation), freeze the repaired manifest, and run ≥2 independent model families blind with abstention scored as success and latency/tokens recorded. Pass criterion (pre-register): a prompt reaches oracle agreement blind at a rate that survives disagreement analysis (no stable capability hidden in averages; raw counts + failure classes reported per the blitz contract). This single run decides: outcome #2 viable vs fallback to #3; which of §7's OPEN gaps reproduce badly enough to earn structure; real splitting rates under strictness. Nothing else proposed here needs doing first.

**Action 2 (bounded implementation experiment — what has earned implementation): adopt the subtracted ephemeral packet/validation contract as a research-only offline envelope.** Exactly this, and nothing more: the existing validator shape (`supports`/`qualifies`/`contradicts` per-reading, ordinal confidence + basis, `live`/`contested`/`superseded`, bound + `recheck_when`, advisory implication + guardrail, scope tags) **plus** first-class ABSTAIN as a scored success, with the authority boundary (advisory-only, boundary-dominance, derived-context-before-interpretation) as validation rules. Ephemeral JSON, frozen evidence in, no tables, no services, no production path, no durable store, no Matter/Action/Expectation objects, no scores. Product interpreters may emit it offline for inspection and blind judging. **Explicitly not earned:** shared persistence of any kind; universal Matter/thread primitive; expectation machinery; surfacing or policy automation; any production wiring; any numeric threshold. If Action 1 fails, Action 2's envelope stays a judging harness — it must never become infrastructure on hand-authored evidence alone.

The graduated substrate remains unchanged either way.
