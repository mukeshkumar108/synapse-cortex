# Interpreter model bake-off (2026-10-06)

Method: the real interpreter prompt (system + structured world state + Honcho context + 6 earlier + 8 new messages, ~8.4k tokens) sent dry (nothing written) to each candidate on OpenRouter; the
same input for every model. One input per model for the first sweep (a heavy real world), two inputs for the Luna family. Measured: wall time, billed tokens/cost, valid JSON, what was extracted.

| Model | Time | Cost/pass | Result |
|---|---|---|---|
| openai/gpt-5.6-luna-pro (was in use) | 44s | $0.0201 (46k prompt, 12k completion) | full. **Bills ~5.5x the prompt tokens: the Pro variant's internal ensembling** |
| **openai/gpt-5.6-luna (now)** | 20-31s | $0.0034-0.0050 | full; slightly richer than Pro |
| openai/gpt-5.6-luna + "be terse" | 15-20s | similar | ~4s faster, slightly fewer claims on a light input: not adopted |
| openai/gpt-6-luna | 20-37s | $0.0017-0.0029 | cheaper but slower and thinner (light input: no claims/events): rejected |
| google/gemini-3.1-flash-lite | 11s | $0.0053 | valid, but only 2 of 10 state reviews: rejected for review coverage |
| google/gemini-3-flash-preview | 12s | $0.0116 | same thinness |
| deepseek/deepseek-v4.1-flash | 68s | $0.0048 | full but slow |
| deepseek/deepseek-v4-flash, anthropic/claude-haiku-4.5, poolside/laguna-s-2.1 | | | invalid JSON (truncation / empty / trailing data) |
| openai/gpt-oss-120b | 73s | $0.0009 | valid; no claims, no objectives |
| openai/gpt-oss-20b | 151s | $0.0010 | valid; no scene content |
| amazon/nova-micro-v1 | 6s | $0.0006 | valid; thin (1 of 10 reviews) |
| ibm-granite/granite-4.0-h-micro | 58s | $0.0004 | **no scene/brief at all** |

Conclusions: the interpreter's INPUT was never the problem (about 8.4k tokens); the "Pro" variant was. Output generation dominates the remaining time. Fast Gemini models roughly 3x quicker but skip
the review obligation (a silent "still true" risk); the very cheap open models fail the structure. Next lever if more speed is needed: shrink the OUTPUT (review verdicts for unchanged items, notes).
Evidence limits: one sample per cell, two inputs, no quality scoring beyond structure and reading.
