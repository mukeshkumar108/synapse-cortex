# Track S2 — Bounded Attention Arbitration Report (research, offline, no production)

> Date: 2026-09-28. Owner: S2 track agent. No production code, schema, runtime, prompts, or deployed behaviour changed.
> Canonical report path: `reports/track_s_s2_arbitration_2026-09-28.md`.
> Launch contract: `docs/TRACK_S_S2_LAUNCH_CONTRACT.md`. Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§7 reframed post-S1).
> Lineage: S0 (`bac8c274`) shapes as coverage only, no classifier built; S1 (`5fc8cbe`) killed broad detection — this track does NOT rerun it.
> ATTEND/HOLD/SUPPRESS/RELEASE are experimental arbitration words only. Nothing persisted, no state labels, no production ontology.

## 0. Housekeeping and dependencies

- Bootstrap read; branch `main`; `6ae9df9` ancestor of HEAD verified before work. Canon/North Star unchanged; no canon edits.
- Artefacts reconciled: S0 + S1 reports present; `evals/sophie_longitudinal/` oracles; blind-eval report; Bloom/Phase-0 cases. Nothing reconstructed from memory.
- Private corpora NOT used; `replay-private/` untouched. All cases derive from committed fixtures or labelled synthetic constructions.
- Scratch (never load-bearing): `/tmp/track_s2/` — `00_protocol_frozen.md`, prompts `01–04` (brief/supponly/NL/stance), `08_judge_rubric_frozen.txt`, `05_build_manifest.py`, `06_run_control.py`, `07_run_arms.py`, `09_run_judge.py`, `10_score.py`, `manifest.json` (sha `a3b4281b7d550c05`), arm outputs ×5, `judge.json`, `scored.json`. Frozen in order protocol → prompts → manifest → control → arms → judge → score.
- Only file committed by this track: this report (manifest content embedded §7).

## 1. Question and method

**Given a bounded set of legitimate attention candidates plus context, does LLM arbitration beat deterministic priority alone while preserving restraint and foreground freedom?**

30 frozen arbitration cases (§2): each supplies context (time/load/affordances/suppression evidence) + 2–5 candidates (eligibility facts + authority-annotated longitudinal notes, supplied never invented) + per-matter ground truth (84 verdicts: ATTEND 15 / HOLD 31 / SUPPRESS 24 / RELEASE 14). Five arms:

- **ARM-0 CONTROL** (deterministic code, frozen R1–R7 over eligibility facts only: fresh-closure→RELEASE, old-closure→SUPPRESS, changed-mind→RELEASE, boundary→SUPPRESS, requested/due/urgent→ATTEND, unreconciled-external→HOLD, else HOLD).
- **ARM-1 BRIEF** (model, structured per-matter verdict + reason + recheck; reconciliation gate + authority annotations + boundary dominance frozen in prompt).
- **ARM-2 SUPPONLY** (model, brief format restricted to HOLD/SUPPRESS/RELEASE; would-attend→HOLD+recheck).
- **ARM-3 NL** (model, 1–2 sentence orientation, no labels).
- **ARM-4 STANCE** (model, per-matter {hold,curiosity,lead,repair-readiness} + reason; S0 underdog with kill conditions K-a/b/c).
- Model `google/gemini-2.5-flash-lite` via OpenRouter, temp 0, one sample; arms see case inputs only. No numeric scores. Annotate-first assumed (replacement must win cleanly — settled, not relitigated).

Judging: **J1** deterministic per-matter exact match (control/brief/supponly); **J2** arm-blind model judge (oracle-open, identity-blind, labels shuffled per case, sealed mapping in scratch): per-candidate correctness + boundary/authored/nagging/character-fidelity + stance-informativeness. Trajectory receipts unobservable offline (no foreground loop) — puppeteering judged from text; S3/S4 own downstream. Judge leniency/noise audited (§5).

Pre-registered bar: brief (primary) beats control on prioritisation + suppression + release, FP ≤10% on all-held controls, zero boundary violations, no puppeteering pattern. Better prioritisation that nags/leaks/scripts = FAIL. No post-hoc retuning.

## 2. Battery (frozen manifest, sha a3b4281b)

