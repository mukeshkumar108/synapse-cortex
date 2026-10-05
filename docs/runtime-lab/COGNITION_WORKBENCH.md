> Mirrored from companion-runtime/docs/COGNITION_WORKBENCH.md (canonical copy lives there).

# Cognition workbench

A causal debugger for companion cognition. Product-agnostic (RPD2, Sophie, Bloom use the same bench). It answers one question:
**which layer produced this behaviour?** — bad interpretation, wrong/missing trajectory, state lost by attention or the compiler, the raw tail
overpowering the state, the kernel wording, or the foreground model itself.

It is NOT an eval suite and does not score. We read replies and compare how they *differ* when exactly one thing changes.

## Mental model

```
transcript T1..Tn  ──chronological──►  real Cortex interpretation (flushed through the exact cut)  ──► FROZEN world @ cut (by value)
                                                                                                          │
                                       same next user turn, one thing changed per variant  ◄──────────────┘
                                       (model · kernel line · scene/trajectory/matters on-off · raw tail · placement · sampling)
                                                    │
                       compiled foreground prompt (exact) → actual model (strict) → reply  → markdown report
```

Guarantees (proved; do not break them):
* Future turns never reach the world before the cut (ingest is chronological, to the cut only).
* The freeze is by value: variants carry the world and never re-read Cortex, so the source world can move without changing a frozen run.
* Evaluation turns write nothing (no world, no scene, no episode ledger); every variant is a fresh person on one shared clock.
* Strict models: a variant that silently fell back to another model is retried twice, then marked INVALID. Never analyse an INVALID sample.

## Running an experiment

```
scripts/lab.sh labs/local/<set>/spec.json        # from the companion-runtime repo; needs ssh to the VPS
```
Reports appear in `./lab-reports/<spec name>/` (`<stamp>-index.md` + one `.md` per cut). Reports contain the roleplay text verbatim
(adult content) — keep them local; `lab-reports/` and `labs/local/` are gitignored.

### Spec

```json
{
  "name": "tail-sweep-1",                        // also the world scope; a NEW name = a new world (re-ingest). Never reuse a name with different cuts.
  "transcript": "transcript.json",               // [{"role": "user"|"assistant", "content": "..."}], next to the spec
  "constitution": "constitution.txt",            // the product's character kernel/voice, already bound to the user's name
  "companion": "elena-voss", "speaker": "Elena", "user": "Kai", "policy": "generative",
  "model": "bytedance/doubao-seed-character",    // pin explicitly; default for every variant
  "samples": 3,                                  // per variant (use >=5 when a difference matters)
  "interpreter": {"system_replace": [["old sentence","new sentence"]], "system_append": "extra rule", "model": "..."},   // optional: interpret THIS world under a variant interpreter (see below)
  "cuts": [ {"name": "cut4", "cut": 81} ],       // first `cut` messages are history; message index `cut` is the next user turn (override: "next_index", or "next_text": "typed turn")
  "variants": [ {"name": "baseline"}, {"name": "tail2", "workbench": {"raw_window": 2}} ]
}
```
List cuts in any order; they are ingested ascending in ONE world (the only paid step: interpreter passes on OpenRouter). Frozen cuts are reused on re-runs;
adding a later cut to an existing spec name only ingests the new stretch. Foreground calls go to NanoGPT (subscription) — change variants freely.

### Variant knobs (`"workbench": {...}` unless noted)

| Knob | Effect |
|---|---|
| `"model"` (variant level) | foreground model for this variant |
| `raw_window: N` | raw tail size in MESSAGES (6 = 3 turns, 2 = one exchange, 0 = interpreted state + current message only) |
| `tail_roles: "user"` | tail keeps only the user's messages (the model's own earlier replies are the strongest local pattern) |
| `placement: "late"` | interpreted blocks (story, scene, objectives, trajectory) ride immediately before the current user message instead of the system prompt |
| `raw_from_scene: true` | take the tail size the interpreter recommended (0–3 turns) |
| `no_world: true` | no interpreted world at all (kernel + tail only: the recent-only control) |
| `drop_paths: [...]` | remove exact parts of the world, dotted from the resident root, e.g. `world_model.continuation.active_intent.trajectory_note`, `world_model.continuation.brief.scene`, `world_model.continuation.active_intent` (orientation+objectives+trajectory) |
| `drop_sections: [...]` / `drop_ids: [...]` / `drop_attention: [...]` | whole world-model sections / items by id / attention keys |
| `prompt_remove: ["exact text"]` | remove a span of the COMPILED prompt (substrate-authored text) |
| `prompt_replace: [["old","new"]]` | exact replacement anywhere in the compiled system prompt (fails loudly if `old` is absent) |
| `drop_blocks: ["[TEMPORAL FACTS", ...]` | drop whole compiled blocks by header prefix (fails loudly if no block matches) |
| `no_roster: true` | disable the production roster block (names of durable actors not otherwise visible) for an A/B against it |
| `project_actors: {detail: names\|relation\|claim, select: all\|absent\|salient, limit}` | LAB-ONLY richer actor projection (replaces the production roster for this variant) |
| `keep_world_only: ["actors", ...]` | keep only these world sections (attention state emptied) to isolate one channel |
| `late_append: "text"` | arbitrary text placed next to the user's message (lab-only steering experiments; products never do this) |
| `sampling: {temperature, top_p, top_k, min_p, repetition_penalty, frequency_penalty, presence_penalty, max_tokens}` | reply sampling override (lab only) |
| `constitution_remove: ["substring"]` (variant level) | drop every kernel line containing the substring (fails loudly if nothing matches) |
| `constitution_replace: [["old","new"]]` (variant level) | replace text in the kernel |
| `constitution_file` (variant level) | use a different kernel file |

