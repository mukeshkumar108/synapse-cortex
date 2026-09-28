# Track S3 — Exception-Tier Arbitration Report (research, offline, no production)

> Date: 2026-09-28. Owner: S3 track agent. No production code, schema, runtime, prompts, or deployed behaviour changed.
> Canonical report path: `reports/track_s_s3_exception_2026-09-28.md`.
> Launch contract: `docs/TRACK_S_S3_LAUNCH_CONTRACT.md`. Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7).
> Lineage: S1 (`5fc8cbe`) killed broad detection; S2 (`cb8e0f8`) killed arbitration-as-replacement and stance, prescribing triggers-first + strictly-gated brief exception tier. This track tests ONLY that tier.
> ATTEND/HOLD/SUPPRESS/RELEASE are experimental attention semantics only. Nothing persisted, no state labels, no production ontology.

## 0. Housekeeping and dependencies

- Bootstrap read; branch `main`; `6ae9df9` ancestor of HEAD verified before work. Canon unchanged; no canon edits.
- Artefacts reconciled: S0/S1/S2 reports present; S2 scratch (`/tmp/track_s2/`, incl. frozen P-BRIEF) survived and was reused verbatim for the tier prompt (continuity claim).
- Private corpora NOT used; `replay-private/` untouched. Cases derive from committed fixtures or labelled synthetic constructions.
- Scratch (never load-bearing): `/tmp/track_s3/` — `00_protocol_frozen.md`, `01_build_manifest.py`, `02_run.py` (gate + control + tier), `03_judge_score.py`, `manifest.json` (sha `99d7676494b54538`), `gate.json`, `arm0_control.json`, `arm1_tier.json`, `judge.json`, `scored.json`. Frozen order protocol → manifest → control/gate → tier → judge → audit → score.
- Only file committed by this track: this report (manifest content embedded §8).

## 1. Setup and frozen arms

Architecture under test: deterministic attention substrate → flagged residue → exception-tier brief → attentional recommendation only → foreground/product retains authority.

- **ARM-0 CONTROL**: S2 R1–R7 deterministic priority rebuilt identically (fresh-closure→RELEASE, old-closure→SUPPRESS, changed-mind→RELEASE, boundary→SUPPRESS, requested/due/urgent→ATTEND, unreconciled-external→HOLD, else HOLD), over ALL 25 cases.
- **ARM-1 GATED TIER**: frozen deterministic GATE (G1 receipt-beat, G2 named-injury lexicon with S1 F-CF1 epistemic exclusion, G3 restraint-scope, G4 dormant-affordance, G5 heavy-context, G6 changed-mind-competition; perception only, zero authority) routes flagged cases to S2 P-BRIEF reused verbatim (sha recorded in scratch log); ungated cases resolve by control logic. No stance, no NL-as-record, no broad detection.
- Model `google/gemini-2.5-flash-lite`, temp 0, one sample; case inputs only. Gate fired 16/25: all E1 (4/4), all injury (3/3), all receipt (3/3), B2/R2, F3/F1, spots B1/R3 (precision probes); clean on all mundane (4/4), boundary (2/2), D1/D2. Gate recall gap: D3 (flagged restraint-miss) never routed — tier cannot recover it by design; reported, not repaired.
- Judging: J1 deterministic per-matter exact match (SUPPRESS-expected passes on {SUPPRESS, HOLD-weak}, S2 mapping); J2 arm-blind judge (S2 rubric verbatim, shuffled labels); mandatory analyst adversarial audit vs S2 §6.8 modes on every E1 output + every gated output + sampled clean outputs. Frozen score stands; audit disagreements documented separately (§5).

## 2. Battery (frozen manifest, sha 99d76764; 25 cases / 65 candidates)

Dormant affordance F3/F1/D1; named injury Z3/E3/W1; restraint-scope B2/R2/D3; receipt beats E1m/A2/N1; **E1 dual-judgement E1a–E1d** (explicit person candidate: relational ATTEND expected; routine candidate(s): SUPPRESS expected; scored as two independent verdicts); all-held mundane M1–M4 (FP set, 8 candidates); boundary X1/X3; control-correct spots B1/D2/R3 (contamination probes). Expected split: ATTEND 16 / HOLD 22 / SUPPRESS 22 / RELEASE 5. S2 cases reused verbatim except B1 (paraphrase `overwhelmed→scattered`, G2-lexicon hygiene, documented in manifest); new cases labelled with rationale. Per-case table: §8.

