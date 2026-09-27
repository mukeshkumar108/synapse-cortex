"""V2 live-model hard verticals (GATED: SYNAPTIC_LIVE_MODEL=1 + OPENROUTER key).

Each vertical: seed start state -> snapshot -> session turns through the
REAL incremental path (rules extractor, no adapters, no scripted
candidates: B is genuinely what per-turn ingestion produces) -> live
reconstruction with Gemini Flash Lite (primary; Laguna subset) -> A/B/C
comparison with classification.

Results are ALSO written to /tmp/v2_live_results.json (not the repo).
"""
import json
import os
import time

import pytest

from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
)
from src.models.expectation import Expectation
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus
from src.services import semantic_judge
from src.services.commitment_candidate_service import canonical_key_for
from src.services.session_consolidation import (
    SessionTurn,
    capture_snapshot,
)
from src.services.session_reconstruction import reconstruct_session

pytestmark = pytest.mark.skipif(
    os.getenv("SYNAPTIC_LIVE_MODEL") != "1",
    reason="live-model soak only (needs SYNAPTIC_LIVE_MODEL=1 + OPENROUTER_API_KEY)")


def _read_key():
    """Read (never mutate) the key. Import-time environ mutation would leak
    a live adapter into unrelated no-adapter tests via the singleton."""
    if os.getenv("OPENROUTER_API_KEY"):
        return os.getenv("OPENROUTER_API_KEY")
    for path in (".env", os.path.expanduser("~/.config/opencode/.env")):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            continue
    return ""


HAS_KEY = bool(_read_key())


@pytest.fixture
def _live_keys():
    """Scope the live key to live tests only: set, reset singleton, and
    always clean up so later no-adapter tests see None."""
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
LAGUNA = "poolside/laguna-s-2.1"

RESULTS_PATH = "/tmp/v2_live_results.json"
RECORDS: list = []


def _record(vertical, model, truth, b, c, classification, notes=""):
    RECORDS.append({"vertical": vertical, "model": model, "truth": truth,
                    "b": b, "c": c, "classification": classification,
                    "notes": notes})
    try:
        with open(RESULTS_PATH, "w") as f:
            json.dump(RECORDS, f, indent=1, default=str)
    except OSError:
        pass


async def _seed_loop(ws, session, mid, title, status=OpenLoopStatus.OPEN):
    async with async_session_maker() as db:
        db.add(OpenLoop(honcho_workspace_id=ws, honcho_session_id=session,
                        honcho_message_id=mid, owner_peer_id="ashley",
                        candidate_key=f"seed-{mid}", title=title, summary=title,
                        status=status))
        await db.commit()


async def _seed_commit(ws, session, mid, title, owner="ashley",
                       authority=CommitmentCandidateAuthority.ACT,
                       status=CommitmentCandidateStatus.PENDING):
    async with async_session_maker() as db:
        db.add(CommitmentCandidate(
            honcho_workspace_id=ws, honcho_session_id=session,
            owner_peer_id=owner, candidate_key=f"seed-{mid}",
            canonical_key=canonical_key_for(title), title=title,
            evidence_verbatim=title, evidence_class="implicit_self_commitment",
            authority=authority, status=status, source_message_id=mid))
        await db.commit()


async def _seed_suppression(ws, session, mid, topic):
    async with async_session_maker() as db:
        db.add(Suppression(honcho_workspace_id=ws, honcho_session_id=session,
                           honcho_message_id=mid, candidate_key=f"seed-{mid}",
                           owner_peer_id="ashley", topic_or_entity=topic,
                           reason="user boundary"))
        await db.commit()


