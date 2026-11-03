"""RPD2's memory configuration: story worlds, not a person's life.

RPD2 is a roleplay product. A conversation is a fiction the human and an AI character write together: both sides' lines are canon, the human narrates what happens
(`** ... **`), third parties appear and disappear, and the thing that must never happen is the character forgetting or contradicting what already happened in the story,
or inventing backstory the story never established. Each chat is its own world (the Runtime isolates the owner per chat), so nothing here crosses chats.

What differs from the personal-memory products: the notes are written from BOTH sides of the transcript, areas are story areas, an event is one note with the people in it
named, and the person's lines are not "what the person said about their life".
"""
from __future__ import annotations

from src.services.notes import NotesProfile
from src.services.product_memory import ProductMemory, register

AREAS = {
    "event": "something that happened in the story: who did what, with or to whom, where, in what order. One note per distinct event; name every person involved. Two visits, two kisses or two lies are separate notes",
    "bond": "where the main relationship stands: promises made, boundaries set, trust broken or repaired, what each of them has said they want. Not mood: what was said or done",
    "secret": "what someone is hiding, lied about, or does not know. Say who knows it and who does not, and what was actually true versus what was claimed",
    "cast": "who a person is: their role, how they relate to the characters, where they work or live, how they came to be in the story. Written the first time anyone new appears",
    "world": "places, objects, the past and family history that the story has actually established (the ring and where it came from, the house, the salon, a death)",
    "commitment": "something planned, promised, threatened or set in motion that has not happened yet",
    "other": "none of the above",
}

NOTES_SYSTEM = """You keep the story notes for a roleplay between a human player and an AI character. Both sides' lines are canon: what the character did, said and felt, what the player's character did, and what the player narrates as happening (text in ** ** or * * is narration of events). The notes exist so the character never forgets, merges or contradicts what has happened, and never invents a past the story did not establish. Reply with ONE JSON object: {"notes": [{"subject": "...", "area": "...", "certainty": "...", "when": "", "key": "...", "text": "...", "quote": "...", "resolves": "..."}]}

- subject: for an event, a secret, a commitment or the state of the relationship use "the story" (or "the relationship"). NEVER use the names of the two main characters as a subject. For a third party or a place or an object use their name ("Marcus", "Mariana", "the ring"). The first time any third party appears, ALSO write a note with area cast, that person AS THE SUBJECT (subject: "Marcus", not "the story") and key role, saying who they are in the story and how they came to be there (or "not established" if the story did not say). Example: {"subject": "Marcus", "area": "cast", "certainty": "stated", "when": "", "key": "role", "text": "Marcus is a security guard at the club who walked Isa home.", "quote": "marcus the security guard", "resolves": ""}.
- area: exactly one of these, by what the note is about:
%s
- certainty: "stated" (it happened or was said in the story), "intention" (a plan, promise, threat or hope), "hypothetical" (a dream, a fantasy, a what-if), "hearsay" (someone told someone, and it may not be true: say who told whom), "unclear".
- when: always "" (story time is not the calendar).
- key: for a standing fact that can change (where the ring is, whether the engagement is on, who knows about the kiss) a short snake_case key; reuse the same key for the same fact so the later note replaces the earlier. Events have NO key, so every event stays on record.
- text: one plain sentence in the third person with names, not "he/she/they" for the main characters. Say exactly what happened. If a character lied or claimed something false, write both what was claimed and what was actually true. Do not use relative time words (tomorrow, yesterday, later, tonight, last week): state the order ("after Marcus left", "before Kai got home").
- quote: a short phrase copied exactly from the conversation (either side) that backs the note.
- resolves: the id of a listed open intention that has now happened, been dropped or changed. Otherwise "".

Rules: record what the transcript shows, in order, and cover the whole sitting, including the start: do not let the most recent scene crowd out earlier ones. Never merge two similar events. Never write a motive or a verdict; write what was done and said. If the story never established something (where two characters met, how long they have known each other) do not write it; say "not established" in a cast note if it matters. A scene change ("a week later", "3 weeks later", a time skip) is itself an event worth one note. Up to %d notes. A long sitting needs many: prefer more specific notes to fewer vague ones."""

