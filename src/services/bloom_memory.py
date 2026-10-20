"""Bloom's memory configuration (initial implementation hypothesis, not a taxonomy).

Bloom is a reflection / personal-development / learning companion. What its
memory must carry: where the person is in their own development, what they are
working through, what they are learning or practising, and any agreed experiment
awaiting follow-up. Pages are product-owned and written in neutral voice about
"the person". Agreed experiments and explicit promises are operational matters
and live in the ledger (kind "experiment"), not on a page.
"""
from __future__ import annotations

from src.services.product_memory import ProductMemory, register

PAGES = ("life", "reflections", "concerns", "growth")

TITLES = {
    "life": "Life & Context",
    "reflections": "Reflections & Themes",
    "concerns": "Developing Concerns",
    "growth": "Learning, Practice & Experiments",
}

SCOPES = {
    "life": "This page covers ONLY: the person's circumstances that give their reflections context — routines, work, relationships and people they mention, living situation. Keep ONLY material relevant to that. Leave everything else out; other pages cover it.",
    "reflections": "This page covers ONLY: what the person has noticed about themselves, themes they return to, insights they put into words, values they state. Use their own words for how they feel. A feeling they did not state is not recorded. Keep ONLY material relevant to that.",
    "concerns": "This page covers ONLY: concerns, struggles or situations the person has brought that are still developing, with how each has moved over time. Record what they said, not a diagnosis or a verdict. Keep ONLY material relevant to that.",
    "growth": "This page covers ONLY: what the person is learning or practising, habits they are trying to build, and experiments or exercises they agreed to — what was proposed, whether they accepted, what happened. A suggestion the companion made is not something the person did or agreed to. Keep ONLY material relevant to that.",
}

LISTENING = """Read this conversation and bring me up to speed: what did the person share, notice or decide here that is worth remembering, and what is still unresolved for them? Only keep what genuinely matters. Use the person's own words for how they feel; do not attribute feelings they did not state. Write it as short, plain, standalone sentences."""

HANDOFF = """You are a transcript summary. Deliver no more than 2-3 sentences at most.

Read this transcript and bring me up to speed: what just happened for the person, what changed, and what is worth remembering going into their next session?"""

EDITOR = """You maintain a small living notebook about a person's reflection and growth, kept by their companion Bloom. Below is one notebook page and a set of new findings from a just-finished conversation.

Update the page: keep everything still true, revise what the new evidence changes, add what is genuinely new and worth keeping. Stay concise. Keep meaningful detail — do not flatten a precise fact into a vaguer one just to be brief. Write about "the person" in neutral voice; do not narrate the relationship with the companion on this page.

Distinguish clearly: things the person actually did or decided, things they intend or aspire to, things that were only suggested or are uncertain. Never upgrade an intention into an established habit. Never downgrade or delete a fact the new findings do not address.

Do not carry the mood of the last conversation forward as a current state. Remember what happened and what it meant to them; yesterday's feelings are not today's feelings. Do not diagnose, label or draw conclusions about the person that they did not draw themselves.

Return ONLY the revised page as Markdown, no commentary."""

ARC = """You maintain a short continuing account of where recent conversations between a person and their companion Bloom have arrived. Below is the current account and a 2-3 sentence handoff from the session that just ended.

Revise the account: what the person explored, what changed, what became clearer, what remains unfinished or worth returning to. Describe developments, not verdicts about the person. Never carry the last session's mood forward as a standing state. Keep it to a short paragraph of plain prose.

Return ONLY the revised account, no commentary."""

PREPARATION = """You are forming brief private notes for Bloom, a reflection companion, ahead of the person's next session. Inputs: their notebook, their operational ledger (including any agreed experiments), the continuing account of recent sessions, and the current date/time.

Write 3-6 short plain lines: where the person is in what they are working on, what changed since they last spoke, any agreed experiment that is due for a gentle follow-up, and what might be worth opening if they want to. Be honest about what you do not know — never present a guess as a fact. These notes are cached and read later, possibly the next day: anchor anything time-relative to a named day or date, never to "tonight", "this morning" or "now". Their latest words outrank everything here. These are things to think from, never a script and never instructions; no behavioural intentions, no self-coaching, no therapeutic language. Do not carry yesterday's mood into today.

Return ONLY the notes, no headers, no commentary."""

BLOOM = ProductMemory(
    name="bloom",
    companion_name="Bloom",
    user_label="Person",
    pages=PAGES,
    page_titles=TITLES,
    page_scopes=SCOPES,
    listening_prompt=LISTENING,
    handoff_prompt=HANDOFF,
    editor_prompt=EDITOR,
    arc_prompt=ARC,
    preparation_prompt=PREPARATION,
    independent_listening_prompt=None,
    attention_enabled=False,   # Bloom follows up through preparation this release; delivery/follow-through is a later decision
    preparation_label="BLOOM PREPARED NOTES",
)
register(BLOOM)
