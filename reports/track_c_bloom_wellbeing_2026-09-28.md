# Track C research packet — Bloom and wellbeing meaning (RESEARCH, offline, non-production)

Owner: Claude Code (this session). Date: 2026-09-28. Status: experiment complete, no production
touched.

Blitz parent: `docs/INTERPRETATION_RESEARCH_BLITZ.md`. Baseline packet:
`docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md` (`evals/interpretation_phase0/cases.json`,
contract `phase0.v1`). This packet is a research artefact, not a patch: no `src/`, schema,
runtime, prompt, or deployed behaviour was changed. New files added this session:
`evals/interpretation_phase0/track_c_bloom_cases.json`,
`evals/interpretation_phase0/run_track_c.py`, this report.

The instruction for this track was explicit: treat Phase 0 as a hypothesis to test, not an
architecture to validate. Phase 0's four Bloom cases were hand-authored, non-blind, and each
individually defensible — exactly the condition Track A's own report shows produces misleadingly
high apparent success. This packet does not re-validate Phase 0; it stress-tests it against 13
new, more realistic longitudinal fixtures plus one small blind-extraction probe, looking
specifically for where the packet shape helps, where it is silent, and where it could actively
produce the "monitored" failure mode the blitz names as the thing to avoid.

## 1. Provenance and frozen case manifest

All 13 Track C fixtures are synthetic and non-diagnostic, authored this session
(`evals/interpretation_phase0/track_c_bloom_cases.json`, contract `phase0.v1`, validated by
`evals/interpretation_phase0/run_track_c.py` against the same `validate_case` function Phase 0
uses — 13/13 pass). No real user health data was used or could be; there is no frozen
historical-replay Bloom corpus in this repository (Phase 0's own README confirms Bloom cases are
synthetic; nothing has changed since). This is the correct honesty label for the whole track:
**every Bloom finding here is a representation test on authored fixtures, not evidence about real
extraction from messy longitudinal health data.**

Manifest (`control_type` tags mine, for cross-reference in this report):

| id | control_type | tests |
|---|---|---|
| bloom_c1 | mandatory_negative_control | self-report overrides biometric "badness" |
| bloom_c2 | mandatory_negative_control | known context (training load) fully explains HRV drop |
| bloom_c3 | shared_negative_control | derived metric must not count as independent convergence |
| bloom_c4 | personal_baseline_boundary | raw value looks notable, personal baseline says no |
| bloom_c5 | boundary_pair | transient single-night dip vs. genuine multi-week trend |
| bloom_c6 | extension_of_phase0 | symptom recurrence linked without a causal/diagnostic claim |
| bloom_c7 | extension_of_phase0 | environmental friction, richer than Phase 0's version |
| bloom_c8 | mandatory_negative_control | explicit "stop discussing this" boundary vs. ongoing data |
| bloom_c9 | foreground_criterion | worth holding vs. worth ever surfacing |
| bloom_c10 | foreground_criterion | dashboard-language anti-example vs. natural equivalent |
| bloom_c11 | foreground_criterion | single mild signal → nothing (abstention/restraint) |
| bloom_c12 | authority_boundary | concerning-looking trend, bounded implication, no clinical escalation authority |
| bloom_c13 | shared_negative_control | convergence vs. score-averaging in the wellbeing domain |

## 2. Method and model/configuration metadata

Two methods, kept separate and not blended into one score, per the blitz's blindness-control
requirement:

**(a) Hand-authored oracle packets (13 cases).** I authored both the fixture evidence and the
sidecar packet together — the same non-blind condition Phase 0 used and flagged as a limitation.
This method answers "can the packet *shape* represent these distinctions at all," not "will a
model produce them." Every case records `current_representation` / `current_decision` (today's
substrate-only behaviour, as I judge it from the graduated substrate's documented capabilities)
against `sidecar_decision` (packet-supported). All 13/13 changed the bounded decision — this
number should be read the same way Phase 0's 9/9 should: directional evidence for
representational usefulness, not a performance score.

