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


@pytest.mark.asyncio
async def test_standing_requests_are_stored_apart_from_the_prose_and_survive_a_pass_that_omits_them():
    ad = _Adapter({"scene": "Planning a busy week.", "standing_requests": ["Do not call him babe; Mukesh is fine."]},
                  {"scene": "Deck first, then Priya."},                       # the model forgot the field: what was held must stay
                  {"scene": "Deck done.", "standing_requests": ["Do not call him babe; Mukesh is fine.", "Fewer questions at the end of replies."]})
    async with async_session_maker() as db:
        first = await scene_narrative.narrate(db, adapter=ad, workspace_id="w-req", owner="o-req", session_id="s-req", messages=ex("please don't call me babe", "ok") + ex("busy week", "got it"), names=N)
        assert first["standing_requests"] == ["Do not call him babe; Mukesh is fine."] and "babe" not in first["text"]
        second = await scene_narrative.narrate(db, adapter=ad, workspace_id="w-req", owner="o-req", session_id="s-req", messages=ex("deck first?", "yes") + ex("ok", "ok"), names=N)
        assert second["standing_requests"] == ["Do not call him babe; Mukesh is fine."]
        assert "PREVIOUS STANDING REQUESTS:\n- Do not call him babe" in ad.prompts[1]
        third = await scene_narrative.narrate(db, adapter=ad, workspace_id="w-req", owner="o-req", session_id="s-req", messages=ex("fewer questions please", "sure") + ex("done", "nice"), names=N)
        assert len(third["standing_requests"]) == 2


@pytest.mark.asyncio
async def test_an_explicit_empty_list_is_how_a_withdrawn_request_leaves():
    ad = _Adapter({"scene": "a", "standing_requests": ["No pet names."]}, {"scene": "b", "standing_requests": []})
    async with async_session_maker() as db:
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w-req2", owner="o-req2", session_id="s-req2", messages=ex("no pet names", "ok") + ex("x", "y"), names=N)
        out = await scene_narrative.narrate(db, adapter=ad, workspace_id="w-req2", owner="o-req2", session_id="s-req2", messages=ex("actually pet names are fine", "ok") + ex("x", "y"), names=N)
        assert out["standing_requests"] == []


@pytest.mark.asyncio
async def test_standing_requests_are_owned_by_the_world_not_the_conversation_and_cross_chats_for_the_same_owner():
    from src.services import standing_requests as sr
    ad = _Adapter({"scene": "chat one", "standing_requests": ["Do not call him babe."]}, {"scene": "chat two", "standing_requests": ["Do not call him babe."]})
    async with async_session_maker() as db:
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w-x", owner="owner-1", session_id="chat_a", messages=ex("don't call me babe", "ok") + ex("x", "y"), names=N)
        assert await sr.active(db, "w-x", "owner-1") == ["Do not call him babe."]
        assert await sr.active(db, "w-x", "owner-2") == []                       # another world never sees it
        await scene_narrative.narrate(db, adapter=ad, workspace_id="w-x", owner="owner-1", session_id="chat_b", messages=ex("hi", "hello") + ex("x", "y"), names=N)
        assert "PREVIOUS STANDING REQUESTS:\n- Do not call him babe." in ad.prompts[1]       # a different chat of the same owner starts from the durable list


@pytest.mark.asyncio
async def test_sync_creates_withdraws_and_reopens_with_history_kept():
    from src.services import standing_requests as sr
    async with async_session_maker() as db:
        assert await sr.sync(db, "w-s", "o", ["No pet names.", "Fewer questions."], source="interpreter") == {"created": 2, "withdrawn": 0}
        assert await sr.sync(db, "w-s", "o", ["no pet names"], source="interpreter") == {"created": 0, "withdrawn": 1}      # same request recognised across wording/case
        assert await sr.active(db, "w-s", "o") == ["No pet names."]
        assert (await sr.sync(db, "w-s", "o", ["No pet names.", "Fewer questions."], source="scene_pass"))["created"] == 1   # reopened, not duplicated


def test_the_picture_keeps_concrete_scene_events_and_marks_a_characters_own_claims_as_claims():
    from src.services import scene_narrative
    assert "KEEP, as short factual clauses" in scene_narrative.SYSTEM and "described as what they SAID" in scene_narrative.SYSTEM


