# Track S1 — Significance Calibration Report (research, offline, no production)

> Date: 2026-09-28. Owner: S1 track agent. No production code, schema, runtime, prompts, or deployed behaviour changed.
> Canonical report path: `reports/track_s_s1_significance_2026-09-28.md`.
> Launch contract: `docs/TRACK_S_S1_LAUNCH_CONTRACT.md`. Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7).
> S0 basis: `reports/track_s_s0_significance_shapes_2026-09-28.md` (commit `bac8c274`); SHP-1..14 used as evaluation coverage only — no `SHP-*` classifier built, none proposed.

## 0. Housekeeping and dependencies

- Bootstrap: `docs/AGENT_BOOTSTRAP.md` read; branch `main`; `git merge-base --is-ancestor 6ae9df9 HEAD` verified OK before work.
- Canon baseline docs unchanged since `1d55e86`/`9cfcee9` (canon, North Star read; no canon edits proposed or made).
- Artefacts reconciled: `evals/sophie_longitudinal/` inputs+oracles (4 scenarios, fixture v1.0.0), blind-eval report `reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`, `evals/interpretation_phase0/cases.json`, `evals/interpretation_phase0/track_c_bloom_cases.json`, Track A reports. All present; nothing reconstructed from memory.
- Private corpora: NOT used. All windows derive from committed fixtures or labelled synthetic constructions. `replay-private/` untouched.
- Scratch (never load-bearing): `/tmp/track_s1/` — `00_protocol_frozen.md`, `01_prompt_strict_frozen.txt`, `02_prompt_open_frozen.txt`, `03_build_manifest.py`, `04_run_cheap.py`, `05_run_detector.py`, `06_score.py`, `manifest.json` (sha `bbd1ca21129cd11c`), `arm0_cheap.json`, `arm_strict.json`, `arm_open.json`, `scored.json`. Protocol/prompts/manifest frozen in that order before runs; timestamps on disk.
- Only file committed by this track: this report.

## 1. Question and method

**Can side cognition recognise what deserves attention now better than cheap deterministic/explicit-signal baselines, without excessive false-positive steering?**

Sliding-window runs over a frozen 69-window battery (§2). Each window supplies operational/context facts as deterministic inputs, trajectory (prior turns) + person/relationship notes as the longitudinal side, and the live moment. Three arms:

- **ARM-0 CHEAP** (deterministic code): T2 boundary/withhold markers → abstain (checked first, dominates); T5 any external event → surface; T1 frustration/correction, T3 completion/change-of-mind, T4 due/time/recall-question regexes → surface; else abstain. Full patterns in scratch `00_protocol_frozen.md`. No tuning after runs.
- **ARM-1 D-STRICT** (frozen prompt, restraint prior: default abstain/hold, surface only on explicit request/correction/due-today/genuine opportunity/accomplishment/release): model `google/gemini-2.5-flash-lite` via OpenRouter, temp 0, one sample.
- **ARM-2 D-OPEN** (frozen prompt, opportunity prior: prefer noticing dormant-goal windows, accomplishments, openings; tie-break hold→surface): same model/config.
- Detector vocabulary (attentional powers only, blitz §10): attend / hold / suppress / surface-as-candidate / narrow-latitude / abstain. Model sees window inputs ONLY — never oracle labels, futures, or other arms. No numeric scores anywhere.

Expected classes (oracle, frozen per window): SURFACE / HOLD / SUPPRESS (includes release-marking) / ABSTAIN. Pass mapping (frozen): SURFACE→{surface,attend}; HOLD→{hold}; SUPPRESS→{suppress,hold}; ABSTAIN→{abstain}. Cheap: SURFACE→surface; HOLD→always miss; SUPPRESS→pass only on abstain; ABSTAIN→abstain. The asymmetry is the experiment's point: cheap cannot represent hold/suppress/release; the detector must earn its keep there without FP blowup.

Pre-registered bar: PASS requires (a) detector recall on user-marked moments EXCEEDS cheap, (b) false-steer on mundane+correct-silence controls ≤10%, (c) no systematic suppression blindness (suppress-probe pass <50% = symmetric FAIL). Recall-without-FP-budget = FAIL. Frustration-only firing = scope FAIL.

## 2. Battery (frozen manifest, sha bbd1ca21)

