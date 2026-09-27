"""Session-consolidation boundary: identity lane, provenance, evidence, coverage.

Proves the invariant: boundary-created matters land in the same durable
lane the live system reads, temporal identity travels as provenance only,
the server owns the authoritative snapshot, checkpoints/receipts have
distinct contracts, and long sessions segment without pretending a
summary is canonical.
"""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.consolidation import ConsolidationRun
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.services import semantic_judge
from src.services.session_reconstruction import segment_transcript
from src.services.session_consolidation import SessionTurn

WS = "ws-boundary"
LANE = "chat-lane-1"
TEMPORAL = "temporal-session-9"


class _Stub:
    def __init__(self, build):
        self.build = build
        self.prompts: list = []

    async def generate_structured(self, **kw):
        self.prompts.append(kw.get("prompt", ""))
        return self.build(kw.get("prompt", ""))


def _turns(n, prefix="t"):
    return [{"message_id": f"m{i}", "speaker": "ashley",
             "text": f"{prefix} turn number {i} with enough words to be real content here."}
            for i in range(n)]


@pytest.mark.asyncio
async def test_lane_visibility_next_session_handover(async_client, monkeypatch):
    """Applied boundary matter under lane L is visible to handover/attention
    reads on L, and absent on the temporal id: one namespace, not two."""
    from src.services.cortex_packet_service import CortexPacketService

    class Stub:
        async def generate_structured(self, **kw):
            return {"session_summary": "watch established",
                    "matters": [{"pid": "m1", "kind": "watch",
                                 "title": "Neck pain watch",
                                 "status": "open", "owner": "user",
                                 "basis": "new", "confidence": 0.85,
                                 "rationale": "multi-day trajectory",
                                 "subjects": [],
                                 "evidence": {"message_ids": ["m1"],
                                              "spans": [{"message_id": "m1",
                                                         "span": "neck has been killing"}]}}]}

    monkeypatch.setattr(semantic_judge, "_adapter", lambda: Stub())
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE,
              "temporal_session_id": TEMPORAL, "mode": "apply",
              "user_peer_id": "ashley",
              "transcript": [{"message_id": "m1", "speaker": "ashley",
                              "text": "My neck has been killing me for days now."}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["error"] == "", body
    from datetime import datetime, timezone
    svc = CortexPacketService()
    async with async_session_maker() as db:
        packet_lane = await svc.compile_attention_packet(
            db, workspace_id=WS, session_id=LANE, now=datetime.now(timezone.utc))
        packet_temp = await svc.compile_attention_packet(
            db, workspace_id=WS, session_id=TEMPORAL, now=datetime.now(timezone.utc))
        titles_lane = [x.get("title", "") for x in packet_lane.get("open_loops", [])]
        titles_temp = [x.get("title", "") for x in packet_temp.get("open_loops", [])]
    assert any("Neck pain watch" in t for t in titles_lane), \
        f"handover on the lane must carry the watch: {titles_lane}"
    assert not any("Neck pain watch" in t for t in titles_temp), \
        "temporal id must not open a second state namespace"
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
        runs = (await db.execute(select(ConsolidationRun).where(
            ConsolidationRun.honcho_workspace_id == WS))).scalars().all()
    assert len(loops) == 1
    assert loops[0].honcho_session_id == LANE
    assert TEMPORAL in (loops[0].honcho_message_id or ""), \
        "temporal boundary survives as row provenance"
    assert runs and runs[0].temporal_session_id == TEMPORAL


@pytest.mark.asyncio
async def test_authoritative_snapshot_not_suppressed_by_caller(async_client, monkeypatch):
    """A partial caller snapshot (empty matters) must not hide the server's
    authoritative rows from the proposal."""
    seen_ids: list = []

    class Stub:
        async def generate_structured(self, **kw):
            import re
            prompt = kw.get("prompt", "")
            ids = re.findall(r"\[matter ([0-9a-f-]{36})\]", prompt)
            seen_ids.extend(ids)
            return {"session_summary": "s",
                    "matters": [{"pid": "m1", "kind": "watch",
                                 "title": "Live matter", "status": "open",
                                 "owner": "user", "basis": "existing",
                                 "matter_id": ids[0] if ids else "none",
                                 "confidence": 0.8, "rationale": "still live",
                                 "evidence": {"message_ids": ["m1"], "spans": []}}]}

    async with async_session_maker() as db:
        db.add(OpenLoop(honcho_workspace_id=WS, honcho_session_id=LANE,
                        honcho_message_id="seed", owner_peer_id="ashley",
                        candidate_key="seed-k", title="Live matter",
                        summary="Live matter", status=OpenLoopStatus.OPEN))
        await db.commit()
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: Stub())
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "shadow",
              "start_snapshot": {"matters": [], "attentions": [],
                                 "suppressions": [], "people": ["Carlos"]},
              "transcript": [{"message_id": "m1", "speaker": "ashley",
                              "text": "just checking in today"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot_source"] == "authoritative+caller-people"
    assert seen_ids, "authoritative row must reach the model despite empty caller snapshot"
    assert body["accepted"] and body["accepted"][0]["op"] == "affirm_matter"


@pytest.mark.asyncio
async def test_receipts_quotable_checkpoints_are_not(async_client, monkeypatch):
    class Stub:
        async def generate_structured(self, **kw):
            return {"session_summary": "s",
                    "matters": [{
                        "pid": "m1", "kind": "event", "title": "Bank transfer arrived",
                        "status": "open", "owner": "user", "basis": "new",
                        "confidence": 0.85, "rationale": "receipt grounded",
                        "evidence": {
                            "message_ids": ["m1"],
                            "spans": [
                                {"message_id": "m1", "span": "checking the transfer"},
                                {"message_id": "receipt:0",
                                 "span": "Transfer of £1,900 completed"}]}},
                        {"pid": "m2", "kind": "watch", "title": "Checkpoint claim",
                         "status": "open", "owner": "user", "basis": "new",
                         "confidence": 0.85, "rationale": "checkpoint grounded?",
                         "evidence": {
                            "message_ids": ["m1"],
                            "spans": [{"message_id": "m1",
                                       "span": "provisional working-memory says"}]}}]}

    monkeypatch.setattr(semantic_judge, "_adapter", lambda: Stub())
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "shadow",
              "receipts": [{"kind": "bank", "text": "Transfer of £1,900 completed"}],
              "checkpoints": [{"label": "working-memory",
                               "text": "provisional working-memory says X"}],
              "transcript": [{"message_id": "m1", "speaker": "ashley",
                              "text": "checking the transfer status today"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    titles = [a["data"].get("title", "") for a in body["accepted"]]
    assert any("Bank transfer" in t for t in titles), \
        f"receipt-quotable matter must validate: {body}"
    assert not any("Checkpoint claim" in t for t in titles), \
        "checkpoint text is navigation, never evidence"
    assert any(x["reason"] == "bad_evidence"
               for x in body["rejected"]), \
        "span outside transcript+receipts must be refused"


def test_segmentation_packs_deterministically():
    turns = [SessionTurn(message_id=f"m{i}", speaker="a", text=f"word " * 50)
             for i in range(100)]
    segs = segment_transcript(turns)
    assert sum(len(s) for s in segs) == 100
    assert all(len(s) <= 40 for s in segs)
    assert [t.message_id for s in segs for t in s] == [f"m{i}" for i in range(100)]


@pytest.mark.asyncio
async def test_long_session_shadow_covers_all_turns(async_client, monkeypatch):
    import re
    calls: list = []

    class SegStub:
        async def generate_structured(self, **kw):
            prompt = kw.get("prompt", "")
            calls.append(prompt)
            if len(calls) == 1:
                return {"session_summary": "s",
                        "matters": [{"pid": "m1", "kind": "watch",
                                     "title": "Dentist reminder thread",
                                     "status": "open", "owner": "user",
                                     "basis": "new", "confidence": 0.85,
                                     "rationale": "repeated reminder",
                                     "subjects": [],
                                     "evidence": {"message_ids": ["m0"],
                                                  "spans": [{"message_id": "m0",
                                                             "span": "dentist"}]}}],
                        "incidental_mids": [
                            m for m in re.findall(r"\[msg:(\w+)\]", prompt)
                            if m != "m0"]}
            return {"session_summary": "s", "matters": [],
                    "incidental_mids": re.findall(r"\[msg:(\w+)\]", prompt)}

    monkeypatch.setattr(semantic_judge, "_adapter", lambda: SegStub())
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "shadow",
              "transcript": _turns(65, prefix="dentist")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coverage"]["complete"] is True
    assert body["coverage"]["turns_in"] == 65
    assert len(body["segments"]) == 2, "65 turns must split, not truncate"
    covered = set()
    for o in body["accepted"]:
        covered.update(o["data"].get("message_ids", []))
    for o in body["accepted"]:
        for s in (o["data"].get("evidence") or {}).get("spans", []):
            covered.add(s.get("message_id"))
    assert covered == {f"m{i}" for i in range(65)}, \
        "every turn accounted for across segments"
    # Second segment must see the first segment's proposals, not re-mint.
    assert "ALREADY PROPOSED" in calls[1]
    assert "Dentist reminder thread" in calls[1]


@pytest.mark.asyncio
async def test_long_session_apply_continues_without_duplicates(async_client, monkeypatch):
    calls: list = []

    class SegStub:
        async def generate_structured(self, **kw):
            import re
            calls.append(kw.get("prompt", ""))
            if len(calls) == 1:
                return {"session_summary": "s",
                        "matters": [{"pid": "m1", "kind": "watch",
                                     "title": "Dentist reminder thread",
                                     "status": "open", "owner": "user",
                                     "basis": "new", "confidence": 0.85,
                                     "rationale": "repeated reminder",
                                     "subjects": [],
                                     "evidence": {"message_ids": ["m0"],
                                                  "spans": [{"message_id": "m0",
                                                             "span": "dentist"}]}}]}
            titles = " ".join(re.findall(
                r"\[matter [0-9a-f-]{36}\] \S+ [\w/]+(?: owner=\S+)?: (.*)", calls[-1]))
            assert "Dentist reminder thread" in titles, \
                "segment 2 must see segment 1's applied row in its snapshot"
            return {"session_summary": "s", "matters": []}

    monkeypatch.setattr(semantic_judge, "_adapter", lambda: SegStub())
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    texts = []
    for i in range(45):
        prefix = "dentist reminder again" if i in (0, 44) else "ordinary chatter here"
        texts.append({"message_id": f"m{i}", "speaker": "ashley",
                      "text": f"{prefix} with enough words to fill the turn content {i}."})
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "apply",
              "user_peer_id": "ashley", "transcript": texts})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["error"] == "", body
    assert len(body["segments"]) == 2
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
    dentists = [l for l in loops if "dentist" in (l.title or "").lower()]
    assert len(dentists) == 1, f"one thread across segments: {[l.title for l in loops]}"
    # Audit completeness: one trace per segment (unique keys, no constraint loss).
    from src.models.operational_state import ExtractionTrace
    async with async_session_maker() as db:
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == WS,
            ExtractionTrace.stage == "session_reconstruction"))).scalars().all()
    assert len(traces) == 2, f"every segment leaves an audit trace: {len(traces)}"


