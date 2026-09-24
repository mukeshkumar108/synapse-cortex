"""Step 3 Slice A/B1: classification sink + supersession churn (deterministic).

Replay evidence (take-2): 52 expectations, nearly all USER_INTENTION with
"User planned action:" summaries; FIFO supersession retired rows on mere
topical resemblance. These tests pin the writer-side fixes:
- event-kind and untyped candidates are rejected, never defaulted;
- pseudo-temporal markers (present/current/ongoing) do not ground intentions;
- summaries are type-specific;
- formation (explicit/inferred) passes through for later dreaming authors;
- supersession requires same-plan (shared subject or >=0.6 content overlap),
  so churn titles ("reflecting/engaging/seeking…") no longer retire rows.
"""
import pytest

from src.models.expectation import ExpectationType
from src.schemas.candidate import ExtractionCandidate
from src.services.expectation_shaper import ExpectationShaper
from src.services.lifecycle_service import LifecycleService

shaper = ExpectationShaper()


def make_cand(**kw):
    base = dict(
        candidate_key="c_test",
        observation="User will do something tomorrow",
        raw_evidence="User will do something tomorrow",
        canonical_title="Do something",
        operational_kind="expectation",
        expectation_type_hint="user_intention",
        temporal_phrase="tomorrow",
        actor_peer_id="user-1",
        confidence=0.95,
        extractor_version="test",
    )
    base.update(kw)
    return ExtractionCandidate(**base)


def test_event_kind_never_becomes_expectation():
    cand = make_cand(operational_kind="event", expectation_type_hint="planned_event",
                     observation="Father died less than a year after diagnosis")
    assert shaper.shape_expectation(cand, "user-1") is None


def test_untyped_expectation_rejected_not_defaulted():
    cand = make_cand(expectation_type_hint=None)
    assert shaper.shape_expectation(cand, "user-1") is None


def test_pseudo_temporal_does_not_ground_intention():
    for marker in ("present", "current", "ongoing", "(present)", "recent", "past"):
        cand = make_cand(temporal_phrase=marker)
        assert shaper.shape_expectation(cand, "user-1") is None, marker


def test_health_state_as_planned_event_rejected():
    cand = make_cand(
        operational_kind="expectation", expectation_type_hint="planned_event",
        observation="User is experiencing a recurring neck ache",
        temporal_phrase="recurring", confidence=0.9)
    assert shaper.shape_expectation(cand, "user-1") is None


def test_type_specific_summaries():
    comm = make_cand(expectation_type_hint="user_commitment", temporal_phrase="tomorrow")
    shaped = shaper.shape_expectation(comm, "user-1")
    assert shaped is not None and shaped["summary"].startswith("User committed:")
    assert "User planned action" not in shaped["summary"]
    fu = make_cand(expectation_type_hint="followup_invitation", temporal_phrase="tomorrow")
    assert shaper.shape_expectation(fu, "user-1")["summary"].startswith("Follow-up invited:")


def test_formation_defaults_explicit_and_preserves_inferred():
    assert shaper.shape_expectation(make_cand(), "user-1")["formation"] == "explicit"
    inferred = make_cand(formation="inferred")
    assert shaper.shape_expectation(inferred, "user-1")["formation"] == "inferred"


def test_durable_objective_without_temporal_still_shaped():
    cand = make_cand(operational_kind="durable_objective", temporal_phrase=None)
    assert shaper.shape_expectation(cand, "user-1") is not None


@pytest.mark.asyncio
async def test_same_plan_supersedes():
    from src.db import async_session_maker
    from src.models.expectation import Expectation
    async with async_session_maker() as db:
        old = Expectation(
            honcho_workspace_id="ws-sup", honcho_session_id="s1", honcho_message_id="m1",
            owner_peer_id="user-1", subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Go to mother's house tonight", summary="x")
        new = Expectation(
            honcho_workspace_id="ws-sup", honcho_session_id="s1", honcho_message_id="m2",
            owner_peer_id="user-1", subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Go to mother's house tomorrow", summary="y")
        db.add_all([old, new])
        await db.commit()
        from datetime import datetime, timezone
        changed = await LifecycleService().reconcile_new_expectation(
            db, expectation=new, now=datetime(2026, 9, 24, tzinfo=timezone.utc))
        assert changed == [old.id]
        await db.refresh(old)
        from src.models.expectation import OutcomeState
        assert old.outcome_state == OutcomeState.SUPERSEDED
        assert old.superseded_by_id == new.id


@pytest.mark.asyncio
async def test_churn_titles_do_not_supersede():
    """Replay regression: 'reflecting/engaging/seeking…' rows must not retire
    each other on shared generic verbs."""
    from src.db import async_session_maker
    from src.models.expectation import Expectation, OutcomeState
    async with async_session_maker() as db:
        old = Expectation(
            honcho_workspace_id="ws-churn", honcho_session_id="s1", honcho_message_id="m1",
            owner_peer_id="user-1", subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="User is reflecting on a hypothetical scenario involving a relationship",
            summary="x")
        new = Expectation(
            honcho_workspace_id="ws-churn", honcho_session_id="s1", honcho_message_id="m2",
            owner_peer_id="user-1", subject_peer_id="user-1",
            expectation_type=ExpectationType.USER_INTENTION,
            title="User is reflecting on the concept of love and its implications",
            summary="y")
        db.add_all([old, new])
        await db.commit()
        from datetime import datetime, timezone
        changed = await LifecycleService().reconcile_new_expectation(
            db, expectation=new, now=datetime(2026, 9, 24, tzinfo=timezone.utc))
        assert changed == []
        await db.refresh(old)
        assert old.outcome_state == OutcomeState.UNKNOWN