class Live:
    """One vertical: real incremental B, live-model C."""

    def __init__(self, async_client, monkeypatch, ws):
        self.c = async_client
        self.m = monkeypatch
        self.ws = ws
        self.transcript: list = []

    async def turn(self, mid, sender, text, now="2026-09-28T10:00:00+01:00"):
        # Honest B: real rules extractor, NO semantic adapters anywhere.
        self.m.setattr(semantic_judge, "_adapter", lambda: None)
        r = await self.c.post(
            "/v1/events/turn",
            json={"workspace_id": self.ws, "session_id": "session-1",
                  "honcho_message_id": mid, "peer_id": sender,
                  "text": text, "now": now, "timezone": "Europe/London"})
        assert r.status_code == 202, r.text
        self.transcript.append({"message_id": mid, "speaker": sender, "text": text})

    async def snap(self):
        async with async_session_maker() as db:
            return await capture_snapshot(
                db, workspace_id=self.ws, session_id="session-1")

    async def state(self):
        async with async_session_maker() as db:
            loops = (await db.execute(select(OpenLoop).where(
                OpenLoop.honcho_workspace_id == self.ws))).scalars().all()
            commits = (await db.execute(select(CommitmentCandidate).where(
                CommitmentCandidate.honcho_workspace_id == self.ws))).scalars().all()
            atts = (await db.execute(select(AttentionCandidate).where(
                AttentionCandidate.honcho_workspace_id == self.ws))).scalars().all()
            clars = (await db.execute(select(ClarificationCandidate).where(
                ClarificationCandidate.honcho_workspace_id == self.ws))).scalars().all()
            supps = (await db.execute(select(Suppression).where(
                Suppression.honcho_workspace_id == self.ws))).scalars().all()
            return {"loops": loops, "commits": commits, "atts": atts,
                    "clars": clars, "supps": supps}

    async def reconstruct(self, snap, model):
        from src.runtime_model import AgendaRankerAdapter
        adapter = AgendaRankerAdapter()
        async with async_session_maker() as db:
            before = await _fingerprint(db, self.ws)
            result = await reconstruct_session(
                db, workspace_id=self.ws, session_id="session-1",
                transcript=self.transcript, start_snapshot=snap,
                adapter=adapter, model_id=model, user_peer_id="ashley")
            after = await _fingerprint(db, self.ws)
        assert before == after, "shadow must mutate nothing"
        return result


async def _fingerprint(db, ws):
    out = []
    for model in (OpenLoop, CommitmentCandidate, Expectation,
                  AttentionCandidate, Suppression):
        try:
            rows = (await db.execute(
                select(model).where(model.honcho_workspace_id == ws))).scalars().all()
        except Exception:
            continue
        for r in rows:
            out.append((model.__tablename__, str(r.id), str(getattr(r, "status", "")),
                        (getattr(r, "title", None) or getattr(r, "content", None)
                         or getattr(r, "topic_or_entity", None))))
    return sorted(out, key=str)


def _ops(result, op):
    return [o for o in result.accepted if o.op == op]


def _title_of(snap, mid):
    for m in snap.matters:
        if m.id == mid:
            return (m.title or "").lower()
    return ""


def _b_summary(st):
    return {
        "loops": [(l.title, str(l.status)) for l in st["loops"]],
        "commits": [(c.title, str(c.status), str(c.authority)) for c in st["commits"]],
        "atts": len(st["atts"]), "clars": len(st["clars"]),
        "supps": [(s.topic_or_entity, str(s.status)) for s in st["supps"]],
    }


def _c_summary(result):
    return {
        "accepted": [(o.op, str(o.data)[:160]) for o in result.accepted],
        "rejected": result.rejected,
        "would_apply": result.would_apply,
        "discards": result.discards,
        "error": result.error, "retries": result.retries,
        "prompt_chars": result.prompt_chars, "latency_s": result.latency_s,
        "summary": result.summary[:200],
    }


needs_key = pytest.mark.skipif(not HAS_KEY, reason="no OPENROUTER_API_KEY")


