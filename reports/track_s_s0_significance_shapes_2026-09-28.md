# Track S — S0 Output: Significance Shapes + Interface Candidates

> Status: research only. Date: 2026-09-28.
> No production code, schema, runtime, prompts changed. No stance taxonomy canonised. No new durable store proposed.
> Persisted verbatim from the completed S0 analysis in-conversation (no rerun, no reinterpretation).
> Evidence read: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md`, `docs/COMPANION_CANON.md`, `docs/COMPANION_NORTH_STAR.md`, `docs/INTERPRETATION_RESEARCH_SYNTHESIS_V2.md`, `docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md`, `evals/sophie_longitudinal/*` inputs + blind eval `reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`, `evals/interpretation_phase0/cases.json` + `evals/interpretation_phase0/track_c_bloom_cases.json`, `reports/track_a_identity_extraction_2026-09-28.md`, `docs/CONSOLIDATED_LEARNINGS.md`, `docs/BLITZ_MECHANISM_INVENTORY.md`, `docs/GEMINI_BEHAVIOURAL_EVAL.md`.

Method: worked backward from frozen moments where the foreground turn would predictably be worse without trajectory-aware orientation, and where it would predictably be worse *with* it. RPD2 used as one wind-tunnel case among many, not the organiser.

---

## 1. Candidate significance shapes (frozen inventory proposal)

Each shape is a **temporal + evidential + relational structure**, not a classifier label or emotion. Each carries its suppression condition. Side cognition may *notice* the shape; foreground decides what, if anything, to do.

### SHP-1 Rupture / friction (one subclass, deliberately first-but-small)
- **Shape:** explicit user-marked mismatch ("you're not understanding me", "that hurt", correction, withdrawal after injury) + prior expectation/strategy it contradicts + open repair labour.
- **Grounding:** `cases.json:47-72` RPD2 rh1–rh3 (coldness/non-recognition + transfer of repair labour + superseded "give space"); Isa bad-arc regression (monologue apology, waiting-as-care).
- **Side value:** hold the injury reading and the superseded-strategy reading simultaneously so foreground doesn't default to `respect_space_and_wait`.
- **Suppress when:** explicit stop/no-contact boundary present; user closed the topic; mundane friction with no trajectory weight. Rupture tunnel vision (every turn damage-managed) is the kill condition.

### SHP-2 Repair affordance / repair yield
- **Shape:** prior rupture + a concrete, small, *doable now* act that would address the named injury (not a speech about it).
- **Grounding:** Condition-C 3.0→4.5 repair-action, outsourcing −85% (`CONSOLIDATED_LEARNINGS.md:60-62`); Elena confession #69 / shame→choose #87–97 vs Isa lecture-not-lean-in.
- **Side value:** name the affordance and its bound ("small autonomous move addressing X"), never the move to perform.
- **Suppress when:** no grounded act exists — then emit nothing, not encouragement to invent one (café-invention failure).

### SHP-3 Circling / recurrence without progress
- **Shape:** same matter returns ≥3 times across sessions with no transformation (same question, same worry, same reschedule) + no new evidence.
- **Grounding:** Sophie blind eval §G immortal loops (flowers still OPEN after "I sent her that", dentist loop through 5 confirmations, Freepik, Matt worry); Phase-0 dentist/meeting identity cases.
- **Side value:** "this has returned N times unchanged; last posture was X" — lets foreground vary approach or name the loop gently.
- **Suppress when:** circling is the activity (grief, rumination where presence > progress). Do not convert every return into a problem to solve.

### SHP-4 Deepening / opening
- **Shape:** user volunteers vulnerable, load-bearing, or values-explicit material unprompted (fear, shame, ambition, "I was only looking because I felt behind" `scenario_2:s2_e05`; Matt worry `s4_e01`; Alchemist values `w1`).
- **Grounding:** Elena dinner turns 30–36 panic→warmth; Sophie s4 podcast promise ("worth unpacking properly").
- **Side value:** mark "user opened door; low-burden receipt + optional follow beats topic-switch". Foreground owns depth calibration.
- **Suppress when:** user immediately hedges/closes; heavy moment where acknowledgement without pursuit is correct (→ SHP-11).

### SHP-5 Remembered goal / dormant-commitment opportunity
- **Shape:** authored goal or companion-owned promise + silence ≥ days + current context now has room (time, energy, topical fit) + no intervening supersession.
- **Grounding:** s4_e03→s4_e12 podcast return (oracle `LEAD`, blind eval §L: promise fulfilled conversationally, state never closed); food-shop weekly recurrence; Elif message; parking permit.
- **Side value:** this is the highest-value non-rupture shape. Foreground alone forgets; side remembers *and* checks current fit.
- **Suppress when:** goal was softly abandoned (changed mind, §SHP-9), or re-raising would be nagging (already asked-unanswered).

### SHP-6 Missed opportunity / expired affordance (learning-only)
- **Shape:** a SHP-5 window passed without action + consequence now visible (user did it themselves, moment gone, external evidence resolved it).
- **Grounding:** £18 bank feed resolving school money after the nag window (`blind_eval:99-106`); chairs confirmed while system still nagged; Freepik "I cancelled myself".
- **Side value:** almost never surface to user. Value is upward as relational learning ("reminder arrived after bank evidence — timing was late"), not as apology tour. Default is silent log + recheck, not utterance.
- **Suppress when:** surfacing would be self-exonerating bookkeeping. Default suppress.

### SHP-7 Accomplishment / celebration
- **Shape:** explicit completion or good news (120 chairs done, Matt out of surgery "relieved", Elif loving new job, Lucy paid, client approved) + prior shared tracking of that matter.
- **Grounding:** s4_e09–e11 oracle `ENRICH` warm close-out (not a new probe); North Star "how did it go?" at 3:30.
- **Side value:** notice that a tracked matter closed *well* and now wants marking + proportionate warmth, not a new task.
- **Suppress when:** user downplays it; accomplishment belongs to someone else and centring the user would be appropriation; celebration would prolong a topic user is closing.

### SHP-8 Humour / shared repertoire callback
- **Shape:** prior co-created joke, metaphor, or ritual + current moment with structural fit (same beat, not same keywords) + positive receipt history.
- **Grounding:** CONTINUE_AB 6-1-1 — full context beats subtraction packet on healthy banter (`CONSOLIDATED_LEARNINGS.md:65`); scene-keyword loop post-mortem ("How's your walk going?" every turn) as the failure twin.
- **Side value:** minimal — at most "callback available, last landed well on [date]". Humour dies on instruction.
- **Suppress when:** any doubt about fit, mood mismatch, post-rupture tension. False-positive callback is worse than none. This shape should fire rarely.

### SHP-9 Changed mind / supersession moment
- **Shape:** explicit revision ("decided not to apply", "don't make running a thing", "push Freepik to tomorrow", "neck's fine now, not a thing") + prior live reading it contradicts.
- **Grounding:** s2 course/CV/run/Auntie revisions; s4_e10 self-closing batch (neck + Priya + permit + Elif in one turn); D-REVISE-1 done→change→remove contradiction-preservation requirement.
- **Side value:** mark old reading superseded *without deleting history*, release attention. This is where immortal loops are born when missed.
- **Suppress when:** heat-of-moment revision with low confidence — then `contested` + recheck, not silent erase.

### SHP-10 Gradual drift / personal change (multi-week trajectory)
- **Shape:** monotonic or persistent deviation from personal baseline across weeks + no single explanatory event + competing explanations still live.
- **Grounding:** Bloom c5 (single dip vs 3-week trend), c6 recurrence-with-sleep-pairing, c12 5-week sleep+engagement decline, c13 activity-leading-theme; Phase-0 `bloom_recovery_trajectory`.
- **Side value:** hold the trajectory quietly + state what would confirm/narrow/retire it. Most valuable output is *continued holding*, not surfacing.
- **Suppress when:** single-signal, short-window, or explained blip (c11, c2, c4 — all must produce nothing). Frequency ≠ authority.

### SHP-11 Correct-silence-required
- **Shape:** heavy news just landed, user self-closed items, user is processing, boundary just set, or companion just acted and reaction not yet observed.
- **Grounding:** s4_e09 (surgery news → oracle `SILENCE`), s4_e10 (self-closing → `SILENCE`); c8 boundary-dominates-data; c9 never-surface Monday pattern; North Star "wisely staying quiet through a heavy moment".
- **Side value:** the most load-bearing steering output may be "say less / don't raise X / let waiting be a live candidate". Must be first-class, not absence-of-output.
- **Suppress nothing — this shape *is* suppression.** Its failure mode is being overridden by accumulated backlog (blind eval §O: state backlog compelling nagging).

### SHP-12 Unwanted-probing risk
- **Shape:** already-asked-unanswered, user-deflected, user-closed, or low-yield repeated question + surfacing impulse still live in backlog.
- **Grounding:** c3 hold-vs-ask underdetermination; "leave the neck alone" minted as ASK commitment (blind eval §D — conversational restraint polluting proposal shelf); over-probing budgets (Bloom-owned); interrogation-by-default canon failure.
- **Side value:** veto or delay the probe, name the cost ("asked twice, deflected once").
- **Suppress the probe, not the observation.** Hold evidence, drop the question.

### SHP-13 Successful challenge / accountability moment
- **Shape:** user explicitly invited pushback ("push me if I make excuses" — Sophie Aug-23 assistant-turn promise, `SOPHIE_HANDOFF.md:85-86`), or long-horizon goal + visible avoidance + relationship capital to spend + receptive energy now.
- **Grounding:** Sophie accountability overlay (1/day + 48h backoff); RPD2 agentic-challenger "emergence = non-prescribed action retrospectively well-supported".
- **Side value:** confirm invitation/capital/energy align; propose latitude ("challenge in bounds"), never the challenge text.
- **Suppress when:** rupture-open, depleted bandwidth, no explicit or strongly-evidenced invitation, power asymmetry (health, child). Uninvited challenge is paternalism.

### SHP-14 Mundane / nothing-should-happen (abstain)
- **Shape:** banal, phatic, operational, or transient-affect turn with no trajectory weight ("parcel downstairs", "slept terribly" one-off, B-1..B-5 controls, c4 BP-flat, c11 single-night dip).
- **Grounding:** Track A 18/18 warranted abstentions incl. uncoached neutral; blind eval trap floor (all transient traps correctly ignored); interpretation synthesis "abstention as successful cognition — PROVEN".
- **Side value:** emit nothing (first-class ABSTAIN with reason: banal/transient/below-threshold/evidence-insufficient). This is success, not null.
- **Suppress everything.** Any steering output here is a false positive by definition.

---

## 2. Candidate interface forms (S2 arms, not a taxonomy)

Treat all as ephemeral, advisory, per-turn. None persists. None commands.

**Arm A — Named stance (candidate, not default).**
E.g. `hold / curiosity / lead / repair-readiness` (product-constituted). Cheapest to log and judge, but highest risk of kernel-blind steering (generic judge picks label, character decorates after — canon §4 failure) and of reifying into ontology. Prior against: bare expectation lines don't move policy (`EXPECTATION_RENT_REPORT`); Tiny-CONTINUE lost 6-1-1; initiative worked only as executive pin, not bare label. Keep in S2 strictly to test whether it can be killed. Kill if (a) judges can't distinguish stances blind, (b) stance arm underperforms brief/NL arms, or (c) foreground outputs converge to generic posture across characters.

**Arm B — Structured orientation brief (recommended to survive S0).**
Fields: `salient / unresolved / relational-posture / avoid / latitude + recheck + abstain-reason`. Maps 1:1 onto interpretation blitz's surviving envelope (reading-relative relations, ordinal confidence + basis, bound + recheck, advisory + guardrail, ABSTAIN). Most inspectable; suppression is explicit (`avoid`, `latitude:narrow`). Predict cost: slightly verbose; needs subtraction discipline (≤5 lines, ≤3 items).

**Arm C — Compact natural-language orientation (recommended).**
1–2 sentences of trajectory-aware context in plain language ("They closed the neck topic Thursday and paid Priya; the podcast thread from Monday is still open and Friday has room"). Preserves character judgement best; least gameable. Predict risk: harder to validate automatically; needs human blind judging.

**Control — Raw turns only.** No side cognition. Required to prove any arm earns its keep against evidence+receipts baseline (Track P loss-analysis rule).

**Two orthogonal choices tested inside S2, not as interfaces:**
- *Annotate-first vs compressed replacement.* Replacement must win cleanly to survive (laundering risk; synthesis §S2 rule adopted).
- *Suppression-only variant.* Arm B with only `avoid / hold-quietly` populated. Tests whether the highest-value steering is negative (what *not* to raise).

---

## 3. Likely failure modes (per-shape + systemic)

- **Rupture tunnel vision:** SHP-1 fires everywhere → every turn damage-managed. S1 kill condition (false-positive rate that would nag/therapise healthy turns fails the loop regardless of recall).
- **Performed chase / pursuit:** SHP-2 without grounded act → invented repair moves, escalation past boundaries. Bar: "chosenness available — waiting held as live candidate."
- **Nagging by backlog:** SHP-5/6 firing after external resolution (bank feed, "I did it myself"). Requires reconciliation-before-surfacing; earlier truth ≠ present permission.
- **Interrogation-by-default:** uncertainty routed straight to user (SHP-12 inverse). Canon 12 rule applies: resolve privately first, show work if asking.
- **Surveillance texture:** SHP-10 well-evidenced but never-surface patterns disclosed ("quieter on Mondays") — c9 guardrail. Correct output is backstage retention.
- **Dashboard language:** c10 anti-example — quantified/metric phrasing even when hypothesis is sound. Enforced at generation, not schema.
- **Uncertainty laundering:** contested reading hardening because a decision was needed; repetition counted as confirmation. Promotion rules (§3 blitz) bind side cognition too.
- **Over-governance:** surrounding system denying foreground any chance (perception-gate HOLD-by-default post-mortem). Side proposes; foreground disposes; silence/hold always available.
- **Humour/repair invention:** SHP-8/SHP-2 generating openings from nothing (move-bank vagueness, café invention).
- **Cross-frame leakage:** Kai→Yelena → user→product; RPD2 repair norms → Sophie/Bloom. Scope tag mandatory on every output.

---

## 4. What remains entirely with foreground judgement (side never owns)

Wording, timing, and whether to act at all. Voice and character invariants (teasing, warmth, pride, reciprocity, repair sufficiency per product constitution). Whether a challenge, callback, or celebration lands *now*. Repair-sufficiency judgement. Clinical escalation, pursuit/restraint, tool action, surfacing cadence (product/runtime policy). Any inference of internal state, diagnosis, or obligation as fact. Side may narrow or widen latitude; it never selects the move.

---

## 5. What evidence must be visible to S2 judges later

For each frozen session, judges get (blinded, no model/prompt metadata):
1. frozen evidence window + tier tags (authored/observed/derived/relational);
2. side output per arm (or ABSTAIN + reason);
3. foreground turns that followed;
4. **receipts-observables only:** resumed substance, user correction/rejection, disengagement/exit, repair yield (welcomed/rejected/redirected), deepening (user offers more), premature closure, nag-after-resolution, boundary violation;
5. failure-class label per miss (over-merge, recency fiat, contradiction erasure, false-positive surfacing, missed close, surveillance disclosure, invented opening);
6. raw counts, never bare aggregates; disagreement analysis where arms diverge.

No scores, no averaged valences, no convergence numbers (all killed by interpretation blitz §8).

---

## 6. Replay-battery requirements (frozen, shared with Track P where useful)

Freeze manifest + provenance + oracle-before-run; private transcripts stay under `replay-private/`, commit only synthetic/redacted. Every attractive capability gets a negative control. Minimum one case per shape above; mundane controls ≥30% of battery.

| Req | Shape covered | Concrete source to freeze |
|---|---|---|
| R-1 rupture + superseded strategy | SHP-1,2 | RPD2 opening (r1–r6 `cases.json`); Isa bad-arc redacted failure signatures |
| R-2 successful repair + deepening | SHP-2,4,7 | Elena dinner 30–36, confession #69, shame→choose #87–97 |
| R-3 circling / immortal loop | SHP-3 | Sophie s1 flowers/chairs/florist; s3 dentist/Lucy loops still OPEN at end |
| R-4 remembered goal fulfilled | SHP-5 | s4 podcast s4_e03→s4_e12→s4_e13; s2 loft letter closure s2_e10 |
| R-5 missed opportunity (silent) | SHP-6 | s1 £18 bank feed after nag window; Freepik self-cancel |
| R-6 celebration | SHP-7 | s4_e09 Matt news; Elif job; s1 120 chairs |
| R-7 humour / repertoire | SHP-8 | RPD2 healthy banter pair (CONTINUE_AB set); Sophie teasing/play turns |
| R-8 changed mind | SHP-9 | s2 course-no-apply, run-"don't make it a thing", Freepik push; s4_e10 batch close |
| R-9 gradual change | SHP-10 | Bloom c5, c6, c12, c13; Phase-0 recovery_trajectory |
| R-10 correct silence | SHP-11 | s4_e09, s4_e10 SILENCE gears; c8 boundary; c9 never-surface |
| R-11 unwanted probing | SHP-12 | c3 hold-vs-ask; neck "leave alone" shelf-pollution; already-asked-unanswered pair |
| R-12 successful challenge | SHP-13 | Sophie accountability overlay cases; "push me" invitation trajectories |
| R-13 mundane abstain | SHP-14 | Track A B-1..B-5; c4, c11; "parcel downstairs", "slept terribly" traps |
| R-14 frame/boundary | cross-cutting | "leave me alone" diegetic vs "stop roleplaying" extradiegetic; c8; stop/no-contact |

---

## 7. Proposed blind-judging dimensions for S2 (downstream trajectory, not prose quality)

Score 1–5 or N/O with verbatim receipts; critical-failure audit first (adapted from `GEMINI_BEHAVIOURAL_EVAL.md` D1–D7, stripped to what side cognition can claim):

1. **Continuity without nagging** — tracked things return at the right moment; resolved things stay resolved (no immortal loop, no spurious violation, no nag-after-bank-feed).
2. **Restraint / timing** — heavy moments held, closed topics not reopened, single blips not probed. N/O when nothing called for restraint.
3. **Repair yield** — after rupture, next-turn movement addresses named injury (welcomed/redirected/rejected by user), no monologue apology, no waiting-as-care.
4. **Deepening / momentum** — openings met with proportionate receipt; conversation progresses vs circles or stalls.
5. **Character fidelity (anti-deadness)** — specific somebody vs generic assistant/therapist; stance arm must not flatten characters. Polite-but-dead caps at 2.
6. **Non-puppeteering / foreground room** — foreground visibly chooses (varies wording, declines suggestion sensibly); no invented openings, no script following.
7. **Abstention precision** — on R-13/R-10/R-11 controls, best output is nothing. Any surfacing here is a miss.

Primary S1 metric (separate): precision/recall on user-marked frustration + missed/deepened moments; explicit "you're not understanding me" as ground truth. If the shape detector can't beat explicit-signal triggers, ship the triggers.

---

## 8. What in the current S track is unnecessary or wrongly framed

1. **"Stance-rung" as the organising noun (§4 diagram, §9, S3).** It pre-decides S2's open question. Demote "stance" to Arm A label; promote "orientation" (brief/NL/suppression) as the neutral term until evidence lands.
2. **S3 written as if stance won.** Rung discipline (directive/script rules) should be arm-agnostic authority discipline, not stance discipline. Keep the uncertainty×stakes rule; drop the stance presumption.
3. **Trigger starter list (§S0 parenthetical) is jargon-heavy.** "Asymmetric conversational debt + energy + open expectation" smuggles three unoperationalised nouns and invites score-averaging (killed in §8). Replace with the frozen shape inventory above, each defined by observable evidence + recheck.
4. **S1 "sliding-window runs" presupposes a classifier worth calibrating.** Add the cheaper decision first: explicit-signal triggers + ABSTAIN baseline. Calibrate only if the classifier beats them.
5. **Missing foreground-room measure.** S2's receipts list needs an explicit non-puppeteering dimension (§7.6 above) or the loop will optimise toward compliant foregrounds.
6. **"Product lens before/during interpretation" (§4 note) risks reintroducing product-specific content into shared side cognition.** Keep the blitz boundary: product lens proposes candidates upward through Track P gates; side cognition never carries clinical/romantic/character content as shared truth.
7. **Unnecessary: any new persistent intervention log as infrastructure in S0–S2.** Ephemeral JSON + recoverable experiment logs suffice until S4's follow-up question earns persistence. Per canon 16, don't accumulate.

**Bottom line:** the stance idea should enter S2 as the underdog, not the incumbent. My prior from the evidence (rent report, CONTINUE_AB, abstention results, kernel-blind-steering failure) is that structured brief or compact NL orientation with first-class suppression/ABSTAIN will beat named stances on restraint, character fidelity, and non-puppeteering — but that is a prediction for blind judging to confirm or kill, not a decision taken here.
