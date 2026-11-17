"""A stand-in for the semantic judge's `self_undertaking` verdict in tests that are not about the judge: the sender owns the action unless the evidence is one of the listed other-person lines.
(The real verdicts are replayed against labelled texts on the VPS; see the commit that removed the first-person marker.)"""
import pytest

from src.services import semantic_judge


class SenderOwnsIt:
    def __init__(self, others=()):
        self.others = tuple(others)

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        later = prompt.split("LATER:\n", 1)[1].split("\nCONTEXT:")[0].split("\nRules:")[0].strip() if "LATER:\n" in prompt else ""
        no = later.startswith(self.others) or "Who owns the action" not in prompt         # only the self_undertaking question is answered; any other judge question gets "no", as with no judge
        return {"verdict": "no" if no else "yes", "confidence": 0.9, "evidence_span": "" if no else later[:40], "rationale": "test double"}


def install(monkeypatch, others=()):
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: SenderOwnsIt(others))
