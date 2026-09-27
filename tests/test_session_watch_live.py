"""Watch-thread graduation proof (GATED: SYNAPTIC_LIVE_MODEL=1 + key).

Proves the upstream path Spark A's pressure machinery needs: session
evidence -> V2 watch matter (owner + spans + subjects) -> durable OPEN
thread with entity links where groundable -> later evidence reattaches
in place (no duplicate) or resolves it. Model judgement gaps are
recorded, not hidden.
"""
import os

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.identity import EntityLink
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.services.session_consolidation import capture_snapshot
from src.services.session_reconstruction import reconstruct_session

pytestmark = pytest.mark.skipif(
    os.getenv("SYNAPTIC_LIVE_MODEL") != "1",
    reason="live-model proof only")


def _read_key():
    """Read-only at import: mutating os.environ here would leak a live
    adapter into unrelated no-adapter tests via the singleton."""
    if os.getenv("OPENROUTER_API_KEY"):
        return os.getenv("OPENROUTER_API_KEY")
    try:
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


needs_key = pytest.mark.skipif(not _read_key(), reason="no OPENROUTER_API_KEY")


@pytest.fixture
def _live_keys():
    import src.runtime_model as rm
    key = _read_key()
    if key:
        os.environ["OPENROUTER_API_KEY"] = key
    rm._adapter_singleton = None
    yield
    os.environ.pop("OPENROUTER_API_KEY", None)
    rm._adapter_singleton = None


pytestmark = [pytestmark, pytest.mark.usefixtures("_live_keys")]

GEMINI = "google/gemini-2.5-flash-lite"


async def _loops(ws):
    async with async_session_maker() as db:
        return (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()


async def _reconstruct(ws, session, transcript, snap, model=GEMINI):
    from src.runtime_model import AgendaRankerAdapter
    async with async_session_maker() as db:
        return await reconstruct_session(
            db, workspace_id=ws, session_id=session, transcript=transcript,
            start_snapshot=snap, adapter=AgendaRankerAdapter(),
            model_id=model, user_peer_id="ashley")


def _new_watches(result):
    return [o for o in result.accepted if o.op == "new_matter"
            and o.data.get("matter_kind") == "watch"]


@needs_key
@pytest.mark.asyncio
async def test_live_neck_becomes_watch_not_just_fact():
    ws = "ws-watch-neck"
    async with async_session_maker() as db:
        snap = await capture_snapshot(db, workspace_id=ws, session_id="s")
    result = await _reconstruct(ws, "s", [
        {"message_id": "e1", "speaker": "ashley",
         "text": "My neck has been killing me and I haven't been sleeping properly."},
        {"message_id": "e2", "speaker": "ashley",
         "text": "It's been like this for days now, I can barely turn my head."},
    ], snap)
    assert result.error == "", result.error
    watches = _new_watches(result)
    assert len(watches) == 1, f"one watch thread, got: {result.accepted}"
    assert watches[0].data.get("owner") == "user"
    print(f"\n[NECK] watch={watches[0].data.get('title')!r} "
          f"subjects={watches[0].data.get('subjects')}")


@needs_key
@pytest.mark.asyncio
async def test_live_matt_watch_links_person_reuse_in_place(async_client, monkeypatch):
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionCandidate
    from src.services import semantic_judge

    ws = "ws-watch-matt"
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    # Session 1 establishes the watch through the real endpoint (apply).
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": ws, "session_id": "s1", "mode": "apply",
              "user_peer_id": "ashley",
              "transcript": [
                  {"message_id": "e1", "speaker": "ashley",
                   "text": "Matt had surgery today and I'm waiting to hear how he is."}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["error"] == "", body
    created = [a for a in body["applied"] if a["op"] == "new_matter"]
    assert created, f"watch must be created: {body}"
    watch_id = created[0]["row_id"]
    async with async_session_maker() as db:
        links = (await db.execute(select(EntityLink).where(
            EntityLink.honcho_workspace_id == ws,
            EntityLink.object_type == "open_loop"))).scalars().all()
    matt_links = [x for x in links if str(x.object_id) == watch_id]
    print(f"\n[MATT] created watch={watch_id[:8]} links={len(matt_links)}")
    # Later evidence reattaches in place via the existing reuse machinery
    # (scripted candidate stands in for the LLM extractor's refs).
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: None)
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *a, **k: [ExtractionCandidate(
            candidate_key="upd1", observation="Still waiting for news on Matt.",
            raw_evidence="Still waiting for news on Matt.",
            canonical_title="Still waiting for news on Matt",
            open_loop_hint="Still waiting for news on Matt",
            operational_kind="open_loop", subject_refs=["Matt"],
            confidence=0.9, formation="explicit",
            extractor_version="watch-proof")])
    r2 = await async_client.post(
        "/v1/events/turn",
        json={"workspace_id": ws, "session_id": "s1",
              "honcho_message_id": "e2", "peer_id": "ashley",
              "text": "Still waiting for news on Matt.",
              "now": "2026-09-28T10:00:00+01:00", "timezone": "Europe/London"})
    assert r2.status_code == 202, r2.text
    loops = await _loops(ws)
    assert len(loops) == 1, f"update must reattach, not duplicate: {[l.title for l in loops]}"
    assert str(loops[0].id) == watch_id
    print("[MATT] update reattached in place, no duplicate")