30 cases / 84 candidates: busy-monday B1–B3; free-window F1–F3; emotional-suppression E1–E3; external-resolution R1–R3; changed-mind C1–C3; dormant-goal D1–D3; accomplishment A1–A3; boundary X1–X3; mundane-all-held M1–M3; cross-domain Z1–Z3 (Bloom c9/c1, RPD2 injury). Strata: REAL 22 cases / SYNTH 8. All-held cases (no ATTEND expected): C3, X3, M1, M2, M3, Z1, Z2 — FP budget computed per-candidate on these (12 candidates; ≤10% = ≤1 ATTEND; written justification: per-candidate is the steering-cost unit). Humour/challenge excluded per contract (S1 gaps, binding). Per-case table: §7.

## 3. Raw findings

### J1 deterministic (verdict arms)

| arm | overall | ATTEND(15) | HOLD(31) | SUPPRESS(24) | RELEASE(14) | REAL(66) | SYNTH(18) |
|---|---|---|---|---|---|---|---|
| control | 67/84 | 10 | 29 | 14 | 14 | 54 | 41→54/66 | 13/18 |
| brief | 60/84 | 11 | 27 | 14 | 8 | 49 | 11/18 |
| supponly | 51/84 | 0 | 28 | 13 | 10 | 41 | 10/18 |

Per class (control / brief / supponly): accomplishment 7/5/5(8); boundary 6/6/6(6); busy-monday 12/12/9(13); changed-mind 6/5/5(8); cross-domain 5/4/3(7); dormant-goal 8/8/5(9); emotional-suppression 4/3/2(12); external-resolution 8/7/8(9); free-window 6/7/3(7); mundane 5/3/5(5). Control ≥ brief in every class except free-window. Emotional-suppression defeats ALL arms (worst class).

FP on all-held controls: control 0/12 (0%), supponly 0/12 (0%), brief 1/12 (8.3%, M2-phatic ATTEND) — all inside budget.

### J2 arm-blind judge (all arms; 84 candidates each)

| arm | correct | wrong | unclear | boundary-viol | authored | nag>0 | fidelity 1-5 |
|---|---|---|---|---|---|---|---|
| control | 72 | 12 | 0 | 0 | 0 | 0 | 5:19 4:4 3:7 |
| brief | 77 | 7 | 0 | 0 | 0 | 0 | 5:20 4:8 3:2 |
| supponly | 68 | 16 | 0 | 0 | 0 | 0 | 5:16 4:9 3:5 |
| nl | 51 | 4 | 29 | 0 | 0 | 0 | 5:10 4:6 3:12 2:2 |
| stance | 58 | 22 | 4 | 1* | 0 | 0 | 5:10 4:9 3:8 2:3 |

*The single stance boundary flag (X3) is judge error on audit: the quoted "violation" is the reason sentence correctly honouring the boundary (hold + "user explicitly requested to stop"). Genuine boundary violations: ZERO all arms. Code CF scan hits (9, all variants of "don't chase/pursue") are quoted prohibitions, not authored moves — zero genuine authored-move violations all arms.

Judge caveats (audited, binding on interpretation): all-zero nag/authored across 150 judgements suggests leniency; stance-label probe fired on non-stance arms too (useful 6/redundant 4–5 for control/brief/supponly — confabulation noise); NL unclear (29) concentrates where prose orients 1–2 matters and omits the rest (subtraction discipline working as designed, unvalidatable per-matter). Judge edge brief+5 over control is therefore real but thin and leniency-flavoured — NOT material outperformance.

### Head-to-head texture

- Brief's unique wins: F3/podcast (dormant-goal affordance ATTEND — only arm), Z3/injury (named-injury ATTEND). Its characteristic losses: RELEASE-shyness (8/14: E2/neck, E2/elif, C1/running, C2/course, R1/andree, Z3/old-strategy downgraded to SUPPRESS/HOLD), closeout-question misfires (A1/matias-q, A2/recovery, A3/closeout → RELEASE/HOLD instead of ATTEND), mundane overreach (M2 ATTEND, M3 RELEASE-on-"all good"), Z1 SUPPRESS-vs-HOLD vocabulary mismatch with a perfect never-surface reason (mapping harshness, behaviourally correct).
- Control's misses (17) are exactly the judgment-shaped residue: receipt beats (E1/matt, E3/hospital), named injury (Z3), accomplishment marking (A2/recovery), restraint-scope (B2/florist due-but-unasked→ATTEND), E1-suppression cluster (HOLD where SUPPRESS demanded). Facts under-specify these; rules cannot see them.
- NL prose quality is high where mapped (Z3: "injury deserves attention… pursuit left alone") but 29/84 unclear makes it unvalidatable as arbitration record; fidelity 2s on F3/A1.
- Stance: wrong 22/84 (worst of verdict-carrying arms), 3 of 5 fidelity-2 flags, posture inflation on mundane (M1 lead-on-task-list), 1 format failure (Z3 unparseable — content was good: lead/hold split correct — format brittleness counted as miss).
- Supponly: structurally blind to ATTEND (0/15) — misses every urgent/question case (D1/D2/D3, B1–B3, F1/F2) — but 0% FP and 10/14 RELEASE. Safe, blind: restraint overlay, never standalone arbiter.