**(b) Blind single-model extraction probe (4 of the 13 cases).** A fresh subagent (no access to
this conversation, no oracle, no `cases.json`, no `expected_decision`) was given only the raw
evidence text — including `baseline_transform` fields — for `bloom_c1`, `bloom_c3`, `bloom_c4`,
and `bloom_c12`, plus the packet-shape description and the same guardrail rules stated in prose
(reason only over baseline_transform; self-report is not automatically overridden; no
dashboard/clinical language; no causal claims from co-occurrence; derived metrics don't count as
independent convergence; empty hypothesis lists are valid; explicit stop-requests dominate). It
was asked to emit its own packet and one-line downstream decision per case, and to flag any rule
ambiguity it hit. This is a genuine (if small, single-model, single-run) blind-extraction check —
the one thing Phase 0 explicitly lacked for Bloom. Model/config: the agent's own default model
for this session's Agent tool; no separate seed, temperature, or determinism control was
available to set; latency/token metadata: 73,185 tokens, ~62s (from the tool call), single run,
no repeats.

Both methods are disclosed limitations: (a) is author-as-judge: same author wrote fixtures and
oracle, mitigated only by drawing directly on the blitz's own named negative controls rather than
ad hoc content. (b) is a sample of 4/13, one model, one run — not a bakeoff (Track A's mandate,
not Track C's), and not something this report treats as reliability evidence.

## 3. Baseline vs. candidate comparison (raw, per case)

| case | current (substrate-only) | sidecar (packet-supported) | changed? |
|---|---|---|---|
| bloom_c1 | surface a low-sleep notice from the biometric row alone | hold quietly; self-report explicitly dominates this week | yes |
| bloom_c2 | hold a possible-decline hypothesis from the HRV row alone | quiet; training-load context fully explains the deviation | yes |
| bloom_c3 | three below-baseline rows read as three converging signals | one underlying autonomic signal with two readouts, one derived metric excluded; moderate not high confidence | yes |
| bloom_c4 | numeric value alone reads as "notable," flagged for review | within this user's own 180-day baseline; no hypothesis, no notice | yes |
| bloom_c5 | every below-average night (including the single dip) treated alike | the single-night dip is ignored; only the genuine 3-week monotonic trend is held, and only as contested | yes |
| bloom_c6 | two symptom episodes stored as unrelated | held as one trajectory with temporal co-occurrence noted, explicit no-causal-claim guardrail | yes |
| bloom_c7 | goal "at risk," reminder frequency increased | environment friction named from the user's own words; timing shifted, not frequency increased | yes |
| bloom_c8 | surfacing resumes after a few days because new data keeps arriving | remains quiet; explicit boundary dominates persisting/worsening data | yes |
| bloom_c9 | pattern this small isn't represented at all today | retained as backstage context; explicitly never surfaced unprompted | yes |
| bloom_c10 | a quantified summary would be the natural way to "surface a finding" | natural-language remark or silence only; quantified/clinical phrasing explicitly rejected as a candidate | yes |
| bloom_c11 | a single mild deviation triggers a check-in question | nothing: no hypothesis, no question | yes |
| bloom_c12 | five-week trend isn't linked today; no trajectory representation exists | held trajectory, one bounded non-clinical gentle-check-in implication, explicit no-escalation-authority guardrail | yes |
| bloom_c13 | an averaged wellbeing score reads as neutral | increased activity stands as the leading theme, mildly qualified by later bedtime, not cancelled | yes |

13/13 "changed" is expected by construction (each fixture was authored precisely to expose a gap)
and should not be read as a hit rate — see §6.

## 4. Negative-control and boundary results

- **Self-report vs. biometric authority (c1, mandatory control):** the packet shape can hold
  both a biometric-deviation hypothesis and a self-report hypothesis side by side without forcing
  either to override the other by default, with the guardrail on c1h2 doing the real work
  ("self-report dominance this week is not permanent license to ignore a recurring or worsening
  deviation"). This matches the blind agent's independent result on the same case (§5).
- **Known context fully explains deviation (c2, mandatory control):** the packet can represent
  "quiet, nothing to do" as a first-class outcome with a populated hypothesis and an explicit
  guardrail against importing a population recovery-time norm — not just as an empty-hypotheses
  abstention. This distinction (a *confident, held, quiet* hypothesis vs. *no hypothesis at all*)
  is not represented anywhere in Phase 0's minimum packet and is discussed as a possible gap in
  §7.
- **Personal-baseline ownership boundary (c4):** the packet correctly produces zero hypotheses
  when the baseline transform says a raw value that reads as "notable" under a naive/population
  prior is, for this specific user, unremarkable. The blind agent reproduced this exactly,
  independently (§5) — the strongest single piece of evidence in this track that the
  personal-baseline boundary, stated as a prose rule, is something a model can actually follow
  rather than just something the packet shape can represent when hand-authored.
- **Correlated measurements are not independent convergence (c3, c13):** the packet's `supports`/
  `qualifies` relations can express "two genuinely distinct measurements moving together, with a
  third derived metric excluded from the count" without a numeric convergence score. The blind
  agent reproduced the literal rule (excluded the derived recovery score) but chose to
  **recommend a check-in question rather than holding quietly** — a real, substantive disagreement
  with the oracle, discussed in §6.
- **Explicit boundary dominates ongoing data (c8):** modelled directly on Track B's frame-of-
  discourse controls but for health data specifically. The packet can express "hold as evidence,
  never surface" as a `durable`-persistence hypothesis whose *implication* is permanent silence
  rather than eventual surfacing — this is a genuinely different shape than Phase 0's other
  persistence bounds (`turn`/`session`/`until_condition` all imply "surface later"; here the
  implication is "never surface, only the user reopening it changes that"). Not exercised by any
  Phase 0 case; flagged as new ground covered, not new machinery needed (same fields, different
  values).
- **Transient vs. trajectory (c5):** the packet can hold two different-shaped facts about the
  same domain in the same window (an ignored single-night dip, a contested multi-week trend)
  without the trend's evidence basis being contaminated by the dip, or vice versa — this required
  explicitly excluding e2 from the trend hypothesis's `evidence.supports`, which the schema
  supports but does not enforce; an extractor could easily lump both together (see §7).

## 5. Blind extraction results (4 cases, one model, one run)

Full output in the subagent transcript. Summary:

| case | oracle downstream decision | blind-model downstream decision | agreement |
|---|---|---|---|
| bloom_c1 | hold quietly, no surfacing | hold quietly this week, re-evaluate if pattern continues/self-report shifts | **agree** |
| bloom_c3 | hold with moderate confidence, gather one more week, do **not** surface | ask one gentle, open question | **disagree** |
| bloom_c4 | no hypothesis, no notice | no hypothesis, no notice | **agree**, and the model correctly refused to import a population BP norm onto 135/85 |
| bloom_c12 | at most one gentle non-clinical check-in; explicit no-escalation-authority guardrail | surface one gentle, low-pressure, non-repeating check-in; explicit no-clinical/no-crisis-escalation guardrail | **agree**, including spontaneously reproducing the "if the user asks to stop, that overrides future evidence" rule from c8 without being shown c8 |

3/4 agreement on the *bounded downstream decision*, including on the two hardest boundary tests
(the personal-baseline case and the no-escalation-authority case), is a meaningfully positive
single-model signal — but 4 cases is not a sample size that supports a reliability claim, and the
one disagreement is instructive rather than noise (below).

**The disagreement (c3) is the most useful finding in this track.** Given the same rules,
including an explicit instruction not to treat the derived recovery score as independent
evidence, the model followed the letter of every rule correctly and still landed on "ask a
question" where the oracle held "stay quiet, gather more evidence." The model's own
self-reported reasoning: two genuinely independent measurements agreeing, with *no* logged
context at all (unlike c2), made it read as "worth a light, curious check-in" rather than "worth
holding." This is not a rule violation — it is the exact ambiguity the blitz's research question
3 asks about: *what should be interpreted vs. what should remain quiet*, at the boundary where
confidence is real but moderate and no explanation is on record. A model with reasonable
instructions given the Phase-0 packet fields will not converge on a single answer to "moderate
confidence + no context = hold or ask?" without that being decided explicitly, in prose, as
product policy — the packet's `confidence` field alone is not enough signal on its own to settle
it.

Other model-reported ambiguities, treated as findings:

- Whether a "this is probably fine" reading should be reified as a hypothesis at all, or left as
  an empty list (c1). The model chose to hold a low-confidence hypothesis; the rules as written
  do not disambiguate this, and Phase 0's contract has no field distinguishing "actively judged
  benign, worth a thread if it recurs" from "not worth representing yet."
  - This is the same shape of gap Track A's report names in its own §5: "no identity-confidence
    distinct from hypothesis-confidence." Here it is "no distinction between *evaluated and
    dismissed* vs. *never evaluated*." Same missing-field category, different track, independent
    discovery — moderate cross-track evidence this is a real Phase-0 gap rather than a fixture
    artefact of either track.
- Whether "durable" persistence on a trend built from a bounded observation window (c12's five
  weeks) is the right value, versus `until_condition` tied to the recheck trigger. The model
  flagged this as underspecified in the contract's own vocabulary; this report agrees it is
  underspecified (Phase 0 defines the four persistence values by example, not by rule) and treats
  it as OPEN rather than resolving it here (would require deciding, e.g., whether "durable" means
  "true forever" or "true of this already-observed period," which is a product-policy question,
  not a Track C representation question).
- How hard to lean on a user's non-response to a prior gentle question (c12). The model capped
  confidence and explicitly declined to repeat the unanswered question rather than reading
  silence as either confirmation or refutation — this is exactly the over-probing failure mode
  the blitz names, correctly avoided, and worth recording as a positive finding: the guardrail
  field, stated once in prose, was sufficient to stop a second follow-up question without any
  additional machinery (a "how many times have we asked" counter, a cooldown field, etc.).

## 6. Representative successes and failures

**Successes (packet shape held up):**
1. c4 and c8 (blind + hand-authored) show the packet can produce *zero surfacing* as a confident,
   well-reasoned outcome rather than a default — this is the opposite failure mode from Track A's
   Config B (which never abstained). Combined with the mandatory abstention case (c11, single
   mild signal → nothing), this track finds no case where the packet shape itself *forced*
   over-surfacing; every over-surfacing risk found (c3's disagreement, c10's anti-example) came
   from how the `implication.decision` field was *worded* or *chosen*, not from the schema.
2. c9 demonstrates a distinction the blitz names but Phase 0 never tested: a hypothesis can be
   well-evidenced, durable, and still carry an implication of "never surface unprompted." Phase
   0's packet fields (persistence + implication) were sufficient to express this without a new
   field — the implication text itself just has to say "hold quietly" instead of "notice."
3. c10 shows the packet's `implication.decision` field is where the dashboard-language failure
   mode actually lives, not in the evidence/confidence/state machinery. The same underlying
   evidence (c3-shaped: two co-moving metrics, one contextual remark) supports both an acceptable
   natural-language implication and a rejected quantified one; nothing in the schema privileges
   either. This means "no dashboard language" cannot be guaranteed by the packet contract alone —
   it has to be enforced as an authoring/generation-time rule (a prompt instruction, a lint on the
   `implication.decision` string, or a review step), not by the representation.

**Failures / open risk (where the packet shape is silent or could mislead):**
1. **No representation for "evaluated and found benign" vs. "not evaluated."** (c1, c2 vs. c11).
   A confident low-risk hypothesis (c2: "training explains this, quiet") and true silence (c11:
   "too mild to represent") currently look almost identical from outside the packet — both result
   in a `hypotheses: []` or a held-but-silent hypothesis with no visible marker distinguishing
   "we looked and it's fine" from "we never looked." Whether this distinction has any downstream
   value (e.g. avoiding re-litigating the same question) is untested here and flagged OPEN.
2. **No enforcement that `evidence.supports` for one hypothesis excludes evidence used for a
   different, competing hypothesis in the same window.** (c5). The transient-dip and the
   multi-week-trend hypotheses had to be authored carefully to keep their evidence bases separate;
   nothing in the validator would catch an extractor that let the single dip "support" the trend
   too. This is a real risk specific to the wellbeing domain, where multiple time-scales of the
   same metric are common (a thing Sophie/RPD2's turn-scale evidence mostly avoids).
3. **The `confidence` + no-context combination is genuinely underdetermined between "hold" and
   "ask."** (c3, confirmed independently by the blind model). This is the single clearest
   candidate for a Bloom-specific (not shared-Cortex) policy rule: something like "moderate
   confidence plus zero logged context defaults to hold, not ask, unless [X]" — but per the
   blitz's authority boundary, that rule belongs to Bloom/product posture policy, not to the
   generic interpretation packet, and this track takes no position on what threshold Bloom should
   pick.
4. **No field distinguishes "the user was asked and didn't answer" from "the user was never
   asked" for over-probing purposes.** (c12). The model self-regulated correctly by putting this
   in `confidence_basis` prose, but nothing structural prevents a differently-instructed extractor
   from re-asking. Given the blitz's explicit "over-probing" failure category, this is worth
   flagging even though no case here actually failed on it.

## 7. Fields used, unused, missing

**Used, and load-bearing for Bloom specifically:** all seven Phase-0 elements. `qualifies`
carried real weight in every negative control (c1's self-report qualifying the sleep-deviation
hypothesis, c2's training-log qualifying/absorbing the HRV hypothesis, c5's dip being excluded
from the trend's evidence, c13's bedtime shift qualifying rather than cancelling the activity
theme). `contested` + `recheck_when` were the entire vehicle for restraint in c3 and c5.
`persistence: durable` combined with a "never surface" implication (c8) is a Bloom-relevant use
of an existing value, not a new one.

**Unused:** nothing in the seven-field contract went unused across the 13 cases — a modest
positive signal that Phase 0's minimum packet is not over-built for this domain, consistent with
Phase 0's own §4 ("what failed or was unnecessary") finding no scalar/graph/ontology machinery
was needed, now replicated once more in a harder domain.

**Missing (gaps this track's fixtures expose, none requiring new machinery, per §6 above):**
(a) no marker distinguishing "actively evaluated as benign" from "never evaluated"; (b) no
enforced separation of evidence between multiple simultaneously-live, different-timescale
hypotheses in the same domain; (c) `persistence: durable` is ambiguous between "true forever" and
"true of this already-observed period" when built from a bounded window rather than a stated
trait; (d) no field for "this question was already asked and not answered," though this was
handled adequately in prose in the one case that needed it. None of (a)-(d) is evidence for a new
top-level field — each is closer to an authoring/validation discipline question than a
representation gap, consistent with Track A's finding that packet *contract* correctness and
extraction *behaviour* correctness are different problems.

## 8. Disagreement and uncertainty analysis

Two distinct kinds of disagreement surfaced, and they should not be conflated:

- **Hand-authored oracle vs. current substrate:** 13/13, by construction (§3) — not informative
  about reliability, only about representational range, same caveat Phase 0 already carries.
- **Hand-authored oracle vs. independent blind model:** 3/4 agreement on the bounded decision,
  1/4 substantive disagreement (c3) that traces to a genuinely underdetermined confidence/context
  boundary rather than a rule violation, plus four self-reported ambiguities (§5) that point at
  the same two contract gaps independently found in §6/§7. This is a small but real sample of
  the thing Track A's report calls "posture-sensitivity" — except here, unlike Track A's Config
  A/B split (deliberately opposed strict vs. permissive prompts), both this report's oracle and
  the blind model were working from the *same* stated rules, and still diverged once on a
  moderate-confidence/no-context case. That is stronger evidence than Track A's posture-split
  finding that at least one Bloom-relevant boundary (hold vs. ask under moderate confidence and no
  context) needs an explicit product rule, not just a well-written packet contract.

## 9. Scope/authority audit

- No implication in any of the 13 cases commands HOLD/ASK/ENRICH/LEAD/ATTEND, clinical
  escalation, or any foreground/tool action; every `implication.decision` is phrased as an
  advisory posture with a guardrail, matching the blitz's authority boundary.
- c12 is the direct test of the clinical-escalation boundary: a five-week trend that a lay reader
  could plausibly read as concerning still produces only "at most one gentle check-in," with an
  explicit guardrail stating that clinical escalation authority belongs to Bloom/product safety
  policy on its own criteria, not to this packet — and the fixture's own evidence (e4) is written
  so that none of those separate safety criteria are present, keeping the boundary honest rather
  than asserted past what the fixture supports.
- c9 is the direct test of the "worth holding vs. worth surfacing" boundary named in the blitz's
  research questions: a real, durable, well-evidenced hypothesis with an implication of "never
  surface unprompted" — demonstrating the packet's advisory-implication field is expressive enough
  to encode silence as the correct policy outcome, not just "notice" or "ask."
- c8 is the direct test of user-boundary dominance carried over from Track B into the health
  domain: an explicit "stop discussing this" statement outranks continuing and even worsening
  evidence on the same topic, with the guardrail explicit that "the data kept coming" is never
  itself new consent to reopen the topic.
- No case produced or required a symptom taxonomy, diagnostic label, treatment recommendation, or
  numeric health-risk score; no case's guardrail was violated by its own implication text.

## 10. What belongs in shared cognition vs. Bloom-specific logic

This track's evidence supports a narrower shared surface than Bloom's own document (§8 of the
Phase 0 packet) already proposed, not a wider one:

- **Shared (Cortex/sidecar-contract level), evidenced by this track:** the seven-field packet
  shape itself, including `qualifies` for context that narrows without negating, `contested` +
  `recheck_when` for held-but-uncertain readings, and `persistence` values whose *implication*
  text can mean "never surface" as easily as "surface later." Nothing found here required a
  health-specific field to be added to the shared contract.
- **Bloom-specific, evidenced by this track:** the personal-baseline transformation step itself
  (raw measurement → deterministic/statistical personal-baseline output) is Bloom-owned
  instrumentation that must run *before* any packet is built — the packet only ever reasons over
  the transform, never the raw value (c4, replicated blind). The confidence/context threshold
  that resolves "hold vs. ask" under moderate confidence and no logged explanation (c3) is a
  Bloom product-policy decision, not a shared rule — this track deliberately does not propose a
  value for it. What counts as "sufficient logged context to explain a deviation" (training load
  counts in c2; nothing counts in c3) is domain knowledge Bloom owns, analogous to how RPD2 owns
  what counts as a frame break in Track B.
- **Explicitly NOT shared, confirmed rather than newly found:** clinical concepts, symptom
  taxonomies, diagnostic thresholds, treatment recommendations, and escalation rules remain
  outside this packet's scope in every case tested (§9) — this track found nothing that would
  argue for relaxing Phase 0's existing position on this.

## 11. Recommendation (per-track claims)

- **PROVEN (within this track's own scope — synthetic fixtures, mostly single-author, one small
  blind sample):**
  1. The Phase-0 minimum packet, unmodified, can represent every Track-C-mandated distinction
     tested — evidence vs. interpretation, personal baseline vs. population normality, transient
     vs. trajectory, convergence vs. duplication, contradiction vs. generic uncertainty,
     self-report vs. external signal, and worth-holding vs. worth-surfacing — without adding a
     new field, an emotion taxonomy, a symptom taxonomy, or a numeric score. (13/13 hand-authored
     cases, §3-§4, §9.)
  2. The failure modes the blitz names for this track (dashboard language, biometrics
     outranking self-report by default, diagnosis from weak evidence, over-probing, clinicalising
     ordinary variation, forcing every held hypothesis into foreground attention) each have at
     least one case here where the packet shape supports *avoiding* the failure, and at least one
     case (c10) showing the same underlying evidence can still be worded into the failure — i.e.
     the packet contract enables restraint but does not enforce it; wording/authoring discipline
     does the enforcing. (§6.)
  3. The personal-baseline ownership boundary (reason only over the baseline transform, never a
     population prior) held up under independent blind extraction, not just hand-authoring — the
     one finding in this track with real (if narrow, single-run) evidence beyond author-as-judge.
     (§5, c4.)
- **HYPOTHESIS:**
  1. The moderate-confidence/no-logged-context boundary (hold vs. ask) is a real, recurring
     product decision point for Bloom, not a one-off fixture artefact — c3's disagreement is
     plausible to generalise, but one case with one model is not enough to claim this is common.
  2. The missing "evaluated and found benign" vs. "never evaluated" distinction (§6, §7) would
     have downstream value (e.g. not re-litigating a dismissed reading) — plausible, untested.
  3. Real longitudinal health data will be noisier and less cleanly separable than these
     fixtures (concurrent context items are rarely as clean as "training load doubled" or "parent
     hospitalised"); this track's clean negative controls likely understate real-world difficulty,
     mirroring Track A's own stated caution about its marker-based corpus being easier than
     reality.
- **OPEN:**
  1. Whether Bloom needs any structural field for evidence-exclusivity between simultaneous
     different-timescale hypotheses in one domain (§6, c5), or whether authoring discipline is
     sufficient.
  2. What "durable" persistence should mean for a trend built from a bounded observation window
     (§5, c12) — a definitional question for the shared contract's own vocabulary, surfaced
     independently by this track's blind probe.
  3. Whether the c1/c2-style distinction between "held, evaluated, quiet" and "not represented at
     all" has any real downstream consumer that would justify a field for it, or whether it is a
     distinction without a difference for Bloom's purposes.
  4. Everything a genuine multi-model, multi-run, real-longitudinal-data replication would be
     needed to answer — this track's blind-extraction evidence is 4 cases, 1 model, 1 run, and
     should be weighted accordingly.
- **Recommendation:** RETAIN the Phase-0 packet, unmodified, as sufficient representation for
  Bloom/wellbeing interpretation at this stage of evidence. Do not add health-specific fields to
  the shared contract. Before any production decision, Bloom-owning research would need: (a) a
  genuine multi-model blind bakeoff on this track's fixtures (this session ran a single-model
  single-run probe only, per Track A's own methodology for comparison); (b) an explicit,
  Bloom-owned product-policy answer to the hold-vs-ask boundary at moderate confidence with no
  logged context (§6, §8); and (c) real (de-identified, consented) longitudinal fixtures once
  available, since every case here is synthetic. No production architecture proposal is made
  beyond this track's evidence.

## 12. Handoff

```text
WHAT I CHANGED: nothing in production; added evals/interpretation_phase0/track_c_bloom_cases.json,
  evals/interpretation_phase0/run_track_c.py, and this report only.
WHY IT SERVES THE NORTH STAR: tests whether Bloom can be noticed-not-monitored before any
  wellbeing behaviour is built on the interpretation packet.
CANON PRINCIPLES TOUCHED: none (research only; no schema/runtime/prompt changed).
EVIDENCE / TESTS: evals/interpretation_phase0/track_c_bloom_cases.json (13/13 validate via
  run_track_c.py); blind-extraction transcript from this session's Agent tool call (4 cases,
  summarised §5, not separately persisted as a file — re-run instructions in §2 if replication
  is wanted).
WHAT I DID NOT CHANGE: src/, schema, runtime, prompts, deployed behaviour, Track A/B's scope,
  Phase 0's cases.json (frozen baseline, untouched).
REGRESSIONS / RISKS: none (offline, removable; new files only).
DELETE CANDIDATES: none proposed; fixtures are reusable for a future genuine multi-model
  replication per §11's recommendation.
OUT-OF-SCOPE FINDINGS: none claimed beyond Track C.
EXACT NEXT STEP: multi-model blind bakeoff on evals/interpretation_phase0/track_c_bloom_cases.json
  using Track A's scoring methodology (reports/track_a_identity_extraction_2026-09-28.md §2),
  before any Bloom production discussion.
```
