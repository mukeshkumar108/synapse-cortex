"""The scene pass: exchanges are buffered and the picture is rewritten only when enough has accrued to leave the raw tail (or on a significant
moment); the previous picture goes in with the new messages; an empty or failed answer never loses the exchanges or the old picture."""
import pytest

from src.db import async_session_maker
from src.services import scene_narrative

N = {"user": "Kai", "assistant": "Elena"}


class _Adapter:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    async def generate_structured(self, *, system, prompt, **_):
        self.prompts.append(prompt)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def ex(u, a):
    return [{"speaker": "user", "text": u}, {"speaker": "assistant", "text": a}]


@pytest.mark.asyncio
async def test_batches_then_rewrites_from_previous_picture():
    ad = _Adapter({"scene": "Kai asked about the trip; Elena has not answered."}, {"scene": "Elena answered: she wants to go."})
    async with async_session_maker() as db:
        r = await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names=N, messages=ex("are we going?", "mm"))
        assert r["status"] == "buffered" and not ad.prompts                      # one exchange: no model call
        r = await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names=N, messages=ex("well?", "yes I want to go"))
        assert r["text"].startswith("Kai asked") and "Kai: are we going?" in ad.prompts[0] and "(none yet)" in ad.prompts[0]   # both buffered exchanges included
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names=N, messages=ex("ok", "ok"), force=True)   # significant moment: now
        assert "Elena has not answered" in ad.prompts[1]
        assert (await scene_narrative.current(db, "w", "s")).text == "Elena answered: she wants to go."


@pytest.mark.asyncio
async def test_failure_and_empty_answer_keep_exchanges_and_old_picture():
    ad = _Adapter({"scene": "first picture"}, RuntimeError("boom"), {"scene": ""}, {"scene": "second picture"})
    async with async_session_maker() as db:
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="t", names=N, messages=ex("a", "b"), force=True)
        with pytest.raises(RuntimeError):
            await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="t", names=N, messages=ex("c", "d"), force=True)
        assert await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="t", names=N, messages=ex("e", "f"), force=True) is None
        assert (await scene_narrative.current(db, "w", "t")).text == "first picture"
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="t", names=N, messages=ex("g", "h"), force=True)
        assert "c" in ad.prompts[3] and "Elena: h" in ad.prompts[3] and "first picture" in ad.prompts[3]    # exchanges kept across the failure