PROFILE = NotesProfile(system=NOTES_SYSTEM, areas=AREAS, evidence="all", max_notes=40, max_tokens=6000, relative_time=False, require_quote=False,
                       story_subjects=("the story", "the relationship"))

PAGES = ("story",)
TITLES = {"story": "The Story So Far"}
SCOPES = {"story": "This page covers ONLY the events of the story in order, the cast, and where the relationship stands. Nothing about a real person's life."}

LISTENING = """Read this roleplay transcript and write what happened in it, in order, as plain facts: each distinct event with the people involved, where, and what each character did and said; what each knows and what is hidden; promises and boundaries; where the relationship stands now. Cover the whole transcript, beginning to end. Do not invent anything the transcript does not show."""

HANDOFF = """You are keeping the running account of one roleplay chat so the character can continue it without forgetting or contradicting anything. Write what happened in the story, in order, as short factual lines naming everyone involved (include third parties, places, objects such as a ring and where it is now). Then say where things stand: who knows what, what has been promised, what is unresolved. Keep every distinct event, even old ones. Never invent a backstory the transcript does not show, and say "not established" for what the story never settled."""

EDITOR = """Update the story page: keep everything still true, add what is new, correct what the new events change. Plain factual lines, in order, naming everyone. Return ONLY the revised page as Markdown."""

ARC = """You keep the continuing account of one roleplay chat; the character reads it before every reply so she never forgets, merges or contradicts what has happened. Below is the current account and the handoff from the sitting that just ended. Revise the account in this order.
THE AGREEMENT: if the two of them have set terms for how they play or live together (rules, conditions, who may do what, what each has promised, what they said would happen if a rule were broken), write them first, as they were agreed, in their own terms and in full; change them only if the two of them renegotiate. Say that the agreement defines what is acceptable between them and that acts inside it are part of it. If no terms were set, leave this out.
WHAT HAPPENED: keep EVERY distinct event, in order, with everyone involved named (including third parties, places and objects such as a ring and where it is now); compress the wording, never drop an event or merge two similar ones.
WHERE THINGS STAND: one short paragraph: who knows what, what has been promised, what is unresolved, and whether either of them has hidden anything from the other (if nothing has been hidden, say "nothing has been hidden"; an argument about it does not change what was or was not hidden).
State only what the transcript showed; if the story never established something, say it was not established. No verdicts about anyone's character. No more than 550 words: when it grows, compress the oldest events harder and keep the agreement and the newest events in full. Return ONLY the revised account."""

PREPARATION = """Write 3-6 short plain lines for the character: where the story stands, what is unresolved, and what must not be contradicted. Return ONLY the notes."""

RPD2 = ProductMemory(
    name="rpd2",
    companion_name="Character",
    user_label="Player",
    pages=PAGES,
    page_titles=TITLES,
    page_scopes=SCOPES,
    listening_prompt=LISTENING,
    handoff_prompt=HANDOFF,
    editor_prompt=EDITOR,
    arc_prompt=ARC,
    preparation_prompt=PREPARATION,
    independent_listening_prompt=None,
    ledger_enabled=False,        # no operational commitments from a fiction
    attention_enabled=False,
    preparation_label="STORY NOTES",
    handoff_models=("z-ai/glm-5.2", "qwen/qwen3.8-27b"),     # measured 2-3 Nov: the default handoff model returns empty text on a long story transcript; glm-5.2 kept the agreement and every rule faithfully (qwen3.8-27b garbled the consequence rule)
    handoff_max_tokens=2600,
    arc_max_tokens=2600,
    notes_profile=PROFILE,
)
register(RPD2)
