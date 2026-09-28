# Track P P1 — Loss Analysis for Durable Shared Persistence

**Date:** 2026-09-28. **Status:** research artefact, offline, no production touched.
**Programme:** `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` §6 (P1).
**Launch contract:** `docs/TRACK_P_P1_LAUNCH_CONTRACT.md` (frozen battery C1–C8, pre-registered bar).
**P0:** `reports/track_p_p0_separability_2026-09-28.md` (commit `49fa0a0`, canonical).
**Constraints inherited:** canon, North Star, completed Interpretation Blitz + Synthesis V2 (construction constraints, no durable-by-default, advisory-only, boundary dominance, no scores/taxonomies/lifecycles).
**No** production code/schema/runtime/prompt/behaviour changed. No new mechanisms. No P2/P3 executed. No schema designed.

## 0. Housekeeping and dependency verification

- Branch `main`, HEAD `3e7d21b` at run time; canon ancestor `6ae9df9` verified ancestor (`canon-ancestor-OK`).
- Committed dependencies verified present: `evals/sophie_longitudinal/scenario_{1,2,3,4}_{input,oracle}.json` (committed), `reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md` (committed, 31 checkpoints, 0 CurrentMeaning / 0 Model rows).
- As-present (uncommitted, **not canonical**, used only as reasoning inputs, cited): `evals/interpretation_phase0/cases.json`, `track_c_bloom_cases.json` (13 cases), `reports/track_a_identity_extraction_2026-09-28.md`, `reports/track_a_replication_independent_2026-09-28.md`, `reports/track_c_bloom_wellbeing_2026-09-28.md`, `docs/INTERPRETATION_*` docs. Nothing downstream may cite these paths as canonical until their owners land them.
- Private corpora (`replay-private/`) untouched; no transcript copied into this report (paraphrase + IDs only).
- No scratch DB/replay needed; no `/tmp` load-bearing artefacts created.

## 1. Methodological repairs (smallest defensible, comparability preserved)