69 windows: 47 REAL (`s1` 14 + `s2` 9 + `s3` 14 + `s4` 10 user/external events; assistant turns are foreground outputs, not orientation moments, and are excluded) + 22 SYNTH (Bloom c1–c13 as 13 windows; RPD2 rupture/strategy-failure as 2; constructed situational-opportunity + grief-suppression 2; Track-A-B-set-adapted mundane controls 5). Expected split: SURFACE 27 / HOLD 20 / SUPPRESS 13 / ABSTAIN 9. Controls (ABSTAIN+SUPPRESS) 22/69 = 31.9% (≥30% per contract). Oracle labels derive from committed oracles/checkpoints/traps/gears + blind-eval findings; one-line rationale per window frozen in manifest. Full per-window table: §7.

Coverage of §7 categories: rupture (3 windows — thin, see §6 flaw F9), repair/strategy-failure (1), circling (via HOLD windows), deepening (3), remembered goals (7), missed opportunity (2), celebration (6), humour (0 real — gap, see §6), changed mind (5), gradual change (7), correct silence (4), unwanted probing (withhold windows 3), successful challenge (0 real — gap, accountability overlay untested), situational opportunity (4), suppression-by-context (7: s1w13 s2w03 s2w05 s2w10 s4w09 s4w10 synw02 + c8), frame/boundary (s3w13 binding, c8, s2w03), mundane (9). Humour and successful-challenge have no real-data windows: genuine battery gaps, not silent passes.

Operating point frozen before scoring: temp 0 single-sample; cheap regexes as listed; no post-hoc tuning of the official numbers (§5 reports a documented secondary re-analysis without replacing them).

## 3. Raw results (frozen; raw counts, no aggregate score)

| cut | cheap | strict | open |
|---|---|---|---|
| Overall (69) | 36 | 43 | 33 |
| SURFACE (27) | 24 | 24 | 23 |
| HOLD (20) | 0 | 6 | 1 |
| SUPPRESS (13) | 7 | 8 | 8 |
| ABSTAIN (9) | 5 | 5 | 1 |
| REAL only (47) | 28 | 34 | 28 |
| SYNTH only (22) | 8 | 9 | 5 |
| User-marked recall (rupture+nonrupt+accomplish+opportunity+deepening, 29) | 24 | 24 | 23 |
| User-marked REAL only (25) | 23 | 23 | 21 |
| Non-rupture significance (26) | 24 | 24 | 22 |
| Rupture only (3: s1w11, rpdw01, rpdw02) | 1 | 1 | 1 |
| FP-budget set false-steer (22 controls) | 10 (45.5%) | 9 (40.9%) | 13 (59.1%) |
| Suppress-probe pass (13) | 7 | 8 | 8 |

Detector latency: median ~440ms, max 945ms (window metadata only; no production claim).

CF audit (frozen scanner): strict 9 flagged windows, open 13. Scanner flaw found: CF1 boundary regex matches epistemic "don't know/recognise" (s4w01 false flag; synw02 flag). Repaired in secondary analysis (§5). No CF4 (authored moves) in any detector output — the attentional vocabulary held. One PARSE-FAIL (open, s3w01: emitted two JSON judgments — counted as miss; Turned out to be representation evidence, §4 F6).

Strict HOLD passes (6): s3w05 (Lucy withhold), s4w02 (neck restraint), s4w07, blw06 (recurrence pairing), blw09 (Monday never-surface), blw10. Strict SUPPRESS passes (8): s2w03, s2w05, s2w10 (changed-mind releases), s3w09, s3w10 (releases), s4w05-weak (hold), s4w10 (batch release), blw08 (explicit boundary). Opportunity windows (s1w12, s2w08, s3w13, synw01): all arms pass all four.

## 4. Bar verdict: FAIL (all arms, on frozen numbers)

- (a) Recall: strict TIES cheap on user-marked moments (24/29; REAL 23/25), open LOSES (23/29; REAL 21/25). Neither detector exceeds the baseline. **FAIL.**
- (b) FP budget: cheap 45.5%, strict 40.9%, open 59.1% — all exceed ≤10% by multiples. **FAIL** (including the baseline itself; see §6 on budget calibration).
- (c) Suppression blindness: strict/open pass 8/13 suppress probes (62%) — no systematic blindness, but two critical-pattern items inside: both detectors attend into the constructed grief window (synw02), and strict attends into the £18-resolution window (s1w13) and Matt-silence window (s4w09, defensible — §5).
- Scope check: detectors fire across all significance classes (not frustration-only) — scope PASS, the only passed gate.

