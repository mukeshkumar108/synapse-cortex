# Action semantics, projection, handover and product policy — decisions (2026-08-30)

Covers Workstreams 1, 2, 3, 6, 7, 8. Companion docs: Honcho capability eval
(llm-agent-test `docs/HONCHO_CAPABILITY_EVAL_2026-08-30.md`), kernel comparison
(companion-runtime `docs/KERNEL_COMPARISON_REPORT.md`).

## WS1 — recurrence cadence audit verdict (original evidence)

| Recurrence | Evidence (verbatim) | Verdict |
|---|---|---|
| daily talk with Ashley | "we talk everyday obviously..." | Real cadence words, but they describe mutual observed behaviour, not a commitment → `observed_pattern` |
| Fix audio transcription bug | "it's been happening every single day, so you need to remind me keep top of me" | Cadence words attach to the PROBLEM, not a practice. One-off durable objective + reminder ask. NOT a recurrence → cancelled with provenance |
| daily step goal | "10 K is the base is the floor" | No cadence evidence in the span; durable measurable goal with floor target → `measurable_goal` |

The pre-existing deterministic demotion guard missed #2 because "every single
day" was matched anywhere in evidence. Fixed in `RecurrenceSemantics`
(turn_extractor.py): problem-frequency patterns ("been happening", "keeps
breaking/failing", "every single time") demote to `durable_objective`; mutual
patterns ("we talk everyday") and hedged habits ("I try to walk most mornings")
classify as `observed_pattern`; target-bearing recurrences classify as
`measurable_goal`; ritual/adherence lexicons classify rituals/adherence. The
model may propose `recurrence_semantic_type` + `cadence_evidence_text`
(verbatim span); deterministic code validates and owns durable state.
Semantic type is persisted on `recurring_intentions.semantic_type`
(migration 0012) and preserved through supersession. Production rows repaired
via `scripts/repair_recurrences_2026_08_30.py` (provenance appended, nothing deleted).

## WS2 — action projection: underlying meaning vs actionable surface

Authority chain (unchanged): explicit user commands remain the app fast-path
canonical Task. Inferred actions flow: Cortex derives a fallible
`commitment_candidate` (authority=ASK) → product surfaces it ("Sophie noticed")
→ user accepts → app materializes a canonical Task via
`materializedCandidateKey` (idempotent, cross-chat, owner-scoped).

New: `services/action_projection.py` — a persisted recurrence whose semantic
type ∈ {recurring_action, recurring_ritual, adherence_action, measurable_goal}
projects into the bounded candidate store (key `recproj:<canonical>`,
provenance note, confidence cap 0.85). `observed_pattern` never projects. No automatic decomposition: a broad goal
never spawns invented subtasks; the candidate carries one actionable title,
the user decides.

Boundary examples (why each lands where):

| Utterance | Becomes | Why |
|---|---|---|
| "Remind me to call the visa office tomorrow" | canonical Task (fast path) | explicit command, dated |
| "I want to walk every morning" | recurring actionable instance | recurring_action + cadence; projects to candidate, Task on acceptance |
| "I want to do morning and evening prayers every day" | recurring ritual instance | recurring_ritual; same path, ritual type preserved underneath |
| "My goal is at least 10k steps per day" | measurable_goal (+ candidate) | target floor; genuinely actionable daily |
| "We talk everyday obviously" | expectation/semantic only | observed_pattern; never a Task |
| "I should probably look at the visa sometime" | Sophie Noticed candidate at most | vague self-talk; ASK authority, no hard lane |
| "I need to fix the audio bug" | expectation / durable_objective only | one-off objective; no cadence, so no recurrence |
| "I saw a beautiful moon" | nothing (semantic_only) | narration is never operational |

## WS7 — product policy profile

`services/product_profile.py`: small typed `ProductProfile` config
(sophie/bluum/health/productivity) holding purpose + operational-kind priority
+ handover limits. Cortex packet compilation stays product-neutral; only the
editorial selection layer (handover today, working-set later) consumes the
profile. No generic policy framework.

## WS8 — tiny session handover

`POST /v1/cortex/handover` → `handover-v1`: sections now/changed/unresolved/
avoid/attention, one line each, priority-ordered by product profile, hard
character budget (~1600 chars ≈ ≤400 tokens), lowest-priority sections trim
first. Compiled from the SAME attention packet as the working set — one
foreground object, not more packet endpoints; JIT detail remains via
`/v1/cortex/evidence`. Replaceable derived projection, not state.

## WS3 — Personal Assistant (design, not yet built)

Keep Chief of Staff = editorial prioritization. Add a separate Personal
Assistant capability: input = one prioritized actionable thing; output =
grounded preparation only (missing info, official requirements, document
checklist, fees/appointment process, draft artefacts, proposed concrete
Tasks). Every proposal must cite grounding (conversation evidence, connector
data, or explicit user statement); no invention; sends/external actions
require explicit user authority. Implementation when built: a capability lane
in companion-runtime with Task-backed outputs.

## WS6 — background intelligence / living Cortex state (design)

Scratchpad = replaceable derived current-world interpretation maintained
between conversations: what appears true now / what changed / what is
unresolved / what became irrelevant / current significant plans. Honcho stays
durable evidence; Cortex canonical rows stay state; the scratchpad may be
rebuilt from those two. Convergence: multiple observations of the same plan
collapse to one current belief (sibling supersede, already shipped); the
dependent-plan cascade (transport failed → Oxford legs leave the scratchpad)
is the first background job when this goes live. The WS8 handover is its tiny
product handover output.