# ── V1 CARLOS (missing matter — MUST PASS) ────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_carlos_missing_matter(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, f"ws-live2-carlos-{model.split('/')[-1]}")
    snap = await s.snap()
    assert snap.matters == []
    await s.turn("e1", "ashley",
                 "Carlos still owes me the remaining balance, about twenty one hundred.")
    await s.turn("e2", "ashley", "Did that ever come through?")
    await s.turn("e3", "bank_feed", "Incoming payment of nineteen hundred from Carlos.")
    st = await s.state()
    b = _b_summary(st)
    assert not [l for l in st["loops"] if "carlos" in (l.title or "").lower()], \
        f"B genuinely misses the matter: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"model/contract failure: {result.error} {result.rejected}"
    new_matters = [o for o in _ops(result, "new_matter") if "carlos" in str(o.data).lower()]
    assert len(new_matters) == 1, f"C must establish exactly the Carlos matter: {c}"
    assert new_matters[0].data.get("status") == "partial", \
        f"new debt already partly paid must carry partiality: {c}"
    remainder = str(new_matters[0].data.get("remainder", ""))
    assert "200" in remainder or "two hundred" in remainder.lower(), \
        f"remainder must survive (£200): {c}"
    assert not [o for o in result.accepted if o.op == "new_matter"
                and "carlos" not in str(o.data).lower()], \
        f"no question-matters: {c}"
    assert not [o for o in result.accepted if o.op == "same_as"]
    cls = "C-fixes-B"
    _record("carlos", model, "debt £2100 + £1900 partial + £200 remainder",
            b, c, cls)
    print(f"\n[CARLOS/{model}] {cls} latency={result.latency_s}s prompt={result.prompt_chars}")


# ── V2 MEETING (missing matter + lunch control inside) ────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_meeting_missing_matter(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-meeting")
    snap = await s.snap()
    await s.turn("e1", "ashley", "I've got that meeting tomorrow and I'm a bit nervous.")
    await s.turn("e2", "ashley", "Not sure whether I'll get lunch there.")
    st = await s.state()
    b = _b_summary(st)
    assert st["loops"] == [], f"B misses the meeting: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    new_matters = _ops(result, "new_matter")
    assert len(new_matters) == 1 and "meeting" in str(new_matters[0].data).lower(), \
        f"exactly the meeting, nothing invented: {c}"
    assert not [o for o in result.accepted if o.op in ("uncertainty", "attend")
                and "lunch" in str(o.data).lower()], "lunch must stay incidental"
    assert any("e2" in str(o.data) for o in _ops(result, "incidental")), \
        f"lunch turn explicitly discarded: {c}"
    _record("meeting", model, "meeting matter + unknown details + lunch incidental",
            b, c, "C-fixes-B")
    print(f"\n[MEETING/{model}] C-fixes-B latency={result.latency_s}s")


# ── V3 CHAIRS (incorrect incremental) ─────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_chairs_correction(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-chairs")
    await _seed_loop(s.ws, "session-1", "seed1", "Confirm headcount with venue")
    snap = await s.snap()
    await s.turn("e1", "ashley", "The chairs. I told the venue yes, 120 chairs, so that's done.")
    await s.turn("e2", "ashley", "Did I ever sort the chairs?")
    st = await s.state()
    b = _b_summary(st)
    assert [l for l in st["loops"] if l.status == OpenLoopStatus.OPEN], \
        f"B must still show chairs unresolved: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    resol = _ops(result, "resolve_matter")
    assert resol and resol[0].data.get("via") == "completed", f"C must complete chairs: {c}"
    assert all(w["would_apply"] for w in result.would_apply if w["op"] == "resolve_matter")
    assert not [o for o in result.accepted if o.op == "new_matter"], \
        "retrospective question must not become a new matter"
    _record("chairs", model, "completed, no resurrection", b, c, "C-fixes-B")
    print(f"\n[CHAIRS/{model}] C-fixes-B latency={result.latency_s}s")


# ── V4 SCHOOL (orphaned evidence + distinct form) ─────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_school_payment_vs_form(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, f"ws-live2-school-{model.split('/')[-1]}")
    await _seed_loop(s.ws, "session-1", "seed1", "School trip payment due Friday")
    await _seed_loop(s.ws, "session-1", "seed2", "School trip permission form needs signing")
    snap = await s.snap()
    await s.turn("e1", "bank_feed", "School trip payment received, thank you.")
    st = await s.state()
    b = _b_summary(st)
    form = [l for l in st["loops"] if "permission form" in (l.title or "").lower()]
    assert form and form[0].status == OpenLoopStatus.OPEN
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    assert not [o for o in result.accepted if o.op == "same_as"], f"never merge: {c}"
    pay_id = next(m.id for m in snap.matters if "payment due friday" in m.title.lower())
    form_id = next(m.id for m in snap.matters if "permission form" in m.title.lower())
    assert not [o for o in _ops(result, "resolve_matter")
                if o.data.get("matter_id") == form_id], f"form must not resolve: {c}"
    assert [o for o in result.accepted
            if o.data.get("matter_id") == pay_id], \
        f"payment evidence must attach to payment: {c}"
    _record("school", model, "payment resolved/distinct form", b, c, "C-fixes-B")
    print(f"\n[SCHOOL/{model}] C-fixes-B latency={result.latency_s}s")