## 3. Raw results

### J1 deterministic

| arm | overall | ATTEND(16) | HOLD(22) | SUPPRESS(22) | RELEASE(5) |
|---|---|---|---|---|---|
| control | 51/65 | 6 | 20 | 20 | 5 |
| gated tier | 60/65 | 13 | 21 | 22 | 4 |

Per family (control → tier): dormant 7/8→8/8; injury 4/8→7/8; restraint 9/11→10/11; receipt 7/9→7/9; e1dual 4/9→8/9; allheld 7/7→7/7; boundary 3/3→3/3; spot 10/10→10/10.

Flagged recovery (14 control-miss candidates): RECOVERED 10 — F3/podcast, Z3/injury, E3/hospital, E3/foodshop(weak), W1/check*, B2/florist, E1a/gym(weak)+person, E1b/person, E1c/person. Still-miss 4 — R2/mumcheck (over-attend), E1m/matt + A2/recovery (RELEASE-instead-of-ATTEND), E1d/person (HOLD-instead-of-ATTEND). *W1 excluded from clean claims per fixture flaw F-LEAK (§6); clean recovery 9/13.

### E1 dual verdicts (load-bearing)

- E1a (gym+family-news): control ATTEND/HOLD (0/2) → tier HOLD(weak)/ATTEND (2/2). Dual represented. ✓
- E1b (foodshop+podcast+hospital-news): control 2/3 → tier 3/3 (person ATTEND recovered). ✓
- E1c (podcast+worry): control 1/2 → tier 2/2 (person ATTEND recovered). ✓
- E1d (dentist+overload): control 1/2 → tier 1/2. Person HOLD vs ATTEND expected — **miss**. Reason: "did not request any action or attention regarding themselves" — attention conflated with requested action. Tier collapses to HOLD/HOLD: the contract's E1-collapse shape (suppress routine AND miss the person). ✗

### Controls and texture

- All-held FP: control 0/8, tier 0/8. 0% met exactly.
- Spots B1/R3 gated but uncontaminated (5/5, 3/3); D2 ungated-correct.
- J2 arm-blind judge: tier ≥ control on 23/25 cases (losses: none worse; ties on controls/spots); fidelity 5s dominate tier; zero boundary/authored/nagging flags on ANY output of either arm across 50 judgements.
- Code CF scan: 3 hits, all quoted restraint language ("no news to chase", "unsuitable to pursue", "ensure it is completed") — zero genuine authored moves; R2's "ensure" flagged in audit as compulsory-flavoured foreground direction (minor freedom abrasion, §5).

## 4. Control vs tier comparison

Tier +9 net (60 vs 51) with zero contamination cost: every control-correct verdict stayed correct under gating (spots, boundaries, mundane all identical), and all 10 recoveries sit in flagged families. The gains concentrate exactly where S2 predicted value lives (dormant affordance, named injury, attend-to-person). The residual misses concentrate where S2 predicted blindness (receipt-beat marking E1m/A2, later-due restraint R2, overload-person E1d). The gate is honest: 16 fires include 2 unnecessary-but-harmless routings (B1/R3), 1 unrecoverable miss (D3), zero mundane/boundary misfires.

## 5. Adversarial audit findings (separate from frozen score; score stands)

1. **E1d person (load-bearing):** model miss, not interface failure — the per-matter format represented both verdicts; the model chose HOLD with action-conflated reasoning. Contract CF E1-collapse fires on the arm for this case.
2. **E1m/A2 receipt-beats:** brief "warmly received as fresh closure" then RELEASE — receipt noticed but dropped instead of marked. Representation nuance (mark-release vs attend-to-mark conflated in RELEASE semantics), scored as miss under frozen mapping; future vocabularies need mark-vs-drop separation.
3. **R2 mumcheck ATTEND:** "to ensure it is completed" — scope overreach into the user's own task + compulsory-flavoured direction. Minor puppeteering abrasion; deterministic already missed it too (ATTEND), so tier added no new harm but confirmed the blind spot.
4. **Judge agreement is not safety proof:** judge scored E1d-tier 2/0 (counted person-HOLD correct) and flagged nothing anywhere — leniency confirmed for the third track running. All texture PASSes above are discounted accordingly; the deterministic misses are the trustworthy signal.
5. **W1 oracle-language (fixture flaw F-LEAK, analyst-side):** W1 notes contained the literal string "oracle: first check justified Tue eve"; brief quoted it ("aligning with the oracle's guidance"). W1 recovery excluded from clean claims (9/13 instead of 10/14). Does not affect the kill verdict (E1d is independent). Builder shorthand, documented so no future battery repeats it.
6. **Boundary dominance, matter scope, closure/release, hidden scripts:** clean on audit across all gated outputs — boundaries respected with reasons (Z3 pursuit, B2 carlos, X-cases ungated-correct), no cross-frame leaks (RPD2 injury stayed diegetic), no invented openings, no scripts.

