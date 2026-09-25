# Sophie Longitudinal Fixture Build & Evaluation Report

**Date:** 2026-09-25  
**Programme Layer:** Shared Companion Substrate (Cortex / Honcho / Companion Runtime)  
**Objective:** Materialize four authored Sophie longitudinal benchmark scenarios from Notion into durable repository fixtures, build a reproducible evaluation harness supporting both determinism-floor rules mode and real model-driven semantic mode, verify multi-source evidence paths, and execute both baselines without mutating production code.

---

## 1. Exact Baseline Commits & Repository Integrity

Before fixture creation and execution, repository baselines were verified as frozen:
- **`synapse-cortex`**: Baseline commit `44a89d1721d95eecd51fd53cf305dd598a27e5e1`
  - *Status:* Clean apart from pre-existing untracked `uv.lock`.
- **`companion-runtime`**: Baseline commit `6b2f78dff838f6d7db29d6bcb58e3c443c101210`
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

## 3. Files Created & Partitioned Structure

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
│           ├── rules/
│           │   ├── scenario_1_raw_checkpoints.md
│           │   ├── scenario_1_summary.json
│           │   ├── scenario_2_raw_checkpoints.md
│           │   ├── scenario_2_summary.json
│           │   ├── scenario_3_raw_checkpoints.md
│           │   ├── scenario_3_summary.json
│           │   ├── scenario_4_raw_checkpoints.md
│           │   └── scenario_4_summary.json
│           └── model/
│               ├── scenario_1_raw_checkpoints.md
│               ├── scenario_1_summary.json
│               ├── scenario_2_raw_checkpoints.md
│               ├── scenario_2_summary.json
│               ├── scenario_3_raw_checkpoints.md
│               ├── scenario_3_summary.json
│               ├── scenario_4_raw_checkpoints.md
│               └── scenario_4_summary.json
└── reports/
    └── sophie_longitudinal_fixture_build_2026-09-25.md
```

---

## 4. Strict Input vs. Oracle Separation

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

## 5. Execution Modes & Preflight Assertions

The evaluation runner (`runner.py`) provides two explicit, non-overlapping execution modes:

### Mode A: Model / Semantic Baseline (`--mode model`)
- **Extractor:** Two-stage model watcher (`LLMExtractorProvider`): loose noticing stage + schema shaping stage.
- **Provider & Model:** `google/gemini-2.5-flash-lite` via OpenRouter (`https://openrouter.ai/api/v1/chat/completions`).
- **Preflight Loud-Failure Assertion:** Verifies presence of `OPENROUTER_API_KEY` (or `OPENAI_API_KEY` / `XAI_API_KEY`) and executes an active connectivity probe. If credentials are missing or the probe fails (e.g. HTTP 401/402 or connection drop), the runner exits non-zero (`exit 1`) immediately with a clear error. It **never** silently falls back to rules.
- **Output Directory:** Saved strictly to `evals/sophie_longitudinal/raw_outputs/model/`.

### Mode B: Rules / Determinism Floor (`--mode rules`)
- **Extractor:** Offline deterministic regex/clause extractor (`RuleBasedExtractorProvider`).
- **Purpose:** Illicit-state regression baseline and determinism floor.
- **Trap Interpretation:** Trap passes in this mode are explicitly labeled as structural floor checks only, **not** as evidence of semantic restraint (an empty extractor cannot false-positive).
- **Output Directory:** Saved strictly to `evals/sophie_longitudinal/raw_outputs/rules/`.

---

## 6. Execution Commands & Evaluator Reproduction

All commands support numeric aliases (`1`, `2`, `3`, `4`) as well as canonical names (`scenario_1`..`scenario_4`) or `all`.

### Running the Model Baseline (Semantic Mode)
```bash
cd /Users/mukeshkumar/play/synapse-cortex

# Run all 4 scenarios:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario all

# Run individual scenarios:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario 1
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario 2
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario 3
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario 4
```

### Running the Rules Baseline (Determinism Floor)
```bash
cd /Users/mukeshkumar/play/synapse-cortex

# Run all 4 scenarios:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode rules --scenario all

# Run individual scenarios:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode rules --scenario 1
```

---

## 7. Comparative Baseline Execution Results

### A. Semantic Model Baseline (`--mode model`)
- **Provider:** `model`
- **Model:** `google/gemini-2.5-flash-lite`
- **External Model Calls:** `True`
- **All 4 Scenarios Completed:** **Yes (4/4)**

| Scenario | Checkpoints | False-Positive Traps | Final Expectations | Final Commitments | Final Open Loops | Final Facts | Final Entities |
|---|---|---|---|---|---|---|---|
| **Scenario 1** (Ashley Event Ops) | 11 / 11 | **2 / 2 passed** | 8 | 3 | 12 | 9 | 5 |
| **Scenario 2** (Ordinary Sophie Plans) | 5 / 5 | **4 / 4 passed** | 1 | 1 | 2 | 1 | 1 |
| **Scenario 3** (Multi-source Conflict) | 6 / 6 | **2 / 2 passed** | 4 | 3 | 8 | 3 | 1 |
| **Scenario 4** (Health & Worry Texture) | 9 / 9 | **2 / 2 passed** | 0 | 3 | 2 | 3 | 3 |
| **Total** | **31 / 31** | **10 / 10 passed** | **13** | **10** | **24** | **16** | **10** |

