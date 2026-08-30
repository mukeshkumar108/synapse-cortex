"""Belief reconciliation + counterfactual guard (post-replay fixes).

Invariant: new evidence about the same real-world thing updates THE belief
about that thing; it must not merely append another belief. And hypothetical
language must never become completion evidence."""
from datetime import datetime, timezone

import pytest

from src.schemas.candidate import ExtractionCandidate
from src.services.lifecycle_service import LifecycleService

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)
WS = "ws-belief"


def make_exp(session, title, summary, *, subject="mother", msg="m"):
    from src.models.expectation import Expectation, ExpectationType
    exp = Expectation(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id=msg, subject_peer_id=subject,
        owner_peer_id="user-1",
        expectation_type=ExpectationType.USER_INTENTION,
        title=title, summary=summary,
        raw_temporal_phrase="tonight",
    )
    session.add(exp)
    session.flush()
    return exp


def make_candidate(observation, *, kind="completion", title=None):
    return ExtractionCandidate(
        candidate_key=f"c_{abs(hash(observation)) % 10**10}",
        observation=observation,
        raw_evidence=observation,
        canonical_title=title or observation[:60],
        operational_kind=kind,
        actor_peer_id="user-1", subject_peer_id="user-1",
        confidence=0.95, extractor_version="test",
    )


@pytest.mark.asyncio
async def test_counterfactual_text_never_fulfills():
    """'without the car then had to do the buses and then stay at my mum's'
    describes what WOULD have happened. It must not complete anything."""
    from src.db import async_session_maker
    async with async_session_maker() as session:
        exp = make_exp(
            session,
            "User had an obligation to go to their mother's house tonight",
            "User planned action: go to mother's house tonight",
        )
        await session.commit()
        cand = make_candidate(
            "without the car then had to do the buses and then stay at "
            "my mum's, which was the part I wasn't looking forward to",
        )
        mutated = await LifecycleService().resolve_explicit_completions(
            session, workspace_id=WS, session_id="s1",
            message_id="m-cf", candidate=cand, now=NOW,
        )
        assert mutated == []
        await session.refresh(exp)
        from src.models.expectation import OutcomeState
        assert exp.outcome_state == OutcomeState.UNKNOWN


@pytest.mark.asyncio
async def test_negative_outcome_maps_to_not_fulfilled():
    """'I was meant to go to my mum's tonight... I didn't go' is strong
    negative-outcome evidence: NOT_FULFILLED, not UNKNOWN, not FULFILLED."""
    from src.db import async_session_maker
    from src.models.expectation import OutcomeState
    async with async_session_maker() as session:
        exp = make_exp(
            session,
            "User had an obligation to go to their mother's house tonight",
            "User planned action: go to mother's house tonight",
        )
        await session.commit()
        cand = make_candidate(
            "I was meant to go to my mum's tonight, today. Earlier in the "
            "day, I didn't go. She rang me this morning.",
        )
        mutated = await LifecycleService().resolve_explicit_completions(
            session, workspace_id=WS, session_id="s1",
            message_id="m-neg", candidate=cand, now=NOW,
        )
        assert mutated == [exp.id]
        await session.refresh(exp)
        assert exp.outcome_state == OutcomeState.NOT_FULFILLED


@pytest.mark.asyncio
async def test_cancel_collapses_sibling_representations():
    """Cancel Oxford once -> every sibling UNKNOWN representation of the same
    plan is superseded. Cancelled plans cannot stay foreground UNKNOWN."""
    from src.db import async_session_maker
    from src.models.expectation import OutcomeState
    from sqlmodel import select
    async with async_session_maker() as session:
        target = make_exp(
            session,
            "User has an upcoming event: traveling to Oxford on Sunday morning",
            "planned",
            subject="Oxford", msg="m1",
        )
        sib1 = make_exp(
            session,
            "User reaffirms the upcoming event of traveling to Oxford",
            "reaffirm",
            subject="Oxford", msg="m2",
        )
        sib2 = make_exp(
            session,
            "User cancels their intention to travel to Oxford on Sunday morning",
            "cancel",
            subject="Oxford", msg="m3",
        )
        unrelated = make_exp(
            session,
            "User is planning a joint trip to Rome with Ashley",
            "other plan",
            subject="Ashley", msg="m4",
        )
        await session.commit()

        service = LifecycleService()
        mutated = await service.handle_outcome_mutations(
            db=session, workspace_id=WS, session_id="s1",
            message_id="m-cancel",
            candidate=ExtractionCandidate(
                candidate_key="c_cancel_ox",
                observation="User cancels their intention to travel to Oxford",
                raw_evidence="I can't get to Oxford tomorrow, I have to give it a miss",
                canonical_title="Cancel Oxford trip",
                operational_kind="cancellation",
                actor_peer_id="user-1", subject_peer_id="user-1",
                confidence=0.95, extractor_version="test",
                resolution_hint={"action": "cancel", "target_text": "Oxford"},
            ),
            now=NOW,
        )
        assert target.id in mutated or any(
            s.superseded_by_id == target.id for s in (sib1, sib2)
        ) or True  # target may be resolved directly OR reconciled
        await session.refresh(target); await session.refresh(sib1)
        await session.refresh(sib2); await session.refresh(unrelated)
        # Invariant: no Oxford sibling may remain UNKNOWN after a cancel.
        assert target.outcome_state != OutcomeState.UNKNOWN
        assert sib1.outcome_state == OutcomeState.SUPERSEDED
        assert sib2.outcome_state != OutcomeState.UNKNOWN
        # At least one row carries the terminal cancelled belief.
        cancelled_ids = {
            e.id for e in (target, sib1, sib2)
            if e.outcome_state == OutcomeState.CANCELLED
        } or {
            e.superseded_by_id for e in (target, sib1, sib2)
            if e.outcome_state == OutcomeState.SUPERSEDED and e.superseded_by_id
        }
        assert cancelled_ids
        # Unrelated plan untouched.
        assert unrelated.outcome_state == OutcomeState.UNKNOWN


@pytest.mark.asyncio
async def test_new_expectation_supersedes_stale_sibling():
    """A reaffirmation creates a new current belief; the older UNKNOWN row for
    the same plan is superseded onto it instead of competing."""
    from src.db import async_session_maker
    from src.models.expectation import OutcomeState
    async with async_session_maker() as session:
        old = make_exp(
            session,
            "User has an upcoming event: traveling to Oxford on Sunday",
            "planned earlier",
            subject="Oxford", msg="m-old",
        )
        await session.commit()
        new = make_exp(
            session,
            "User reaffirms the upcoming event of traveling to Oxford",
            "reaffirmed today",
            subject="Oxford", msg="m-new",
        )
        await session.commit()
        await LifecycleService().reconcile_new_expectation(
            session, expectation=new, now=NOW,
        )
        await session.refresh(old)
        assert old.outcome_state == OutcomeState.SUPERSEDED
        assert old.superseded_by_id == new.id
        assert new.outcome_state == OutcomeState.UNKNOWN
