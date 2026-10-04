# Sophie convergence plan (Layer 2)

Status: plan. Not executed. Sophie is the only real daily user; the evidence needed to switch her reader does not exist yet (see "Why not now").
Written 2026-10-04 after the Layer-2 protocol pass (leased/transactional interpretation, pinned identities, state review, trace).

## What Sophie needs that RPD2 does not
| Need | What it is | Where it lives today |
|---|---|---|
| Reminders / expectations | A time-bound thing the user (or Sophie) said will happen, with a due window | Narrow lane -> `Expectation` (+ temporal grounding of the phrase, lifecycle sweep) |
| Open loops | A thread someone opened and has not closed | `OpenLoop`, lifecycle, reopen conditions |
| Commitments | Who promised what to whom, tentative or firm | `CommitmentCandidate`; the interpreter also emits `commitments` |
| Completion / failure / cancellation | Later evidence closes, fails or cancels the above | `operational_state_service` lifecycle, narrow lane `outcome` |
| Routines | Recurring intentions | recurrence rows, `Matter(kind=routine)` |
| Real-world grounding | What the companion asserts about the user's life is not fact | interpreter `policy=grounded` + materialiser downgrade (already shared) |
| Follow-through | Sophie acts on due items (initiative engine) | initiative engine reading the operational tables |

RPD2 needs none of the operational lifecycle; it needs relationship/narrative state. The interpreter already covers Sophie's *meaning* side (actors, relationships, events, claims, narrative, commitments, matters, grounded policy). What it does not do is **time-grounded operational intents with a lifecycle**.

## Target (one canonical meaning author, one mechanics layer)
1. **Meaning:** the world interpreter is the only reader that authors meaning for every owner, Sophie included (`policy=grounded`, product-supplied identities, same lease / ledger / trace).
2. **Operational intents:** the interpreter gains one more typed output, `operational` (`reminder | expectation | loop | routine | completion | cancellation | failure`, each with evidence, the raw time phrase, and the id of what it closes). The model decides *that* something is a reminder and *which* open item a later message closes. Existing deterministic code keeps owning *when* (temporal grounding), lifecycle transitions, sweeps and the initiative engine. This is the same split as everywhere else: models decide meaning, code owns mechanics.
3. **Realtime nominator:** the narrow lane stays as a cheap per-turn *nominator* for "something time-bound was just said" so a reminder is not delayed to the next checkpoint. It writes through the same operational service; the interpreter later confirms, enriches or closes it by id (never creates a twin: identity by id, same ledger).
4. **Retired readers (after parity):** 3-stage session consolidation, `turn_interpretation`, `CurrentMeaning`, the semantic judge, Lane 2 sweeper discovery. Each is a second model reader of the same conversation.

## Steps, each reversible behind a flag
1. **Shadow:** run the interpreter for Sophie at session end with `producer=world-interpreter-shadow` writing to a shadow owner scope (`shadow:` prefix), not her live world. Cost is about one Luna pass per session. Compare, on her real sessions, against what the legacy readers wrote.
2. **Operational output:** add `operational[]` to the interpreter schema, materialised through `operational_state_service`; run in the same shadow scope.
3. **Parity review by the user** (a handful of real sessions, shown side by side): reminders found / missed / invented, loops closed correctly, no ungrounded facts promoted.
4. **Cut over per capability** (loops, then commitments, then reminders), retiring the corresponding legacy reader each time.
5. Honcho deriver / dreams for `user_*` owners: decide whether Sophie also moves to `observe_me=false` (Honcho remembers, Cortex interprets). Until then Honcho holds a competing representation for her; that is the largest remaining ownership overlap.

## Product decisions needed (genuinely yours)
- Should Sophie proactively act on a reminder she captured from an inferred (not explicit) cue, or only on explicit asks?
- When the user and Sophie disagree about whether something was done, which account wins for follow-through? (Today: the user's, via `outcome` evidence.)

## Why not now
- Nothing observed shows the interpreter matches the narrow lane on reminders; the replays so far are RPD2-style relational state.
- Sophie's mistakes land on a real person's day (a missed reminder), unlike a roleplay world. Shadow + side-by-side review is the cheap way to earn the cutover.
- The race that made the narrow lane return 500 on duplicate delivery is fixed (per-message serialisation in `v1_events.py`), so the existing system is reliable meanwhile.
