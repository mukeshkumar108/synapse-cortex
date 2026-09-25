# Sophie Longitudinal Benchmark Suite

This directory contains the durable regression and evaluation fixtures for the four Sophie longitudinal scenarios authored for the Companion Programme.

## 1. Overview & Purpose

Following extensive validation against relationship-heavy RPD2 transcripts, these fixtures test whether the shared companion substrate (`Cortex` + `Honcho` + `Runtime`) maintains truth, continuity, and restraint across messy, real-world everyday life:
- Rambling, voice-note style brain dumps
- Children, family obligations, and school logistics
- Invoices, payments, debts, and banking feeds
- External multi-source evidence (emails, calendar shifts, SMS) arriving while the user is inactive
- Half-intentions vs. actionable commitments
- Somatic complaints and emotional worry (true positives vs. one-off false positive traps)
- Relational personality texture and proactive companion follow-through
- Conversational restraint and silence

## 2. Canonical Source Notion Specifications

- **Parent Requirements:** [Sophie Messy Longitudinal Corpus](https://app.notion.com/p/3e66297866b081efa21acc9b46944c22)
- **Scenario 1:** [Ashley Event Ops + Children + External Evidence](https://app.notion.com/p/3e66297866b081e68e0ddfbca87e2afa)
- **Scenario 2:** [Ordinary Sophie: Plans, Half-Intentions, Changed Mind, Missing Detail](https://app.notion.com/p/3e66297866b08116a057e8bfd240630a)
- **Scenario 3:** [Multi-source Conflict, Two People Same Name, Indirect Closure](https://app.notion.com/p/3e66297866b08176a1c9cdf95348db15)
- **Scenario 4:** [Health, Worry & Personality Texture: Bidirectional Check-ins](https://app.notion.com/p/3e66297866b081019ecdfbed758ee2df)

## 3. Baseline Commits

- **synapse-cortex:** `44a89d1721d95eecd51fd53cf305dd598a27e5e1`
- **companion-runtime:** `6b2f78dff838f6d7db29d6bcb58e3c443c101210`

## 4. Strict Input vs. Oracle Separation

To ensure evaluation validity, fixtures are split into separate files:
- **INPUT (`scenario_*_input.json`):** Contains only what the system under test may see: timestamps, speakers, roles, source types, and verbatim content/metadata.
- **ORACLE (`scenario_*_oracle.json`):** Contains hidden evaluator truth, expected state transitions, false-positive traps, expected release/closure conditions, and Dual Aperture gear expectations (`HOLD` / `ENRICH` / `LEAD` / `ATTEND` / `SILENCE`).
**The oracle is NEVER injected into Cortex or Honcho.** It is loaded exclusively by the evaluation assertion layer.

## 5. Execution Modes & CLI Usage

The benchmark runner supports two explicit execution modes:

### Mode A: Model / Semantic Baseline (`--mode model`)
Exercises real model-led turn extraction via LLM (`google/gemini-2.5-flash-lite` via OpenRouter or configured model).
- **Loud Preflight Enforcement:** Requires valid API credentials (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, or `XAI_API_KEY`). Executes an active connectivity probe and fails with exit code 1 if credentials are missing or invalid.
- **No Silent Fallback:** Invariants guarantee that model mode never silently downgrades to rule-based extraction.
- **Outputs Directory:** Saved separately under `evals/sophie_longitudinal/raw_outputs/model/`.

```bash
# Run all four scenarios with the model extractor:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario all

# Run a single scenario (supports numeric aliases 1, 2, 3, 4 as well as scenario_1..4):
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario 1
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario scenario_2
```

### Mode B: Rules / Determinism Floor (`--mode rules`)
Exercises deterministic, offline rule-based extraction.
- **Labeling & Intent:** Serves strictly as a structural regression baseline and determinism floor.
- **Trap Interpretation:** Trap passes in this mode are explicitly labeled as structural floor checks only, NOT as semantic evidence of conversational restraint (since an empty/minimal extractor cannot false-positive).
- **Outputs Directory:** Saved separately under `evals/sophie_longitudinal/raw_outputs/rules/`.

```bash
# Run all four scenarios with the rules extractor:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode rules --scenario all

# Run a single scenario:
./.venv/bin/python evals/sophie_longitudinal/runner.py --mode rules --scenario 1
```

### CLI Arguments Summary:
- `--scenario {1, 2, 3, 4, scenario_1, scenario_2, scenario_3, scenario_4, all}`: Target scenario(s) to execute (default: `all`).
- `--mode {rules, model}`: Selects execution mode (default: `rules`).
- `--provider {rules, model}`: Alias for `--mode`.

## 6. Output Artifacts

Running the harness populates partitioned output directories:
- `evals/sophie_longitudinal/raw_outputs/rules/`
- `evals/sophie_longitudinal/raw_outputs/model/`

Each directory contains:
1. **Raw Markdown Checkpoints (`<scenario>_raw_checkpoints.md`):** Complete structured state dumps at each checkpoint matching canonical RPD2 replay formatting:
   - Active Expectations
   - Commitments (ACT vs. ASK authority)
   - Proposal Exposure (stored ASK vs. surfaced shelf + skipped reasons)
   - Open Loops
   - Current Meaning (T2b rollup)
   - Attention & Suppressions
   - Entities, Aliases & Links
   - Model Entries & Turn Frames
   - What Changed Since Last Checkpoint
2. **Evaluation Summary JSON (`<scenario>_summary.json`):** Programmatic checkpoint metrics, exact provider/model metadata, external call flags, final state counts, and false-positive trap defense evaluations.

## 7. Multi-Source Evidence Architecture

- **Calendar Updates:** Ingested via native Cortex `/v1/events/object` with `system="google_calendar"`. Updates supersede prior expectations; completions record resolved tombstones.
- **Conversation Turns:** Ingested via `/v1/events/turn` (`is_assistant_turn=False` for user, `is_assistant_turn=True` for Sophie).
- **Non-Chat External Feeds (Email, Payment Feeds, SMS):** Ingested via bounded test adapter preserving exact external peer identity (`peer_id="external:<sender>"`). Production Cortex does not yet possess dedicated email/bank statement ingress routes; the harness preserves provenance without converting events into fake user speech.
