# MISSION: Turn Known State Into Useful Work — Multi-Agent Specialist Architecture

Status: NEXT MISSION. Supersedes the mixed single-layer version.
Frozen (do NOT reopen): Lane 1 extraction, Lane 2 extraction, foreground bakeoff,
deepseek comparison, reminder architecture, proactive plumbing, Honcho substrate,
regex cleanup, streaming, token optimization.

## 0. Standing invariants (unchanged)
- model proposes; deterministic code commits (state, tasks, ledgers, ids)
- user evidence > machine inference; provenance preserved; supersede never delete
- unknown ≠ failed; plan failure ≠ objective failure; owed never silently dropped
- no LLM output mutates canonical state directly

## 1. Architecture: specialists reason over shared state

```
HONCHO      evidence + longitudinal understanding (already live)
   ↓
CORTEX      canonical state ONLY (deterministic; already live)
            objectives / commitments / expectations / recurrences /
            occurrences / open loops / blockers / tasks / rhythms / ledgers
   ↓
SPECIALIST AGENTS (LLM reasoners, live in Synapse/Runtime; read typed packets
from Cortex, emit TYPED PROPOSALS — never direct mutation)
   ChiefOfStaff  "what matters now?"          → ranked attention packet
   Planner       "how do we move this?"       → proposed decomposition/plan
   PATask        "what needs doing, by whom?" → work-item proposals + status
   Rhythm        "what normally happens now?" → soft priors + useful unknowns
   (Trajectory — explicitly OUT OF SCOPE this mission)
   ↓
SYNAPSE     arbitrates: what deserves attention NOW; admission; timing
   ↓
LUNA        speaks
```

Ownership matrix (aggressively typed; violations = bugs):
| Agent | MAY | MAY NOT |
|---|---|---|
| ChiefOfStaff | rank, flag risk, mark what matters | create tasks, decide interruption |
| Planner | propose decompositions/next actions | commit tasks, decide timing |
| PATask | propose work items w/ owner+window; track execution | decide emotional salience |
| Rhythm | emit soft priors + specific useful unknowns | turn priors into obligations |
| Synapse | arbitrate/admit/defer | invent plans or tasks |


## 2. Work order (sequence matters)

### W1 — Fix the ask/surfacing ledger FIRST (blocker for all policy)
Audit whether ask_count still increments post handover-v4 (v1_cortex.py ~line 142
iterates a dead "agenda" key). One truthful ledger: never surfaced / surfaced /
acknowledged / awaiting answer / ignored / snoozed / dismissed / resolved /
recovery due. Reuse occurrence/follow-through/initiative ledgers. Port the old
Synapse CONCEPTS (ignore reduces pressure; repeated ignore reduces nagging;
snooze moves the window) — not the historical magic numbers. No "2 ignores =
suppress forever" hard-code.

### W2 — Task model (audit canonical Tasks in app Postgres first)
Do not duplicate. If Tasks support parent linkage/owner/dependencies/status, use
them; add narrowly if not. Projection: PARENT (objective/project/open
loop/commitment/expectation) → ACTIONABLE CHILDREN with owner user|sophie.
Minimum metadata: id, parent id(s)+type, owner, action, status, importance,
due window, dependency/blocker, provenance, completion condition,
recurrence/occurrence ref, next viable action, sophie-executable flag.
Sophie must not dump "eight things you need to do" — every parent asks:
user work? sophie work? what can she prepare? smallest useful next step?
No claimed execution without a real tool call.
Decompose only when: user supplied steps / structure obvious / blocker implies a
concrete action / Sophie materially helps / necessary to move the parent.
Otherwise preserve parent, propose decomposition.

### W3 — Rhythm / routine expectations (soft priors)
Hierarchy: generic human prior → learned personal rhythm (from Lane 2/Honcho) →
user-confirmed rhythm → today's observed reality. Stronger evidence overrides.
Never "violated bedtime" — derive "awake later than learned rhythm; cause
unknown." These feed fallback conversational intelligence: specific useful
unknowns (eaten? in bed? walk happened?) replace generic filler. Priority:
acute > OWED > important unresolved work > meaningful context > learned rhythm >
generic priors > filler.

### W4 — Day brief + current-window packet
Cortex compiles (deterministically) a compact day picture: active objectives,
occurrences, deadlines, expectations, Sophie commitments, important tasks,
blockers, rhythms, unresolved outcomes. Synapse reduces it per moment:
morning window active → elapsed → adapt → reconcile. Objectives persist,
strategies adapt. No pre-generated hourly prompts; recompute on state change.
Expectations give "window elapsed + outcome unknown → reconciliation
opportunity". Transition/Gap/Deviation are DERIVED state, not new permanent
tables; promote to Open Loop only when persistence is warranted. Never the word
"violation" for human deviation.

### W5 — Wire triggers (partially done)
sweeper_triggers.py already implements settle/turn-count/catch-up debounce in
Cortex (deployed). Remaining: verify Lane 2 findings reach Planner/CoS within
minutes, not hours. Explicit promises/goals must not wait hours; Lane 1 handles
truly immediate things.


## 3. Acceptance scenarios (build coherent capability, then prove A–G)
A. Job application decomposition (parent + user/sophie tasks; "CV done" updates
   only CV; "not applying anymore" closes dependents)
B. Walk accountability (10k + split strategy + daylight blocker + Sophie
   promise; morning/afternoon/evening current-window adaptation; completion
   resolves; no duplicate nag)
C. Meeting 14:00–15:00 → at 15:30 transition elapsed, outcome unknown, Sophie
   actionable = establish outcome
D. Routine fallback (specific useful unknown instead of generic filler; no
   compulsory nagging)
E. Acute override (hospital) — acute dominates; walk durable but deferred
F. Ignore/snooze feedback affects pressure/window; contractual never deleted
G. Sophie task — concrete Sophie work, no false execution claims

## 4. Deliverables
1. What changed (implementation only) 2. Final operational model (durable
primitives + relationships) 3. Task model (parent/owner/completion/deps/
provenance) 4. Rhythm model (generic→learned→confirmed→today) 5. Real day brief
from a fixture 6. Current-window packet at 3 times in one scenario 7. Ledger
audit verdict + what now tracks surfacing 8. A–G PASS/FAIL with resulting state
9. Genuine gaps only 10. Exactly one next step.

## 5. Implementation stance
Inspect what exists; reuse canonical Tasks, occurrence ledger, follow-through,
admission, initiative, temporal grounding, Honcho provenance, existing lifecycle.
Minimum new storage. No new architecture document beyond this brief.

### W6 — Behavioral verification of greeting/re-entry with Lane 2 state
NOT a rebuild. Reactive re-entry already consumes the handover. Verify behavior
with richer state; fix only what breaks.
