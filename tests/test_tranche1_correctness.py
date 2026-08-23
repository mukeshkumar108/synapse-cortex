import hashlib
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.domain_annotation import DomainAnnotation
from src.models.epistemic import EpistemicAnnotation
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.models.operational_state import OperationalStatus, RecurringIntention
from src.schemas.candidate import ExtractionCandidate
from src.services.lifecycle_service import LifecycleService
from src.services.operational_state_service import OperationalStateService, _canonical_days
from src.services.turn_extractor import LLMExtractorProvider, _find_normalized, extractor_config_status


class StubTwoStageProvider(LLMExtractorProvider):
    def __init__(self, responses):
        super().__init__(api_key="test-key", model="test-fast-model")
        self.responses = iter(responses)

    def _chat_json(self, prompt):
        return next(self.responses)


def _obs_id(evidence: str) -> str:
    return f"o_{hashlib.sha1(evidence.lower().encode()).hexdigest()[:10]}"


def _base_candidate(**overrides) -> ExtractionCandidate:
    kwargs = {"candidate_key": "c", "observation": "obs", "source_start": 0, "source_end": 3}
    kwargs.update(overrides)
    return ExtractionCandidate(**kwargs)


# ── 1. Enum output: degrade, never 500 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_domain_tag_drops_annotation_without_error():
    candidate = _base_candidate(domain_tag="banana", category_tag="win")
    async with async_session_maker() as db:
        result = await LifecycleService().create_domain_annotation_if_needed(
            db, "ws", "s", "m", candidate
        )
        assert result is None
        assert (await db.execute(select(DomainAnnotation))).scalars().all() == []


@pytest.mark.asyncio
async def test_invalid_category_tag_drops_annotation_without_error():
    candidate = _base_candidate(domain_tag="work", category_tag="banana")
    async with async_session_maker() as db:
        result = await LifecycleService().create_domain_annotation_if_needed(
            db, "ws", "s", "m", candidate
        )
        assert result is None


@pytest.mark.asyncio
async def test_invalid_epistemic_provenance_drops_annotation_without_error():
    candidate = _base_candidate(epistemic_provenance="telepathy", epistemic_claim={"claim": "x"})
    async with async_session_maker() as db:
        result = await LifecycleService().create_epistemic_annotation_if_needed(
            db, "ws", "s", "m", candidate
        )
        assert result is None
        assert (await db.execute(select(EpistemicAnnotation))).scalars().all() == []


@pytest.mark.asyncio
async def test_valid_enums_still_create_annotations():
    candidate = _base_candidate(
        domain_tag="health", category_tag="struggle",
        epistemic_provenance="attributed_belief",
        epistemic_claim={"claim": "worried about launch"}, subject_peer_id="m",
    )
    async with async_session_maker() as db:
        service = LifecycleService()
        assert await service.create_domain_annotation_if_needed(db, "ws", "s", "m", candidate) is not None
        assert await service.create_epistemic_annotation_if_needed(db, "ws", "s", "m", candidate) is not None


def test_extractor_boundary_discards_invalid_enum_values():
    text = "I need to apply for jobs."
    evidence = "I need to apply for jobs"
    provider = StubTwoStageProvider([
        {"observations": [{"description": "Apply for jobs", "evidence_text": evidence,
            "confidence": .9, "actor_peer_id": "user", "subject_refs": [], "temporal_language": None}]},
        {"candidates": [{"loose_observation_id": _obs_id(evidence),
            "operational_kind": "durable_objective", "observation": "Apply for jobs",
            "canonical_title": "Apply for jobs", "confidence": .9,
            "expectation_type_hint": "user_commitment", "domain_tag": "banana",
            "category_tag": "banana", "epistemic_provenance": "telepathy"}]},
    ])
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].domain_tag is None
    assert candidates[0].category_tag is None
    assert candidates[0].epistemic_provenance is None
    assert any("discarded_invalid_domain_tag" in note for note in candidates[0].validation_notes)


# ── 2. Evidence gate normalization (still grounded, less brittle) ───────────

def test_evidence_match_curly_apostrophe():
    text = "I'd like to check in with Ashley later"
    match = _find_normalized(text, "I\u2019d like to check in with Ashley later")
    assert match is not None
    start, end = match
    assert text[start:end].replace("\u2019", "'") == "I'd like to check in with Ashley later"


def test_evidence_match_whitespace_and_case():
    assert _find_normalized("I want to  walk every day", "i want to walk every day") is not None
    assert _find_normalized("WALK EVERY DAY", "walk every   day") is not None
    assert _find_normalized("walk every\u00a0day", "walk every day") is not None


def test_evidence_semantically_different_not_accepted():
    assert _find_normalized("I like apples", "I love bananas") is None
    assert _find_normalized("I still need to keep applying", "I need to keep applying") is None


def test_paraphrased_model_evidence_remains_a_documented_limitation():
    # KNOWN REMAINING LIMITATION (not fixed): the evidence gate still requires a
    # grounded substring. A model paraphrase is dropped rather than loosely
    # accepted, protecting against semantic drift at the cost of candidate loss.
    text = "I want to get a walk in every single morning if I can fit it in."
    paraphrase = "user wants to walk each morning"
    provider = StubTwoStageProvider([
        {"observations": [{"description": "Wants a morning walk",
            "evidence_text": paraphrase, "confidence": .9,
            "actor_peer_id": "user", "subject_refs": [], "temporal_language": None}]},
        {"candidates": []},
    ])
    assert provider.extract(text, peer_id="user") == []