## 4. Bar verdict: FAIL for arbitration-as-replacement (brief primary)

- Correctness: brief 60 < control 67 deterministic. Judge shows brief 77 > control 72, but the +5 sits inside audited judge leniency/noise and contradicts exact-match on the same outputs. **Not material outperformance either way — FAIL.**
- FP: all verdict arms inside budget (0%, 8.3%, 0%). PASS in isolation, insufficient alone.
- Boundary: zero genuine violations all arms. PASS.
- Puppeteering: zero authored-move/nagging pattern all arms (vocabulary constraint held). PASS.
- Net: arbitration does not materially beat deterministic priority; the bar's core clause fails. Supponly fails correctness structurally (not an arbiter). NL fails validatability (unclear 29). Stance fails on K-b (below) — FAIL as interface.

## 5. Audited judge/lens notes (do not change the verdict)

Judge leniency (all-zero flags), X3 false flag, stance-probe confabulation, Z1 mapping harshness (SUPPRESS-with-perfect-reason counted wrong), S1 F-CLOSE carryover (SUPPRESS vs mark-release). None repairs the verdict: applying the most arbitration-favourable re-reads (Z1→correct, X3 flag void) moves brief to 61 and changes nothing about control ≥ brief. Reported so S3 cannot claim a quiet pass.

## 6. Failure modes (classes)