@needs_key
@pytest.mark.asyncio
async def test_live_recovery_resolves_watch(async_client, monkeypatch):
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    ws = "ws-watch-resolve"
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": ws, "session_id": "s1", "mode": "apply",
              "user_peer_id": "ashley",
              "transcript": [
                  {"message_id": "e1", "speaker": "ashley",
                   "text": "Matt had surgery today and I'm waiting to hear how he is."}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "apply"
    async with async_session_maker() as db:
        snap = await capture_snapshot(db, workspace_id=ws, session_id="s1")
    assert any("matt" in m.title.lower() for m in snap.matters), \
        "precondition: watch durable after session 1"
    second = await _reconstruct(ws, "s1", [
        {"message_id": "e2", "speaker": "ashley",
         "text": "Matt is out of surgery, it went well."},
    ], snap)
    assert second.error == "", second.error
    print(f"\n[RESOLVE] ops={[(o.op, o.data) for o in second.accepted]}")
    resol = [o for o in second.accepted if o.op == "resolve_matter"]
    assert resol, "outcome session must resolve the live watch"
    assert all(w["would_apply"] for w in second.would_apply
               if w["op"] == "resolve_matter")
    assert not [o for o in second.accepted if o.op == "new_matter"
                and "waiting" in str(o.data.get("title", "")).lower()], \
        "outcome must not re-establish the waiting watch"


@needs_key
@pytest.mark.asyncio
async def test_live_second_session_does_not_duplicate_watch(async_client, monkeypatch):
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    ws = "ws-watch-nodup"
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": ws, "session_id": "s1", "mode": "apply",
              "user_peer_id": "ashley",
              "transcript": [
                  {"message_id": "e1", "speaker": "ashley",
                   "text": "My neck has been killing me and I haven't been sleeping properly."}]})
    assert r.status_code == 200, r.text
    async with async_session_maker() as db:
        snap = await capture_snapshot(db, workspace_id=ws, session_id="s1")
    assert any("neck" in m.title.lower() for m in snap.matters), \
        "precondition: neck watch durable after session 1"
    second = await _reconstruct(ws, "s1", [
        {"message_id": "e2", "speaker": "ashley",
         "text": "Neck still bad today, might call the physio."},
    ], snap)
    assert second.error == "", second.error
    new_watches = _new_watches(second)
    print(f"\n[NODUP] second-session new watches: "
          f"{[w.data.get('title') for w in new_watches]}")
    assert not [w for w in new_watches
                if "neck" in str(w.data.get("title", "")).lower()], \
        "second session must continue the thread, not re-mint it"