# ── V5 JUNK (non-affirmation) ─────────────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_junk_rejected(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, f"ws-live2-junk-{model.split('/')[-1]}")
    await _seed_loop(s.ws, "session-1", "seed1", "Inquire about arrival status")
    await _seed_loop(s.ws, "session-1", "seed2", "Carlos still owes £2,100 from the event")
    snap = await s.snap()
    await s.turn("e1", "ashley", "Did that ever come through?")
    st = await s.state()
    b = _b_summary(st)
    assert any("inquire about arrival" in (l.title or "").lower() for l in st["loops"])
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    junk_id = next(m.id for m in snap.matters if "inquire about arrival" in m.title.lower())
    assert not [o for o in result.accepted
                if o.data.get("matter_id") == junk_id], \
        f"junk must never be affirmed: {c}"
    assert [d for d in result.discards if d.get("matter_id") == junk_id], \
        f"junk must be explicitly marked: {c}"
    assert not [o for o in result.accepted if o.op == "new_matter"], \
        "reference must not mint a matter"
    _record("junk", model, "junk discarded + reference attached", b, c, "C-fixes-B")
    print(f"\n[JUNK/{model}] C-fixes-B latency={result.latency_s}s")


# ── V6 CONTRADICTION ──────────────────────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_contradiction_revises(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, f"ws-live2-contra-{model.split('/')[-1]}")
    await _seed_loop(s.ws, "session-1", "seed1",
                     "Studio Sam will sign the revised contract this week")
    snap = await s.snap()
    await s.turn("e1", "external:studio_sam",
                 "There will be no signature after all, we went with another studio.")
    st = await s.state()
    b = _b_summary(st)
    assert [l for l in st["loops"] if l.status == OpenLoopStatus.OPEN], \
        f"B misses the contradiction: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    loop_id = snap.matters[0].id
    resol = [o for o in _ops(result, "resolve_matter")
             if o.data.get("matter_id") == loop_id and o.data.get("via") == "cancelled"]
    assert resol, f"C must cancel on contradiction, not affirm: {c}"
    assert not [o for o in _ops(result, "affirm_matter")
                if o.data.get("matter_id") == loop_id], \
        "old interpretation must not be blindly affirmed"
    _record("contradiction", model, "pursuit cancelled on counter-evidence",
            b, c, "C-fixes-B")
    print(f"\n[CONTRA/{model}] C-fixes-B latency={result.latency_s}s")


# ── V7 MATT ───────────────────────────────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_matt_phase_transition(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-matt")
    await _seed_loop(s.ws, "session-1", "seed1", "Matt surgery tomorrow, waiting for news")
    snap = await s.snap()
    await s.turn("e1", "ashley", "Matt is out of surgery, it went well.")
    await s.turn("e2", "ashley", "Matt has a fever after the surgery, watching it.")
    st = await s.state()
    b = _b_summary(st)
    assert not [l for l in st["loops"] if "fever" in (l.title or "").lower()], \
        f"B misses the fever phase: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    fever = [o for o in _ops(result, "new_matter") if "fever" in str(o.data).lower()]
    assert fever, f"C must establish the fever phase: {c}"
    waiting_id = snap.matters[0].id
    waiting_ops = [o for o in result.accepted
                   if o.data.get("matter_id") == waiting_id]
    assert waiting_ops and waiting_ops[0].op in ("resolve_matter", "affirm_matter"), \
        f"waiting must release or be affirmed-resolved, never reopened: {c}"
    _record("matt", model, "waiting released + fever phase", b, c, "C-fixes-B")
    print(f"\n[MATT/{model}] C-fixes-B latency={result.latency_s}s")


