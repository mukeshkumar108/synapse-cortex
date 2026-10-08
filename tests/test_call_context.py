import asyncio

from src import call_context


def test_header_is_parsed_defensively():
    assert call_context.parse_header('{"product":"sophie-nextjs","turn_id":"t1","junk":"x"}') == {"product": "sophie-nextjs", "turn_id": "t1"}
    assert call_context.parse_header("not json") == {} and call_context.parse_header(None) == {}


def test_record_uses_request_context_or_marks_self_scheduled(monkeypatch):
    rows = []

    async def fake_write(row):
        rows.append(row)
    monkeypatch.setattr(call_context, "_write", fake_write)

    async def scenario():
        call_context.record(module="executive", provider="openrouter", model="m", usage={"prompt_tokens": 5, "completion_tokens": 2}, cost=0.001)
        token = call_context.CTX.set({"product": "sophie-nextjs", "turn_id": "t9", "trigger": "post_reply:world-interpret", "mode": "async"})
        call_context.record(module="world_interpreter", provider="openrouter", model="m")
        call_context.CTX.reset(token)
        await asyncio.sleep(0)
    asyncio.run(scenario())
    own, served = rows
    assert (own["trigger"], own["mode"], own["turn_id"], own["tokens_in"]) == ("self_scheduled", "async", None, 5)
    assert (served["trigger"], served["mode"], served["turn_id"], served["product"]) == ("post_reply:world-interpret", "async", "t9", "sophie-nextjs")