@pytest.mark.asyncio
async def test_segment_cap_reports_dropped_honestly(async_client, monkeypatch):
    stub = _Stub(lambda prompt: {"session_summary": "s", "matters": []})
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    long_turns = [{"message_id": f"m{i}", "speaker": "ashley",
                   "text": f"verbose turn number {i} " + "with many words " * 40}
                  for i in range(450)]
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "shadow",
              "transcript": long_turns})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coverage"]["complete"] is False
    assert len(body["segments"]) <= 20
    assert body["coverage"]["turns_dropped"] > 0
    assert len(stub.prompts) <= 20


# ── partial-success semantics ────────────────────────────────────────────────

class _ScriptStub:
    """Scripted per-call adapter: each response is a payload dict or an
    exception to raise. Counts calls for retry-convergence assertions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def generate_structured(self, **kw):
        self.calls += 1
        if not self.responses:
            raise AssertionError("adapter called more times than scripted")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _matter_payload(title, mids, kind="watch"):
    return {"session_summary": "s",
            "matters": [{"pid": "m1", "kind": kind, "title": title,
                         "status": "open", "owner": "user", "basis": "new",
                         "confidence": 0.85, "rationale": "fixture",
                         "subjects": [],
                         "evidence": {"message_ids": mids,
                                      "spans": [{"message_id": mids[0],
                                                 "span": "turn number"}]}}]}


@pytest.mark.asyncio
async def test_failed_window_visible_completion_partial(async_client, monkeypatch):
    stub = _ScriptStub(
        [_matter_payload("First thread", ["m0"])] + [RuntimeError("boom")] * 3)
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "apply",
              "user_peer_id": "ashley", "temporal_session_id": "temp-1",
              "transcript": _turns(65, prefix="dentist")})
    assert r.status_code == 200, r.text
    body = r.json()
    # Packing covered everything; semantics did not.
    assert body["coverage"]["packing"]["complete"] is True
    assert body["coverage"]["semantic"]["complete"] is False
    assert body["coverage"]["complete"] is False, \
        "a failed window must never report complete"
    assert body["completion"] == "partial"
    failed = body["failed_segments"]
    assert len(failed) == 1 and failed[0]["segment"] == 1
    assert len(failed[0]["message_ids"]) == 25, "failed window stays explicit"
    # Successful window still applied (no atomic rollback of good state)...
    assert [a for a in body["applied"] if a["op"] == "new_matter"]
    # ...and the ledger exposes the partial state for operators.
    async with async_session_maker() as db:
        from src.models.consolidation import ConsolidationRun
        runs = (await db.execute(select(ConsolidationRun).where(
            ConsolidationRun.honcho_workspace_id == WS))).scalars().all()
    assert len(runs) == 1
    assert runs[0].completion == "partial"
    assert runs[0].temporal_session_id == "temp-1"
    import json as _json
    segmap = _json.loads(runs[0].segment_map_json)
    assert {s["status"] for s in segmap} == {"ok", "failed"}
    assert runs[0].accepted_json and "First thread" in runs[0].accepted_json


@pytest.mark.asyncio
async def test_retry_converges_without_duplicates(async_client, monkeypatch):
    stub = _ScriptStub(
        [_matter_payload("First thread", ["m0"])]
        + [RuntimeError("boom")] * 2
        + [_matter_payload("Second thread", ["m40"])])
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    base = {"workspace_id": WS, "session_id": LANE, "mode": "apply",
            "user_peer_id": "ashley", "transcript": _turns(65, prefix="dentist")}
    r1 = await async_client.post("/v1/sessions/consolidate", json=base)
    assert r1.status_code == 200, r1.text
    run1 = r1.json()
    assert run1["completion"] == "partial"
    assert stub.calls == 3, "1 ok + 2 transport attempts on the failed window"
    r2 = await async_client.post(
        "/v1/sessions/consolidate/retry",
        json={"workspace_id": WS, "session_id": LANE,
              "run_id": run1["run_id"], "user_peer_id": "ashley",
              "transcript": base["transcript"]})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert stub.calls == 4, "only the failed window re-runs: no wasted model cost"
    assert body["completion"] == "complete"
    assert body["coverage"]["semantic"]["windows_skipped_covered"] == 1
    titles = [a["data"].get("title", "") for a in body["accepted"]]
    assert any("First thread" in t for t in titles), "prior accepted merged"
    assert any("Second thread" in t for t in titles)
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
        from src.models.consolidation import ConsolidationRun
        runs = (await db.execute(select(ConsolidationRun).where(
            ConsolidationRun.honcho_workspace_id == WS))).scalars().all()
    assert len([l for l in loops if "thread" in (l.title or "").lower()]) == 2, \
        "retry must converge without reminting covered windows"
    assert len(runs) == 2 and runs[1].prior_run_id == runs[0].id, \
        "runs chain instead of mutating history"


@pytest.mark.asyncio
async def test_retry_rejects_changed_transcript(async_client, monkeypatch):
    stub = _ScriptStub([_matter_payload("First thread", ["m0"])] + [RuntimeError("boom")] * 3)
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    base = {"workspace_id": WS, "session_id": LANE, "mode": "shadow",
            "transcript": _turns(65, prefix="dentist")}
    run1 = (await async_client.post("/v1/sessions/consolidate", json=base)).json()
    changed = base["transcript"][:-1]  # drop a turn: boundary drifted
    r = await async_client.post(
        "/v1/sessions/consolidate/retry",
        json={"workspace_id": WS, "session_id": LANE,
              "run_id": run1["run_id"], "transcript": changed})
    assert r.status_code == 400, r.text
    r = await async_client.post(
        "/v1/sessions/consolidate/retry",
        json={"workspace_id": "other-ws", "session_id": LANE,
              "run_id": run1["run_id"], "transcript": base["transcript"]})
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_retry_complete_returns_already(async_client, monkeypatch):
    stub = _ScriptStub([{"session_summary": "s", "matters": []}])
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    base = {"workspace_id": WS, "session_id": LANE, "mode": "shadow",
            "transcript": _turns(5)}
    run1 = (await async_client.post("/v1/sessions/consolidate", json=base)).json()
    assert run1["completion"] == "complete"
    r = await async_client.post(
        "/v1/sessions/consolidate/retry",
        json={"workspace_id": WS, "session_id": LANE,
              "run_id": run1["run_id"], "transcript": base["transcript"]})
    assert r.status_code == 200, r.text
    assert r.json()["already_complete"] is True
    assert stub.calls == 1, "no model call for an already-complete run"


@pytest.mark.asyncio
async def test_all_windows_failed_shadow_applies_nothing(async_client, monkeypatch):
    stub = _ScriptStub([RuntimeError("boom")] * 6)
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": WS, "session_id": LANE, "mode": "apply",
              "transcript": _turns(65, prefix="dentist")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["completion"] == "failed"
    assert body["coverage"]["complete"] is False
    assert body["applied"] == []
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
    assert loops == []