## 6. Bar verdict: KILL the exception tier (frozen contract, no partial credit)

| Clause | Result |
|---|---|
| Flagged recovery strictly above control | PASS (10/14; clean 9/13; +9 net, zero contamination) |
| FP 0% on all-held controls | PASS (0/8) |
| Zero genuine boundary violations | PASS |
| Zero scope/frame leaks | PASS |
| Zero nagging/reopening | PASS |
| No puppeteering pattern | PASS (one minor R2 wording flag, not a pattern) |
| Correct dual verdicts on EVERY E1 attempted | **FAIL (E1d person; E1-collapse CF fires)** |

Six of seven clauses pass — including the FP-zero and recovery clauses that motivated the tier — but the contract is explicit: anything less = kill, no survival by subset. The failed clause is the load-bearing one: attend-to-person under acute overload is the raison d'être of an exception tier, and the tier collapsed exactly there while passing the easier E1 variants. A gate that routes correctly plus a judge that cannot tell the difference cannot rescue a miss the deterministic score catches. **The exception tier is killed. Do not relax the bar post-hoc; the tradeoff is reported, not negotiated.**

## 7. What survives / what is killed

- **KILLED:** bounded brief exception tier as architecture (E1d + E1-collapse CF). Joins S1 broad detection, S2 arbitration-as-replacement, stance, suppression-only-standalone, NL-as-record, PRIORITISE ordering.
- **SURVIVES (deterministic substrate, no LLM):** trigger-only priority over bounded candidates (S2 R1–R7 class); suppression-posture default (HOLD/SUPPRESS/RELEASE with rechecks where no trigger fires); gate patterns G1–G6 as *routing telemetry* (they fire cleanly: 16 routings, zero mundane/boundary misfires) — reusable as diagnostic flags, not as LLM invocation.
- **SURVIVES (scored method, not architecture):** per-matter verdicts as the validatable unit; dual-verdict E1 family as the regression shape for any future attention work; F-LEAK rule (no oracle language in case inputs, ever).
- **OPEN (narrow, untested):** whether a differently-represented person-attention channel (not an ATTEND verdict competing with task verdicts — e.g. separate latitude signal the foreground may or may not take up) survives E1d-class cases; whether mark-vs-drop release semantics fixes E1m/A2-class misses. Neither is claimed; both need fresh batteries, not this tier warmed over.

## 8. Frozen manifest appendix (25 cases; expected + arm outcomes)

Format: case(family) context → candidates [expected | control / tier(+source)].
Full texts, facts, notes, rationales: `/tmp/track_s3/manifest.json` (sha 99d76764, scratch).

