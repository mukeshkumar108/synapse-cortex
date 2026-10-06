"""The fast scene pass: the previous picture goes in with the last messages, the new picture replaces it (one row per session), and an empty or
failed model answer leaves the stored picture alone."""
import pytest

from src.db import async_session_maker
from src.services import scene_narrative


class _Adapter:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    async def generate_structured(self, *, system, prompt, **_):
        self.prompts.append(prompt)
        return self.answers.pop(0)


@pytest.mark.asyncio
async def test_picture_is_rewritten_from_previous_and_replaced():
    msgs = lambda *t: [{"speaker": s, "text": x} for s, x in t]
    ad = _Adapter({"scene": "Kai asked about the trip; Elena has not answered."}, {"scene": "Elena answered: she wants to go."}, {"scene": ""})
    async with async_session_maker() as db:
        first = await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names={"user": "Kai", "assistant": "Elena"},
                                              messages=msgs(("user", "are we going?"), ("assistant", "mm")))
        assert first["text"].startswith("Kai asked")
        assert "(none yet)" in ad.prompts[0] and "Kai: are we going?" in ad.prompts[0]
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names={"user": "Kai", "assistant": "Elena"},
                                      messages=msgs(("user", "well?"), ("assistant", "yes, I want to go")))
        assert "Elena has not answered" in ad.prompts[1]            # previous picture carried in
        assert (await scene_narrative.current(db, "w", "s")).text == "Elena answered: she wants to go."
        assert await scene_narrative.narrate(db, adapter=ad, workspace_id="w", session_id="s", names={}, messages=msgs(("user", "hi"))) is None
        assert (await scene_narrative.current(db, "w", "s")).text == "Elena answered: she wants to go."   # empty answer kept the old picture
