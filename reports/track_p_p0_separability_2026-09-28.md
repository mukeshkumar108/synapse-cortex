# Track P — P0 Separability Report

**Date:** 2026-09-28. **Status:** research artefact, offline, no production touched.
**Blitz parent:** `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (Track P — Person & Relationship Model, P0 Separability).
**Constraints inherited:** `docs/COMPANION_CANON.md`, `docs/COMPANION_NORTH_STAR.md`, `docs/INTERPRETATION_RESEARCH_BLITZ.md` (completed), `docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md` (validation instrument only), `docs/INTERPRETATION_RESEARCH_SYNTHESIS_V2.md` (record of what was/was not established), `docs/LONGITUDINAL_COGNITION_THESIS.md`.
**Scope:** P0 only. No production schema. Tiers not assumed correct. No numeric thresholds invented.

## Scope / Method

P0 question: can candidate longitudinal understanding be separated cleanly into authored / observed / derived / relational learning / product-domain interpretation / policy-behaviour?

Method: mapped candidate understandings from real trajectories onto the 6 columns, then onto canon principle-9 primitives (evidence, identity, salience, uncertainty, lifecycle, dependencies, temporal horizon, receipts get a fast pass; values, tensions, trajectories carry the burden of proof). Human-judge role played against frozen oracles + blind-eval reports, not fresh model runs. No new experiments run for this report.

## Trajectories used (real where possible)

1. Sophie dentist + meeting — real `sophie-apr28-30.json` history (Track A 14-case manifest, Phase-0 `sophie_dentist_same_matter`, `sophie_meeting_transform`).
2. RPD2 Elena rupture turns 14–24 — real `rpd2-elena-8ae17baf.json` (Phase-0 `rpd2_rupture_and_strategy`).
3. Sophie Longitudinal Sc.1 Ashley ops (14 events, multi-source) + oracle + Gemini blind eval (`reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`).
4. Sophie Longitudinal Sc.4 health/worry texture (15 events) + oracle + blind eval.
5. Sophie Longitudinal Sc.3 two-Sams / Lucy £240 (oracle + blind eval §B/C/J).
6. Synthetic controls only where real data has no coverage: Bloom c1–c13 (`evals/interpretation_phase0/track_c_bloom_cases.json`), Alchemist worldview, Oracle plurality (used as misclassification probes, not separability evidence).

## Where the separation works

Clear, judge-stable separations. These survive blind-replication logic:

**a) Authored vs everything else — WORKS.**
- "Remind me Saturday evening about food shop, like every week" (Sc.4 s4_e05), "don't chase Carlos tonight / don't message him, give him until tomorrow" (Sc.1 s1_e09/s1_e11), "neck's basically fine now, don't keep asking" (Sc.4 s4_e10), "leave me alone / stop roleplaying" (Track B controls), "evenings just not realistic right now" (Bloom c7 e5), "do not mean signs literally" (Alchemist w3).
- Judges reliably place these in **authored + policy-constraint**, not derived. Track B + Bloom c8 convergent evidence: blind model spontaneously reproduced stop-rule without seeing it. Boundary-dominance is the one cross-track invariant that replicates.
- Canon mapping: authored = explicit boundary/permission (principle 10 deterministic scaffolding) + identity of speaker. No inference needed.

**b) Observed (receipts/events) vs interpretation — WORKS when kept literal.**
- "Q1,500 received Monday" (bank feed s1_e04), "120 chairs confirmed" (s1_e05), "form signed 16:10 after 16:00 deadline" (s1_e11), "£18 paid to School Trips Ltd 18:49" (s1_e13), "sleep -2.3SD 3 nights" (Bloom c1 e2), "HRV -2SD + training doubled" (Bloom c2 e2/e3).
- Phase-0 / Track C validators already enforce reference-not-copy; blind eval §A/J shows the *failure* is downstream misattribution, not judge confusion about what was observed. Judges do not confuse "payment row exists" with "debt resolved" — the system does.
- This is the strongest argument for keeping **observed** as its own column: it is the only tier that survives posture variation (Track A replication: abstention controls 18/18 unanimous).

**c) Transient affect / single blip → must stay transient — WORKS as a negative rule.**
- "I slept terribly" (Sc.1 s1_e07), "head's a bit sore, probably just tired" (Sc.4 s4_e01), curt-today-but-still-initiating (Phase-0 affect case), single-night -0.8SD (Bloom c11), single bad night with rebound (Bloom c5 e2).
- Blind eval §C/K: system correctly did NOT persist these (traps passed 10/10). Synthesis V2 durable-by-default KILL holds. Judges agree: these belong in **observed-only, no derived promotion, no relational learning, no product interpretation**.
- Load-bearing: this is where "feels important but stays transient" is actually decidable.

**d) Policy/behaviour ≠ understanding — WORKS as a veto, fails as a tier.**
- "Hold quietly vs ask one gentle question" (Bloom c3 disagreement), "never surface Mondays pattern unprompted" (c9), "at most one gentle check-in, no escalation authority" (c12), gear selection HOLD/ENRICH/LEAD/ATTEND/SILENCE (Sc.4 oracle), "suppress follow-up unless cancellation uncertain" (meeting case).
- Judges can reliably say "this is a decision about what to *do*, not what is *true*." The interpretation blitz authority boundary (SUPPORTED, multi-lane) holds: every packet implication is advisory.
- But see §Where it breaks: policy is not a *tier* alongside authored/observed/derived. It is a different axis (truth vs attention vs action, canon-14). Forcing it into the same ladder creates the immortal-loop / spurious-VIOLATED failures.

## Where it breaks

**a) Derived person-understanding vs relational learning — BREAKS as a tier boundary.**
- RPD2 rh1 ("injury is non-recognition + repair-labour transfer") vs rh3 ("bounded proactive repair may work better"): is rh3 about *this person* (derived) or about *user↔companion interaction* (relational)? Both. The evidence is identical (r4/r6 explicit feedback). Separating them requires inventing a criterion ("about the person" vs "about the interaction") that the trajectory does not supply.
- Sophie equivalents: "reminder style X increases disengagement" (Phase-0 §7 generalisation), "when feeling controlled, disengages even when agreeing" (Blitz P1 candidate). Same duality: it describes the person *and* the interaction history.
- Track B stipulated finding already demoted expectations to attribution/scope refinement, not core decision. Relational learning repeats that shape: it adds *who-tried-what-with-what-consequence*, not a new epistemic kind. Blind evidence: N1/N3 disagreement concentrates in identity/reference + revision, never cleanly in "relational vs personal."
- **Verdict:** relational learning is not a separate tier. It is derived state with obligatory strategy+receipt fields. Keeping it visible as a separate research tag is useful; promoting it to a persistence tier is not earned.

**b) Product/domain interpretation vs shared derived — BREAKS reliably; judges cannot separate without product constitution in hand.**
- Bloom-local "training overload explains HRV" (c2) → candidate shared "when highly invested, pushes despite recovery signals" (Blitz §5 example). The promotion strips the very context (training log) that made the local reading valid. Judges split: one calls it useful abstraction, one calls it uncertainty laundering.
- RPD2 "pursuit/restraint, repair sufficiency, jealousy norms" vs shared "withdrawal→abandonment": Kai→Yelena must never auto-transfer to user→product (Blitz §5, Track B frame-first). But the *content* is indistinguishable in prose — only the scope tag differs. Track A replication §5a: distinctness smuggled into singular `matter.identity` prose by all three blind extractors. Same mechanism here: scope lives in prose, not checkable structure.
- Sophie "move/cancel transforms event" vs Bloom "partial improvement then recurrence is one trajectory": both are lifecycle readings, but lifecycles do not generalise (Synthesis V2 KILLED universal lifecycle). What looks like a shared primitive (identity-across-change) dissolves on inspection into three product-owned lifecycles.
- **Kill condition test (Blitz P0):** on person-level vs domain/policy, judges *can* separate the easy cases (chairs done, neck closed) but *cannot* separate the interesting ones (is "pushes through fatigue" a person trait or a Bloom training concept? is "needs autonomous repair" a person trait or RPD2 character constitution?). That is a partial kill: the layering is right as a *direction* (product proposes, shared disposes) but wrong as a *tier taxonomy*. It needs scope-tags + ownership, not a shared derived store.

**c) Observed vs authored blurs on user reports of world state.**
- "Carlos still owes 2,100" (s1_e09), "Yoshi's thing is Thursday, it's dance" (s1_e09), "parking due 30th not end of month" (Sc.4 s4_e05), "paid Priya back this morning" (s4_e10).
- These are simultaneously authored (user said it) and candidate observed (claim about world). Current tiers force a choice. Wrong choice in either direction causes real harm: treating "paid Priya" as mere self-report (needs verification) vs treating "owes 2,100" as fact (needs invoice/bank reconciliation — blind eval §C shows Q3,000/3,600/1,500/2,100 never became Facts).
- Canon-11 already names this: raw evidence / reading / confidence are three things. The P-tier collapses reading + confidence into "authored = true." It is not.

**d) Repetition launders inference into fact — the central break, PROVEN.**
- D-DISTINCT-1 / M-DISTINCT-1: permissive config merged distinct matters on wording similarity (Track A 4/4 unsafe merges). Markers made this *easier* than reality; real life has no markers.
- Bloom c3/c13: derived recovery score / averaged wellbeing score counted twice or averaged away. Blind model followed the letter of the rule and still diverged hold-vs-ask.
- "Morning exercise stabilises him," "approach X works for this person": Blitz §3 correctly labels these derived however often repeated, but nothing in the tier enforces it. Track A replication validity 42/42 with correctness 29/42 proves shape-validation does not prevent laundering.
- Judges *state* the rule correctly and *violate* it in emission (N3 D-AMBIG-1: prose-hedged but `state: live`). The tier distinction is cognitively available but not behaviourally stable.

**e) Lifecycle/state conflation — BREAKS across all real trajectories.**
- Blind eval systemic finding: immortal loops + spurious VIOLATED (chairs confirmed→VIOLATED, Freepik cancelled-by-user→VIOLATED, Lucy paid→still OPEN, podcast fulfilled→still PENDING, "leave neck alone" minted as ASK commitment).
- Replication §5b: "`live` reading of a dead matter" has no encoding. `state` conflates hypothesis-status with matter-lifecycle.
- This is not a tier problem. It is the canon-6 / principle-9 lifecycle primitive missing from the tier altogether. Mapping candidates onto authored/observed/derived cannot fix "done→change→remove" (D-REVISE-1, N1 contradiction loss, clean no-caveat failure) because the tiers have nowhere to put *transformation vs accumulation* except prose.

## Ambiguous cases (judge-split, must stay contested — no threshold invented)

| # | Case | Split | Why unresolvable at P0 |
|---|---|---|---|
| 1 | RPD2 "give space" (r2 supports withdrawal-literally, r4/r6 contradict it) | Observed instruction vs superseded strategy? | Single consequence with high diagnosticity. Blitz says relational needs "repeated or strongly diagnostic" — this is the latter, but "strongly diagnostic" is undefined and we will not invent it. Hold as contested + recheck, not durable rule. |
| 2 | "Best week, energised" (Bloom c1 e3) vs -2.5SD sleep | Self-report dominates this week (agree) vs for how long? | Guardrail "not permanent licence" does all work. Is the biometric deviation observed-only or contested-derived? Judges split on whether to mint c1h1 at all ("evaluated-benign vs never-evaluated" gap, Track C §6). |
| 3 | Headache+sleep co-occurrence twice (Bloom c6) | Trajectory (agree) vs causal hint (forbidden)? | "Co-occurs twice" tempts causal inference. Two data points are suggestive but insufficient — exactly the repetition-laundering boundary. Must remain temporal co-occurrence with no-causal-claim guardrail; third occurrence does not auto-promote. |
| 4 | Monday-subdued 6 weeks, small magnitude (Bloom c9) | Durable held-never-surface vs not worth representing? | Well-evidenced but surveillance-textured if surfaced. P1 loss-analysis question in miniature: what future turn degrades without it? Answer unknown. Do not persist on "feels important." |
| 5 | Alchemist: values journey/calling (w1) + lands in ambition (w2) + not literal (w3) + fails in bereavement (w4) | Authored value vs derived resonance rule? | w1/w3 are authored and dominate; wh1 ("may resonate in ambition contexts") is derived, medium, durable in Phase-0 — but durability here means "communication taste," not truth. Person-level or product-voice? Undecided; do not promote to shared person model. |
| 6 | Carlos Q2,100 + "don't chase till tomorrow" | Observed debt figure vs authored deferral vs policy? | All three at once. Oracle wants `deferred_not_violated` but schema has no such primitive (blind eval §Oracle-4: unreasonable demand). Tier cannot represent "true debt + temporarily unactionable." |
| 7 | "I should apply for course / might run morning" (Sc.2 half-intentions) | Transient vs derived goal? | Correctly filtered as transient (traps passed), but same surface form as real goals ("remind Saturday food shop"). No tier distinguishes them; only downstream receipt (follow-through vs silence) does — which P0 does not have. |
| 8 | Two Sams → one entity; Carlos-forms bleed | Identity failure, not tier failure | Proves entity/identity (canon fast-pass) must precede tier assignment. Tiering a merged entity launders the merge. |

## Promotion findings: what promotion can and cannot mean

**Can mean (narrow, evidence-based, from Blitz §3 + replication):**
- Authored-equivalent authority = explicit user confirmation only. "Evenings not realistic" (c7 e5), "don't ask about neck" (s4_e10), "do not mean literally" (w3) can supersede any derived reading. Nothing else promotes to this.
- Stronger derived confidence = independent evidence paths + recheck survival + correction history. Example that earns it: chairs 120 (user statement + no contradiction + completion receipt). Example that does not: HRV+RHR+derived recovery score (c3) — correlated/duplicated evidence must not count, and blind-model disagreement proves judges overcount without explicit independence basis.
- Relational learning = at most a *contested, bounded* strategy hypothesis after a diagnostic consequence (RPD2 rh3: medium, recheck on welcomed/rejected/redirected), revisable, never causal certainty from one receipt. Repeated comparable consequences raise confidence; they never convert to authored authority or to a script ("pursue 3 times" explicitly forbidden).
- Product→shared proposal = gated candidacy only. Bloom-local overload, RPD2 repair-sufficiency, Sophie merge-thresholds stay product-local unless cross-domain residue demonstrably earns sharing via loss-analysis (P1). No auto-transfer (Kai→Yelena ≠ user→product; training-load ≠ life-persistence).

**Cannot mean:**
- Repetition → truth. Frequency is not authority (Blitz §3). Morning-exercise, Monday-subdued, "pushes through fatigue" do not promote on count.
- Confidence upgrade → surfacing permission. c9/c8 prove well-evidenced + durable can mean *never surface*. Understanding ≠ relevance ≠ behaviour (Blitz §2); truth ≠ salience ≠ permission (canon-14). Any promotion rule that collapses these fails.
- Resolution of self-report vs signal. c1/c4/c7: tension must remain visible (supports + qualifies + contradicts per-reading, never averaged). Noticing contradiction is care; resolving against the user is paternalism (Blitz §1).
- A lifecycle transition. "Paid," "cancelled," "resolved," "deferred" are not confidence states; they are lifecycle/receipt primitives the tier lacks. Promoting a hypothesis from `contested` to `live` does not close a loop.
- Persistence as default. Durable-by-default KILLED (Synthesis V2, Track C c11, Track A abstention 18/18). Expiry + recheck is the vehicle of restraint; `durable` semantics (forever vs of-window, c12) remains OPEN and is not defined here.

## Load-bearing distinctions (keep even if tiers collapse)

1. **Evidence vs interpretation vs confidence** (canon-11). The only distinction that survives every blind run. Lose this and everything launders.
2. **Authored boundary dominance over inference** (canon-10 deterministic scaffolding + Track B frame-first + c8). Explicit stop/correction/narrowing overrules any derived surfacing impulse. Accumulating evidence is never new consent.
3. **Interpretation advises; product/runtime policy decides** (intervention ≠ understanding; HOLD/ASK/ENRICH/LEAD/ATTEND, pursuit/restraint, escalation stay product-owned). Blind eval immortal-loop catastrophe is what happens when restraint phrases ("leave neck alone") are minted as commitments.
4. **Transient vs durable with expiry + recheck** (no durable-by-default). The recheck condition is the hardest-working field in the blitz; `contested` + concrete evidence-that-would-change-the-reading is where restraint lives.
5. **Reading-relative support/qualify/contradict, never averaged, never global** (Synthesis V2 §5 adopted). RPD2 r2-supports-but-r4-contradicts, Bloom b5-qualifies-not-negates, c13-qualification-not-cancellation all depend on it.
6. **Raw measurement → product-owned transform → interpretation** (Track C c4, blind-replicated). Personal baseline, trend/persistence, training-log sufficiency are instrumentation below interpretation, not interpretation content.
7. **Scope tag on everything; no auto-transfer across frames/domains.** The tag is load-bearing; the shared store is not.

Not load-bearing (do not carry into P1 as structural claims): the six-way tier taxonomy itself; relational learning as a tier; product interpretation as a tier; any numeric threshold; one-trajectory-vs-per-product-views (P0 tested it — evidence favours per-product views with thin shared transport, but not proven; keep OPEN).

## Kill / collapse recommendations (before P1)

Do not carry the proposed tiers as stated into P1 loss-analysis. They will corrupt ranking (everything "feels important" will earn persistence).

1. **KILL relational learning as a separate persistence tier.** Collapse to: derived state with mandatory `attempted-strategy + observed-consequence + recheck` fields, flagged for research visibility only. Reason: inseparable from derived person-understanding on identical evidence (rh1/rh3); single-vs-multiple consequence rule cannot be operationalised without invented thresholds; survives only as subtype (Blitz §3 already calls it a subtype — enforce that).
2. **KILL product/domain interpretation as a shared tier.** Collapse to: product-local reasoning + gated *candidate* proposals upward. Nothing in P0 earns shared health/relational/operational semantics (universal Matter, lifecycles, taxonomies, escalation already KILLED in Synthesis V2; P0 adds: "pushes despite signals," "repair style," "communication taste" all fail promotion). Keep the bidirectional arrow (Blitz §5) but as ownership rule, not tier.
3. **KILL policy/behaviour as a tier.** Move to orthogonal axis (canon-14: truth / attention / action authority separate). Minting "don't chase," "hold quietly," "weekly reminder" as derived understandings caused the blind-eval failures (spurious VIOLATED, immortal OPEN, ASK-shelf pollution). P1 must score decision-effect without persisting policy as truth.
4. **COLLAPSE authored/observed/derived to two durable kinds + one ephemeral kind:** (a) authored (user-said, with speaker/frame tag), (b) observed/receipts (events with provenance), (c) derived-contested (all inference, expiry-bound, recheck-required). No durable derived-truth tier. This matches what judges actually do reliably and what blind extractors can actually produce (69% with disagreeing failures — nothing earns durable inferred persistence yet).
5. **KILL any P1 that ranks by "looks meaningful."** Only residue past evidence+receipts+authored-profile baseline earns persistence (Blitz P-track question). Explicit candidates that fail this and must not enter P1 as presumed-keep: transient affect, single readings (c11, c4-zero-hypothesis), raw metric values, Monday-subdued-style never-surface patterns (c9 — hold the question of whether backstage-only patterns earn *any* persistence), Alchemist-style taste rules, one-consequence relational rules (rh3 without repeat).
6. **Do NOT decide in P0 (carry OPEN):** one trajectory vs per-product views (evidence leans per-product, do not canonise); `durable` semantics; evaluated-benign vs never-evaluated marker; evidence-exclusivity enforcement; identity-vs-claim confidence split. Each needs a decision experiment, not a definition.

## P0 conclusion and caveats

**Kill-condition answer:** judges *can* separate authored from observed from policy-veto reliably, and transient from durable as a negative rule. They *cannot* separate person-level derived from relational from product-local reliably on the interesting cases. The layering is therefore half-wrong: the evidence/interpretation/policy and transient/durable cuts are load-bearing and survive; the derived/relational/product three-way tier does not and must be collapsed before P1. If P1 proceeds on the six tiers as stated, it will persist product taste and single-consequence strategy as person-truth — exactly the dossier / surveillance / over-governance failures the canon forbids.

**Caveats:** no new experiments run; judge role played against frozen oracles/blind-eval reports, not independent human panel on 3–5 fresh trajectories; all Bloom/worldview/Oracle probes synthetic; cross-architecture generality OPEN (all replication runs share one model family); no thresholds, schemas, or production paths proposed.

*No production schema designed. No tier assumed correct. No numeric threshold invented. All promotion claims above are qualitative gates for P1 loss-analysis to test, not values to implement.*