### Varying the interpreter itself
The scene the foreground sees is produced by Cortex's world interpreter. To test a different scene prompt, give the spec an `interpreter` block and a NEW spec name:
that world is ingested chronologically under the variant (lab-only: Cortex accepts overrides only for `world:lab:*` owners, and a replacement that matches
nothing is rejected, so an experiment can never silently test nothing). Compare reports from two spec names over the same transcript and cuts.
To see the exact deployed prompt, schema notes and where its output goes: `ssh <vps> "docker exec -i companion-runtime python - interpreter-config" < scripts/workbench.py`
(authoritative export; see `docs/SCENE_INTERPRETER.md`). The kernel/constitution is a plain file per spec (and `constitution_*` per variant), so a sentence is
tested by editing text, not repo source.

## How to read a report
1. **World at the cut** — what Cortex believed (story, live scene, orientation, objectives, trajectory). If this is wrong, the fault is interpretation.
2. **Evidence Cortex was given** lists the interpretation passes (and points at the per-run trace with kept/dropped candidates and reasons).
3. **Exact compiled prompt and the exact messages sent after it** — if the right state is here but the reply ignores it, the fault is attention/foreground, not Cortex.
4. **Variants** — compare replies across variants and across samples. Differences *between* variants that exceed the spread *within* a variant are signal.
   Remember n is small; say "suggestive" not "proved".
5. Note the **prompt diff** lines to confirm a variant changed only what you meant.

## Operating rules
* Never edit Runtime, Cortex, Honcho or the compiler from a lab task. Experiments change spec files only.
* Always pin the model. Treat INVALID samples as missing, not as data.
* Do not score or rank replies; describe differences (what the character does/claims/asks, whether it stays legible against the world and kernel).
* Do not re-ingest to "refresh" a world: new name, new world, new interpreter spend — only when the question needs it.
* Reports are the deliverable. Save them; summarise observations separately from interpretation; list anything surprising.

## Standing hypotheses (run in this order; one spec each; same cuts and model throughout)

1. **Tail sweep** — `raw_window` 0 / 2 / 4 / 6, each with `tail_roles` both and `user`. Cuts: one healthy (cut2) and one poisoned (cut4). *Known so far:* on the poisoned cut, ≥4 messages let the local frame win; ≤2 shifts toward the kernel/state.
   The healthy cut is the unknown: does a short tail make ordinary scenes dull, clingy or discontinuous?
2. **Late placement** — baseline vs `placement: "late"` at tail 6, 2 and 0. Hypothesis (long-validated in the old RPD2 steering work): instructions/state closest to generation win; the system prompt is overwritten.
   We want the interpreted state to win WITHOUT being an instruction.
3. **Kernel lines** — toggle one kernel line at a time with `constitution_remove`; look at which line the behaviour actually depends on (e.g. lines like "greedy in private", "chose Kai every day").
4. **Sampling** — temperature 0.5 / 0.8 / 1.0 / 1.2 (and top_p) at fixed tail. Does variance, not the tail, explain some of the drift?
5. **Models** — same variants on `bytedance/doubao-seed-character` and `deepseek/deepseek-v4-flash` (NanoGPT; if the id is wrong the sample shows INVALID). A frontier model on OpenRouter costs money — ask first.
6. **Scene ablation** — `drop_paths: ["world_model.continuation.brief.scene"]` vs scene present, at tails 0 and 2: does the interpreted live scene add anything beyond kernel + short tail?

## What this bench cannot do yet
* Multi-turn continuation of a variant (needs a Cortex-owned world fork; deliberately not built until one-turn results demand it).
* Pin Jev's routing flags across variants (they are captured in the report; divergence shows there).
* Change the interpreter's OUTPUT SCHEMA per variant (prompt/model yes; new fields need a code change in Cortex).
