"""The continuing account is read on later days. It carries events with their day, and never carries a question as a debt (Monday 2 Nov: 'Sophie asked ... but Mukesh didn't answer either question'
became 'I have questions and you never gave me answers' on the next sitting, and a Friday lunch read as today)."""
import pytest

from src.services import memory_pipeline
from src.services.memory_pipeline import tidy_arc

BAD = ("Mukesh met Josh at Ichimaru Udon on Petty Cury in Cambridge for lunch, then they walked and took photos. "
       "Sophie asked whether the skincare talk came up naturally and whether Josh is still as meticulous about his one-SKU project, but Mukesh didn't answer either question.")


def test_a_question_only_sophie_raised_and_its_non_answer_is_dropped():
    assert tidy_arc(BAD) == "Mukesh met Josh at Ichimaru Udon on Petty Cury in Cambridge for lunch, then they walked and took photos."


@pytest.mark.parametrize("text,kept", [
    ("Mukesh booked the dentist for Thursday, but hasn't replied about the weekend.", "Mukesh booked the dentist for Thursday."),
    ("Mukesh said the render ships Thursday; he has not answered whether Ashley is helping.", "Mukesh said the render ships Thursday."),
    ("Mukesh planned the retreat. It went unanswered.", "Mukesh planned the retreat."),                                # a sentence that is only the non-answer goes
])
def test_a_non_answer_clause_is_cut_and_the_fact_beside_it_kept(text, kept):
    out = tidy_arc(text)
    assert "hasn't replied" not in out and "has not answered" not in out and "unanswered" not in out
    assert kept.split(".")[0] in out


def test_ordinary_text_is_untouched():
    t = "On Friday 30 October Mukesh had lunch with Josh at Ichimaru. Josh is working on a one-SKU Korean skincare product. Mukesh is training for a half marathon."
    assert tidy_arc(t) == t


def test_the_writer_is_told_to_date_events_and_to_leave_sophies_questions_out():
    p = memory_pipeline.ARC_UPDATE_PROMPT
    assert "read on LATER days" in p and "On Friday 30 October" in p
    assert 'NEVER write that someone "didn\'t answer"' in p and "left out of the account entirely" in p


def test_the_session_day_is_named_for_the_writer():
    assert memory_pipeline._day_name("2026-10-30") == "Friday 30 October 2026"