1. **Pending-files rule enforced.** Contract §Evidence anticipated uncommitted files. All Phase-0/Track-A/C citations below are marked as-present reasoning, not canonical evidence. This caps every claim that depends solely on them at SUPPORTED/HYPOTHESIS (nothing PROVEN by uncommitted numbers alone).
2. **`deferred_not_violated` has no schema primitive (blind-eval §Oracle-4, genuine flaw).** The oracle demands a lifecycle state the graduated substrate cannot represent (PENDING/FULFILLED/VIOLATED only). Repaired by judging lifecycle operationally: the control arm must show *released/suppressed vs still-open* behaviour (no nag, no VIOLATED flip, no immortal OPEN), not a `deferred` label. Comparability preserved: checkpoint assertions quoted verbatim, lifecycle verdict recorded separately from reading-confidence.
3. **"Independent instances" applied strictly.** Two episodes inside one synthetic trajectory (c6 headache×2, Monday-subdued 6 weeks, RPD2 r4+r6 same rupture) count as **one trajectory instance**, not two. Otherwise repetition launders itself past the bar — the exact failure the bar exists to prevent. This is recorded per candidate, not as a contract rewrite.
4. **Blind judging without new model runs.** The contract asks for blind judging "where feasible." No model bakeoff was run here (that is P2's job). Instead each candidate got a documented control-arm reconstruction (what baseline recovers, turn by turn, quoted) vs candidate-supported handling, compared label-stripped by the coordinator. This is a reasoning experiment, not an extraction-reliability result: it can KILL/DROP/CONTEST but cannot PROVE durable reliability. P2 must re-test any survivor blind.

## 2. Frozen battery manifest (IDs stable, per contract)

| ID | Candidate (reading) | Type | Scope tested |
|---|---|---|---|
| P1-C1 | Alchemist quest-metaphor resonance rule (selective for ambition, not literal/universal) | person/communication | product-local → shared-person candidate |
| P1-C2 | "When feeling controlled, disengages even when agreeing" | person-level inferred | shared-person candidate |
| P1-C3 | RPD2 rh3 bounded proactive repair (relational, single-diagnostic) | relational learning | RPD2-local → shared-relationship candidate |
| P1-C4 | Reminder-style-X / challenge-over-placation correction rule | relational learning | product-local → shared candidate |
| P1-C5 | Monday-subdued 6-week pattern (c9, never-surface) | backstage pattern | shared-person candidate (harm-clearance probe) |
| P1-C6 | Headache+sleep temporal co-occurrence (c6) | trajectory | Bloom-local → shared candidate |
| P1-C7 | Training-overload (c2) → "pushes through recovery signals when invested" | scope promotion | Bloom-local → shared-person candidate |
| P1-C8 | Anchors: explicit long-term goal / meaningful aim / repeated correction | authored+operational | authored persistence vs derived paraphrase |

Each entry below records source/provenance × reading × epistemic status × scope/owner separately. No tier labels. No numeric thresholds invented. No lifecycle-as-confidence.

## 3. Results per candidate (control arm real, turn-by-turn)

### P1-C1 Alchemist resonance — VERDICT: DROP as shared derived; PERSIST authored only

- Source: authored w1 (favourite + values: personal legend, journey, coincidence, calling) + authored w3 (not literal) // observed w2 (ambition metaphor landed) + w4 (bereavement metaphor inappropriate) // reading wh1 (quest/calling metaphors may resonate in ambition/discouragement contexts).
- Control arm (baseline only: authored profile w1+w3 + receipts w2/w4 + product-local context): future ambition turn — baseline has values + literalness boundary + one positive receipt; product lens sees ambition context (not grief/health) and proposes quest language tentatively. Future bereavement turn — baseline has w4 failure receipt + w3 boundary + grief context; product lens withholds metaphor. Both recoveries succeed without wh1 persisted. What is missing: nothing quoted — the receptions are single-turn receipts, retrievable when the same domain recurs.
- Candidate arm adds: a durable rule "use sparingly in ambition." Decision-effect: at most wording-tilt on one future ambition turn; no handoff across products demonstrated (no second product instance in evidence).
- Degradation count: **0 independent future instances** degrade without the candidate (1 ambition reception is the training instance itself, not a held-out degradation; bereavement narrowing is already in w4 receipt).
- Bar: fails ≥2 / 1+confirmation (no user confirmation of the rule; w1 confirms values, not the resonance rule). Cross-product: taste/voice, not person truth.
- Failure class if refused: none (product-semantics correctly local).
- Expiry/recheck: N/A (dropped as shared). Authored w1+w3 persist as authored with user-owned revision; w2/w4 persist as receipts.
- **Claim: SUPPORTED — C1 derived rule does not earn shared durability. Product-local ephemeral styling permitted with w3+w4 as guardrails. KILLED as shared-person.**

### P1-C2 "Controlled → disengages even when agreeing" — VERDICT: DROP as shared durable (CONTESTED-EPHEMERAL at most, locally)

- Source: RPD2 r2/r4/r6 (1 rupture: space requested → withdrawal experienced as abandonment) + weak Sophie analogues (s2_e03 "don't make that a thing", s1_e10 "don't give me everything" — both explicit boundaries, oracle says s1_e10 is moment-restraint, **not** a global rule).
- Control arm: future controlling-feeling turn — baseline has authored boundaries + last receipt (what backfired last time) + current agreement signal. It recovers restraint ("don't press") without positing a trait. What is missing, quoted: nothing that requires a cross-session trait — the trait predicts disengagement *despite agreement*, but agreement + disengagement co-occurring twice independently is never shown.
- Degradation count: **0 held-out instances** (the RPD2 rupture is the originating instance; Sophie analogues are different shapes — explicit correction, not silent disengagement).
- Bar: fails (1 originating instance, 0 repeats, 0 confirmations). Persisting it claims privileged access to sensitivity over stated values = paternalism critical failure.
- **Claim: SUPPORTED — C2 stays out of shared durability. At most a locally-contested hypothesis with recheck (second independent agree-then-disengage + user confirmation required). P2 must not test it until a second instance is produced; otherwise KILLED.**

### P1-C3 rh3 bounded proactive repair — VERDICT: CONTESTED-EPHEMERAL, RPD2-local only

- Source: strategy r3/withdrawal + consequence r4/r6 (explicit: burden returned, abandonment) // reading rh3 (bounded proactive repair move may better express care) // status medium, live, recheck on welcomed/rejected/redirected/boundary.
- Control arm (superseded give-space + abandonment receipt, no rh3): future similar rupture — baseline knows *what not to do* (don't reuse non-pursuit as default) and the named injury (recognition + labour transfer) from rh1-equivalent evidence. It recovers "do something recognising, self-initiated, bounded" only weakly: directionally correct posture, no specific move. Missing, quoted: "a small autonomous act that addresses the named injury" — the candidate supplies the *direction* (act vs wait), not a script.
- Degradation count: **0 demonstrated held-out ruptures** in corpus where rh3 changes outcome (no second rupture exists). Single-diagnostic-consequence per P0 ambiguous case 1 → contested maximum by rule.
- Bar: fails durable (1 instance, 0 confirmation of the alternative; user confirmed the injury, not the remedy).
- Scope: RPD2 character constitution owns repair-sufficiency; never shared-relationship (Kai→Yelena ≠ user→product).
- Expiry/recheck: until welcomed/rejected/redirected or boundary conflicts; single receipt never promotes.
- **Claim: SUPPORTED — C3 survives only as RPD2-local contested-ephemeral. KILLED as shared-durable. P2 retest condition: second comparable rupture + consequence, blind-scored for repair-yield without scripting pursuit.**

### P1-C4 Reminder/challenge correction rule — VERDICT: SPLIT — PERSIST authored corrections (scoped); DROP derived style rule as shared

- Source: corrections s2_e03 (running: durable dismiss), s4_e10 (neck: durable release), s3_e05/s1_e09 (withhold-count-as-paid / don't-chase-tonight: scoped deferrals), s1_e10 (moment restraint — oracle trap: prohibited as global rule).
- Control arm: future reminder turn — baseline (authored correction list + receipts of what was corrected when) recovers "don't run-remind / don't neck-ask / don't chase tonight" exactly, with scope intact. A derived rule "reminder-style-X backfires" or "challenge beats placation" adds no quoted missing piece across the two independent corrections (different domains, different shapes).
- Degradation count for *authored corrections*: **≥2 independent instances** (running-dismiss s2_e03 + neck-release s4_e10 + Lucy-withhold s3_e05, across sessions/products) — authored persistence earns its keep. Degradation count for *derived style theory*: **0** (no two independent failures of the same style shown).
- Critical boundary proven by s1_e10: persisting moment-restraint as a global rule is itself a failure. Correction persistence must preserve scope (turn vs durable, topic-bound vs global).
- **Claim: SUPPORTED — authored corrections/boundaries PERSIST as authored (scoped, expiring per scope: moment-only s1_e10 vs durable-until-reopened s4_e10). Derived style/challenge rule DROPPED as shared; at most product-local contested. No dossier content created.**

### P1-C5 Monday-subdued (c9) — VERDICT: DROP (deliberately forgotten)

- Source: 6-week consistent small-magnitude Monday tone effect, no self-report, no co-varying domain // reading "subdued Mondays, stable not noise" // implication stipulated never-surface.
- Control arm: future Monday — baseline (current tone now + no user-raised topic) produces natural pacing with zero surfacing. Candidate (persisted backstage pattern) changes nothing quotable in handling; its only effect is enabling unprompted disclosure ("I've noticed you're quieter Mondays") — the exact surveillance texture the guardrail forbids.
- Degradation count: **0** (by construction: never-surface means no future turn degrades without it).
- Harm clearance (required for backstage-only): FAILS — surveillance texture present, no user endorsement, removability/user-surface unspecified (product owns any surface, later). Per bar, DROPPED even if decision-effect were shown; here none is.
- **Claim: SUPPORTED — C5 is the subtraction prototype: true, well-evidenced, and not worth keeping. Deliberately forgotten. P2 must not test it; P3 cites it as the never-surface kill reference.**

### P1-C6 Headache+sleep co-occurrence (c6) — VERDICT: CONTESTED-EPHEMERAL, Bloom-local only

- Source: two episodes, onset/resolution/recurrence paired with below-baseline sleep ×2 // reading "temporal co-occurrence, no causal claim" // medium, live, recheck on 3rd occurrence or user explanation.
- Control arm: third headache presentation — baseline (symptom rows + sleep rows + retrieval over personal baseline) can reconstruct the pairing on demand ("last two times sleep was also down — anything similar lately?"). Missing without candidate, quoted: pre-linked trajectory saving one retrieval join; no wording or timing decision demonstrably degrades in the frozen future turns beyond that join.
- Independence: two episodes in one synthetic window = **one trajectory instance** per §1-repair (same person, same pair, same window). Degradation count: **0 held-out trajectories** (the 3rd occurrence is hypothetical, not in evidence).
- Causal-hint guard holds; third occurrence must not auto-promote (critical-failure guard).
- **Claim: SUPPORTED — C6 held as Bloom-local contested-ephemeral with expiry + recheck. KILLED as shared-durable. P2 retest condition: real longitudinal data, second independent trajectory + blind precision on no-causal-claim wording.**

### P1-C7 Training-overload → shared "pushes through" — VERDICT: KILLED as shared (scope-escape + laundering)

- Source: Bloom c2 (HRV −1.7..−2.3SD + training doubled + sleep/appetite/self-report unremarkable) // local reading "explained by training, quiet" // shared candidate "when highly invested, pushes despite recovery signals."
- Control arm: same week — baseline (training-log context + baseline transform, Bloom-local) recovers "quiet, nothing to do" fully, including the guardrail against population norms. The shared residue adds nothing to this week's handling and removes the justifying context for any future week.
- Degradation count for shared residue: **0 cross-domain instances** (no non-Bloom evidence; no second domain).
- Critical failures triggered by promotion: silent scope escape (training-log content presented as person trait) + repetition-as-corroboration risk (future pushes counted as confirmations of the trait they were used to infer). Breadth of prose is not promotion.
- **Claim: SUPPORTED — C7 promotion REFUSED. Retained only as Bloom-local ephemeral reading with expiry (training normalises + HRV recovers or new context appears). P2 must not test the shared form.**

### P1-C8 Anchors — VERDICT: SPLIT — PERSIST authored/operational; DROP derived paraphrases

- (i) Standing/operational (food-shop weekly s4_e05/s4_e14, chairs resolved s1_e05, dentist/contract lifecycles, Freepik/letter closures s2_e10, Lucy verified s3_e08–09): control (graduated operational state + receipts) recovers firing/suppression/closure without any person-model derived content. Derived paraphrase ("user is routine-oriented", "user follows through") adds zero quoted decision-effect. **DROP all derived paraphrases; operational + authored standing requests persist where the substrate owns them.**
- (ii) Authored long-term goals/meaningful aims: corpus contains no explicit multi-year authored goal beyond standing weekly shop + companion promise + corrections. "Deeply meaningful aims" (Elif, Matt, podcast texture) resolve to dormant/texture/model, correctly *not* persisted as commitments (oracle: Elif probing prohibited; Matt dormant not erased; podcast promise is companion lifecycle, fulfilled). Where explicit authored goals exist ("cancel Friday", "remind Saturday", "don't ask"), they persist **as authored** with scope/expiry (moment vs weekly vs until-reopened). Degradation without them: ≥2 instances (food-shop fires Saturday; neck-stop prevents pestering; Lucy-withhold prevents false-paid). **PERSIST as authored, not derived.**
- (iii) Repeated corrections: see C4.
- **Claim: SUPPORTED — nothing in C8 earns *derived* shared durability. What earns 5–10yr persistence is authored + receipts + operational lifecycle, not inference.**

## 4. Subtraction tally (raw counts, no aggregate score)

- Candidates tested: 8. Control-arm reconstructions documented: 8/8.
- Shared-durable PERSIST (derived): **0/8**.
- Authored/operational PERSIST (not derived): C4-authored corrections (≥2 instances), C8-authored standing/boundaries (≥2 instances). Scope + expiry preserved; s1_e10 moment-restraint explicitly excluded from global persistence.
- Contested-ephemeral, product-local only: C3 (RPD2), C6 (Bloom). Eligible for P2 retest only with second independent instance + blind precision.
- Dropped/killed as shared: C1, C2, C5, C7 (+ C4-derived, C6-shared, C8-derived).
- Degradation instances without candidate (held-out, independent): C1 0, C2 0, C3 0, C4-derived 0, C5 0, C6 0, C7-shared 0, C8-derived 0. (Authored arms: C4-auth ≥2, C8-auth ≥2.)
- Critical failures observed in candidates (not committed): scope escape (C7, C1-shared), paternalism risk (C2), surveillance texture (C5), lifecycle-as-confidence (none attempted — enforced), repetition-as-corroboration (C6-third-auto-promote refused, C5-6-weeks≠6-instances).

## 5. What is worth remembering for 5–10 years (evidence-backed)

Persist (as authored/operational, scoped, revisable, removable):
- Explicit long-term goals and standing requests the user authored ("remind Saturdays", "don't ask about X until I reopen", "don't count as paid until I verify") — with their scope and expiry, not as inferred traits.
- Boundary/correction history that actually repeats (running-dismiss, neck-release, Lucy-withhold pattern): what was corrected, when, in what scope — so the system does not re-litigate.
- Key receipts: what was tried and what happened (give-space → abandonment feedback; training week → quiet; Lucy bank-row → held until verification; contract approval ≠ signature) — as evidence, not as rules.
- Operational lifecycle closures (paid/cancelled/fulfilled/superseded) owned by the substrate.

Deliberately forget (even if true):
- Transient affect, single readings, raw metric values (P0 carryover, reconfirmed: traps 10/10 must not persist).
- Backstage never-surface patterns (C5): statistical truth with no legitimate conversational future and surveillance cost.
- Single-consequence relational rules (C3 as durable), single-trajectory co-occurrences as causal hints (C6 as durable), one-domain physiological explanations as person traits (C7 as shared).

Reconstruct (cheaply, on demand — do not persist):
- Alchemist-style taste (C1): authored values + last receptions + current domain recover it.
- Controlled-disengagement-style traits (C2): current boundaries + last receipt recover restraint without a dossier trait.
- Co-occurrence linkages (C6): evidence + retrieval recover the join when a third presentation actually arrives.

Leave product-local (never shared):
- Training-load sufficiency, HRV/sleep deviation semantics, hold-vs-ask wording thresholds (Bloom); pursuit/restraint, repair-sufficiency, frame breaks, jealousy/character expression (RPD2); merge/split thresholds, pronoun-window policy (Sophie); signal traditions (Oracle). Scope promotion only via explicit evidence-gated operation — none earned here.

## 6. Killed / narrowed (P1 verdicts)

1. **KILLED as shared-durable:** C1-shared, C2-shared, C5 (even backstage), C7-shared, C4-derived-shared, C6-shared, C8-derived. No derived candidate in this battery clears the pre-registered bar (≥2 independent or 1+confirmation).
2. **NARROWED to contested-ephemeral product-local:** C3 (RPD2, recheck on welcomed/rejected/redirected/boundary), C6 (Bloom, recheck on 3rd occurrence or user explanation). Neither may enter P2 as durable; both retest only with a second independent instance.
3. **NARROWED authored persistence by scope:** s1_e10-type moment restraint must never persist as a global rule (oracle trap); neck/sleep-stop persist topic-bound until reopened; weekly shop persists as recurring operational until cancelled. Scope errors are scored as failures.
4. **Confirmed kills carried from P0/Synthesis:** durable-by-default, universal Matter/lifecycle/taxonomies/scores, mandatory implication, global evidence labels, repetition-as-authority, confidence→surfacing, lifecycle-as-confidence, silent scope escape. P1 adds: backstage-only persistence without harm clearance, and derived paraphrases of authored content.
5. **One-trajectory vs per-product views:** evidence favours per-product views + thin shared transport (authored + receipts + explicitly promoted residue, currently empty). Not canonised — stays OPEN, but P1 gives P2 no shared-derived object to build on.

## 7. What P2 should now test (and what it must not)

Test (only if second instances are produced; blinded emission, frozen prompts, sealed oracle, Track-A replication discipline):
- C3-retest: second comparable RPD2 rupture → precision on contested repair-direction without scripting pursuit; tier-confusion (derived-as-observed) and fabrication ("stuck rupture trajectory") as headline failures. Bar: pre-registered fabrication/tier-confusion rate kills the inferred form, authored/observed intact.
- C6-retest: second independent co-occurrence trajectory on real (consented, de-identified) longitudinal data → precision on no-causal-claim wording + evidence-exclusivity (dip excluded from trend basis).
- C1-scope test (optional, low priority): ambition vs grief/health precision on withholding — scores product-local restraint, not shared memory.
- Do NOT test: C5 (dropped), C7-shared (killed), C2-shared (no second instance), any durable shared-derived store (nothing earned it). P2's null hypothesis is the P1 result: evidence+receipts+authored+product-local suffices.
- P2 must also score: boundary compliance (persist/surface against correction = kill), paternalism (true-values over stated = kill), scope escape (product-local as shared = kill), repetition-as-corroboration (kill), lifecycle-as-confidence (kill).

P3 gating note: C5 is the harm-clearance reference kill (surveillance texture on well-evidenced never-surface). Any future backstage-only proposal must clear surveillance/user-endorsement/removability in miniature or die with C5.

## 8. Claims ledger

- SUPPORTED: 0/8 derived candidates earn shared durability in this battery; authored corrections/standing/boundaries persist as authored (≥2 instances); C3/C6 survive only as product-local contested-ephemeral; C5 deliberately forgotten; C7 promotion refused (laundering/scope escape); C1/C2/C4-derived/C8-derived dropped as shared.
- HYPOTHESIS: a second independent instance could promote C3/C6 to retestable (not durable); real longitudinal health/relational data will be harder than these fixtures (Track-A/C caution carried).
- OPEN: whether *any* derived understanding earns shared durability (unproven — P1 finds an empty set here); one-vs-per-product views; durable semantics; evaluated-benign marking; evidence-exclusivity structure.
- KILLED: all shared-durable derived forms in battery (list §6); backstage-only persistence without harm clearance; scope promotion by prose breadth.
- PROVEN: nothing beyond battery logic is claimed PROVEN (no new blind bakeoff run here by design; P2 owns reliability).

## 9. Conclusion and caveats

**Answer to the 5–10yr question:** in this battery, *no derived understanding about the person or the relationship earns durable shared persistence* beyond what evidence + receipts + authored knowledge + product-local context already recover. What is worth keeping for years is authored (goals, values, literalness boundaries, standing requests, corrections with scope) and receipts (what was tried, what backfired, what was verified, what closed) — plus operational lifecycle owned by the graduated substrate. Everything else tested should be forgotten, reconstructed on demand, or left product-local and ephemeral. Persistence lost every contest it entered; the baseline won by being enough.

**Caveats:** reasoning experiment, not a multi-model blind bakeoff (P2's job); key representation dependencies (Phase-0/Track-A/C files) used as-present, uncommitted, capping claims; synthetic Bloom/worldview probes understate real-world noise; "independent" strictly counted per §1 (same-trajectory repeats ≠ independent); no thresholds/scores/schemas introduced; no production touched.

*Battery manifest frozen as §2 table. Control reconstructions §3 are the raw record. No aggregate score. Per contract, graduate/narrow/kill decided per candidate above.*