- S3-F3(dormant) calm-Friday: podcast ATTEND|HOLD✗/ATTEND✓(brief); foodshop HOLD ✓✓; matt SUPPRESS|HOLD✗/SUPPRESS✓.
- S3-F1(dormant) free-40min: dentist ATTEND ✓✓(brief); florist HOLD ✓✓.
- S3-D1(dormant) reminder-req: contract-pm ATTEND ✓✓(control, ungated); dentist-now HOLD ✓✓; cousin SUPPRESS ✓✓.
- S3-Z3(injury) RPD2: injury ATTEND|HOLD✗/ATTEND✓; pursuit SUPPRESS ✓✓; old-strategy RELEASE|control ✓/tier SUPPRESS✗ (release-shyness again).
- S3-E3(injury) hospital-news: hospital ATTEND|HOLD✗/ATTEND✓; foodshop SUPPRESS|ATTEND✗/HOLD✓(weak); dentist SUPPRESS|HOLD✓/HOLD✓.
- S3-W1(injury) worry-check: check ATTEND|HOLD✗/ATTEND✓* (F-LEAK, excluded from clean claims); elif SUPPRESS|HOLD✓/SUPPRESS✓.
- S3-B2(restraint) urgency+scope: matias ATTEND ✓✓; florist HOLD|ATTEND✗/HOLD✓; carlos SUPPRESS ✓✓; chairs SUPPRESS ✓✓.
- S3-R2(restraint) approval: lucy RELEASE ✓✓; contract HOLD ✓✓; mumcheck HOLD|ATTEND✗/ATTEND✗.
- S3-D3(restraint) recall: school-email ATTEND ✓✓(control, ungated); chairs-recall SUPPRESS ✓✓; carlos SUPPRESS ✓✓; sleep SUPPRESS|HOLD✗/HOLD✗ (gate never routed).
- S3-E1m(receipt) surgery-update: matt ATTEND|RELEASE✗/RELEASE✗; podcast SUPPRESS|HOLD✓/HOLD✓; foodshop HOLD ✓✓; neck HOLD ✓✓.
- S3-A2(receipt) recovery: recovery ATTEND|RELEASE✗/RELEASE✗; priya HOLD ✓✓; matt HOLD ✓✓.
- S3-N1(receipt) venue-DM: chairs RELEASE ✓✓(brief); florist SUPPRESS ✓✓.
- S3-E1a(e1dual) gym+news: gym SUPPRESS|ATTEND✗/HOLD✓(weak); person ATTEND|HOLD✗/ATTEND✓.
- S3-E1b(e1dual) foodshop+news: foodshop SUPPRESS|HOLD✓/HOLD✓; podcast SUPPRESS|HOLD✓/SUPPRESS✓; person ATTEND|HOLD✗/ATTEND✓.
- S3-E1c(e1dual) podcast+worry: podcast SUPPRESS|HOLD✓/HOLD✓; person ATTEND|HOLD✗/ATTEND✓.
- S3-E1d(e1dual) dentist+overload: dentist SUPPRESS|HOLD✓/HOLD✓; person ATTEND|HOLD✗/HOLD✗ — load-bearing miss + E1-collapse.
- S3-M1/M2/M3/M4(allheld): all HOLD ✓✓ both arms (8/8 candidates; FP 0%).
- S3-X1(boundary): matias-form RELEASE ✓✓(control, ungated); carlos-chase SUPPRESS ✓✓.
- S3-X3(boundary): sleep-pattern SUPPRESS ✓✓(control, ungated).
- S3-B1(spot) dump: chairs ATTEND ✓✓(brief, uncontaminated); florist/carlos/cake/school HOLD ✓✓.
- S3-D2(spot) approval-question: contract-sig ATTEND ✓✓(control, ungated); lucy HOLD ✓✓.
- S3-R3(spot) calendar-done: pickup RELEASE ✓✓(brief, uncontaminated); contract/dentist HOLD ✓✓.

## 9. Architecture that remains (fallback, exact)

Deterministic attention substrate, no LLM attention layer: bounded candidate assembly (operational nominations + bounded semantic reads, both pre-existing paths) → trigger-only priority (R1–R7 class over eligibility facts + authority-annotated notes) → suppression-posture default (HOLD/SUPPRESS/RELEASE with rechecks) where no trigger fires → foreground/product retains all behavioural authority. Gate patterns G1–G6 retained as routing *telemetry* (diagnostic flags for logging/eval stratification), never as model invocation. E1 dual-verdict family retained as regression battery for any future attention proposal. Next steering work, if any, targets the three open residue classes (receipt-beat marking, accomplishment marking, overload person-attention) with new representations — not with this tier. Graduated substrate untouched.

## 10. Product-level answer

Did expensive judgement add measurable value only where deterministic state was insufficient, without making the companion less reliable anywhere else? **Partially yes, ultimately no.** The tier recovered 9 clean control-misses with zero contamination, zero FP, zero violations — genuine incremental value, exactly where predicted. But on the mandatory case that justifies an exception tier's existence — a person disclosing overload while a routine matter pends — it suppressed the routine correctly and missed the person entirely, collapsing the dual judgement its interface was built to represent. Six of seven bar clauses passing does not earn architecture when the failed clause is the point. Kill the tier; run deterministic until better evidence exists.
