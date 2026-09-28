# Companion Projection Spec (Draft — Research Architecture, Not Production)

> Status: draft for programme use. Nothing here authorises schema, runtime
> wiring, thresholds, or production behaviour. Graduated substrate unchanged.
> Evidence: P1 (`1ce11ee`), S1 (`5fc8cbe`), S2 (`cb8e0f8`), Honcho probe
> (`85942ef`), P0 (`49fa0a0`), S0 (`bac8c274`).
>
> **The packet is a projection, not truth.** Its authoritative source is
> always lower down (Cortex evidence, authored claims, corrections,
> receipts, lifecycle). It is disposable, regenerable, and invalidated by
> recheck, contradiction, or correction.

## What it is

A small, fast, prepared map of the current world for Companion Runtime:
what is known, what is eligible, what is open/closed/sensitive, what
becomes useful when, what reads may be needed, and what must be
revalidated before surfacing. It answers readiness, not identity. It does
not contain the person.

## Horizons (preparation timescales)

- **Session open:** full projection build (deterministic substrate pull +
  longitudinal context attach).
- **Day boundaries / morning-afternoon-evening refresh:** lightweight
  rebuild or delta update.
- **Event-triggered:** calendar/task sync, major event, meaningful
  conversation close, explicit user correction (corrections invalidate
  immediately, never wait for the next cycle).
- Exact cadence is OPEN — S3/Honcho evidence first, timers later.

## Sections (readiness kinds)

```text
FACTUAL READINESS — what is known and current?
  calendar constraints, meetings, hard deadlines, due/eligible tasks,
  explicit reminders, open commitments, recently resolved matters,
  authored boundaries and deferrals. Deterministic, substrate-backed.

ATTENTION READINESS — what candidates are eligible?
  attend / held / suppressed / released-closed candidates with
  eligibility facts. Deterministic default posture;   exception-tier
  judgements attached only where S3 earns them, flagged provisional
  (judgement, not fact).

SOCIAL READINESS — what topics are open / closed / sensitive / welcomed?
  boundaries, closures, heavy-context flags, never-surface patterns
  (referenced, never disclosed: "topic closed Thursday", not content).

TEMPORAL READINESS — what becomes useful now / later / this week?
  recheck conditions, dormant goals with reopening shapes, upcoming
  horizons, expiry times.

SEMANTIC READINESS — what bounded reads may be needed?
  questions the arbiter is likely to pull (e.g. "how have exercise
  nudges landed lately?"), NOT precomputed answers. Answers are JIT.

JIT REQUIREMENTS — what must be revalidated before surfacing?
  reconciliation gates (receipt beats rule), authority annotations
  (self-report dominance, invitation status), per-matter freshness.
```

Dual-judgement shape (E1 family): routine candidacy and relational
attention are separate fields — e.g. `gym: eligible yes, surface_now no`
alongside `person: relational_attention elevated, warm-check-in allowed`.
A task list with suppression flags alone is insufficient by programme rule.

## Deterministic vs cached vs JIT

- **Deterministic:** everything derivable from substrate + triggers.
  Majority of the projection. Cheap, testable, owns ~80% of cases (S2).
- **Cached:** revisable derived views ONLY if scale evidence demands
  (OPEN). Disposable materialised interpretations with invalidation
  conditions on their face; never source-of-truth; invalidated by
  recheck, contradiction, or correction.
- **JIT:** bounded longitudinal reads pulled by live candidates, plus
  authoritative Cortex queries for missing facts. S3 exception tier and
  Honcho-probe-verified reads are the only sanctioned sources.

## Runtime requests (sketch, not API)

Runtime holds the projection; on a gap it requests downward: missing fact
→ Cortex authoritative query; missing judgement → bounded read pulled by
the live candidate (never open scans); changed world → partial rebuild or
correction-triggered invalidation. No request path may persist an answer
as truth.

## Status marking (anti-graduation-guard)

- **Proven:** deterministic candidate generation; lifecycle ownership;
  bounded candidate sets reduce false positives (S1→S2: 40–59% to 0–8.3%);
  packet-as-disposable-projection; JIT authoritative fallback.
- **Supported, not production-proven:** recruited longitudinal reads
  (10/10 author-performed, blind rerun required); LLM exception tier
  (isolated wins, S3 must confirm at FP 0%).
- **Open:** E1 person-vs-task handling; cached derived views; Honcho
  longitudinal QA; refresh cadence/horizon design; prioritisation ordering
  (no evidence PRIORITISE is decidable — default without it).

No hypothesis above may appear in an architecture diagram without its
marking. Markings change only on pre-registered experimental evidence.