Headline: strict's +7 overall over cheap comes ENTIRELY from HOLD (+6) and SUPPRESS (+1); on moment detection (SURFACE) it ties cheap exactly (24/27, same misses minus/plus: cheap misses s4w01+rpd pair; strict misses s3w14+rpd pair). The detector's value is a quiet-tracking vocabulary cheap structurally lacks — but it drowns that edge in over-attending noise (attend on 14/20 HOLD windows for strict, 19/20 for open) and critical suppression failures.

## 5. Documented secondary analysis (repaired flaws; does NOT replace frozen verdict)

Genuine flaws found during audit, repaired conservatively here with deltas shown:

- **F-CF1 (judging setup):** CF1 scanner matched epistemic "don't know/recognise" as boundaries. Repaired pattern requires contact/mention verbs. Removes s4w01 flags (both arms) and synw02 CF1 (CF6 assessment unchanged).
- **F-CLOSE (battery oracle harshness):** SUPPRESS label vs closure-marking. Reasons show s3w08-strict ("confirms the £240 payment, resolving uncertainty"), s4w09-both ("resolves the immediate concern and warrants acknowledgment"), synw02-strict ("acute news… warrants immediate foreground attention" — attend-to-person, not to routine) are receipt/closure-marking, not nagging. Reclassified as non-false-steers with rationale; the single-judgment vocabulary cannot split attend-to-person from suppress-routine (representation flaw F6, kept open).
- Repaired FP: strict 9→6/22 (27.3%), open 13→11/22 (50%), cheap held frozen at 45.5% (conservative: cheap has no reasons to audit, so its closure-marks stay counted).
- Verdict unchanged under repair: recall still tied/lost; FP still multiples of budget. The repair narrows but does not cross the bar — reported so future work cannot claim a quiet pass.

## 6. Failure modes (with classes; window refs)

1. **Over-attending (model; dominant):** attend on HOLD windows — strict 14/20, open 19/20. E.g. s1w03/04/06 (counterparty/calendar tracking), s3w02/07, s4w04 (neck 3rd mention), blw03/05/07/12. The model reaches for attend where the oracle demands quiet tracking.
2. **Boundary overgeneralisation (model + prompt):** rpdw01-strict suppress ("requested space" → closed the injury itself), rpdw02-strict suppress ("rejected strategy" → matter closed), s1w11-open suppress (boundary + completion → suppressed the marking too). Restraint priors kill rupture recall: 1/3 all arms.
3. **External-resolution blindness (model; confirms blind-eval):** s1w13 both detectors attend to the £18 feed as live need instead of releasing the Andree commitment. Reconciliation-before-surfacing absent.
4. **Authority ranking missing (product-semantics/fixture):** blw01-strict attends to the -2.5SD dip despite dominant self-report — the frozen prompts never state self-report dominance (product knowledge, correctly absent from shared machinery; must arrive via person-model annotations).
5. **Operational-vs-trajectory confusion (representation):** munw01/02/04-strict attend ("direct request", "core function"). Operational queries deserve foreground answers but no trajectory judgment; side attending is individually harmless, in aggregate noise. munw03/05 abstains show posture inconsistency (model noise).
6. **Single-judgment bottleneck (representation):** mixed moments (s1w11: completion + boundary; s4w09: heavy news + suppress-rest; s3w14: self-completion + closeout question) and multi-matter moments (s3w01-open emitted two JSONs — PARSE-FAIL that proves the point) need per-matter judgments. S0's brief shape anticipated this; confirmed empirically. OPEN question for S2, not a fix claimed here.
7. **Closure-marking harshness (battery oracle):** see §5 F-CLOSE. SUPPRESS conflated "release tracking" with "no attention beat". Future batteries need a mark-release class.
8. **Cheap T2 over-match (baseline flaw):** bare "don't" fires withhold on epistemic uses ("don't know" → s4w01 cheap abstain-miss on a SURFACE window). Conservative effect (hurts cheap); documented, not repaired in official numbers.
9. **Rupture coverage thin (battery flaw):** 3 rupture windows; RPD2 redactions lack explicit markers ("hurt", "abandonment" absent from T1 by freeze). No rupture verdict beyond: nothing here detects rupture above explicit markers. Rupture needs a dedicated battery before any repair-loop claim.
10. **Humour + successful-challenge gaps (battery):** zero real-data windows. No claim either way; S2 must not test these interfaces without real coverage.

## 7. Frozen manifest appendix (all 69 windows; oracle + per-arm outcomes)

