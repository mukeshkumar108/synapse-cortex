# NARROW REAL-TIME CONTRACT — Item 2 shadow findings (2026-09-01)

## What was built (committed 35d957e)
- `src/services/narrow_realtime.py`: the narrow contract (decisions: none/create/
  progress/complete/cancel/reschedule/correct/suppress/reopen), a deterministic
  validator (verbatim turn evidence, PRIOR-STATE target requirement for
  transitions, temporal grounding for event/deadline, fail-safe to `none` with
  preserved rejection notes), and `to_candidate()` — commit-path mapping onto
  the EXISTING lanes (expectation/reminder_request, resolution_hint actions,
  suppression_hint, commitment_candidate). No new state system.
- `v1_events.py`: `SYNAPSE_NARROW_REALTIME=shadow` runs the narrow classifier
  alongside the current extractor, traces it (`extraction_traces.stage =
  narrow_shadow`), and returns it under `narrow_shadow` in the turn response.
  Non-destructive: default is OFF; shadow never mutates state.
- `tests/test_narrow_realtime.py`: 10 deterministic validator tests (all pass).
- `evals/narrow_contract_compare.py` + `evals/narrow_contract_cases.json`:
  harness comparing current vs narrow over 14 REAL production turns
  (verbatim, provenance timestamps, harvested from Honcho messages).

## Incident found during comparison (production-impacting, fix committed)
`turn_extractor._call_model` sent no `max_tokens`, so OpenRouter reserved the
model's full budget; with low credits every LONG-turn extraction failed HTTP
402 and both extractors fail-open to zero candidates. Production per-turn
extraction is silently degraded on long turns whenever the OpenRouter balance
is low. Fix: `SYNAPSE_EXTRACTOR_MAX_TOKENS` (default 900, 2500-4000 for the
big loose stage). MUST be deployed, and OpenRouter credits topped up.

## Comparison results (partial — credits exhausted mid-matrix)
Cases that ran clean (from run 1 + targeted diag):
- reminder turn (2026-08-23 "remind me to go out for a walk... tomorrow"):
  narrow=create/reminder (grounded "tomorrow") — matches current lane
  (user_commitment, reminder_request=true). MATCH.
- Oxford Raksha Bandhan turn (2026-08-28): narrow=create/event,
  temporal "Sunday morning", verbatim evidence. MATCH.
- Two Oxford-cancellation turns (2026-08-29/30): narrow=cancel with correct
  target_key `oxford_raksha_bandhan` from prior state. MATCH.
- diag: deepseek flash returns clean, correct JSON for the narrow prompt.
Remaining 10 cases could not run live (402 credit exhaustion). Rerun
`narrow_contract_compare.py` after topping up credits.

## Capability delta — what the current per-turn pass does that the narrow
## contract would stop doing (deferred to Lane 2)
1. Durable-objective discovery ("I still need to apply for jobs") — Lane 2
   question: goal? MUST have a Lane 2 home. HAS ONE (planned sweeper).
2. Habit/recurrence discovery incl. observed_pattern ("Burwell Fen is my
   everyday walk, 10k floor") — Lane 2: habit?/pattern?. HAS ONE.
3. Implicit/vague self-commitments ("I should renew my passport",
   "I know I need to do tidying") with authority=ask — Lane 2: commitment by
   USER (weak evidence). HAS ONE, but the sweeper must mine vague commitments,
   not only explicit ones.
4. Sophie promises / assistant turns — ALREADY known never mined; narrow
   contract makes that explicit. Lane 2: commitment by SOPHIE. HAS ONE.
5. Preference/category/domain memory ("i like cooking", feedback about Sophie,
   sleep patterns) — Lane 2 memory questions. HAS ONE (Honcho itself derives
   these; conclusions/representation already capture them).
6. Open-loop discovery from general statements ("still waiting on the
   insurance") — Lane 2: open loop?. HAS ONE.

## Capabilities with NO safe home yet (flagged — do not cut over until solved)
a. SUPPRESSION SCOPING: the current pass derives suppressions from semantic
   context ("leave her alone while the event is happening" → outbound_contact
   scoped to a window). The narrow suppress decision covers explicit
   boundaries, but scoped-derivation quality must be proven in shadow before
   cutover.
b. CLARIFICATION HINTS for ambiguous reminders: preserved in narrow (reminder
   without window → deterministic clarification) but needs e2e verification.
c. TURN CONTEXT CONTINUITY: current pass treats restatement-in-context as
   update-not-new ("I told you before..."). Narrow handles this via PRIOR
   STATE targets; needs shadow evidence on restatement turns.
d. Sleep-signal, reopen-conditions, dual-aperture context: orthogonal
   deterministic services — unchanged by the narrow contract (not affected).

## Recommendation
Keep `SYNAPSE_NARROW_REALTIME=shadow` OFF in prod until (1) OpenRouter credits
topped up + max_tokens fix deployed, (2) full 14-case matrix green, (3) 7-day
shadow soak comparing real traffic. Then cutover Lane 1 to narrow decisions;
launch Lane 2 sweeper (items 3-4 of mission) for all deferred discovery.
