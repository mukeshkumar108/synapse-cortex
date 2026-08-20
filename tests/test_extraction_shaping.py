from src.services.turn_extractor import TurnExtractor
from src.services.expectation_shaper import ExpectationShaper
from src.models.expectation import ExpectationType

extractor = TurnExtractor()
shaper = ExpectationShaper()


def test_extraction_and_shaping_intention():
    text = "I'm going to test the Sophie initiative changes tonight."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) > 0

    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.USER_INTENTION
    assert shaped["title"] == "Test the Sophie initiative changes"
    assert shaped["raw_temporal_phrase"] == "tonight"


def test_extraction_and_shaping_commitment():
    text = "I have to submit this by 5pm Friday."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) > 0

    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.USER_COMMITMENT
    assert shaped["title"] == "Submit this"
    assert shaped["raw_temporal_phrase"] == "by 5pm friday"


def test_rejection_of_excitement_statement():
    text = "I'm really excited about Sophie."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) == 0  # High-precision filtering: rejected early


def test_rejection_of_hypothetical_action():
    text = "If I had time I would test it."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) == 0


def test_extraction_and_shaping_followup_invitation():
    text = "Remind me to ask Ashley tomorrow."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) > 0

    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.FOLLOWUP_INVITATION
    assert shaped["raw_temporal_phrase"] == "tomorrow"


def test_extraction_and_shaping_external_dependency():
    text = "James said he'll send it tomorrow."
    candidates = extractor.extract_candidates(text)
    assert len(candidates) > 0

    shaped = shaper.shape_expectation(candidates[0], subject_peer_id="mukesh")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
    assert shaped["raw_temporal_phrase"] == "tomorrow"


def test_quoted_or_negated_intent_is_not_extracted():
    cands1 = extractor.extract_candidates('Sophie said "I will call tomorrow."')
    if cands1:
        assert shaper.shape_expectation(cands1[0], "mukesh") is None
    
    cands2 = extractor.extract_candidates("I don't think I'll call tomorrow.")
    if cands2:
        assert shaper.shape_expectation(cands2[0], "mukesh") is None


def test_multiple_expectations_retain_distinct_evidence():
    candidates = extractor.extract_candidates(
        "I'll call James tomorrow; I will submit the report Friday."
    )

    assert len(candidates) == 2
    assert [candidate.temporal_phrase for candidate in candidates] == [
        "tomorrow",
        "friday",
    ]
    assert candidates[0].candidate_key != candidates[1].candidate_key
