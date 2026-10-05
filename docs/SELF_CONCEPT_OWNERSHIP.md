# Self-concept: ownership model (analysis only — no implementation)

Premise from Gemini (not independently verified here): explicit self-beliefs materially change how the interpreter reads a scene, and stay dormant in healthy scenes.
This document is about structure: who owns what, and whether the dynamic half needs a new Cortex object. **It does not.**

## The two halves
| | Baseline self-concept | Current self-model |
|---|---|---|
| Owner | **Product** (character identity, beside constitution, biography, voice) | **Cortex** (interpretation of accumulated evidence) |
| Nature | Authored premise. Characters differ by data ("I'm someone who keeps my word" vs "I'm someone who runs from conflict") | Revisable reading of what the character currently believes / fears / has learned about itself |
| Where it lives | Runtime registry, on the companion definition, as a typed list of short first-person statements | Existing world structures (below) |
| Who can change it | Only the product, by a versioned edit | The interpreter, by evidence, via supersession |
| How the model sees it | Inside the constitution (the product composes it), first in the prompt | A short descriptive block, only when relevant (below) |

Precedent already in the system: the **constitutional orientation** is product-authored input; the interpreter *assesses current behaviour against it* and writes a trajectory note; it never extracts or rewrites it. The baseline self-concept is the same pattern for the self. The interpreter receives it as a typed input next to the orientation ("CHARACTER BASELINE SELF-CONCEPT — product-authored, never extracted, never rewritten").

## Mapping the dynamic half onto what exists
| Requirement | Existing structure that already does it |
|---|---|
| Revisable belief that can strengthen, weaken, evolve | **Dimensions** (`durability` acute/provisional/durable, `supersedes`, `confidence`, `formation`, evidence ids, review obligation each pass) — used today for directional relationship facets |
| Transient shame/fear must not become identity | The DURABILITY rule (a single dramatic turn is an event + *acute* state, never durable by itself) and the acute TTL in the projection |
| Positive growth as well as deterioration | The same supersession mechanism; a facet replaced by a healthier reading under the same evidence bar |
| Provenance: self-stated vs user attribution vs Cortex inference | **Direction + formation + evidence**: (a) self-stated = a dimension from the character *to itself*, `formation: explicit/reported`, evidence = its own words; (b) user attribution = a *different* facet, user→character ("Kai: sees her as selfish") — evidence of the user's view, not of the self; (c) Cortex inference = `formation: inferred`. ClaimC additionally has `holder` (actor / "model" / narrator) for attribute claims |
| Avoid duplicating trajectory | Trajectory stays "how current behaviour relates to the product orientation"; it may *cite* the self-view as a driver (the prompt already asks for drivers: hurt, fear, shame) but does not store it |
| Avoid duplicating relationships / Matters | Self-view facets are about the self; relationship facets about others; a Matter only if future behaviour depends on an unresolved situation (`continuity_required`) |
| Avoid prescriptions | The projection is description with age and provenance, framed like the scene and trajectory blocks: context, never an instruction |

**Representation:** a **self-directed dimension** — a relationship facet whose `from_actor` and `to_actor` are the same actor, hung under a typed self-edge (`relationship.type = "self"`). Everything above then comes for free, including the TTL on acute facets and the review verdicts that make silence unable to mean "still true".

### Smallest set of changes (when approved; none made)
1. Allow a self-edge (`actors: [a, a]`, type `self`) in the interpreter output and the materializer. *To verify first:* no service or DB constraint forbids an edge from an entity to itself (the schema does not forbid it; untested).
2. A SELF-MODEL section in the interpreter prompt: what counts as evidence; self-statements and the character's own turns are evidence of what it *says*, never authority; acute reactions stay acute; durable needs sustained, corroborated evidence across separate episodes; growth meets the same bar as decline; a user's attribution is recorded as the user's view, not the character's.
3. The baseline as a typed input to the interpreter (registry field on the companion definition), beside the constitutional orientation.
4. A compact projection: "how the character currently sees itself", rendered only for facets that are active or diverge from the baseline, each with durability, provenance and age; dormant otherwise (selected by the interpreter's own judgement of state, not keywords).
5. A registry field for the baseline (data; no behaviour).

No new table, no new object, no new store.

## Authority hierarchy (highest first)
1. **Product constitution and baseline self-concept** — identity; the substrate cannot edit, reorder or contradict it; compiled first.
2. **Explicit product policy** (registry: epistemic policy, isolation) — what kinds of claims become canon.
3. **Sustained, corroborated self-model** (durable facets) — how the character currently relates to its baseline; descriptive.
4. **Provisional self-model** — supported, unconfirmed; labelled as such.
5. **Acute reactions** — a moment's state; short TTL; never rendered as established.

Disagreement rule: where the self-model disagrees with the baseline, **the baseline wins in identity**; the self-model describes *how the character presently stands in relation to it* ("currently doubts she is someone who keeps her word"), it never replaces it. A *persistent* divergence is surfaced as a signal to the product (trace/report), not silently adopted: only the product evolves the baseline, by a versioned edit.

## Requirement check
| Requirement | Met by |
|---|---|
| Constitution highest | baseline lives in the registry, compiled first; Cortex rows reference it, never replace it |
| Cortex cannot silently rewrite identity | no write path to the registry; divergence is reported, not applied |
| Strengthen / weaken / evolve | supersession + confidence + durability tiers |
| Transient shame ≠ identity | acute tier, TTL, sustained-evidence rule |
| Distinct provenance | direction (self vs user→character) + formation + evidence |
| Growth as well as deterioration | symmetric supersession under the same evidence bar |
| No behavioural prescription | descriptive block with age/provenance; never an instruction |
| No duplication | self facets ≠ trajectory (behaviour vs orientation) ≠ relationship facets ≠ Matters |

## Risks to test in the lab, not assume
* **Self-reinforcing loop.** The character's own words become evidence, which becomes a self-model, which returns to the foreground. The existing guard ("what the character says is evidence of what occurred, never authority") and the durability bar are the defence; the bench should ablate the self-view block (`drop_paths`) to see whether it changes behaviour at all in healthy scenes (Gemini says it should not) and in stressed ones (where it should).
* **Selection.** Dormant in healthy scenes depends on the interpreter judging relevance; a wrong judgement silently drops or over-surfaces the block.
* **Cost.** Self facets add rows and prompt text to every interpreter pass; measure.
* **Scope.** For Sophie (grounded, a real person's companion) the same mechanism applies, but a Sophie self-model must never be promoted from her own unsupported assertions (the grounded policy already downgrades them).

## Open questions for review
1. Baseline authored as a typed list of first-person statements (recommended: the interpreter can see them separately) versus embedded in the kernel prose (then the interpreter cannot tell premise from texture).
2. Whether a `holder` field on dimensions is ever needed, or direction suffices (current view: direction suffices).
3. The lab test plan: an interpreter-variant spec (baseline self-concept supplied; same transcript) against none, comparing the self-facet rows and the downstream foreground reply, using the existing workbench only.