# ── V8 FREEPIK (preservation control) ─────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_freepik_preserved(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-freepik")
    await _seed_commit(s.ws, "session-1", "seed1", "Cancel Freepik renewal Friday")
    await _seed_suppression(s.ws, "session-1", "seed2", "Freepik renewal")
    await _seed_loop(s.ws, "session-1", "seed3", "Freepik renewal awaiting client approval")
    snap = await s.snap()
    await s.turn("e1", "ashley", "Pushed the cancellation to tomorrow, client still needs it.")
    await s.turn("e2", "ashley", "Cancelled Freepik myself after client approval.")
    st = await s.state()
    b = _b_summary(st)
    assert [c for c in st["commits"] if c.status == CommitmentCandidateStatus.PENDING]
    assert [x for x in st["supps"] if x.status == SuppressionStatus.ACTIVE]
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    assert not [o for o in result.accepted if o.op == "new_matter"], \
        f"no new obligations on a completed arc: {c}"
    commit_id = next(m.id for m in snap.matters if "freepik" in m.title.lower()
                     and m.kind == "commitment")
    resol = [o for o in _ops(result, "resolve_matter")
             if o.data.get("matter_id") == commit_id]
    assert resol, f"C must complete the cancelled commitment: {c}"
    assert not [o for o in result.accepted if o.op == "same_as"]
    _record("freepik", model, "completed + suppression preserved, nothing added",
            b, c, "C-fixes-B")
    print(f"\n[FREEPIK/{model}] C-fixes-B latency={result.latency_s}s")


# ── V9 SAM ────────────────────────────────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_sam_disambiguated(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-sam")
    await _seed_loop(s.ws, "session-1", "seed1", "Studio Sam revised contract pending")
    await _seed_loop(s.ws, "session-1", "seed2", "Cousin Sam dinner Sunday")
    snap = await s.snap()
    await s.turn("e1", "external:studio_sam", "Signed revised contract copy attached.")
    st = await s.state()
    b = _b_summary(st)
    assert len([l for l in st["loops"] if l.status == OpenLoopStatus.OPEN]) == 2, \
        f"B misses the signature: {b}"
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    contract_id = next(m.id for m in snap.matters if "contract" in m.title.lower())
    dinner_id = next(m.id for m in snap.matters if "dinner" in m.title.lower())
    resol = [o for o in _ops(result, "resolve_matter")
             if o.data.get("matter_id") == contract_id]
    assert resol, f"C must close the contract on signature: {c}"
    assert not [o for o in result.accepted if o.op == "same_as"], f"never merge Sams: {c}"
    dinner = [o for o in result.accepted if o.data.get("matter_id") == dinner_id]
    assert dinner and dinner[0].op == "affirm_matter", f"dinner affirmed separate: {c}"
    _record("sam", model, "contract closed + dinner separate", b, c, "C-fixes-B")
    print(f"\n[SAM/{model}] C-fixes-B latency={result.latency_s}s")


# ── V10 TRIVIA ────────────────────────────────────────────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_trivia_restrained(async_client, monkeypatch, model):
    s = Live(async_client, monkeypatch, "ws-live2-trivia")
    snap = await s.snap()
    await s.turn("e1", "ashley", "Not sure whether I'll get lunch there.")
    await s.turn("e2", "ashley", "That joke about the seagull still makes me laugh.")
    await s.turn("e3", "ashley", "Might rain later, whatever.")
    st = await s.state()
    b = _b_summary(st)
    assert st["loops"] == [] and st["commits"] == [] and st["atts"] == []
    result = await s.reconstruct(snap, model)
    c = _c_summary(result)
    assert result.error == "", f"{result.error} {result.rejected}"
    assert not [o for o in result.accepted
                if o.op in ("new_matter", "uncertainty", "attend", "suppress")], \
        f"selective persistence: trivia stays trivial: {c}"
    covered = set()
    for o in _ops(result, "incidental"):
        covered.update(o.data.get("message_ids", []))
    assert {"e1", "e2", "e3"} <= covered, f"every turn discarded explicitly: {c}"
    _record("trivia", model, "all incidental, nothing persisted", b, c, "C-preserves-B")
    print(f"\n[TRIVIA/{model}] C-preserves-B latency={result.latency_s}s")

# ── GRADUATION PROOF: endpoint apply mode end-to-end ─────────────────────────