def test_anchors_are_append_only_deduped_closable_and_the_bond_peaks_outlast_detail():
    from datetime import datetime
    from src.services.scene_narrative import merge_anchors, MAX_ANCHORS, MAX_NEW_PER_PASS
    now = datetime(2026, 10, 8, 17, 0)
    a = merge_anchors([], [{"kind": "milestone", "text": "Kai got the VP role, base salary 280k; they celebrated"}, {"kind": "open_loop", "text": "Isa has not told Kai about Marco"},
                          {"kind": "event", "text": "Kai got the VP role with a 280k base salary and they celebrated it"}], None, now)
    assert [x["id"] for x in a] == ["a1", "a2"] and a[1]["status"] == "open"             # the reworded duplicate was not added
    b = merge_anchors(a, [{"kind": "external", "text": "Marco sent explicit photos and parked outside; she refused and blocked him"}], ["a2"], now)
    assert b[0]["text"] == a[0]["text"] and b[1]["status"] == "closed" and b[2]["id"] == "a3"
    assert len(merge_anchors([], [{"kind": "event", "text": f"distinct fact number {i} about thing{i}"} for i in range(9)], None, now)) == MAX_NEW_PER_PASS
    state = b
    for i in range(40):                                   # a long scene of ordinary detail
        state = merge_anchors(state, [{"kind": "event", "text": f"detail {i} alpha{i} beta{i} gamma{i}"}], None, now)
    assert len(state) <= MAX_ANCHORS and any("280k" in x["text"] for x in state), "the promotion must outlast hours of detail"
    assert merge_anchors(b, [{"kind": "claim", "text": "Isa said she kissed Marco last week"}], None, now)[-1]["status"] == "claimed"


@pytest.mark.asyncio
async def test_related_questions_resolve_against_one_private_event_and_are_never_authored_twice():
    ad = _Adapter({"scene": "Kai wants to know what happened at Lila's.", "new_anchors": [{"kind": "open_loop", "text": "Kai asked what happened at Lila's party and has not been told"},
                                                                                    {"kind": "open_loop", "text": "Kai asked whether Arabella kissed anyone at the party"}]},
                  {"action": "new", "topic": "Lila's party", "truth": "At Lila's party last June Arabella left early with Tom, her ex, and spent the night at his flat; she has never told Kai because Tom was still in her life then."},
                  {"action": "extend", "target_id": "a3", "truth": "They kissed once in the car before she went up; nothing more happened."},
                  {"action": "new", "topic": "the kiss", "truth": "She actually slept with Tom, a second, different story."},
                  {"action": "new", "topic": "her salary", "truth": "She earns 90k, unrelated hidden thing."})
    async with async_session_maker() as db:
        pic = await scene_narrative.narrate(db, adapter=ad, workspace_id="w-t", session_id="s-t", names=N, messages=ex("tell me about lila's", "I can't"), force=True)
        loops = [a for a in pic["anchors"] if a["kind"] == "open_loop"]
        kw = dict(adapter=ad, workspace_id="w-t", session_id="s-t", picture=pic["text"], recent=ex("tell me", "I can't"), character="Arabella", constitution="", names=N)
        first = await scene_narrative.author_truth(db, question_anchor_id=loops[0]["id"], question="what happened at Lila's?", **kw)
        truths = [a for a in first["anchors"] if a["kind"] == "private_truth"]
        assert first["needed"] and len(truths) == 1 and "Tom" in truths[0]["text"]
        second = await scene_narrative.author_truth(db, question_anchor_id=loops[1]["id"], question="did you kiss him?", **kw)
        truths = [a for a in second["anchors"] if a["kind"] == "private_truth"]
        assert len(truths) == 1 and second["extended"] == truths[0]["id"] and "Tom" in truths[0]["text"] and "kissed once in the car" in truths[0]["text"]      # one event, grown
        assert "Arabella left early with Tom" in ad.prompts[2] and "EXISTING PRIVATE TRUTHS" in ad.prompts[2]                                               # the author sees the event it must stay inside
        again = await scene_narrative.author_truth(db, question_anchor_id=loops[0]["id"], question="what happened at Lila's?", **kw)
        assert again["needed"] is False and again["reason"] == "already_authored" and len(ad.prompts) == 3
        pic2 = await scene_narrative.narrate(db, adapter=_Adapter({"scene": "x", "new_anchors": [{"kind": "open_loop", "text": "Kai asked whether she slept with Tom at the party"}]}), workspace_id="w-t", session_id="s-t", names=N, messages=ex("did you sleep with Tom at the party?", "..."), force=True)
        third = next(a for a in pic2["anchors"] if a["kind"] == "open_loop" and "slept" in a["text"])
        forked = await scene_narrative.author_truth(db, question_anchor_id=third["id"], question="did you sleep with Tom at the party?", **kw)
        truths = [a for a in forked["anchors"] if a["kind"] == "private_truth"]
        assert len(truths) == 1 and "second, different story" in truths[0]["text"]          # the model said "new"; the question shares the event's words, so it is the same event, extended
        assert scene_narrative.EVICTION_RANK["private_truth"] > max(v for k, v in scene_narrative.EVICTION_RANK.items() if k != "private_truth")