Columns: id | stratum | live event | expected | probes | strict got | open got | cheap got.
Live texts: committed fixtures (`evals/sophie_longitudinal/*_input.json`, `track_c_bloom_cases.json`, Phase-0 `cases.json` RPD2 case) or labelled synthetic (reasons in manifest). Full texts + facts + rationales: `/tmp/track_s1/manifest.json` (sha bbd1ca21, scratch).

REAL/s1: s1w01 SURFACE nonrupt S/A? strict attend PASS, open attend PASS, cheap surface PASS. s1w03 HOLD strict attend MISS, open attend MISS, cheap surface MISS. s1w04 HOLD A/A/MISS all miss. s1w05 SURFACE nonrupt+accomplish all pass. s1w06 HOLD all miss. s1w07 SURFACE all pass. s1w08 SURFACE all pass. s1w09 SURFACE all pass. s1w10 SURFACE all pass. s1w11 SURFACE rupture: cheap surface PASS, strict surface? strict passes list — strict SURFACE misses were s3w14+rpdw01+rpdw02 only, so strict s1w11 PASS; open suppress MISS. s1w12 SURFACE opportunity all pass. s1w13 SUPPRESS: all miss (cheap surface, strict attend, open attend). s1w14 SURFACE all pass.
REAL/s2: s2w01 SURFACE all pass. s2w03 SUPPRESS all pass (cheap abstain-T2, strict suppress, open suppress). s2w04 HOLD all miss. s2w05 SUPPRESS: cheap surface MISS, strict suppress PASS, open suppress PASS. s2w06 SURFACE all pass. s2w07 SURFACE all pass. s2w08 SURFACE opportunity all pass. s2w09 HOLD all miss. s2w10 SUPPRESS all pass.
REAL/s3: s3w01 SURFACE: cheap pass, strict pass, open PARSE-FAIL MISS. s3w02 HOLD all miss. s3w03 SURFACE all pass. s3w04 SURFACE all pass. s3w05 HOLD: cheap miss, strict hold PASS, open attend MISS. s3w06 SURFACE all pass. s3w07 HOLD all miss. s3w08 SUPPRESS: cheap miss, strict attend MISS (reclassified §5), open suppress PASS. s3w09 SUPPRESS: cheap miss, strict suppress PASS, open suppress PASS. s3w10 SUPPRESS: cheap miss, strict suppress PASS, open suppress PASS. s3w11 SURFACE all pass. s3w12 SURFACE all pass. s3w13 SURFACE opportunity all pass. s3w14 SURFACE accomplish: cheap pass, strict suppress MISS, open suppress MISS.
REAL/s4: s4w01 SURFACE deepening: cheap abstain MISS (T2 flaw), strict attend PASS, open attend PASS. s4w02 HOLD restraint: cheap miss, strict hold PASS, open attend MISS. s4w04 HOLD restraint: cheap miss, strict attend MISS, open attend MISS. s4w05 SUPPRESS: cheap miss, strict hold PASS(weak), open attend MISS. s4w07 HOLD: cheap miss, strict hold PASS, open attend MISS. s4w08 SURFACE accomplish all pass. s4w09 SUPPRESS silence: cheap abstain PASS (T2 accidental), strict attend MISS (reclassified §5), open attend MISS (reclassified). s4w10 SUPPRESS silence: cheap abstain PASS, strict suppress PASS, open suppress PASS. s4w13 HOLD deepening: cheap miss, strict attend MISS, open attend MISS. s4w15 ABSTAIN mundane: cheap abstain PASS, strict abstain PASS, open suppress MISS.
SYNTH/bloom: blw01 SUPPRESS: cheap abstain PASS (ignorance), strict attend MISS, open attend MISS. blw02 ABSTAIN: cheap PASS, strict PASS, open attend MISS. blw03 HOLD: cheap miss, strict attend MISS, open attend MISS. blw04 ABSTAIN: cheap PASS, strict PASS, open attend MISS. blw05 HOLD: all miss. blw06 HOLD: cheap miss, strict hold PASS, open attend MISS. blw07 HOLD: cheap miss, strict attend MISS, open attend MISS. blw08 SUPPRESS: all pass. blw09 HOLD: cheap miss, strict hold PASS, open hold PASS. blw10 HOLD: cheap miss, strict hold PASS, open attend MISS. blw11 ABSTAIN mundane: cheap PASS, strict hold MISS, open attend MISS. blw12 HOLD: cheap miss, strict attend MISS, open attend MISS. blw13 HOLD accomplish: cheap miss, strict abstain MISS, open attend MISS.
SYNTH/rpd2: rpdw01 SURFACE rupture: all miss (cheap abstain, strict suppress, open attend PASS? — open passed rpdw01 per §3 accounting: open SURFACE misses were s1w11, s3w01, s3w14 → rpdw01 open PASS). Correction: open rpdw01 PASS (attend). rpdw02 SURFACE rupture: all miss.
SYNTH/constructed: synw01 SURFACE opportunity: all pass. synw02 SUPPRESS grief: cheap abstain PASS (T2 accidental), strict attend MISS (reclassified §5), open attend MISS (reclassified).
SYNTH/mundane: munw01 ABSTAIN: cheap surface MISS, strict attend MISS, open attend MISS. munw02 same, all miss. munw03: cheap miss, strict abstain PASS, open attend MISS. munw04: all miss. munw05: all pass.

