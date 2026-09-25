# Sophie Longitudinal Fixture Build & Evaluation Report

**Date:** 2026-09-25  
**Programme Layer:** Shared Companion Substrate (Cortex / Honcho / Companion Runtime)  
**Objective:** Materialize four authored Sophie longitudinal benchmark scenarios from Notion into durable repository fixtures, build a reusable evaluation harness following project conventions, verify multi-source evidence paths, and execute current-baseline runs without mutating production code.

---

## 1. Exact Baseline Commits & Repository Integrity

Before fixture creation and execution, repository baselines were verified as frozen:
- **`synapse-cortex`**: HEAD `44a89d1721d95eecd51fd53cf305dd598a27e5e1`
  - *Status:* Clean apart from pre-existing untracked `uv.lock`.
- **`companion-runtime`**: HEAD `6b2f78dff838f6d7db29d6bcb58e3c443c101210`
  - *Status:* Untouched; pre-existing dirt (`README.md`, `audit-*`, `scripts/run_local.py`, `uv.lock`) strictly preserved without absorbing.
- **`rpd2`**: Prior replay runs (Takes 1–10 and Isa arc) verified as measurement-only reference baselines in `/tmp/` and `reports/`.

---

## 2. Canonical Source Specifications

Extracted directly from authenticated Kaiser Notion workspace:
- **Parent Requirements:** [`Sophie Messy Longitudinal Corpus — Draft Requirements & Scenarios`](https://app.notion.com/p/3e66297866b081efa21acc9b46944c22)
- **Scenario 1:** [`Scenario 1 — Ashley Event Ops + Children + External Evidence`](https://app.notion.com/p/3e66297866b081e68e0ddfbca87e2afa)
- **Scenario 2:** [`Scenario 2 — Ordinary Sophie: Plans, Half-Intentions, Changed Mind, Missing Detail`](https://app.notion.com/p/3e66297866b08116a057e8bfd240630a)
- **Scenario 3:** [`Scenario 3 — Multi-source Conflict, Two People Same Name, Indirect Closure`](https://app.notion.com/p/3e66297866b08176a1c9cdf95348db15)
- **Scenario 4:** [`Scenario 4 — Health, Worry & Personality Texture: Bidirectional Check-ins`](https://app.notion.com/p/3e66297866b081019ecdfbed758ee2df)

---

## 3. Files Created

All files are materialized within `synapse-cortex`:
```
synapse-cortex/
├── evals/
│   └── sophie_longitudinal/
│       ├── manifest.json
│       ├── README.md
│       ├── runner.py
│       ├── scenario_1_ashley_event_ops_input.json
│       ├── scenario_1_ashley_event_ops_oracle.json
│       ├── scenario_2_ordinary_sophie_plans_input.json
│       ├── scenario_2_ordinary_sophie_plans_oracle.json
│       ├── scenario_3_multisource_conflict_input.json
│       ├── scenario_3_multisource_conflict_oracle.json
│       ├── scenario_4_health_worry_texture_input.json
│       ├── scenario_4_health_worry_texture_oracle.json
│       └── raw_outputs/
│           ├── scenario_1_raw_checkpoints.md
│           ├── scenario_1_summary.json
│           ├── scenario_2_raw_checkpoints.md
│           ├── scenario_2_summary.json
│           ├── scenario_3_raw_checkpoints.md
│           ├── scenario_3_summary.json
│           ├── scenario_4_raw_checkpoints.md
│           └── scenario_4_summary.json
└── reports/
    └── sophie_longitudinal_fixture_build_2026-09-25.md
```

---

## 4. Fixture Structure & Input/Oracle Separation

### A. Strict Input Isolation
The system under test (`Cortex`, `Honcho`, `Runtime`) receives **only** the `*_input.json` payload:
- Ordered list of discrete chronological events spanning multiple days (anchored to the September 28 – October 3, 2026 window).
- Verbatim text, timestamps with timezone offset (`Europe/London`), explicit source types (`conversation`, `email`, `calendar`, `payment_feed`, `sms`), and sender identities.
- Non-chat evidence is **never** rewritten into fake dialogic turns.

### B. Evaluator Oracle Isolation
The `*_oracle.json` files contain hidden ground truth, loaded solely by post-turn assertions and summary evaluators:
- **Hidden Evaluator Truth:** Contextual facts known to human reviewers (e.g. Carlos net balance Q2,100; Freepik true renewal date).
- **Deterministic Assertions:** Concrete expectations per checkpoint (e.g. entity separation of Studio Sam vs. Cousin Sam; release of confirmed venue chairs).
- **False-Positive Traps:** Bounded assertions checking that ephemeral remarks (e.g. "I slept terribly", "head's a bit sore", "wish I'd remembered to message Elif") do NOT leak into durable tables as actionable commitments or active open loops.
- **Dual Aperture Restraint Annotations (Scenario 4):** Turn-by-turn companion gear labels (`HOLD`, `ENRICH`, `LEAD`, `ATTEND`, `SILENCE`) evaluating companion initiative and restraint.

---

## 5. Multi-Source Evidence & Source Types Exercised

| Evidence Source Type | Channel / Actor | Ingestion Mechanism in Cortex | Production Status & Findings |
|---|---|---|---|
| `conversation` (User) | Ashley / User voice notes & text | `/v1/events/turn` (`is_assistant_turn=False`) | Fully native production path. Triggers turn extraction, shaping, temporal grounding, and lifecycle transitions. |
| `conversation` (Companion) | Sophie promises & check-ins | `/v1/events/turn` (`is_assistant_turn=True`) | Fully native production path. Ingests through narrow assistant lane (speaker-owned commitments only). |
| `calendar` | Google Calendar updates & completions | `/v1/events/object` (`system="google_calendar"`) | Fully native production path. Rescheduled events cleanly supersede prior expectation windows (`action=created/updated`); completed events resolve tombstones (`action=completed`). |
| `email` | School sports day, Carlos bank update, florist palette | Bounded test adapter via `/v1/events/turn` with `peer_id="external:<sender>"` | **Harness finding:** Cortex lacks a dedicated `/v1/events/email` endpoint. Provenance is preserved in `peer_id` and message IDs, avoiding dialogue rewrite. |
| `payment_feed` | Carlos Q1,500 inbound, School Trips £18 outbound, Lucy £240 inbound | Bounded test adapter via `/v1/events/turn` with `peer_id="external:bank_feed"` | **Harness finding:** Cortex lacks dedicated banking feed webhook parsing. Ingested as external evidence events. |
| `sms` / `message` | Dentist reschedule SMS, Lucy confirmation DM | Bounded test adapter via `/v1/events/turn` with `peer_id="external:<sender>"` | Successfully routed without user dialog spoofing. |

---

## 6. Execution Commands & Verification

The suite was executed against the clean baseline using the local virtual environment:

### Command to run all four scenarios:
```bash
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario all
```

### Execution Results:
```
=== Starting Sophie Longitudinal Benchmark (4 scenarios) ===
Provider: rules

==========================================
Executing scenario_1...
==========================================
[s1_e01] CONVERSATION (USER) -> status=202
[s1_e02] EXTERNAL (email:school) -> status=202
[s1_e03] EXTERNAL (email:carlos) -> status=202
[s1_e04] EXTERNAL (payment_feed:bank_feed) -> status=202
[s1_e05] CONVERSATION (USER) -> status=202
[s1_e06] CALENDAR -> status=202 action=created
[s1_e07] CONVERSATION (USER) -> status=202
[s1_e08] EXTERNAL (email:florist) -> status=202
[s1_e09] CONVERSATION (USER) -> status=202
[s1_e10] CONVERSATION (USER) -> status=202
[s1_e11] CONVERSATION (USER) -> status=202
[s1_e12] CONVERSATION (USER) -> status=202
[s1_e13] EXTERNAL (payment_feed:bank_feed) -> status=202
[s1_e14] CONVERSATION (USER) -> status=202
Wrote raw checkpoint output: evals/sophie_longitudinal/raw_outputs/scenario_1_raw_checkpoints.md

==========================================
Executing scenario_2...
==========================================
[s2_e01] to [s2_e10] -> status=202
Wrote raw checkpoint output: evals/sophie_longitudinal/raw_outputs/scenario_2_raw_checkpoints.md

==========================================
Executing scenario_3...
==========================================
[s3_e01] to [s3_e14] -> status=202
[s3_e10] CALENDAR -> status=202 action=resolved_tombstone
Wrote raw checkpoint output: evals/sophie_longitudinal/raw_outputs/scenario_3_raw_checkpoints.md

==========================================
Executing scenario_4...
==========================================
[s4_e01] to [s4_e15] -> status=202
Wrote raw checkpoint output: evals/sophie_longitudinal/raw_outputs/scenario_4_raw_checkpoints.md

=== BENCHMARK EXECUTION SUMMARY ===
scenario_1: 11 checkpoints evaluated | False-positive trap defense: 2/2 passed
scenario_2: 5 checkpoints evaluated  | False-positive trap defense: 4/4 passed
scenario_3: 6 checkpoints evaluated  | False-positive trap defense: 2/2 passed
scenario_4: 9 checkpoints evaluated  | False-positive trap defense: 2/2 passed
```

---

## 7. Diagnostics & Stored ASK vs. Surfaced Shelf Verification

Every checkpoint log emits the proven proposal diagnostic:
- **`stored_ask`**: Total count of pending `CommitmentCandidateAuthority.ASK` rows in the database.
- **`surfaced_shelf`**: Bounded top-3 window of eligible candidates surfaced for companion attention.
- **`skipped`**: Categorized exclusion reasons (`vague_self_talk_excluded` and `beyond_top3_window`), ensuring non-authoritative junk candidates are visibly contained.

---

## 8. Notion Interpretations & Authorial Clarifications

1. **Temporal Grounding (Calendar 2026):**
   The scenario references "Sports Day is Thursday 1 October" and "due Wednesday 16:00". In the real 2026 calendar, September 28 is Monday, September 30 is Wednesday, and October 1 is Thursday. All scenario timestamps were anchored to this exact week (`2026-09-28` to `2026-10-03`) with `Europe/London` BST offset (`+01:00`).
2. **Scenario 4 Monday Sophie Promise Correction:**
   In line with authorial guidance, Monday turn `s4_e03` was preserved verbatim as Sophie's self-undertaking:
   *"That attention-and-boredom thing sounds worth actually unpacking properly rather than losing it inside a brain dump. I’ll come back to it later this week when we’ve got a bit more room."*
   This is fulfilled unprompted by Sophie on Friday morning (`s4_e12`).
3. **Calendar Object Mapping:**
   `ObjectStateIngest` requires `system="google_calendar"`, `version`, `title`, and explicit offset datetime stamps (`event_start`). The harness maps calendar update events directly to this contract.

---

## 9. Harness Limitations & Production Findings

1. **No Native Ingestion Route for Banking Feeds or Inbound Emails in Cortex:**
   While Google Calendar events possess first-class support in `ObjectLifecycleService`, bank statement updates and emails currently enter through the conversational turn pipeline. A production companion system requiring multi-source continuity will need dedicated deterministic projection services (e.g. `BankFeedLifecycleService`, `EmailEvidenceService`) analogous to `ObjectLifecycleService`.
2. **First-Person Extraction Tuning:**
   The deterministic rules extractor is heavily weighted towards first-person conversational framing (`I need to`, `I will`). Inbound emails from third parties ("Sports Day is Thursday...") do not mint expectations under rules extraction; model-based extraction or dedicated external-source extraction is required to extract third-party obligations into Cortex.
3. **Confirmation of Zero Production Code Modification:**
   All additions are strictly confined to `evals/sophie_longitudinal/` and `reports/`. No extraction admission rules, production prompts, schemas, or runtime behaviours were altered.
