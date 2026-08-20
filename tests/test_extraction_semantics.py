from src.services.turn_extractor import TurnExtractor
from src.services.expectation_shaper import ExpectationShaper
from src.models.expectation import ExpectationType

extractor = TurnExtractor()
shaper = ExpectationShaper()


def test_quoted_speech_rejected():
    text = 'She said "I\'ll call tomorrow"'
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    candidate = candidates[0]
    assert candidate.is_quoted is True
    shaped = shaper.shape_expectation(candidate, subject_peer_id="mukesh")
    assert shaped is None  # Must NOT create positive user expectation


def test_negation_rejected():
    text = "I'm not going to call him tomorrow."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    candidate = candidates[0]
    assert candidate.is_negated is True
    shaped = shaper.shape_expectation(candidate, subject_peer_id="mukesh")
    assert shaped is None


def test_uncertainty_rejected():
    text = "I might test it tonight."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    candidate = candidates[0]
    assert candidate.is_hypothetical is True
    shaped = shaper.shape_expectation(candidate, subject_peer_id="mukesh")
    assert shaped is None


def test_hypothetical_rejected():
    text = "If I test it tonight, I'll know."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    candidate = candidates[0]
    assert candidate.is_hypothetical is True
    shaped = shaper.shape_expectation(candidate, subject_peer_id="mukesh")
    assert shaped is None


def test_excitement_rejected():
    text = "I'm really excited about Sophie!"
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) == 0


def test_reported_speech_external_dependency():
    text = "James said he'll send it tomorrow."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    candidate = candidates[0]
    assert candidate.is_reported_speech is True
    shaped = shaper.shape_expectation(candidate, subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
    assert shaped["subject_peer_id"] == "James"


def test_planned_event():
    text = "I have a doctor's appointment tomorrow."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.PLANNED_EVENT


def test_external_dependency_waiting():
    text = "Waiting for Ashley to respond tomorrow."
    candidates = extractor.extract_candidates(text, peer_id="mukesh")
    assert len(candidates) > 0
    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
