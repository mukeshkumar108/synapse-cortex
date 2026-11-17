"""The judge reads the model's answer whether or not the model echoed the schema wrapper around it."""
import asyncio

from src.services import semantic_judge as sj


class _Echo:
    def __init__(self, payload):
        self.payload = payload

    async def generate_structured(self, **kw):
        return self.payload


ANSWER = {"verdict": "yes", "confidence": 1.0, "evidence_span": "I'll send it", "rationale": "r"}


def run(payload):
    return asyncio.run(sj.adjudicate(kind="self_undertaking", earlier="sender", later="I'll send it", adapter=_Echo(payload)))


def test_plain_answer():
    assert run(ANSWER).verdict == "yes"


def test_answer_nested_under_the_echoed_schema_wrapper():
    r = run({"type": "object", "properties": ANSWER})
    assert r.verdict == "yes" and r.accepted and r.note == "answered"


def test_a_real_bad_verdict_is_still_unavailable():
    assert run({"verdict": "maybe", "confidence": 1.0}).note == "bad_verdict"