*Trap Defense Interpretation in Model Mode:* Genuine semantic defense against false-positive traps while actively generating non-empty state (e.g. 10 commitments, 24 open loops, 16 facts, 10 entities).

### B. Rules Baseline (`--mode rules`)
- **Provider:** `rules`
- **Model:** `None`
- **External Model Calls:** `False`
- **All 4 Scenarios Completed:** **Yes (4/4)**

| Scenario | Checkpoints | Traps Passed (Structural Floor) | Final Expectations | Final Commitments | Final Open Loops | Final Facts | Final Entities |
|---|---|---|---|---|---|---|---|
| **Scenario 1** (Ashley Event Ops) | 11 / 11 | 2 / 2 passed* | 8 (via calendar) | 0 | 0 | 0 | 0 |
| **Scenario 2** (Ordinary Sophie Plans) | 5 / 5 | 4 / 4 passed* | 2 | 0 | 0 | 0 | 0 |
| **Scenario 3** (Multi-source Conflict) | 6 / 6 | 2 / 2 passed* | 8 | 0 | 2 | 0 | 0 |
| **Scenario 4** (Health & Worry Texture) | 9 / 9 | 2 / 2 passed* | 1 | 0 | 0 | 0 | 0 |

*\*Note on Rules Trap Defense:* Trap passes in rules mode are a determinism floor check only. Because the rule-based extractor produces near-zero state on conversational turns, it cannot false-positive. Only the model baseline provides semantic evidence of conversational restraint.

---

## 8. Proposal Exposure & Stored ASK Diagnostics

Every checkpoint trace in both modes preserves full stored-vs-surfaced ASK diagnostics:
- **`stored_ask`**: Total count of pending `CommitmentCandidateAuthority.ASK` rows in the database.
- **`surfaced_shelf`**: Bounded top-3 window of eligible candidates surfaced for companion attention.
- **`skipped`**: Categorized exclusion reasons (`vague_self_talk_excluded` and `beyond_top3_window`), ensuring non-authoritative candidate sprawl is visible and bounded.

---

## 9. Multi-Source Evidence Architecture & Ingestion Paths

| Evidence Source Type | Channel / Actor | Ingestion Mechanism in Cortex | Production Status & Findings |
|---|---|---|---|
| `conversation` (User) | Ashley / User voice notes & text | `/v1/events/turn` (`is_assistant_turn=False`) | Fully native production path. In model mode, triggers loose noticing + shaping + grounding + lifecycle. |
| `conversation` (Companion) | Sophie promises & check-ins | `/v1/events/turn` (`is_assistant_turn=True`) | Fully native production path. Ingests through narrow assistant lane (`extract_self_owned`: speaker-owned commitments only). |
| `calendar` | Google Calendar updates & completions | `/v1/events/object` (`system="google_calendar"`) | Fully native production path. Rescheduled events cleanly supersede prior expectation windows (`action=created/updated`); completed events resolve tombstones (`action=completed`). |
| `email` | School sports day, Carlos bank update, florist palette | Bounded test adapter via `/v1/events/turn` with `peer_id="external:<sender>"` | Ingested via external-provenance adapter to preserve identity without rewriting into fake user dialogue. |
| `payment_feed` | Carlos Q1,500 inbound, School Trips £18 outbound, Lucy £240 inbound | Bounded test adapter via `/v1/events/turn` with `peer_id="external:bank_feed"` | Preserves financial provenance without dialogue rewrite. |
| `sms` / `message` | Dentist reschedule SMS, Lucy confirmation DM | Bounded test adapter via `/v1/events/turn` with `peer_id="external:<sender>"` | Preserves SMS provenance without dialogue rewrite. |

---

## 10. Harness Findings & Infrastructure Learnings

1. **Longitudinal Brain Dump Token Budget (`SYNAPSE_EXTRACTOR_MAX_TOKENS`):**
   The default `SYNAPSE_EXTRACTOR_MAX_TOKENS=900` in `turn_extractor.py` was tuned for single-sentence turns. Real longitudinal voice-note brain dumps (e.g. Scenario 1 Turn 1, containing 7 distinct operational items) generated ~2,800 characters of JSON observations. At 900 tokens, OpenRouter truncated the response mid-stream (`finish_reason="length"`), resulting in `JSONDecodeError`. Setting `SYNAPSE_EXTRACTOR_MAX_TOKENS=3500` in the harness allowed full multi-item extraction to complete without truncation.
2. **Fact Model Schema Contract:**
   The `Fact` model in `src/models/fact.py` possesses `title` and `evidence_verbatim`, but not `summary`. The trap evaluator was updated to safely check `evidence_verbatim` or `title` without raising `AttributeError`.
3. **Absence of Dedicated Non-Calendar Ingestion Endpoints in Cortex:**
   While Google Calendar updates map directly to `/v1/events/object` with native tombstoning, Cortex currently has no dedicated ingestion endpoints for banking statements or inbound email documents. The benchmark harness routes them through external-provenance adapters (`peer_id="external:<sender>"`), preserving origin without spoofing user turns.
4. **Zero Production Code Alteration:**
   All changes and configurations are isolated to `evals/sophie_longitudinal/` and `reports/`. Cortex production logic, database schemas, and lifecycle rules remain at baseline `44a89d1721d95eecd51fd53cf305dd598a27e5e1`.