## 8. Claims (labelled)

- **KILLED:** LLM moment-detection beating cheap explicit triggers on this battery (tie/loss on user-marked and non-rupture recall). Ship the triggers for explicit moments.
- **KILLED:** D-OPEN opportunity-prior operating point (worse FP 59%, over-suppresses mixed moments s1w11/s3w14, holds almost nothing 1/20).
- **KILLED:** rupture detection by restraint-prior side cognition (1/3; both RPD2 windows suppressed by boundary overgeneralisation).
- **SUPPORTED (representation, not reliability):** hold/suppress/release vocabulary carries decision value cheap structurally lacks (strict +7: HOLD 6/20 incl. Lucy withhold s3w05, neck restraint s4w02, never-surface blw09; releases s2 batch, s3w09/10, s4w10, blw08). Oracle-coupled battery, single model family — reliability OPEN.
- **SUPPORTED:** per-matter judgments needed (s3w01 double-JSON, mixed-moment failures); single-label attention verdicts conflate attend-to-person with suppress-routine.
- **HYPOTHESIS:** reconciliation-before-surfacing (s1w13 class) and authority-annotated person notes (blw01 class) are the two cheapest fixes to test before any S2 interface bakeoff.
- **OPEN:** cross-architecture generality; real-data rupture recall; humour/challenge coverage; whether any operating point meets ≤10% FP with recall above triggers.
- **PROVEN (within battery):** no detector arm meets the pre-registered bar; the FP budget binds harder than recall (all arms fail it, baseline included).

## 9. What S2 should now compare (and what it must not)

1. Compare interfaces on HOLD/suppress/release/orientation quality — where S1 found the only detector edge — NOT on raw moment detection (triggers own that; include a trigger-only control arm or S2 will rediscover S1).
2. Require per-matter judgments (or explicit single-target discipline with a stated rule) — S1's representation bottleneck.
3. Supply authority-annotated person notes (self-report dominance, explicit-vs-inferred invitation) — do not test whether models invent authority ranking; they don't (blw01).
4. Add a reconciliation gate: external evidence must resolve-against-open-commitments before any surfacing judgment (s1w13 rule).
5. Keep stance as underdog; test brief vs NL vs suppression-only on restraint precision and non-puppeteering, with the repaired CF scanner and a mark-release class in the rubric.
6. Do NOT test humour or successful-challenge interfaces without first building real-data batteries (S1 gaps).
7. Do NOT re-tune this battery's operating points to pass the bar post-hoc; the bar stands for the next operating point to meet blind.

## 10. Product-level answer

**Can this system look at the person, their commitments, their trajectory and the present situation and make a meaningfully better judgement about what deserves attention right now — including when the correct answer is nothing?**

On this battery, with these arms: **no — not yet, and specifically not where it counts.** Moment detection ties cheap explicit triggers exactly; correct-nothing performance is the worst gap (27–50% false-steer even after documented repairs, vs a 10% budget); and restraint-prior prompting actively suppresses the ruptures it should catch. What the detector genuinely adds is a quiet-tracking vocabulary — hold, suppress-with-reason, release-marking — that a trigger list structurally cannot express (Lucy withhold held, neck pattern rested, Monday-pattern never surfaced, changed minds released, boundary honoured). That vocabulary is currently drowned in over-attending noise. The path forward is triggers for explicit moments + a strictly-gated hold/suppress/release layer with per-matter judgments and reconciliation-before-surfacing — which is an S2 interface question, not an S1 detection claim. Nothing here earns production proximity; the graduated substrate is untouched.