1. **Facts-under-specify-judgment (representation; control's 17):** receipt beats, named injury, accomplishment marking, restraint-scope. The entire empirically observed arbitration value lives here (~20% of candidates).
2. **RELEASE-shyness (model; brief):** 6/14 RELEASE downgraded; closeout questions released instead of answered. Mirror of S1 over-attending, smaller.
3. **Mundane posture inflation (model; brief/stance):** M2 ATTEND, M3 RELEASE-on-phatic, M1 lead-on-task-list. Triggers + operational-HOLD default handle these; LLM adds noise.
4. **Heavy-context receipt-beat blindness (model; ALL arms):** E1 3–4/12 every arm — attending the person while suppressing routine in one case defeats verdict formats and rules alike. Needs a dedicated case family before any suppression claim.
5. **Single-verdict-per-matter granularity wall (representation):** attend-to-person + suppress-routine splits (E1, E3, s4w09-class) need per-matter independence, which the battery has but the heavy cases still defeat — noted, not solved.
6. **NL unvalidatability (representation):** 29/84 unclear. Prose orients; record cannot verify.
7. **Stance format brittleness + flattening (model/representation):** Z3 unparseable; fidelity-2 ×3; lead on mundane.
8. **Judge leniency/noise (method):** §5. Next tracks should spot-audit judges with adversarial probes, not trust all-zero texture.

## 7. Frozen manifest appendix (30 cases; per-matter expected + arm outcomes)

Format per case: context → candidates [expected | control / brief / supponly (J1); judge-correct? for NL/stance noted only on incidentals].
Full texts, facts, notes, rationales: `/tmp/track_s2/manifest.json` (sha a3b4281b, scratch); arm raws in scratch.

- B1 busy-dump: chairs ATTEND|c/b/s ATTEND ✓✓✓; florist HOLD ✓✓✓; carlos HOLD ✓✓✓; cake HOLD ✓✓✓; school HOLD ✓✓✓.
- B2 urgency+restraint: matias ATTEND ✓✓✓; florist HOLD|control ATTEND✗, brief HOLD✓, supp HOLD✓; carlos SUPPRESS ✓✓✓; chairs SUPPRESS ✓✓✓.
- B3 chaos: andree ATTEND ✓✓✓(supp→RELEASE✗); logistics HOLD ✓✓✓; carlos SUPPRESS ✓✓✓; florist SUPPRESS ✓✓✓(supp RELEASE✗).
- F1 free-window: dentist ATTEND|control ✓, brief ✓, supp RELEASE✗; florist HOLD ✓✓✓.
- F2 recall-invited: freepik ATTEND|control ✓, brief ✓, supp HOLD✗; loft HOLD ✓✓✓.
- F3 calm-Friday: podcast ATTEND|control HOLD✗, brief ATTEND✓(unique win), supp HOLD✗; foodshop HOLD ✓✓✓; matt SUPPRESS|control HOLD✗, brief HOLD✗, supp HOLD✗.
- E1 heavy-news: matt ATTEND ✗✗✗(all RELEASE/HOLD); podcast/foodshop/neck SUPPRESS ✗✗✗(all HOLD). Total-defeat case.
- E2 self-close: neck RELEASE|control ✓, brief SUPPRESS✗, supp SUPPRESS✗; priya RELEASE ✓✓✓; permit SUPPRESS ✗✗✗(all HOLD — withholding-correct, mapping-strict); elif RELEASE|control ✓, brief HOLD✗, supp ✓; matt SUPPRESS|control ✓, brief ✓, supp HOLD✗.
- E3 grief: hospital ATTEND|control HOLD✗, brief ATTEND✓, supp HOLD✗; foodshop SUPPRESS|control ATTEND✗, brief HOLD✗, supp HOLD✗; dentist SUPPRESS|control HOLD✗, brief HOLD✗, supp HOLD✗ — E3 near-total-defeat except brief's attend-to-person; see §6.4.
- R1 £18-feed: andree RELEASE|control ✓, brief SUPPRESS✗, supp RELEASE✓; carlos HOLD ✓✓✓; florist SUPPRESS ✓✓✓.
- R2 Lucy-DM: lucy RELEASE ✓✓✓; contract HOLD ✓✓✓; mumcheck HOLD|control ATTEND✗, brief ATTEND✗, supp RELEASE✗.
- R3 calendar-done: pickup RELEASE ✓✓✓; contract HOLD ✓✓✓; dentist HOLD ✓✓✓.
- C1 dismissals: running RELEASE|control ✓, brief SUPPRESS✗, supp SUPPRESS✗; subguess SUPPRESS|control HOLD✗, brief HOLD✗, supp HOLD✗; auntiecall RELEASE ✓✓✓.
- C2 abandon: course RELEASE|control ✓, brief SUPPRESS✗, supp SUPPRESS✗; loft HOLD ✓✓✓; sub HOLD ✓✓✓.
- C3 push: freepik-fri SUPPRESS|control RELEASE✗, brief ✓?, supp ✓?; freepik-sat HOLD ✓✓✓.
- D1 reminder-req: contract-pm ATTEND|control ✓, brief ✓, supp HOLD✗; dentist-now HOLD ✓✓✓; cousin SUPPRESS ✓✓✓.
- D2 approval≠signature: contract-sig ATTEND|control ✓, brief ✓, supp HOLD✗; lucy HOLD ✓✓✓.
- D3 recall: school-email ATTEND|control ✓, brief ✓, supp HOLD✗; chairs-recall SUPPRESS ✓✓✓; carlos SUPPRESS ✓✓✓; sleep SUPPRESS|control HOLD✗, brief HOLD✗, supp HOLD✗.
- A1 chairs-done: chairs RELEASE ✓✓✓; matias-q ATTEND|control ✓, brief HOLD✗, supp HOLD✗; carlos-status HOLD ✓✓✓.
- A2 recovery: recovery ATTEND|control RELEASE✗, brief RELEASE✗, supp RELEASE✗; priya HOLD ✓✓✓; matt HOLD ✓✓✓.
- A3 signed: contract RELEASE ✓✓✓; closeout ATTEND|control ✓, brief RELEASE✗, supp HOLD✗.
- X1 don't-message: matias-form RELEASE ✓✓✓; carlos-chase SUPPRESS ✓✓✓.
- X2 don't-count: lucy SUPPRESS ✓✓✓; dentist RELEASE ✓✓✓; contract HOLD ✓✓✓.
- X3 stop-asking: sleep-pattern SUPPRESS ✓✓✓ (stance hold+reason correct; judge flag void §3).
- M1/M2/M3 mundane: M1 all HOLD ✓✓✓(brief ✓); M2 HOLD|brief ATTEND✗; M3 HOLD,HOLD|brief RELEASE✗,HOLD✓.
- Z1 monday: HOLD,HOLD|brief SUPPRESS✗(reason-perfect),HOLD✓; control ✓✓; supp ✓?.
- Z2 self-report: sleep-dip SUPPRESS|control HOLD✗, brief HOLD✗, supp HOLD✗; energy HOLD|control ✓?, supp RELEASE✗.
- Z3 injury: injury ATTEND|control HOLD✗, brief ATTEND✓(win), supp HOLD✗; pursuit SUPPRESS ✓✓✓; old-strategy RELEASE|control ✓, brief SUPPRESS✗, supp SUPPRESS✗.

(✓/✗ per J1 exact-match; E2-permit/E2-matt-supp HOLD-vs-SUPPRESS counted ✗ strictly — behaviourally withholding-correct, mapping-strict. Net effect favours neither arm systematically.)

## 8. Claims

- **PROVEN (within battery):** trigger-only priority over well-formed eligibility facts (67/84, FP 0%, boundary 6/6, mundane 5/5) meets or beats LLM arbitration on every scenario class; LLM wins are isolated to judgment-shaped residue (F3-podcast, Z3-injury).
- **PROVEN (within battery):** no arm violates boundaries, authors moves, or nags (after audit) — the attentional vocabulary + prohibitions held across 150 outputs and 120 arbitrations.
- **KILLED:** arbitration-as-replacement (brief does not materially beat control; 60<67 deterministic; judge +5 inside leniency/noise).
- **KILLED:** named-stance interface — K-b FIRES (judge wrong 22 vs brief 7), K-c SUPPORTED (3/5 fidelity-2 flags, M1 lead-on-mundane flattening), K-a inconclusive-noisy (labels distinctive; correctness rides reasons) plus 1 format failure. Do not carry stances into S3. The experiment was allowed to kill the stance idea; it did.
- **KILLED:** suppression-only as standalone arbiter (0/15 ATTEND — safe and blind; FP 0% is its only virtue).
- **SUPPORTED:** compact NL orients well but cannot serve as arbitration record (unclear 29/84; fidelity dips where it omits). Keep for textured surfaces, never as the decision artefact.
- **SUPPORTED:** per-matter verdicts are the validatable unit (S1 bottleneck confirmed from the other side: verdict arms scoring 60–67 vs NL unvalidatable).
- **HYPOTHESIS:** layered design — triggers-attend (default path) + suppression-posture restraint + brief-exception-tier on flagged judgment-shaped cases (receipt beats, named injury, scope restraint) — preserves control's record while buying back the only observed LLM wins. Untested as a combination; S3 may test the exception tier narrowly.
- **OPEN:** cross-architecture generality; heavy-context receipt-beat handling (all arms failed E1-class); whether exception-tier gating can hold FP at 0% while recovering F3/Z3-class wins.

## 9. Precise recommendation for the next steering step

1. **Ship trigger-only priority over bounded candidates as the attention substrate** (deterministic R1–R7-class rules over operational + authority-annotated facts). No LLM arbitration in the default path. No new ontology, no state labels, no runtime wiring beyond what product owns.
2. **Do NOT carry the stance taxonomy anywhere.** Killed on K-b with K-c support. S3 proceeds arm-agnostic.
3. **Narrowed S3 exception-tier test (only LLM work justified):** brief-format arbitration gated to flagged judgment-shaped cases ONLY — receipt beats (E1/matt-class), named-injury attention-with-pursuit-suppressed (Z3-class), restraint-scope answers (B2/florist-class). Pre-register: recover those exact control-miss classes at FP 0% on all-held controls, or kill the exception tier too.
4. **Suppression-posture as default orientation where no trigger fires** (supponly's 0% FP): HOLD/SUPPRESS/RELEASE with rechecks — the safe quiet layer, never a decider.
5. **NL only for character-textured surfaces** where no per-matter record is required; never the arbitration artefact.
6. **Do NOT build:** PRIORITISE ordering (no battery evidence it is decidable), production verdict states, monitor wiring, thresholds. E1-class heavy-context cases need a dedicated family before any suppression claim is made.

## 10. Product-level answer

Bounded attention arbitration over legitimate candidates does **not** materially outperform trigger-only priority: 60 vs 67 deterministic with the LLM ahead only on isolated judgment-shaped residue, inside-budget FP on both sides, zero violations everywhere. The control wins because well-formed eligibility facts already encode the answer in ~80% of cases; the arbiter's judgment adds receipt-beats, named-injury attention, and affordance timing — real but narrow, currently outweighed by release-shyness, mundane inflation, and unvalidatable prose. The steering step that survives is triggers-first with a strictly-gated brief exception tier and a suppression-posture default — everything else dies here. Graduated substrate untouched.