@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_apply_creates_missing_carlos_matter(async_client, monkeypatch, model):
    """A completed conversation is submitted; the missing debt matter becomes
    a durable ASK row with consolidation provenance. Nothing else appears."""
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    transcript = [
        {"message_id": "e1", "speaker": "ashley",
         "text": "Carlos still owes me the remaining balance, about twenty one hundred."},
        {"message_id": "e2", "speaker": "ashley", "text": "Did that ever come through?"},
        {"message_id": "e3", "speaker": "bank_feed",
         "text": "Incoming payment of nineteen hundred from Carlos."},
    ]
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": "ws-grad-carlos", "session_id": "s real-session",
              "mode": "apply", "user_peer_id": "ashley",
              "transcript": transcript})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply", body
    assert body["error"] == "", body
    assert "run_id" in body and body["run_id"]
    applied_kinds = [a["op"] for a in body["applied"]]
    assert "new_matter" in applied_kinds, f"missing matter must be created: {body}"
    assert not [a for a in body["applied"] if a["op"] not in
                ("new_matter", "affirm_matter", "incidental", "attend", "uncertainty",
                 "partial_fulfilment")], f"only safe tiers may apply: {body}"
    async with async_session_maker() as db:
        commits = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == "ws-grad-carlos"))).scalars().all()
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-grad-carlos"))).scalars().all()
        from src.models.consolidation import ConsolidationRun
        runs = (await db.execute(select(ConsolidationRun).where(
            ConsolidationRun.honcho_workspace_id == "ws-grad-carlos"))).scalars().all()
    rows = [c for c in commits if "carlos" in (c.title or "").lower()] + \
           [l for l in loops if "carlos" in (l.title or "").lower()]
    assert rows, "durable Carlos state must exist after apply"
    assert all("consolidation:" in (getattr(x, "source_message_id", "") or "")
               or getattr(x, "honcho_message_id", "") == "consolidation:s real-session"
               for x in rows), "provenance must cite the consolidation run"
    assert len(runs) == 1 and runs[0].mode == "apply" and runs[0].applied_count >= 1
    print(f"\n[GRAD-CARLOS] applied={applied_kinds} run={body['run_id'][:8]}")


@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_apply_resolves_chairs_without_resurrection(async_client, monkeypatch, model):
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    ws = "ws-grad-chairs"
    await _seed_loop(ws, "session-1", "seed1", "Confirm headcount with venue")
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": ws, "session_id": "session-1",
              "mode": "apply", "user_peer_id": "ashley",
              "transcript": [
                  {"message_id": "e1", "speaker": "ashley",
                   "text": "The chairs. I told the venue yes, 120 chairs, so that's done."},
                  {"message_id": "e2", "speaker": "ashley",
                   "text": "Did I ever sort the chairs?"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["error"] == "", body
    assert [a for a in body["applied"] if a["op"] == "resolve_matter"], \
        f"completion must apply: {body}"
    assert not [a for a in body["applied"] if a["op"] == "new_matter"], \
        "retrospective question must not become a row"
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
    assert len(loops) == 1 and loops[0].status == OpenLoopStatus.RESOLVED
    assert "consolidation:" in (loops[0].resolution_evidence or "")
    print(f"\n[GRAD-CHAIRS] resolved, loops={len(loops)}")


@needs_key
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [GEMINI])
async def test_live_apply_trivia_persists_nothing(async_client, monkeypatch, model):
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    ws = "ws-grad-trivia"
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": ws, "session_id": "s",
              "mode": "apply", "user_peer_id": "ashley",
              "transcript": [
                  {"message_id": "e1", "speaker": "ashley",
                   "text": "Not sure whether I'll get lunch there."},
                  {"message_id": "e2", "speaker": "ashley",
                   "text": "That joke about the seagull still makes me laugh."}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "apply" and body["error"] == "", body
    assert body["applied"] == [] or all(
        a["op"] == "incidental" for a in body["applied"]), \
        f"trivial session must persist nothing: {body}"
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == ws))).scalars().all()
        commits = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == ws))).scalars().all()
        atts = (await db.execute(select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == ws))).scalars().all()
    assert loops == [] and commits == [] and atts == [], \
        "apply mode must not mint state from trivia"
    print("\n[GRAD-TRIVIA] nothing persisted")
