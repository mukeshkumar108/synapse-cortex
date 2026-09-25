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

## 5. How to Run

From the root of `synapse-cortex`:

### Run all four scenarios:
```bash
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario all
```

### Run a single scenario:
```bash
# Scenario 1 (Ashley Event Ops)
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario scenario_1

# Scenario 2 (Ordinary Plans & Half-Intentions)
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario scenario_2

# Scenario 3 (Multi-source Conflict & Disambiguation)
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario scenario_3

# Scenario 4 (Health, Worry & Personality Texture)
./.venv/bin/python evals/sophie_longitudinal/runner.py --scenario scenario_4
```

### Options:
- `--provider {rules,model}`: Set the extraction provider (default: `rules`).
- `--db <path>`: Override the temporary SQLite database path.

## 6. Output Artifacts

Running the harness generates:
1. **Raw Markdown Checkpoints (`evals/sophie_longitudinal/raw_outputs/<scenario>_raw_checkpoints.md`):** Complete structured state dumps at each checkpoint matching canonical RPD2 replay formatting:
   - Active Expectations
   - Commitments (ACT vs. ASK authority)
   - Proposal Exposure (stored ASK vs. surfaced shelf + skipped reasons)
   - Open Loops
   - Current Meaning (T2b rollup)
   - Attention & Suppressions
   - Entities, Aliases & Links
   - Model Entries & Turn Frames
   - What Changed Since Last Checkpoint
2. **Evaluation Summary JSON (`evals/sophie_longitudinal/raw_outputs/<scenario>_summary.json`):** Programmatic checkpoint metrics and false-positive trap defense results.

## 7. Multi-Source Evidence Architecture

- **Calendar Updates:** Ingested via native Cortex `/v1/events/object` with `system="google_calendar"`. Updates supersede prior expectations; completions record resolved tombstones.
- **Conversation Turns:** Ingested via `/v1/events/turn` (`is_assistant_turn=False` for user, `is_assistant_turn=True` for Sophie).
- **Non-Chat External Feeds (Email, Payment Feeds, SMS):** Ingested via bounded test adapter preserving exact external peer identity (`peer_id="external:<sender>"`). Production Cortex does not yet possess dedicated email/bank statement ingress routes; the harness preserves provenance without converting events into fake user speech.
