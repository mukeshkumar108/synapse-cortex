"""Memory pipeline: Cortex-owned consolidation, preparation, replay-safety, and the
legacy-interpret retirement gate. No network: the model is an injected fake."""
import asyncio
import json

import pytest

from sqlmodel import select

from src.services import memory_pipeline
from src.services.memory_pipeline import LISTENING_PROMPT, HANDOFF_PROMPT


def _fake_model(kind, prompt, max_tokens, models):
    if kind == "discovery":
        return {"text": "He walks about five miles most evenings. A morning walk is an aspiration, not a routine.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "handoff":
        return {"text": "They talked walking. The morning walk stays an open idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind.startswith("edit:"):
        page = kind.split(":", 1)[1]
        return {"text": f"# {page}\n\nEvening walk ~5 miles established. Morning walk is an aspiration, not a routine.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "ledger":
        return {"text": '{"new": [{"key": "thursday-render", "title": "Deliver the render by Thursday", "kind": "commitment", "confidence": "reported", "timing_text": "Thursday", "expected_date": null, "waiting_on": "", "question_text": "", "linked_keys": [], "detail": "", "evidence": ["test"]}], "update": [], "close": []}',
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "arc":
        return {"text": "They talked walking; the morning walk remains an open idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "preparation":
        return {"text": "I wonder if he got his evening walk in. The morning walk is still just an idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    raise AssertionError(kind)


@pytest.fixture(autouse=True)
def fake_models():
    memory_pipeline.set_model_fn(_fake_model)
    yield
    memory_pipeline.set_model_fn(None)


def _msgs(n, prefix="m"):
    return [{"id": f"{prefix}{i}", "speaker": "user" if i % 2 == 0 else "assistant",
             "text": f"message {i}"} for i in range(n)]


BASE = {"workspace_id": "ws1", "owner": "user_1", "conversation_id": "c1"}


async def _wait_run(client, run_id, tries=50):
    for _ in range(tries):
        r = await client.get(f"/v1/memory/run/{run_id}")
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("consolidated", "replay_noop", "empty", "failed"):
            return r.json()
        await asyncio.sleep(0.1)
    raise AssertionError("run never finished")


@pytest.mark.asyncio
async def test_baseline_prompts_verbatim():
    assert "Only keep what genuinely matters. Write it as short, plain, standalone sentences." in LISTENING_PROMPT
    assert "Deliver no more than 2-3 sentences at most." in HANDOFF_PROMPT
    assert "Structure" not in LISTENING_PROMPT
    blob = (memory_pipeline.NOTEBOOK_EDITOR_PROMPT + memory_pipeline.ARC_UPDATE_PROMPT
            + memory_pipeline.SITUATIONS_PROMPT + memory_pipeline.PREPARATION_PROMPT)
    for guard in ("Do not carry the mood", "never turn one difficult exchange into a lasting verdict",
                  "aspiration is not a task and never closes by silence", "honest about what you don't know",
                  "Close only on evidence", "An invitation is not an accepted commitment",
                  "Inferred is not observed"):
        assert guard in blob


@pytest.mark.asyncio
async def test_consolidate_preparation_state_roundtrip(async_client):
    r = await async_client.post("/v1/memory/consolidate",
                                json={**BASE, "session_id": "s1", "messages": _msgs(10)})
    assert r.status_code == 202, r.text
    run = await _wait_run(async_client, r.json()["run_id"])
    assert run["status"] == "consolidated"
    assert run["summary"]["new_message_count"] if "new_message_count" in run["summary"] else True

    prep = (await async_client.get("/v1/memory/preparation", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert prep["found"] and "evening walk" in prep["text"]

    state = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert "aspiration, not a routine" in state["notebook"]["routines"]["text"]
    assert state["notebook"]["routines"]["version"] == 2
    assert any(i["title"] == "Deliver the render by Thursday" for i in state["ledger"])
    assert "open idea" in state["arc"]["text"]
    # page scopes hold: routines page carries no infrastructure material
    assert "database" not in state["notebook"]["routines"]["text"].lower()


@pytest.mark.asyncio
async def test_replay_is_noop_without_duplicates(async_client):
    r1 = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s1", "messages": _msgs(6)})
    assert (await _wait_run(async_client, r1.json()["run_id"]))["status"] == "consolidated"
    before = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    r2 = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s1b", "messages": _msgs(6)})
    run2 = await _wait_run(async_client, r2.json()["run_id"])
    assert run2["status"] == "replay_noop"
    after = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert after["notebook"] == before["notebook"] and after["arc"] == before["arc"]
    titles = [i["title"] for i in after["ledger"]]
    assert len(titles) == len(set(titles))


@pytest.mark.asyncio
async def test_full_fifty_message_coverage(async_client):
    r = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "long", "messages": _msgs(50)})
    run = await _wait_run(async_client, r.json()["run_id"])
    assert run["status"] == "consolidated" and len(run["covered_ids"]) == 50


@pytest.mark.asyncio
async def test_legacy_interpret_retired_for_sophie(async_client):
    r = await async_client.post("/v1/world/interpret", json={
        "workspace_id": "ws1", "owner": "user_1", "session_id": "c1",
        "messages": [{"id": "a", "speaker": "user", "text": "hi"}, {"id": "b", "speaker": "assistant", "text": "hey"}],
        "policy": "grounded", "companion_id": "sophie", "agency": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "superseded_by_memory_pipeline"


@pytest.mark.asyncio
async def test_empty_transcript_rejected(async_client):
    r = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s0", "messages": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_situations_update_by_key_and_close_needs_evidence():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
            statements={"new": [{"key": "thursday-talk", "title": "Big presentation Thursday, research outstanding",
                                 "kind": "commitment", "confidence": "reported", "timing_text": "Thursday",
                                 "waiting_on": "", "question_text": "What is still missing from the research?",
                                 "linked_keys": [], "detail": "", "evidence": ["big talk Thursday, research TBD"]}],
                        "update": [], "close": []})
        assert c == {"added": 1, "updated": 0, "closed": 0}
        await db.commit()
        # duplicate title does not duplicate
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s2",
            statements={"new": [{"key": "thursday-talk", "title": "Big presentation Thursday, research outstanding",
                                 "kind": "commitment", "evidence": []}], "update": [], "close": []})
        assert c["added"] == 0
        # update by key patches fields and appends evidence
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s2",
            statements={"new": [], "update": [{"key": "thursday-talk", "waiting_on": "research notes from Ana",
                                               "status": "waiting", "evidence": "still waiting on Ana"}], "close": []})
        assert c["updated"] == 1
        # close without evidence is refused
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s3",
            statements={"new": [], "update": [], "close": [{"key": "thursday-talk", "status": "done"}]})
        assert c["closed"] == 0
        # close with evidence applies
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s3",
            statements={"new": [], "update": [],
                        "close": [{"key": "thursday-talk", "status": "done", "evidence": "delivered it Thursday, went well"}]})
        assert c["closed"] == 1
        await db.commit()
        items = await memory_pipeline.open_ledger(db, "ws1", "u1")
        assert items == []  # done items leave the open list


@pytest.mark.asyncio
async def test_review_notices_without_closing():
    from src.db import async_session_maker

    async def memfn(kind, prompt, max_tokens, models):
        if kind == "review":
            return {"text": '{"updates": [{"key": "rent-invoice", "waiting_on": "still nothing after 9 days"}], '
                            '"noticed": ["invoice wait is getting long; may be worth a nudge"]}',
                    "model": "f", "provider": "f", "usage": {}, "ms": 1}
        raise AssertionError(kind)

    memory_pipeline.set_model_fn(memfn)
    try:
        async with async_session_maker() as db:
            await memory_pipeline.apply_situations(
                db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
                statements={"new": [{"key": "rent-invoice", "title": "Unpaid invoice, waiting on client",
                                     "kind": "situation", "waiting_on": "client payment", "evidence": ["sent it"]}],
                            "update": [], "close": []})
            await db.commit()
            rep = await memory_pipeline.review(db, workspace_id="ws1", owner="u1")
        assert rep["updates_applied"] == 1 and len(rep["noticed"]) == 1
        async with async_session_maker() as db:
            items = await memory_pipeline.open_ledger(db, "ws1", "u1")
            assert items and items[0].status == "open"  # review never closes
            assert "9 days" in items[0].waiting_on
    finally:
        memory_pipeline.set_model_fn(None)


@pytest.mark.asyncio
async def test_review_endpoint(async_client):
    r = await async_client.post("/v1/memory/review", json={"workspace_id": "ws1", "owner": "nobody"})
    assert r.status_code == 200, r.text
    assert r.json()["open_count"] == 0


@pytest.mark.asyncio
async def test_tagged_lines_parse_and_shape():
    raw = ("ITEM: Send the proposal to Sarah\nKIND: commitment\nDETAIL: 20 pages, needs Ana numbers\n"
           "TIMING: by Thursday\nPERSON: Ana (holds the numbers)\nWAITING-ON: Ana's numbers\n"
           "EVIDENCE: \"send the proposal by Thursday\"\nCONFIDENCE: observed\n"
           "ITEM: Morning run\nKIND: aspiration\nTIMING: someday\n"
           "ITEM: Ignore Pete tonight\nSTATUS-HINT: suppressed\nEVIDENCE: \"ignore it for now\"\n"
           "some stray line without a tag\n")
    items, unparsed = memory_pipeline.parse_tagged_lines(raw)
    assert len(items) == 3
    # untagged lines are preserved visibly as continuations, never dropped
    assert unparsed == [] and "stray line" in items[2].get("detail", "")
    assert items[0]["waiting_on"] == "Ana's numbers"
    st, _ = await memory_pipeline.shape_situations(items, "2026-10-19", [])
    assert len(st["new"]) == 3
    assert st["new"][0]["expected_date"] == "2026-10-22"  # Thursday from Mon Oct 19, deterministic
    assert st["new"][1]["kind"] == "aspiration" and st["new"][1]["expected_date"] is None


def test_resolve_date_conservative():
    r = memory_pipeline.resolve_date
    assert r("tomorrow", "2026-10-19").strftime("%Y-%m-%d") == "2026-10-20"
    assert r("Friday", "2026-10-19").strftime("%Y-%m-%d") == "2026-10-23"
    assert r('"before tomorrow afternoon"', "2026-10-19").strftime("%Y-%m-%d") == "2026-10-20"
    assert r('"by Tuesday morning"', "2026-10-19").strftime("%Y-%m-%d") == "2026-10-20"
    assert r("2026-10-24", "2026-10-19").strftime("%Y-%m-%d") == "2026-10-24"
    assert r("someday", "2026-10-19") is None
    assert r("next week", "2026-10-19") is None
    assert r("", "2026-10-19") is None
    assert r("N/A", "2026-10-19") is None


def test_clean_drops_null_words():
    c = memory_pipeline._clean
    assert c("N/A", 10) == "" and c("none", 10) == "" and c("null", 10) == ""
    assert c('"Thursday"', 50) == "Thursday"


@pytest.mark.asyncio
async def test_reminder_authorised_flagged():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
            statements={"new": [{"key": "call-mum", "title": "Call mum", "kind": "reminder",
                                 "reminder_authorised": True, "evidence": ["remind me"]}],
                        "update": [], "close": []})
        assert c["added"] == 1
        await db.commit()
        rows = (await db.execute(select(memory_pipeline.LedgerItem))).scalars().all()
        import json as _json
        assert _json.loads(rows[0].authorised_json) == {"reminder": True, "at": "s1"}


@pytest.mark.asyncio
async def test_match_merges_same_circumstance_different_words():
    from src.db import async_session_maker

    async def memfn(kind, prompt, max_tokens, models):
        if kind == "match":
            return {"text": "SAME: Vinesh contract review = [review-contract-amendments-for-vinesh]\nNEW: Dentist appointment",
                    "model": "f", "provider": "f", "usage": {}, "ms": 1}
        raise AssertionError(kind)

    memory_pipeline.set_model_fn(memfn)
    try:
        async with async_session_maker() as db:
            await memory_pipeline.apply_situations(
                db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
                statements={"new": [{"key": "review-contract-amendments-for-vinesh",
                                     "title": "Review contract amendments for Vinesh",
                                     "kind": "commitment", "evidence": ["v1"]}], "update": [], "close": []})
            await db.commit()
            known = await memory_pipeline.open_ledger(db, "ws1", "u1")
            items, _ = memory_pipeline.parse_tagged_lines(
                "ITEM: Vinesh contract review\nDETAIL: Ana sent the numbers, folding them in tonight\n"
                "EVIDENCE: \"ana sent it\"\nITEM: Dentist appointment\nTIMING: Thursday 2pm\n")
            st, _ = await memory_pipeline.shape_situations(items, "2026-10-19", known)
            assert [e["key"] for e in st["update"]] == ["review-contract-amendments-for-vinesh"]
            assert [e["title"] for e in st["new"]] == ["Dentist appointment"]
            counts = await memory_pipeline.apply_situations(
                db, workspace_id="ws1", owner="u1", run_id=None, session_id="s2",
                statements=st, known=known)
            assert counts == {"added": 1, "updated": 1, "closed": 0}
    finally:
        memory_pipeline.set_model_fn(None)


@pytest.mark.asyncio
async def test_same_title_different_kind_updates_never_duplicates():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
            statements={"new": [{"key": "dentist", "title": "Dentist appointment",
                                 "kind": "reminder", "evidence": ["dentist thursday"]}],
                        "update": [], "close": []})
        await db.commit()
        c = await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s2",
            statements={"new": [{"key": "dentist-appointment", "title": "Dentist appointment",
                                 "kind": "commitment", "timing_text": "Thursday 2pm",
                                 "evidence": ["dentist thursday 2pm"]}], "update": [], "close": []})
        # same normalized title + different kind: merged as update, kind revised
        assert c["added"] == 0 and c["updated"] == 1
        await db.commit()
        rows = (await db.execute(select(memory_pipeline.LedgerItem).where(
            memory_pipeline.LedgerItem.owner_peer_id == "u1"))).scalars().all()
        assert len(rows) == 1 and rows[0].kind == "commitment"