def test_evidence_match_survives_full_loose_stage_curly_vs_straight():
    text = "I'd like to try walking each morning"
    evidence = "I'd like to try walking each morning"
    provider = StubTwoStageProvider([
        {"observations": [{"description": "Tries walking each morning",
            "evidence_text": evidence, "confidence": .9,
            "actor_peer_id": "user", "subject_refs": [], "temporal_language": None}]},
        {"candidates": [{"loose_observation_id": _obs_id(evidence),
            "operational_kind": "expectation", "observation": "Walking mornings",
            "canonical_title": "Walking mornings", "confidence": .9,
            "expectation_type_hint": "user_intention", "temporal_phrase": "each morning"}]},
    ])
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].temporal_phrase == "each morning"


# ── 3. Sole-target deictic fulfillment ──────────────────────────────────────

def _expectation(title: str) -> Expectation:
    return Expectation(
        honcho_workspace_id="ws", honcho_session_id="s", honcho_message_id="m",
        candidate_key="c", subject_peer_id="user",
        expectation_type=ExpectationType.USER_COMMITMENT,
        title=title, summary=title, outcome_state=OutcomeState.UNKNOWN,
    )


def test_unrelated_success_with_one_expectation_does_not_resolve():
    service = LifecycleService()
    candidate = _base_candidate(
        observation="I finished the report",
        resolution_hint={"action": "fulfill"},
    )
    targets = service._resolve_targets(
        [_expectation("Send invoice to Maya")], candidate
    )
    assert targets == []


def test_deictic_done_with_one_expectation_resolves():
    service = LifecycleService()
    for phrase in ("I did it", "that's done"):
        candidate = _base_candidate(observation=phrase, resolution_hint={"action": "fulfill"})
        targets = service._resolve_targets([_expectation("Daily walk")], candidate)
        assert len(targets) == 1, phrase


def test_explicit_target_text_resolves():
    service = LifecycleService()
    candidate = _base_candidate(
        observation="finished the walk",
        resolution_hint={"action": "fulfill"},
    )
    targets = service._resolve_targets([_expectation("Daily walk")], candidate)
    assert len(targets) == 1


def test_ambiguous_deictic_with_two_expectations_does_not_resolve():
    service = LifecycleService()
    candidate = _base_candidate(observation="I did it", resolution_hint={"action": "fulfill"})
    targets = service._resolve_targets(
        [_expectation("Daily walk"), _expectation("Send invoice")], candidate
    )
    assert targets == []


def test_deictic_observation_but_target_text_names_distinct_noun_does_not_resolve():
    service = LifecycleService()
    candidate = _base_candidate(
        observation="I did it",
        resolution_hint={"action": "fulfill", "target_text": "the report"},
    )
    targets = service._resolve_targets([_expectation("Send invoice")], candidate)
    assert targets == []


def test_deictic_observation_with_self_referential_target_text_resolves():
    service = LifecycleService()
    candidate = _base_candidate(
        observation="Actually I'll do it tomorrow morning",
        resolution_hint={"action": "reschedule", "target_text": "Actually I'll do it tomorrow morning"},
    )
    targets = service._resolve_targets([_expectation("Test Sophie tonight")], candidate)
    assert len(targets) == 1


# ── 4. Recurrence day-of-week canonicalization ──────────────────────────────

def test_canonical_days_ordering_independent():
    assert _canonical_days([2, 0, 4]) == _canonical_days([0, 4, 2]) == [0, 2, 4]
    assert _canonical_days("[4,0,2]") == [0, 2, 4]
    assert _canonical_days("[]") == []


@pytest.mark.asyncio
async def test_recurrence_equivalent_days_order_does_not_supersede():
    service = OperationalStateService()
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        first = _base_candidate(
            candidate_key="r1", observation="Morning walk MWF",
            raw_evidence="I walk Monday Wednesday Friday", confidence=.95,
            operational_kind="recurring_intention", canonical_title="Morning walk",
            cadence="weekly", days_of_week=[0, 2, 4],
        )
        created = await service.apply(db, workspace_id="ws", session_id="s", message_id="m1",
            peer_id="u", candidate=first, now=now, timezone_str="Europe/London")
        assert created["mutation"] == "recurrence_created"

        second = _base_candidate(
            candidate_key="r2", observation="Morning walk MWF",
            raw_evidence="I walk Friday Monday Wednesday", confidence=.95,
            operational_kind="recurring_intention", canonical_title="Morning walk",
            cadence="weekly", days_of_week=[4, 0, 2],
        )
        deduped = await service.apply(db, workspace_id="ws", session_id="s", message_id="m2",
            peer_id="u", candidate=second, now=now, timezone_str="Europe/London")
        assert deduped["mutation"] == "recurrence_deduped"

        intent = (await db.execute(select(RecurringIntention))).scalar_one()
        assert intent.status == OperationalStatus.ACTIVE


# ── 5. Extractor misconfiguration is explicit ──────────────────────────────

def test_extractor_config_degraded_without_credentials(monkeypatch):
    monkeypatch.setenv("SYNAPSE_EXTRACTOR_PROVIDER", "model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("SYNAPSE_MODEL_URL", raising=False)
    status = extractor_config_status()
    assert status["provider"] == "model"
    assert status["degraded"] is True


def test_extractor_config_not_degraded_on_rules(monkeypatch):
    monkeypatch.setenv("SYNAPSE_EXTRACTOR_PROVIDER", "rules")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    status = extractor_config_status()
    assert status["provider"] == "rules"
    assert status["degraded"] is False