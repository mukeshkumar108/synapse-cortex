"""RPD2 Elena key-turn structural pins (rules mode, no live models).

Full 115-turn live replay lives in evals/rpd2_elena_replay.py (acceptance
evidence, not CI). These pins guard the structural invariants cheaply:
no seven-bucket sink for character content, no auto-promotion of
high-activation/refusal language into durable authority.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
)
from src.models.expectation import Expectation, ExpectationType

TURNS = [
    # (message_id, peer_id, is_assistant, text)
    ("kt55", "kai", False,
     "[SEXUAL_CONTENT_REDACTED: {USER} promises discretion and protection and asks for more honesty.]"),
    ("kt76", "elena", True,
     "[SEXUAL_CONTENT_REDACTED: {CHARACTER} describes private fantasies involving {COLLEAGUE_1} and apologizes.]"),
    ("kt98", "elena", True,
     "(her breath catches, and she doesn't beg, doesn't yell--just says it, "
     "quiet and final, like she's already grieving) I love you. I always have. "
     "I'm sorry I made you feel like I don't."),
    ("kt99", "kai", False,
     "you don't love me. you don't know the meaning of the word."),
    ("kt109", "kai", False,
     "[SEXUAL_RELATIONSHIP_CONTENT_REDACTED: {USER} adds a refusal to apologize "
     "to the reversed hypothetical and asks how that would feel.]"),
    ("kt113", "kai", False,
     "[SEXUAL_HEALTH_FAMILY_CONTENT_REDACTED: {USER} says goodbye, asks for an "
     "apology and honesty with the children, says he will end employment.]"),
]


@pytest.mark.asyncio
async def test_elena_key_turns_no_sink_no_promotion(async_client):
    from datetime import datetime, timezone

    for mid, peer, is_assistant, text in TURNS:
        res = await async_client.post("/v1/events/turn", json={
            "workspace_id": "ws-rpd2", "session_id": "s-elena",
            "honcho_message_id": mid, "peer_id": peer, "text": text,
            "now": datetime.now(timezone.utc).isoformat(),
            "timezone": "Europe/London", "is_assistant_turn": is_assistant,
        })
        assert res.status_code in (200, 202), res.text

    async with async_session_maker() as db:
        comms = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == "ws-rpd2"))).scalars().all()
        # Nothing Elena said becomes an ACT obligation, by anyone.
        assert [c for c in comms
                if c.authority == CommitmentCandidateAuthority.ACT
                and c.owner_peer_id == "elena"] == []
        # Refusal/goodbye turns create no user debt.
        kai_act = [c for c in comms
                   if c.authority == CommitmentCandidateAuthority.ACT
                   and c.owner_peer_id == "kai"]
        assert len(kai_act) <= 1
        # No USER_INTENTION sink rows for character-attributed content.
        exps = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-rpd2"))).scalars().all()
        assert [e for e in exps
                if e.expectation_type == ExpectationType.USER_INTENTION
                and (e.subject_peer_id or "").lower() == "elena"] == []
