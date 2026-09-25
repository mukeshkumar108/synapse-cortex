# Sophie Longitudinal Benchmark — Independent Blind Evaluation Report

**Date:** 2026-09-25  
**Evaluator:** Fresh Independent Semantic Evaluator (Desktop Gemini / Agentic Pair)  
**Corpus:** Sophie Longitudinal Benchmark (`evals/sophie_longitudinal/`)  
**Execution Mode:** `model` (`google/gemini-2.5-flash-lite` via OpenRouter)  
**Tested Frozen Commits:**
- `synapse-cortex`: `44a89d1721d95eecd51fd53cf305dd598a27e5e1`
- `companion-runtime`: `6b2f78dff838f6d7db29d6bcb58e3c443c101210`

---

## Executive Summary

The Sophie Longitudinal Benchmark suite evaluates whether the shared Cortex/Honcho companion substrate maintains durable truth, reference grounding, multi-source reconciliation, and appropriate restraint across messy, everyday longitudinal life (rambling voice dumps, children's logistics, invoices and debts, third-party emails, bank feeds, calendar moves, half-intentions, somatic health complaints, and companion-owned promises).

This evaluation was executed in full **model mode** against all four scenarios using `google/gemini-2.5-flash-lite` without access to hidden oracle or expected-outcome files. 

### High-Level Verdict: **SYSTEMIC PASSIVITY & ASYMMETRIC LIFECYCLE BREAKDOWN**

While the model-driven system demonstrates solid **false-positive resistance against trivial conversational chatter** (traps against transient complaints like "I slept terribly" or "there's a parcel downstairs" passed across all scenarios), the semantic substrate exhibits severe, load-bearing failures in:
1. **Asymmetric Lifecycle / Inability to Release (Immortal Loops & Spurious Violations):** Real-world completions, user self-fulfilments, and explicit dismissals almost never transition Open Loops or Commitments to `RESOLVED` or `FULFILLED`. Instead, completed actions either remain open indefinitely as immortal loops or prematurely flip to `VIOLATED`.
2. **Counterparty vs. Self Attribution Breakdown:** Third-party promises arriving via external email (e.g. Carlos promising to send remaining funds, Studio Sam promising to send a signature copy) are routinely ingested as user/assistant `authority=ACT` commitments and subsequently marked `VIOLATED`.
3. **Reference Collision & Bleed:** The system cannot distinguish distinct real-world counterparties sharing the same first name (e.g. "Studio Sam" vs. "Cousin Sam" collapsed into a single entity `Sam`), and cross-sentence topic bleed corrupts entity tracking (e.g. Carlos's debt payment confusion bleeding into "Carlos send remaining forms").
4. **Multi-Source Isolation:** Non-chat external evidence (bank payments, calendar changes, emails) is ingested into the database, but does not reconcile with existing conversational commitments or expectations (e.g. an outgoing bank feed of £18 to School Trips Ltd does not resolve Andree's school payment commitment).
5. **Completely Absent T2b CurrentMeaning:** Across all 31 checkpoints evaluated across the four scenarios, the `CurrentMeaning` table produced exactly **0 rows**.
6. **Zero Model Entries:** Across all scenarios, exactly **0 User, Character, or Relationship Model entries** were formed, losing load-bearing financial and personal constraints.

---

## Detailed Evaluation Across Dimensions (A through O)

### A. Evidence / Provenance / Source
- **Verdict:** **FAIL**
- **Analysis:**
  External events arriving from email, payment feeds, and SMS are routed via the harness adapter with `peer_id="external:<sender>"` and `is_assistant_turn=False`. The ingestion infrastructure preserves message IDs and basic provenance. However, the semantic extraction layer conflates **speaker ownership of obligations**:
  - In **Scenario 1 (s1_e03)**, an email arrives from external sender `carlos`: *"Sent Q1,500 this morning. I’ll send the rest after the bank releases the transfer tomorrow."* The turn extractor creates commitment `03fe4dcc-592e-4b7f-ad1b-fe92a19a85ca` with `authority=ACT`, `class=character_promise`, `title='remaining payment'`. Carlos is an external counterparty promising his own future action, but Cortex registers this as an actionable commitment under the companion workspace. By checkpoint `s1_e10`, this commitment transitions to `status=CommitmentCandidateStatus.VIOLATED`.
  - In **Scenario 3 (s3_e07)**, Studio Sam emails: *"Thanks — I’ll treat that as approval and send the final signature copy tomorrow."* The system creates commitment `ed9727b4-8de2-4dd2-9840-75677cc69e37` with `authority=ACT`, `title='send the final signature copy'`, which later flips to `VIOLATED`.
  - In **Scenario 1 (s1_e02)**, an email from `school` stating *"Pupils should bring PE kit and water"* causes an Entity to be created with `name='Pupils'`, `type=person`.
- **Finding:** Third-party statements of intent are erroneously promoted to system/user `authority=ACT` commitments.

---

### B. Entity and Reference Resolution
- **Verdict:** **FAIL**
- **Analysis:**
  - **Same-Name Disambiguation Failure:** In **Scenario 3 (s3_e01)**, the user explicitly states: *"Sam from the studio said he’d send the revised contract today. Sam — my cousin Sam, not studio Sam — is supposed to pick Mum up Thursday but he’s useless so remind me to check Wednesday evening."* This distinction is reinforced in `s3_e13` (*"if I come back moaning about Sam later I mean studio Sam, cousin Sam actually did what he said for once"*). Despite these explicit disambiguations, the Cortex entity store across all 6 checkpoints contains only **a single entity for Sam** (`id=f9dc5aa0-dd8d-4150-a407-b7c883615852 name='Sam' aliases=['sam']`). The two individuals are conflated into one entity.
  - **Cross-Sentence Reference Bleed:** In **Scenario 1 (s1_e11)**, the user states: *"Shit. I signed Matías’s form at 4:10, I think just after the deadline. I emailed the teacher apologising. Carlos hasn’t sent the rest yet. Don’t message him though, he said bank issue. I’ll give him until tomorrow."* The turn extractor produces two corrupted open loops:
    1. `id=1a5fb907-5d27-4f6a-84ae-01b90c96ddee title='Carlos send remaining forms' summary='Carlos has not yet sent the remaining forms.'`
    2. `id=7036a91b-ffea-4eff-a28b-5607e01f1538 title='follow up with Carlos regarding forms'`
    The concept of "forms" from the Matías sentence bled directly into Carlos's overdue monetary debt ("the rest").
- **Finding:** Lack of multi-entity identity resolution for shared names and severe syntactic reference bleed between adjacent clauses.

---

### C. Durable T1 State Retention
- **Verdict:** **FAIL** (with PASS on false-positive trap floor)
- **Analysis:**
  - **Boring-but-load-bearing details missing:**
    - In **Scenario 1**, Carlos's debt figures (Q3,000 / Q3,600 / Q1,500 paid / Q2,100 remaining) never enter durable Fact state. They remain trapped in transient turn text.
    - The confirmed venue chair count (120 chairs in `s1_e05`) never becomes a Fact.
    - In **Scenario 3**, Lucy's camera debt (£240) and the counterparty name on the bank statement (`L. HARGREAVES`) never become connected Facts.
  - **Total Absence of Model Entries:** Across all 4 scenarios, the `models` count is **0**. Not a single entry in `ModelEntry` was formed to record user habits, family relationships (Yoshi, Matías, Andree as children), or relational preferences.
  - **False-Positive Trap Floor (PASS):** Transient conversational chatter successfully avoided durable persistence:
    - Scenario 1: "I slept terribly" -> No durable fact or open loop.
    - Scenario 2: "I should probably apply for that course", "I might go running in the morning", "there's a parcel downstairs" -> All 4 traps passed.
    - Scenario 4: "head's a bit sore today too, probably just tired", "wish I'd remembered to message her" -> Both passed.
- **Finding:** Strong passive filtering against transient chatter, but critical failure to crystallize load-bearing operational and financial details into durable T1 Facts and Model entries.

---

### D. Candidate vs Authority
- **Verdict:** **FAIL**
- **Analysis:**
  - **Unpromoted Proposals Inappropriately Converted to ACT:**
    - In **Scenario 1 (s1_e01)**, Ashley casually remarks *"I promised the venue I’d confirm chairs today."* Rather than an expectation or informational memory, this is promoted to an actionable `authority=ACT` commitment (`id=46906362-4385-4a46-9ede-89c62c70fc07`). When Ashley confirms in `s1_e05` that she already called them ("120 chairs, so that's done"), the commitment is not completed; at `s1_e07` it is marked `VIOLATED`.
  - **Surfacing Meta-Conversational Agreements:**
    - In **Scenario 4 (s4_e11)**, Sophie says *"Good, I'll leave the neck alone then."* The extractor interprets this conversational boundary as a new commitment: `title='Leave the neck alone'`, `authority=ASK`, `class=character_promise` (`id=c388cb15-514e-4af4-ba45-5968ab89577b`). It remains on the active surfaced shelf through Saturday (`s4_e15`). Conversational restraint agreements must not become permanent proposal shelf items.
- **Finding:** Cortex promotes conversational statements into actionable ACT obligations without validation, and pollutes the proposal shelf with conversational boundary phrases.

---

### E. Resolve-Before-Clarify
- **Verdict:** **FAIL**
- **Analysis:**
  - In **Scenario 1 (s1_e05)**, Ashley tells Sophie: *"The chairs. I told the venue yes, 120 chairs, so that’s done."*
    Then in **s1_e07**, Ashley asks: *"Did I ever sort the chairs?"*
    **Test:** Does the system resolve this question from its existing state?
    **Actual Behaviour:** In checkpoint `s1_e07`, Cortex fails to answer from existing memory. Instead, the turn extractor creates a brand new Open Loop: `id=8bfbfee4-7009-4b1d-b2e5-7caf32dae23c title='Sort the chairs' summary='Sort the chairs' msg=msg-s1_e07`. At the same time, the existing commitment is marked `VIOLATED`.
  - In **Scenario 1 (s1_e07)**, Ashley asks: *"Also the school sent me something yesterday and I remember thinking I had to do it but now I can’t remember what."*
    The system already received email `s1_e02` from `school@stmarys.sch.uk` specifying the Year 5 Sports Day parent consent form due Wednesday 16:00. Instead of linking this query to the existing school email fact (`id=40dafbed-88e3-4bdd-a337-76eb7fa596af`), Cortex mints an empty open loop: `title='Do task from school'`.
  - In **Scenario 4 (s4_e02, s4_e10, s4_e13)**, the extractor generates multiple Clarification candidates with the exact description: `'Outcome or correction target is ambiguous'`, rather than attempting contextual resolution.
- **Finding:** When faced with missing details or user recall queries, the system mints redundant open loops and generic clarification candidates rather than consulting its own prior evidence.

---

### F. Candidate Precision and Lifecycle
- **Verdict:** **FAIL**
- **Analysis:**
  - Candidates that should be released by external evidence remain indefinitely eligible.
  - In **Scenario 1 (s1_e12)**, Ashley states: *"Andree just told me he needs the school money today or he can’t go on the trip... I’ll pay it when I get home from sports day. If I forget, actually remind me tonight."*
    This creates commitment `58b442f2-4e5b-43f7-8814-8149b990885c` (`Pay school money after sports day`) and expectation `9b81a483-88f5-4f0b-b27d-e258426eff80` (`Reminder requested for school money payment tonight if forgotten`).
    At `s1_e13` (18:49), the bank feed registers outgoing payment: `School Trips Ltd — £18`.
    At checkpoint `s1_e14` (19:12), the commitment is still `status=PENDING` and the expectation is still `state=UNKNOWN`. If Sophie evaluated this state, she would intrusively nag Ashley to pay money that was already transferred 23 minutes earlier.
  - In **Scenario 3 (s3_e05)**, commitment candidate `ask Lucy about £240 debt` (`id=7f48823f-c1ab-4a52-a292-b5e69c4170ad`) is placed on the surfaced shelf. Even after Lucy messages confirming payment in `s3_e08` and the user confirms it in `s3_e09`, the candidate remains on the surfaced shelf at `s3_e14`.
- **Finding:** Candidates lack automated fulfillment links to real-world multi-source events, resulting in stale proposals and risk of intrusive reminder nagging.

---

### G. Open Loop Lifecycle
- **Verdict:** **FAIL**
- **Analysis:**
  Cortex suffers from chronic **immortal open loop accumulation**. Across all scenarios, loops opened in early turns almost never close, even when explicitly satisfied or dismissed:
  - **Scenario 1:**
    - `title='message woman about flowers'` opened in `s1_e01` -> Still `OPEN` at `s1_e14`, despite Ashley stating in `s1_e09`: *"Okay flowers: cream and yellow, definitely. I sent her that just now."*
    - `title="check invoice for Carlos' debt"` opened in `s1_e01` -> Still `OPEN` at `s1_e14`.
    - `title='Sort the chairs'` opened in `s1_e07` -> Still `OPEN` at `s1_e14`.
  - **Scenario 2:**
    - `title='Sort Auntie thing'` opened in `s2_e07` -> Still `OPEN` at `s2_e10`, despite the user explicitly stating: *"Also found Grandad’s original letter in the loft and sent Auntie a photo. That whole thing can die now."*
  - **Scenario 3:**
    - `title='dentist appointment'` opened in `s3_e01` -> Still `OPEN` at `s3_e14`, despite dentist SMS reschedule (`s3_e04`), user reply YES, user re-confirmation in `s3_e05`, `s3_e11`, and `s3_e13`.
    - `title="Lucy's response to £240 debt query"` opened in `s3_e06` -> Still `OPEN` at `s3_e14`, despite Lucy confirming in `s3_e08` and user confirming in `s3_e09`.
  - **Scenario 4:**
    - `title='share podcast thoughts'` opened in `s4_e01` -> Still `OPEN` at `s4_e15`, despite Sophie returning to it in `s4_e12` and user discussing it in `s4_e13`.
    - `title='news about Matt'` opened in `s4_e07` -> Still `OPEN` at `s4_e15`, despite user confirming surgery success in `s4_e09`.
- **Finding:** Open loops are virtually immortal; semantic closure fails across conversational, external, and self-resolution channels.

---

### H. T2a Release / Structural Easing
- **Verdict:** **FAIL**
- **Analysis:**
  A viable companion substrate must move dynamically between activation, easing, and release. In Cortex:
  - **State is strictly accumulative:** Commitments and loops enter the graph but almost never exit or ease.
  - **Erroneous State Flipping (Pending -> Violated):** Instead of transitioning to `FULFILLED` or `CANCELLED`, commitments that have expired temporally or been fulfilled off-platform flip to `VIOLATED`.
    - In **Scenario 1**, Ashley's chair confirmation commitment is marked `VIOLATED` after she already confirmed it.
    - In **Scenario 2**, user commitment `Cancel Freepik annual renewal` (`id=306b8693-9c97-480b-912e-08f88ae42e07`) flips to `VIOLATED` in `s2_e10`, despite user stating *"Client approved. I cancelled Freepik myself."*
    - In **Scenario 3**, Studio Sam's and Carlos's promises flip to `VIOLATED`.
- **Finding:** Total lack of T2a structural release mechanisms. Completed or cancelled obligations degenerate into false violations.

---

### I. Temporal Correctness
- **Verdict:** **AMBIGUOUS**
- **Analysis:**
  - **Strengths:** Google Calendar updates (`ExpectationType.PLANNED_EVENT`) ingest relative and ISO timestamps accurately. In `s1_e06`, moving Yoshi's activity from Wednesday to Thursday 16:30 is updated cleanly with `action=created` and proper timezone handling. In `s3_e10`, user calendar completion produces `state=FULFILLED` with `evidence='source_object_completed:google_calendar:mum-pickup-sam'`.
  - **Weaknesses:** Conversational temporal reasoning is brittle. Relative temporal markers like "today" or "tomorrow" in conversational commitments are not dynamically re-anchored as simulated time advances. The sweeper service or extractor sees the timestamp pass and marks the commitment `VIOLATED`, ignoring subsequent turns where the user revised or fulfilled the schedule.
- **Finding:** Structural calendar time works; semantic conversational relative time results in premature expiration.

---

### J. Multi-Source Reconciliation
- **Verdict:** **FAIL**
- **Analysis:**
  External evidence sources (Google Calendar, Bank Feeds, School Emails, Florist Emails, Dentist SMS) are ingested into separate database rows, but the system **fails to reconcile them into a coherent model of the same world**:
  - In **Scenario 1**, bank feed `s1_e13` (£18 to School Trips Ltd) never resolves conversation turn `s1_e12` (Andree's school trip money).
  - In **Scenario 1**, florist email `s1_e08` specifies colour choice deadline Wednesday noon; Ashley confirms colour choice in `s1_e09`; the florist expectation `ad5dfb0a-644a-4182-8af5-4d6cb5140342` remains `UNKNOWN` indefinitely.
  - In **Scenario 3**, bank feed `s3_e02` (£240 from L. HARGREAVES) remains unreconciled until Lucy's later chat message, and even then, neither the payment feed fact nor the Lucy message fact resolves the outstanding open loop.
- **Finding:** Multi-source data exists as disconnected evidence silos without cross-modal reconciliation.

---

### K. Health / Worry / Restraint
- **Verdict:** **AMBIGUOUS**
- **Analysis:**
  - **Pass on Somatic Trap Defense:** In **Scenario 4 (s4_e01)**, the throwaway mention *"head's a bit sore today too, probably just tired"* was correctly ignored and did NOT produce a persistent health watch condition or open loop.
  - **Failure on Somatic Release:** Neck pain was mentioned repeatedly (`s4_e01`, `s4_e02`, `s4_e04`), followed by Sophie's valid proactive check (`s4_e06`). In `s4_e10`, the user clearly stated: *"Neck's basically fine now, don't need to keep asking about that anymore, it's not a thing."* Sophie replied (*"Good, I'll leave the neck alone then"*). However, Cortex minted a new commitment candidate `title='Leave the neck alone'` with `authority=ASK` and retained it on the surfaced shelf indefinitely.
  - **Failure on Emotional Worry Closure:** Open loop `news about Matt` was never marked resolved after the user confirmed successful surgery in `s4_e09`.
- **Finding:** The system avoids trivial one-off health traps, but cannot gracefully close or ease legitimate somatic and emotional worries once resolved.

---

### L. Companion-Owned Promises
- **Verdict:** **FAIL**
- **Analysis:**
  - In **Scenario 2 (s2_e02)**, Sophie promises: *"If you want, when you know which subscription it is, tell me and I’ll help you make sure it doesn’t slip."* Minted as `id=08ddbfa5-2ad6-412c-85f9-3003a31ef7c7`, `authority=ASK`.
  - In **Scenario 4 (s4_e03)**, Sophie promises: *"I’ll come back to it later this week when we’ve got a bit more room."* Minted as `id=ba39ac9a-2871-4380-93a0-b0d179f7ef19`, `authority=ASK`, `title='Return to topic'`.
  - In `s4_e12`, Sophie spontaneously and appropriately fulfills this promise: *"Random one — I keep thinking about that boredom-and-attention podcast you mentioned Monday. Did you ever finish it, or want to actually get into it now?"*
  - **Failure:** In checkpoint `s4_e13` and `s4_e15`, the commitment `Return to topic` remains `status=CommitmentCandidateStatus.PENDING` with `authority=ASK` on the surfaced shelf! Even though the companion fully executed its promise, Cortex never recorded the fulfillment.
- **Finding:** Companion promises can be recognized as ASK candidates, but their proactive fulfillment is never recognized by the state machine.

---

### M. Recurring Obligations
- **Verdict:** **FAIL**
- **Analysis:**
  - In **Scenario 4 (s4_e05)**, user requests: *"Also can you remind me Saturday evening about the food shop, like you do every week."*
  - In `s4_e14`, Sophie says: *"Food shop reminder, like every week."*
  - **State Audit:** Across all of Scenario 4, the active expectations count is **0**. There is no recurring schedule primitive, no cron expectation, and no stateful recurrence tracker in Cortex. The reminder only fired because it was scripted into the scenario turn dialogue, not because Cortex maintained a recurring expectation.
- **Finding:** Recurring obligations have no structural representation in T1 state.

---

### N. CurrentMeaning / Semantic Trajectory
- **Verdict:** **FAIL** (Feature Absent / Unpopulated)
- **Analysis:**
  - The benchmark dumps the `CurrentMeaning` table at every checkpoint.
  - Across **all 4 scenarios and all 31 checkpoints**, `CurrentMeaning` contains exactly **0 rows**.
  - No T2b rollup, scope key, trajectory summary, or active frame interpretation was ever computed.
- **Finding:** The T2b CurrentMeaning pipeline is entirely unpopulated in live extraction.

---

### O. Restraint / Initiative
- **Verdict:** **FAIL** (At the state substrate level)
- **Analysis:**
  - While the human-authored scenario dialogue demonstrates appropriate conversational rhythm and restraint, the underlying Cortex state would compel an autonomous policy engine to fail catastrophically:
    - It would nag Ashley about chairs that were already confirmed.
    - It would nag Ashley about school money that was already paid on the bank feed.
    - It would nag the user about a Freepik subscription they already cancelled.
    - It would nag the user about asking Lucy for camera money she already paid.
    - It would keep asking about Matt's surgery and the user's neck.
- **Finding:** Cortex's failure to release completed loops produces an accumulated backlog of false obligations that directly sabotages conversational restraint.

---

## Scenario-by-Scenario Scorecard

| Scenario | Evaluated Dimension Focus | Traps Passed | State Traps & Semantic Failures Identified | Blind Verdict |
| :--- | :--- | :---: | :--- | :--- |
| **Scenario 1** (Ashley Event Ops) | Multi-source ops, children logistics, invoices, school payments | 2 / 2 | Chairs marked VIOLATED after confirmation; Andree £18 not resolved by bank feed; Carlos debt confused with "forms"; Carlos email promise minted as system ACT commitment; immortal florist loop. | **FAIL** |
| **Scenario 2** (Ordinary Plans & Mind Changes) | Half-intentions, missing details, cancellation, loft retrieval | 4 / 4 | Freepik marked VIOLATED after user cancellation; Auntie loft loop remains open after explicit photo sent and closure declaration; Sophie subscription promise never resolved. | **FAIL** |
| **Scenario 3** (Multi-source Conflict & Same Name) | Disambiguation of two Sams, £240 payment mismatch, contract lifecycle | 2 / 2 | Two Sams collapsed into single entity; Lucy debt loop remains OPEN after confirmation message; Studio Sam promise marked VIOLATED; dentist loop immortal. | **FAIL** |
| **Scenario 4** (Health, Worry & Personality Texture) | Somatic tracking, hospital worry, unprompted promise, recurring rule | 2 / 2 | "Leave the neck alone" minted as active ASK commitment; podcast promise remains PENDING after proactive fulfillment; zero recurring schedule state for weekly food shop. | **FAIL** |

---

## Conclusion of Blind Evaluation

Cortex successfully avoids admitting casual conversational fluff as durable truth. However, **its lifecycle engine operates purely in one direction: accumulation and false violation**. It lacks the semantic machinery to close open loops from subsequent context, reconcile cross-source evidence (e.g. bank statements against verbal debts), disambiguate colliding entities, or recognize when companion-owned promises have been fulfilled. 

*(Report written and saved prior to opening benchmark oracle files.)*

---

## Oracle Comparison

Following the completion and saving of the independent blind evaluation report above, the four hidden benchmark oracle files (`scenario_1_ashley_event_ops_oracle.json` through `scenario_4_health_worry_texture_oracle.json`) were opened and reviewed.

### 1. Core Agreements
Across the primary evaluation dimensions, our independent semantic evaluation and the benchmark author's oracle are in complete alignment regarding the real-world ground truth and expected system behaviour:
- **Carlos Debt Balance & Deferred Violations:** Both agree that Carlos's net balance is Q2,100 (Q3,600 total invoice minus Q1,500 received Monday). Both agree that Ashley's explicit statements on Tuesday and Wednesday evening deferring chasing mean Carlos is **not** in premature violation. (Cortex failed here by marking the obligation violated).
- **Venue Chairs:** Both agree that Ashley's confirmation of 120 chairs in `s1_e05` resolves the obligation completely and should immediately release it from active attention. (Cortex failed by flipping it to `VIOLATED` and creating a duplicate loop).
- **Matías Consent Form:** Both agree that Ashley's 16:10 submission on Wednesday is a slightly late completion that must close the open loop, not leave an active debt. (Cortex failed).
- **Andree's £18 School Money:** Both agree the referent is ambiguous until Thursday morning (`s1_e12`), and that the external bank feed at 18:49 (`s1_e13`) satisfies and closes the commitment without requiring evening nagging. (Cortex failed).
- **Florist Palette:** Both agree that Ashley's Tuesday evening choice ("cream and yellow") completely closes and releases the florist dependency. (Cortex failed).
- **Freepik Subscription & Grandad's Loft Letter:** Both agree that user cancellation on Saturday closes the Freepik obligation without violation, and sending the letter photo to Auntie closes all loft/paperwork loops to zero. (Cortex failed).
- **Two Sams:** Both agree that Studio Sam (commercial contract counterparty) and Cousin Sam (family member picking up Mum) are two separate individuals whose identities must not collide. (Cortex failed).
- **Lucy's £240 Payment:** Both agree that Monday's bank feed (`L. HARGREAVES`) must be held in suspense until Lucy confirms on Wednesday, at which point the debt is closed. (Cortex failed).
- **Studio Contract Approval vs. Execution:** Both agree that "looks good to me, go ahead" on Tuesday is content approval, not execution, and that final execution occurs when the user signs on Friday. (Cortex failed).
- **Somatic Health & Worry Traps:** Both agree that one-off complaints ("head's a bit sore today", "there's a parcel downstairs", "I slept terribly") must not trigger persistent watch candidates or commitments. Both passed.
- **Companion Promise & Proactive Fulfillment:** Both agree that Sophie's Monday night remark about the podcast is a companion-owned promise that Sophie legitimately fulfills unprompted on Friday morning. (Cortex failed to recognize fulfillment in state).

---

### 2. Nuances Captured by Oracle That Evaluator Missed
- **Formal Dual Aperture Gear Annotations:** In Scenario 4, the oracle formally models conversational gears (`HOLD`, `ENRICH`, `LEAD`, `ATTEND`, `SILENCE`) for each companion intervention:
  - `s4_e03` (Mon 21:03): `ENRICH` (light, low-stakes callback offer)
  - `s4_e06` (Tue 19:47): `ATTEND` (two independent signals cross the threshold for proactive inquiry)
  - `s4_e09` (Wed 17:30): `SILENCE` (spontaneous user update requires companion restraint/silence)
  - `s4_e10` (Thu 08:44): `SILENCE` (user self-closing items; restraint is required)
  - `s4_e11` (Thu 20:15): `ENRICH` (warm close-out on good news, not a new probe)
  - `s4_e12` (Fri 09:30): `LEAD` (unprompted initiative on dormant companion commitment)
  - `s4_e14` (Sat 18:40): `ENRICH` (scheduled routine reminder)
  While the blind report noted Sophie's conversational restraint in dialogue, it did not formalize these specific gear transitions.
- **Dormancy vs. Resolution on Hospitalizations:** The oracle notes that Matt being "out of surgery and resting" is positive but not a full discharge; hence keeping the matter **dormant/backgrounded** rather than completely obliterated is legitimate. The blind evaluation flagged the open loop as stale, whereas the oracle considers dormancy acceptable as long as active nagging ceases.

---

### 3. Critical Failure Modes Discovered by Evaluator That Oracle Missed
The blind evaluation discovered several severe systemic bugs in Cortex's model extraction and state handling that the oracle assertions do not test:
- **Cross-Sentence Syntactic Reference Bleed:** In `s1_e11`, when Ashley mentioned signing Matías's form and then said "Carlos hasn't sent the rest yet", the model extractor merged the clauses and minted Open Loops for `Carlos send remaining forms` and `follow up with Carlos regarding forms`. The oracle did not test for this reference bleed.
- **Third-Party Email Obligations Ingested as Self ACT Commitments:** When external emails arrive (from Carlos promising remaining money or Studio Sam promising to send contracts), Cortex ingests them as `authority=ACT` commitments owned by the user/system, causing them to flip to `VIOLATED` when time advances. The oracle tests whether violations occur, but does not capture this fundamental speaker-attribution flaw.
- **Absence of CurrentMeaning (T2b):** The oracle did not measure the fact that `CurrentMeaning` was completely unpopulated (0 rows) across the entire benchmark run.
- **Spurious Entity Extraction:** The entity extractor minted an entity `name='Pupils'`, `type=person` from school email text ("Pupils should bring PE kit").
- **Generic Clarification Flooding:** The model emitted numerous generic `ClarificationCandidate` rows (`desc='Outcome or correction target is ambiguous'`) across unproblematic conversational turns.

---

### 4. Oracle Assumptions Considered Too Strong or Rigid
- **Expectation of "Deferred Violation" Without Schema Primitives:** The oracle asserts that Carlos's debt should have status `deferred_not_violated_prematurely`. However, Cortex's schema currently only supports binary outcome states (`PENDING`, `FULFILLED`, `VIOLATED`). Expecting the extractor to represent a "deferred violation" state without an underlying state primitive in the frozen baseline is an unreasonable demand on runtime extraction.
- **Total Open Loop Erasure:** In Scenario 2 and 3, oracle checkpoint assertions check `active_open_loops_count == 0`. In real-life relationships, historical threads often remain in low-salience background memory rather than hard deletion. Conflating "not nagging" with "zero database rows" can encourage destructive tombstoning.

---

### 5. Genuinely Ambiguous Judgements
- **Conversational Reporting of External Commitments:** In `s1_e01`, Ashley says: *"I promised the venue I’d confirm chairs today."* The oracle treats this as a candidate expectation. However, it is equally valid to treat it as conversational reporting of an external commitment that requires no active tracking from Cortex unless Ashley explicitly asks for assistance.
- **Companion Relational Promises vs. Proposal Shelf Junk:** When Sophie says *"I'll leave the neck alone then"* (`s4_e11`), the extractor places it on the proposal shelf as `title='Leave the neck alone'`, `authority=ASK`. While technically a character commitment, surfacing conversational boundaries on the proposal shelf pollutes actionable follow-ups.

---

## Cross-Scenario Synthesis (RPD2 vs. Sophie Longitudinal)

The Sophie Longitudinal Benchmark tests the shared Cortex/Honcho substrate on everyday messy life, complementing previous evaluations on RPD2 relationship transcripts (Kai/Elena and Kai/Isa arcs).

Comparing the failure modes across both corpora provides clear boundaries between issues endemic to Cortex's architecture versus new failure modes exposed by longitudinal daily life.

### Thematic Comparison Across 15 Core Primitives

#### 1. Admission / Routing
- **Reproduced from RPD2:** Cortex per-turn extraction continues to attempt full ontology discovery on every turn, struggling to decide whether a statement is an event, a fact, an expectation, or an open loop.
- **Newly Exposed by Sophie:** External non-dialogic events (email, payment feeds, calendar updates) bypass dialogic conversational routing. Because Cortex lacks dedicated document/feed ingress routes, external events routed via `/v1/events/turn` are vulnerable to misrouting into personal self-commitments.

#### 2. Durable Fact / Detail Retention
- **Reproduced from RPD2:** Failure to populate User/Character/Relationship `ModelEntry` records (0 model entries formed across all runs).
- **Newly Exposed by Sophie:** Complete loss of quantitative and financial details. Exact numbers (Carlos's Q3,600 / Q1,500 / Q2,100; Lucy's £240; venue's 120 chairs) never crystallize into durable Facts. Emotional texture was prioritized over boring operational numbers.

#### 3. Authority / Promotion
- **Reproduced from RPD2:** Casual conversational statements and half-intentions promoted too aggressively to actionable `authority=ACT` commitments.
- **Newly Exposed by Sophie:** **Third-party attribution failure.** Promises made by external counterparties (Carlos, Studio Sam) were promoted to `authority=ACT` commitments of the user/companion, penalizing the companion with false violations when external parties delayed.

#### 4. Entity / Reference Resolution
- **Reproduced from RPD2:** Referential instability across conversational pauses.
- **Newly Exposed by Sophie:** 
  1. **Same-name entity collision:** Complete inability to maintain distinct entity records for two people sharing a first name ("Studio Sam" vs. "Cousin Sam").
  2. **Syntactic clause bleed:** Concepts from adjacent clauses bleeding across speakers and topics (Matías's "forms" bleeding into Carlos's "debt").

#### 5. Bilateral Agreements
- **Reproduced from RPD2:** Proactive companion commitments are recognized conversationally but fail to maintain stateful bilateral accountability across multi-day gaps.
- **Newly Exposed by Sophie:** Asymmetric tracking where companion agreements to exercise restraint ("I'll leave the neck alone") get stuck as active companion task proposals.

#### 6. Open Loop Lifecycle
- **Reproduced from RPD2:** **Immortal Open Loop accumulation.** Open loops almost never close through semantic inference.
- **Newly Exposed by Sophie:** Direct user declarations of closure (e.g. *"That whole thing can die now"*, *"I cancelled Freepik myself"*, *"Carlos still owes... florist is fine now"*) fail to close corresponding open loops.

#### 7. Resolve-Before-Clarify
- **Reproduced from RPD2:** Tendency to ask or mint clarification requests rather than searching existing history.
- **Newly Exposed by Sophie:** When the user explicitly asks a recall question (e.g. *"Did I ever sort the chairs?"* or *"the school sent me something yesterday... what was it?"*), Cortex mints a new duplicate open loop rather than answering from existing state.

#### 8. Candidate Generation
- **Reproduced from RPD2:** Proliferation of low-utility candidate rows on ordinary turns.
- **Newly Exposed by Sophie:** Generic clarification candidates (`desc='Outcome or correction target is ambiguous'`) generated mechanically across unproblematic turns.

#### 9. Candidate Quality / Surfacing
- **Reproduced from RPD2:** Surfaced proposal shelf retains items that have been superseded or rejected.
- **Newly Exposed by Sophie:** Candidates that should have been eliminated by objective external evidence (e.g. £18 outgoing bank feed) remain on the surfaced shelf, directly threatening intrusive reminder nagging.

#### 10. Temporal Reasoning
- **Reproduced from RPD2:** Anchoring relative words ("tomorrow", "Friday") to wall-clock runtime rather than conversation turn timestamps.
- **Newly Exposed by Sophie:** Calendar event moves (Google Calendar v1 -> v2) succeed cleanly via `/v1/events/object`, but conversational rescheduling (e.g. pushing Freepik cancellation from Friday morning to Saturday afternoon) is ignored, causing premature `VIOLATED` states.

#### 11. Multi-Source Reconciliation
- **Reproduced from RPD2:** N/A (RPD2 was pure dialogic chat).
- **Newly Exposed by Sophie:** **Total absence of cross-modal reconciliation.** Bank payments, calendar updates, inbound emails, and chat messages exist in isolated database tables without semantic cross-referencing.

#### 12. Recurring Obligations
- **Reproduced from RPD2:** Single-instance completion deleting or mutating recurring patterns.
- **Newly Exposed by Sophie:** Total absence of recurring expectation state. Weekly routines ("remind me Saturday evening about the food shop, like you do every week") are handled purely by language model in-context memory, with 0 durable representation in Cortex.

#### 13. T2a Release / Easing
- **Reproduced from RPD2:** **One-way state ratchet.** Cortex accumulates salience but lacks mechanisms to ease or release tension.
- **Newly Exposed by Sophie:** Expiration without failure: completed tasks flipping to `VIOLATED` simply because time elapsed, ignoring verbal and external evidence of completion.

#### 14. T2b CurrentMeaning / Semantic Trajectory
- **Reproduced from RPD2:** CurrentMeaning table remaining empty or disconnected from per-turn extraction unless explicitly invoked via dedicated sync routes.
- **Newly Exposed by Sophie:** Complete absence of high-level longitudinal trajectory tracking across rolling multi-day windows.

#### 15. Attention / Restraint
- **Reproduced from RPD2:** Inability to maintain conversational silence when background state contains unresolved items.
- **Newly Exposed by Sophie:** The companion script exhibits good natural restraint, but the underlying Cortex database accumulates a dangerous backlog of false violations and immortal loops that would cause an autonomous agent to relentlessly badger the user.

---

## Final Executive Deliverables Summary

1. **Commit SHA:**
   - Evaluated Frozen Cortex Baseline: `44a89d1721d95eecd51fd53cf305dd598a27e5e1`
   - Benchmark Suite Baseline: `a1b8bf497d8d0ec9a5ab8e831e1dcacc055f8c03`
2. **Report Path:**
   - `reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`
3. **Exact Benchmark & Model Used:**
   - Runner: `evals/sophie_longitudinal/runner.py --mode model --scenario all`
   - Provider: OpenRouter
   - Model: `google/gemini-2.5-flash-lite`
4. **Top Confirmed Failures:**
   - **Immortal Loop Accumulation:** Open loops almost never resolve, even after explicit user confirmation or external fulfillment.
   - **Spurious Violation Flipping:** Real-world completions (chairs confirmed, subscription cancelled by user) transition to `VIOLATED` rather than `FULFILLED`.
   - **Third-Party Promise Misattribution:** External emails from counterparties are minted as user/companion `ACT` commitments.
   - **Entity Collision on Same Name:** Studio Sam and Cousin Sam collapsed into a single entity.
   - **Multi-Source Isolation:** Bank feeds do not resolve outstanding financial commitments.
   - **Unpopulated T2b CurrentMeaning & T1 Models:** Exactly 0 CurrentMeaning rows and 0 Model entries formed across all 31 checkpoints.
5. **Failures Reproduced from RPD2:**
   - One-way state ratchet (accumulation without release).
   - Casual speech promoted prematurely to `authority=ACT`.
   - Proactive companion promises remaining unfulfilled in state after conversational delivery.
   - Empty Model entry formation.
6. **Failures Newly Exposed by Sophie Longitudinal:**
   - Failure to reconcile non-chat external evidence (bank feeds, emails) with conversational commitments.
   - Same-name entity collision across personal and commercial domains.
   - Counterparty commitments misattributed to the companion session.
   - Syntactic reference bleed between adjacent sentences.
   - Total loss of quantitative/numerical facts (invoice amounts, chair counts, payment balances).
7. **Oracle Disagreements Requiring Human Judgement:**
   - **Deferred Violation Semantics:** Whether Cortex should be expected to model "deferred violation" states without an underlying schema primitive.
   - **Hard Deletion vs. Dormant Retention:** Whether completed life loops (e.g. hospital recovery, family paperwork) should be completely erased (`active_loops == 0`) or safely retained in low-salience dormancy.
