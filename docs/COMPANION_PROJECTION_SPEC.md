# Companion Projection v1 (Research Architecture — Not Production)

> Status: v1 draft for programme use. Nothing here authorises schema,
> runtime wiring, thresholds, or production behaviour. Graduated substrate
> unchanged.
> Evidence: P1 (`1ce11ee`, 0/8 shared-durable), S1 (`5fc8cbe`, broad
> detection fails), S2 (`cb8e0f8`, control 67/84 wins; stance killed),
> S3 (`b5b9591`, exception tier self-killed on E1d), Honcho rerun
> (`b7dabcb`, retrieval 10/10, synthesis 7/10, stored conclusions unsafe).
>
> **The projection is a prepared desk, not a director.** Cortex puts the
> useful papers on the desk; Companion Runtime sits down with the user and
> decides which papers to look at. The packet says "here is what may be
> relevant", never "do X" — except hard state (§Hard vs soft).

## Hard state vs soft relevance (binding boundary)

**Hard state / hard constraints** — Cortex sends these as authoritative;
they constrain Runtime:

- task completed → closed; bill paid; user changed mind → obligation
  released/removed; explicit reminder requested at a time;
- user said "don't mention X" → boundary (until reopened);
- meeting starts in N minutes; deadline facts; lifecycle transitions.

**Soft relevance / potential significance** — Cortex sends these as
**context and candidates**, never commands:

- goal still active; user seemed concerned about X recently;
- task could fit a free window; project important for weeks;
- unresolved thread from yesterday; history suggests a topic may matter.

ATTEND / HOLD / SUPPRESS / RELEASE are **research labels for evaluating
relevance**, not commands Cortex sends downstream. Runtime, holding the
live turn, character, product rules, and relational state, decides:
mention now, hold in mind, circle back later, ask, let it colour tone
without surfacing. The S-track's verdict is therefore not "no LLM
judgement" but: **no separate upstream LLM attention governor — judgement
lives in Runtime, which has the moment.**

## Sections

```text
CURRENT WORLD (factual, deterministic, substrate-backed)
- calendar, time constraints, active commitments, task state
- recent closures, recent important events

ATTENTION (eligible matters + deterministic trigger state)
- eligible / held / suppressed / released matters with eligibility facts
- explicit boundaries, recheck conditions
- NO general arbiter verdicts; exception tier killed (S3)

CONTINUITY (session and relationship texture)
- recent session handoff, open conversation threads
- promises the companion made, explicit user concerns

RELATIONAL CONTEXT (distinct channel from operational attention)
- emotionally important personal material currently salient
  (e.g. family concern disclosed today) — stated as context,
  never as an ATTEND command. E1-class dual handling lives here:
  routine SUPPRESS coexists with relational salience; Runtime
  reconciles them in the live turn.

HORIZONS (temporal readiness)
- today / next few days / current week
- dormant goals with known deterministic reopening conditions

JIT READ HINTS (not answers)
- candidate/questions for which longitudinal retrieval may become
  useful if the matter becomes live
  (e.g. "if exercise reminder becomes eligible under overload →
  longitudinal read may help")
- NEVER precomputed conclusions ("user dislikes reminders when
  overwhelmed" is forbidden as projection content — P1 0/8)
```

## Horizons and refresh

Session open (full build), day-boundary / morning-afternoon-evening
refresh (delta), event-triggered rebuild (calendar/task sync, major
event, meaningful conversation close), correction-triggered immediate
invalidation (corrections never wait for a cycle). Exact cadence OPEN.

## Invalidation

Recheck firing, contradiction, user correction, lifecycle closure, or
boundary-setting invalidates the affected projection parts immediately.
Stale projection must be unreachable, not merely marked.

## JIT protocol (sketch, not API)

Runtime on a gap: missing fact → authoritative Cortex query; missing
judgement → bounded longitudinal read pulled by the live candidate
(per Longitudinal Read contract; interrogative-only, recruited, ephemeral);
changed world → partial rebuild or correction-triggered invalidation. No
request path persists an answer as truth. No open-ended scans, ever.

## Banned content (programme kills, binding here)

General LLM attention verdicts; stance labels; trusted Honcho stored
conclusions (retrieval hints / debugging artefacts only); precomputed
trait/pattern conclusions about the person; numeric scores or priority
rankings presented as production state; any surfacing instruction beyond
hard state. G1–G6-style gate firings may appear as **telemetry /
diagnostics** (evaluation, observability, projection selection) — never
as behavioural authority.
