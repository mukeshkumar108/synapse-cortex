"""Session -> Cortex consolidation verticals (experiment, SHADOW ONLY).

For each scenario: seed pre-session state -> snapshot -> run the full
session through real `/v1/events/turn` incremental ingest -> record the
incremental final state -> run the session consolidator (scripted STAND-IN
adapter: it stands in for the model judgement; what is REAL here is the
contract, the validation, the would-apply invariants, the shadow safety,
and the A-vs-B-vs-C comparison) -> assert the proposal matches product
truth and nothing was mutated.

Honest scope: these tests prove the semantic unit CAN express the needed
corrections with session context, and that the invariant layer holds.
They do not prove a production model judges perfectly — that needs a
live-model soak (next step).
"""
import re

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.commitment_candidate import CommitmentCandidateStatus
from src.models.expectation import Expectation
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import ExtractionTrace
from src.models.suppression import Suppression, SuppressionStatus
from src.models.commitment_candidate import CommitmentCandidate
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services import semantic_judge
from src.services.session_consolidation import (
    StartSnapshot,
    capture_snapshot,
    consolidate_session,
)

NOW = "2026-09-28T10:00:00+01:00"


# ── harness ─────────────────────────────────────────────────────────────────

class _TurnStub:
    """Per-turn scripted adapter (extractor-phase judges + turn interpreter
    defaulting to incidental so the incremental lane stays observable)."""

    def __init__(self, kinds: dict | None = None):
        self.kinds = kinds or {}
        self.calls: list = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        self.calls.append(prompt)
        if "TURN INTERPRETER" in prompt:
            return {"decision": "incidental", "primary_index": None,
                    "also_plausible": [], "confidence": 0.9,
                    "evidence_span": "", "rationale": "coexistence-fixture"}
        if "FULLY done" in prompt:
            kind = "fulfils"
        elif "PART of" in prompt:
            kind = "partially_fulfils"
        elif "settle/answer/complete" in prompt:
            kind = "resolves"
        elif "SAME specific" in prompt:
            kind = "same_matter"
        else:
            kind = "unknown"
        verdict = self.kinds.get(kind, "no")
        later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
        for stop in ("\nCONTEXT:", "\nRules:"):
            if stop in later:
                later = later.split(stop)[0]
                break
        later = later.strip()
        return {"verdict": verdict,
                "confidence": 0.85 if verdict == "yes" else 0.8,
                "evidence_span": later[:60] if verdict == "yes" else "",
                "rationale": "session-fixture"}


class _SessionStub:
    """STAND-IN for the session model. `build` receives the full prompt and
    returns {session_summary, ops}; it resolves real matter ids by matching
    titles in the prompt (a real model reads them directly)."""

    def __init__(self, build):
        self.build = build
        self.prompts: list = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        self.prompts.append(prompt)
        return self.build(prompt)


def _matter_ids(prompt: str) -> dict:
    """title-keyword -> matter id, parsed from the prompt's start-state block."""
    out = {}
    for mid, title in re.findall(
            r"\[matter ([0-9a-f-]{36})\] \S+ [\w/]+(?: owner=\S+)?: (.*)", prompt):
        out[title.strip().lower()] = mid
    return out


def _find(ids: dict, *keywords: str) -> str:
    for title, mid in ids.items():
        if all(k.lower() in title for k in keywords):
            return mid
    raise AssertionError(f"no matter matching {keywords} in {[t for t in ids]}")


def _ev(mid: str, span: str) -> dict:
    return {"message_ids": [mid], "spans": [{"message_id": mid, "span": span}]}


def _loop(*, key: str, text: str, title: str, refs: list,
          confidence: float = 0.9) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, open_loop_hint=title,
        operational_kind="open_loop", subject_refs=refs,
        confidence=confidence, formation="explicit",
        extractor_version="session-vertical",
    )


def _commit(*, key: str, text: str, title: str, refs: list,
            evidence_class: str = "implicit_self_commitment",
            authority: str = "act", actor: str | None = None) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, operational_kind="commitment_candidate",
        evidence_class=evidence_class, authority=authority,
        subject_refs=refs, actor_peer_id=actor,
        temporal_phrase="tomorrow", confidence=0.9, formation="explicit",
        extractor_version="session-vertical",
    )


def _event(*, key: str, text: str, refs: list, action: str = "fulfill",
           target_kind: str | None = None,
           suppression_hint: dict | None = None) -> ExtractionCandidate:
    hint: dict = {"action": action}
    if target_kind:
        hint["target_kind"] = target_kind
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=text[:120], operational_kind="event",
        subject_refs=refs, confidence=0.9, formation="explicit",
        extractor_version="session-vertical", resolution_hint=hint,
        suppression_hint=suppression_hint,
    )


def _semantic(*, key: str, text: str, confidence: float = 0.3) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=text[:120], operational_kind="semantic_only",
        subject_refs=[], confidence=confidence, formation="explicit",
        extractor_version="session-vertical",
    )


class Session:
    """Runs one scenario: seed -> snapshot -> session turns -> consolidate."""

    def __init__(self, async_client, monkeypatch, ws: str):
        self.c = async_client
        self.m = monkeypatch
        self.ws = ws
        self.transcript: list = []
        self.turn_stub = _TurnStub()

    async def turn(self, mid: str, sender: str, text: str,
                   cand: ExtractionCandidate | None,
                   kinds: dict | None = None):
        if kinds is not None:
            self.turn_stub = _TurnStub(kinds)
        self.m.setattr(semantic_judge, "_adapter", lambda: self.turn_stub)
        self.m.setattr(
            v1_events.turn_extractor, "extract_candidates",
            lambda *a, **k: ([cand] if cand is not None else []),
        )
        r = await self.c.post(
            "/v1/events/turn",
            json={"workspace_id": self.ws, "session_id": "session-1",
                  "honcho_message_id": mid, "peer_id": sender,
                  "text": text, "now": NOW, "timezone": "Europe/London"})
        assert r.status_code == 202, r.text
        self.transcript.append({"message_id": mid, "speaker": sender, "text": text})

    async def snapshot(self) -> StartSnapshot:
        async with async_session_maker() as db:
            return await capture_snapshot(
                db, workspace_id=self.ws, session_id="session-1")

    async def state(self):
        async with async_session_maker() as db:
            loops = (await db.execute(select(OpenLoop).where(
                OpenLoop.honcho_workspace_id == self.ws))).scalars().all()
            commits = (await db.execute(select(CommitmentCandidate).where(
                CommitmentCandidate.honcho_workspace_id == self.ws))).scalars().all()
            exps = (await db.execute(select(Expectation).where(
                Expectation.honcho_workspace_id == self.ws))).scalars().all()
            atts = (await db.execute(select(AttentionCandidate).where(
                AttentionCandidate.honcho_workspace_id == self.ws))).scalars().all()
            clars = (await db.execute(select(ClarificationCandidate).where(
                ClarificationCandidate.honcho_workspace_id == self.ws))).scalars().all()
            supps = (await db.execute(select(Suppression).where(
                Suppression.honcho_workspace_id == self.ws))).scalars().all()
            return {"loops": loops, "commits": commits, "exps": exps,
                    "atts": atts, "clars": clars, "supps": supps}

    async def consolidate(self, build):
        stub = _SessionStub(build)
        snap = self._snap
        async with async_session_maker() as db:
            before = await self._fingerprint(db)
            result = await consolidate_session(
                db, workspace_id=self.ws, session_id="session-1",
                transcript=self._transcript_since_snap(),
                start_snapshot=snap, adapter=stub)
            after = await self._fingerprint(db)
        assert before == after, "shadow consolidation must mutate nothing"
        return result, stub

    async def _fingerprint(self, db):
        out = []
        for model, filt in (
                (OpenLoop, OpenLoop.honcho_workspace_id == self.ws),
                (CommitmentCandidate, CommitmentCandidate.honcho_workspace_id == self.ws),
                (Expectation, Expectation.honcho_workspace_id == self.ws),
                (AttentionCandidate, AttentionCandidate.honcho_workspace_id == self.ws),
                (Suppression, Suppression.honcho_workspace_id == self.ws)):
            rows = (await db.execute(select(model).where(filt))).scalars().all()
            for r in rows:
                out.append((model.__tablename__, str(r.id),
                            str(getattr(r, "status", "")),
                            getattr(r, "title", None) or getattr(r, "content", None) or getattr(r, "topic_or_entity", None)))
        return sorted(out, key=str)

    def _transcript_since_snap(self):
        return [t for t in self.transcript if t["message_id"] not in self._seed_ids]

    async def begin_session(self):
        self._snap = await self.snapshot()
        self._seed_ids = {t["message_id"] for t in self.transcript}


def _accepted_by(result, op: str):
    return [o for o in result.accepted if o.op == op]


def _would(result, op: str):
    return [w for w in result.would_apply if w["op"] == op]


# ── 1. CHAIRS ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chairs_completed_no_violation_no_resurrection(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-chairs")
    await s.turn("seed1", "ashley", "I'll confirm the chairs with the venue tomorrow.",
                 _commit(key="c1", text="I'll confirm the chairs with the venue tomorrow.",
                         title="Confirm chairs with venue", refs=[]))
    await s.begin_session()
    await s.turn("e1", "ashley", "The chairs. I told the venue yes, 120 chairs, so that's done.",
                 _event(key="e1", text="The chairs. I told the venue yes, 120 chairs, so that's done.",
                        refs=[], action="fulfill"),
                 kinds={"fulfils": "yes"})
    await s.turn("e2", "ashley", "Did I ever sort the chairs?",
                 _loop(key="q1", text="Did I ever sort the chairs?",
                       title="Did I ever sort the chairs?", refs=[]))
    st = await s.state()
    assert [c for c in st["commits"]
            if c.status == CommitmentCandidateStatus.VIOLATED] == [], \
        "incremental baseline must not violate completed chairs"

    def build(prompt):
        ids = _matter_ids(prompt)
        cid = _find(ids, "chairs")
        return {"session_summary": "Chairs confirmed 120 at venue; recall answered from history.",
                "ops": [
                    {"op": "affirm_matter", "matter_id": cid,
                     "confidence": 0.9, "rationale": "completed, no violation outstanding"},
                    {"op": "incidental", "message_ids": ["e2"],
                     "confidence": 0.9, "rationale": "retrospective question, settled history answers"},
                ]}

    result, stub = await s.consolidate(build)
    assert result.error == ""
    assert len(_accepted_by(result, "affirm_matter")) == 1
    assert result.rejected == []
    assert all(w["would_apply"] for w in result.would_apply)
    assert "chairs" in stub.prompts[0] and "120 chairs" in stub.prompts[0], \
        "whole trajectory must reach the model"


# ── 2. CARLOS / PARTIAL ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_carlos_partial_remainder_survives(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-carlos")
    await s.turn("seed1", "ashley", "Carlos still owes me £2,100 from the event.",
                 _loop(key="d1", text="Carlos still owes me £2,100 from the event.",
                       title="Carlos still owes £2,100 from the event", refs=["Carlos"]))
    await s.begin_session()
    await s.turn("e1", "external:carlos", "The bank delayed it. I'll send it tomorrow.",
                 _commit(key="p1", text="The bank delayed it. I'll send it tomorrow.",
                         title="Carlos will send the £2,100 tomorrow", refs=["Carlos"],
                         evidence_class="character_promise", authority="act"))
    await s.turn("e2", "bank_feed", "Incoming payment £1,900 from Carlos.",
                 _event(key="b1", text="Incoming payment £1,900 from Carlos.",
                        refs=["Carlos"], action="fulfill"),
                 kinds={"fulfils": "no", "partially_fulfils": "yes"})
    await s.turn("e3", "ashley", "Did that ever come through?", None)
    st = await s.state()
    assert [c for c in st["commits"]
            if getattr(c, "owner_peer_id", "") == "ashley"
            and str(getattr(c.authority, "value", c.authority)) == "act"] == [], \
        "counterparty promise must never become a user ACT commitment"

    def build(prompt):
        ids = _matter_ids(prompt)
        debt = _find(ids, "£2,100")
        return {"session_summary": "Carlos debt partly paid; £200 remainder outstanding.",
                "ops": [
                    {"op": "partial_fulfilment", "matter_id": debt,
                     "evidence": _ev("e2", "£1,900"), "remainder": "£200 of £2,100 still outstanding",
                     "confidence": 0.85, "rationale": "bank evidence is part, not full"},
                    {"op": "incidental", "message_ids": ["e3"],
                     "confidence": 0.8, "rationale": "'that' = the Carlos payment; no new matter"},
                ]}

    result, _ = await s.consolidate(build)
    partials = _accepted_by(result, "partial_fulfilment")
    assert len(partials) == 1 and "200" in partials[0].data["remainder"]
    assert all(w["would_apply"] for w in _would(result, "partial_fulfilment"))
    assert not _accepted_by(result, "new_matter"), "references must not mint matters"


# ── 3. SCHOOL PAYMENT + FORM ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_school_payment_resolves_form_stays_distinct(async_client, monkeypatch):
    # Mirrors the proven Track D pendulum structure (payment AND form as
    # loops): structural release closes the payment on shared vocabulary
    # while the consumed-evidence guard stops the double-close of the form.
    s = Session(async_client, monkeypatch, "ws-cons-school")
    await s.turn("seed1", "ashley", "School trip payment due Friday.",
                 _loop(key="s1", text="School trip payment due Friday.",
                       title="School trip payment due Friday", refs=[]))
    await s.turn("seed2", "ashley", "School trip permission form needs signing.",
                 _loop(key="f1", text="School trip permission form needs signing.",
                       title="School trip permission form needs signing", refs=[]))
    await s.begin_session()
    await s.turn("e1", "bank_feed", "School trip payment received, thank you.",
                 _event(key="b1", text="School trip payment received, thank you.",
                        refs=[], action="fulfill", target_kind="open_loop"),
                 kinds={"fulfils": "yes", "resolves": "yes"})
    st = await s.state()
    by_title = {(l.title or ""): l.status for l in st["loops"]}
    assert by_title.get("School trip payment due Friday") == OpenLoopStatus.RESOLVED
    assert by_title.get("School trip permission form needs signing") == OpenLoopStatus.OPEN
    assert st["commits"] == [], "no duplicate commitment minted"

    def build(prompt):
        ids = _matter_ids(prompt)
        pay = _find(ids, "payment due friday")
        form = _find(ids, "permission form")
        return {"session_summary": "Bank payment settled the money; the form is a separate matter.",
                "ops": [
                    {"op": "affirm_matter", "matter_id": pay,
                     "confidence": 0.9, "rationale": "payment evidence closed the money thread"},
                    {"op": "affirm_matter", "matter_id": form,
                     "confidence": 0.9, "rationale": "form is distinct, still open"},
                ]}

    result, _ = await s.consolidate(build)
    assert len(_accepted_by(result, "affirm_matter")) == 2
    assert not _accepted_by(result, "same_as"), "payment and form must never merge"


# ── 4. STUDIO SAM vs COUSIN SAM ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sam_no_collision_signature_closes_contract(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-sam")
    await s.turn("seed1", "ashley", "Studio Sam needs to send the revised contract.",
                 _loop(key="s1", text="Studio Sam needs to send the revised contract.",
                       title="Studio Sam revised contract pending", refs=["Studio Sam"]))
    await s.turn("seed2", "ashley", "Cousin Sam is coming for dinner Sunday.",
                 _loop(key="d1", text="Cousin Sam is coming for dinner Sunday.",
                       title="Cousin Sam dinner Sunday", refs=["Cousin Sam"]),
                 kinds={"same_matter": "no"})
    await s.begin_session()
    await s.turn("e1", "external:studio_sam", "I'll send the revised contract tomorrow.",
                 _commit(key="p1", text="I'll send the revised contract tomorrow.",
                         title="Sam will send revised contract", refs=["Studio Sam"],
                         evidence_class="character_promise", authority="act"))
    await s.turn("e2", "ashley", "Gave verbal approval on the call.",
                 _event(key="v1", text="Gave verbal approval on the call.",
                        refs=["Studio Sam"], action="fulfill"),
                 kinds={"fulfils": "no", "partially_fulfils": "no"})
    await s.turn("e3", "external:studio_sam", "Signed revised contract copy attached.",
                 _event(key="g1", text="Signed revised contract copy attached.",
                        refs=["Studio Sam"], action="fulfill", target_kind="open_loop"),
                 kinds={"fulfils": "yes", "resolves": "yes"})
    st = await s.state()
    assert [c for c in st["commits"]
            if getattr(c, "owner_peer_id", "") == "ashley"
            and str(getattr(c.authority, "value", c.authority)) == "act"] == []
    dinners = [l for l in st["loops"] if "dinner" in (l.title or "").lower()]
    assert len(dinners) == 1 and dinners[0].status == OpenLoopStatus.OPEN

    def build(prompt):
        ids = _matter_ids(prompt)
        contract = _find(ids, "revised contract pending")
        dinner = _find(ids, "dinner")
        return {"session_summary": "Signature executed the contract; verbal approval did not; dinner untouched.",
                "ops": [
                    {"op": "resolve_matter", "matter_id": contract, "via": "completed",
                     "evidence": _ev("e3", "Signed revised contract"),
                     "confidence": 0.9, "rationale": "written execution arrived"},
                    {"op": "affirm_matter", "matter_id": dinner,
                     "confidence": 0.95, "rationale": "different Sam, separate matter"},
                ]}

    result, _ = await s.consolidate(build)
    resol = _accepted_by(result, "resolve_matter")
    assert len(resol) == 1
    # Incremental lane already closed it deterministically: the guard must
    # refuse to re-resolve (resolved-state protection), not double-close.
    assert _would(result, "resolve_matter")[0]["would_apply"] is False
    assert "resolved_state_protected" in _would(result, "resolve_matter")[0]["reason"]
    assert not _accepted_by(result, "same_as")


# ── 5. FREEPIK (strong case: preserve, do not regress) ───────────────────────

@pytest.mark.asyncio
async def test_freepik_deferral_dependency_cancellation_preserved(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-freepik")
    await s.turn("seed1", "ashley", "I'll cancel the Freepik renewal on Friday.",
                 _commit(key="f1", text="I'll cancel the Freepik renewal on Friday.",
                         title="Cancel Freepik renewal Friday", refs=[]))
    await s.turn("seed2", "ashley", "Pause Freepik renewal reminders until Friday.",
                 _event(key="h1", text="Pause Freepik renewal reminders until Friday.",
                        refs=[], action="fulfill",
                        suppression_hint={"direction": "refuse", "target_type": "topic",
                                          "topic_or_entity": "Freepik renewal"}))
    await s.begin_session()
    await s.turn("e1", "ashley", "Push the Freepik cancellation to tomorrow, client still needs it.",
                 _event(key="r1", text="Push the Freepik cancellation to tomorrow.",
                        refs=[], action="reschedule"))
    await s.turn("e2", "ashley", "Cancelled Freepik myself after client approval.",
                 _event(key="c1", text="Cancelled Freepik myself after client approval.",
                        refs=[], action="fulfill"),
                 kinds={"fulfils": "yes"})
    st = await s.state()
    assert [c for c in st["commits"]
            if c.status == CommitmentCandidateStatus.VIOLATED] == [], \
        "no false user failure across deferral and cancellation"
    assert [x for x in st["supps"] if x.status == SuppressionStatus.ACTIVE], \
        "deferral boundary must survive"

    def build(prompt):
        ids = _matter_ids(prompt)
        freepik = _find(ids, "freepik")
        return {"session_summary": "Deferred for the client, then cancelled by the user; boundary held throughout.",
                "ops": [
                    {"op": "affirm_matter", "matter_id": freepik,
                     "confidence": 0.9, "rationale": "completed by user action, never violated"},
                ]}

    result, _ = await s.consolidate(build)
    assert len(_accepted_by(result, "affirm_matter")) == 1
    assert result.rejected == []
    assert all(w["would_apply"] for w in result.would_apply)


# ── 6. MATT SURGERY ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_matt_waiting_releases_fever_phase_persists(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-matt")
    await s.turn("seed1", "ashley", "Matt has surgery tomorrow.",
                 _loop(key="m1", text="Matt has surgery tomorrow.",
                       title="Matt surgery tomorrow, waiting for news", refs=["Matt"]))
    await s.begin_session()
    await s.turn("e1", "ashley", "Matt is out of surgery, it went well.",
                 _event(key="w1", text="Matt is out of surgery, it went well.",
                        refs=["Matt"], action="fulfill", target_kind="open_loop"),
                 kinds={"fulfils": "yes", "resolves": "yes"})
    await s.turn("e2", "ashley", "Matt has a fever after the surgery, watching it.",
                 _loop(key="f1", text="Matt has a fever after the surgery, watching it.",
                       title="Matt post-surgery fever watch", refs=["Matt"]),
                 kinds={"resolves": "no", "same_matter": "no"})
    st = await s.state()
    fevers = [l for l in st["loops"] if "fever" in (l.title or "").lower()
              and l.status == OpenLoopStatus.OPEN]
    assert len(fevers) == 1, "recovery watch must persist as its own phase"

    def build(prompt):
        ids = _matter_ids(prompt)
        fever = _find(ids, "fever")
        waiting = _find(ids, "waiting for news")
        return {"session_summary": "Surgery succeeded (waiting released); fever is the live phase.",
                "ops": [
                    {"op": "affirm_matter", "matter_id": waiting,
                     "confidence": 0.9, "rationale": "waiting phase settled by good outcome"},
                    {"op": "affirm_matter", "matter_id": fever,
                     "confidence": 0.9, "rationale": "recovery watch is the live thread"},
                ]}

    result, _ = await s.consolidate(build)
    assert len(_accepted_by(result, "affirm_matter")) == 2
    assert not _accepted_by(result, "resolve_matter"), \
        "consolidation must not close the live fever watch"


# ── 7. NERVOUS MEETING ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_meeting_uncertainty_survives_without_interrogation(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-meeting")
    await s.begin_session()
    await s.turn("e1", "ashley", "I've got that meeting tomorrow and I'm a bit nervous.",
                 _loop(key="m1", text="I've got that meeting tomorrow and I'm a bit nervous.",
                       title="Meeting tomorrow, nervous, unknown what for", refs=[],
                       confidence=0.4))
    st = await s.state()
    assert len([l for l in st["loops"] if l.status == OpenLoopStatus.OPEN]) == 1

    def build(prompt):
        ids = _matter_ids(prompt)
        meeting = _find(ids, "meeting")
        return {"session_summary": "Important meeting ahead; details unknown; no interrogation.",
                "ops": [
                    {"op": "uncertainty", "content": "Meeting tomorrow matters to the user; what it is for was never caught",
                     "alternatives": [], "related_ids": [meeting],
                     "evidence": _ev("e1", "nervous"),
                     "confidence": 0.75, "rationale": "emotional salience + future outcome, details missing"},
                    {"op": "attend", "content": "After the meeting: how did it go, and what was it for",
                     "related_ids": [meeting], "evidence": _ev("e1", "meeting tomorrow"),
                     "confidence": 0.7, "rationale": "natural future follow-up opportunity"},
                ]}

    result, _ = await s.consolidate(build)
    assert result.error == "" and result.rejected == []
    assert len(_accepted_by(result, "uncertainty")) == 1
    assert len(_accepted_by(result, "attend")) == 1
    assert all(w["would_apply"] for w in result.would_apply)


# ── 8. INCIDENTAL LUNCH ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lunch_incidental_no_durable_matter(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-lunch")
    await s.begin_session()
    await s.turn("e1", "ashley", "Not sure whether I'll get lunch there.",
                 _semantic(key="z1", text="Not sure whether I'll get lunch there."))
    st = await s.state()
    assert st["loops"] == [] and st["atts"] == []

    def build(prompt):
        assert "lunch" in prompt
        return {"session_summary": "Nothing durable: passing lunch remark.",
                "ops": [{"op": "incidental", "message_ids": ["e1"],
                         "confidence": 0.95, "rationale": "low-consequence aside, no longitudinal weight"}]}

    result, _ = await s.consolidate(build)
    assert len(_accepted_by(result, "incidental")) == 1
    assert not [o for o in result.accepted if o.op in
                ("new_matter", "attend", "uncertainty")], \
        "session context must distinguish incidental from meaningful uncertainty"


# ── 9. NECK BOUNDARY ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_neck_boundary_survives_without_surfaced_obligation(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-neck")
    await s.begin_session()
    await s.turn("e1", "ashley", "Leave my neck alone for now.",
                 _event(key="n1", text="Leave my neck alone for now.", refs=[],
                        action="fulfill",
                        suppression_hint={"direction": "refuse", "target_type": "topic",
                                          "topic_or_entity": "neck"}))
    st = await s.state()
    assert [x for x in st["supps"] if x.status == SuppressionStatus.ACTIVE]

    def build(prompt):
        return {"session_summary": "User set a boundary around the neck topic.",
                "ops": [{"op": "suppress", "topic_or_entity": "neck",
                         "reason": "explicit user boundary",
                         "evidence": _ev("e1", "Leave my neck alone"),
                         "confidence": 0.95, "rationale": "direct boundary statement"}]}

    result, _ = await s.consolidate(build)
    assert len(_accepted_by(result, "suppress")) == 1
    # Already suppressed incrementally: idempotent guard refuses the double.
    assert _would(result, "suppress")[0]["would_apply"] is False
    assert "duplicate_suppression_idempotent" in _would(result, "suppress")[0]["reason"]
    assert not [o for o in result.accepted
                if o.op in ("new_matter", "attend")
                and "neck" in str(o.data).lower()], \
        "must never mint a surfaced obligation to mention the muted topic"


# ── 10. ENTITY-LESS REFERENCES at session scope ───────────────────────────────

@pytest.mark.asyncio
async def test_entityless_references_resolve_in_full_trajectory(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-entityless")
    await s.turn("seed1", "ashley", "Studio Sam is sending the revised contract.",
                 _loop(key="s1", text="Studio Sam is sending the revised contract.",
                       title="Studio Sam revised contract pending", refs=["Studio Sam"]))
    await s.turn("seed2", "ashley", "Carlos still owes me £2,100 from the event.",
                 _loop(key="d1", text="Carlos still owes me £2,100 from the event.",
                       title="Carlos still owes £2,100 from the event", refs=["Carlos"]))
    await s.turn("seed3", "ashley", "Matt has surgery tomorrow.",
                 _loop(key="m1", text="Matt has surgery tomorrow.",
                       title="Matt surgery tomorrow, waiting for news", refs=["Matt"]))
    await s.begin_session()
    # All four reference turns yield ZERO extractor candidates live.
    await s.turn("e1", "ashley", "What happened with the paperwork?", None)
    await s.turn("e2", "ashley", "Did that ever come through?", None)
    await s.turn("e3", "ashley", "How's he doing now?", None)
    await s.turn("e4", "ashley", "¿Y eso, llegó al final?", None)
    st = await s.state()
    assert len([l for l in st["loops"] if l.status == OpenLoopStatus.OPEN]) == 3

    def build(prompt):
        ids = _matter_ids(prompt)
        sam = _find(ids, "contract")
        carlos = _find(ids, "£2,100")
        matt = _find(ids, "matt")
        for mid in ("e1", "e2", "e3", "e4"):
            assert f"[msg:{mid}]" in prompt, f"turn {mid} must reach the model"
        return {"session_summary": "Four references into three live matters; nothing new.",
                "ops": [
                    {"op": "attend", "content": "Contract still pending — user asked again about the paperwork",
                     "related_ids": [sam], "evidence": _ev("e1", "paperwork"),
                     "confidence": 0.8,
                     "rationale": "'paperwork' = the Sam contract thread in this trajectory"},
                    {"op": "uncertainty", "content": "'that'/'eso' could be the Carlos payment; trajectory supports no other money matter",
                     "alternatives": [], "related_ids": [carlos],
                     "evidence": _ev("e2", "come through"),
                     "confidence": 0.7, "rationale": "deictic + Spanish paraphrase, one money matter live"},
                    {"op": "incidental", "message_ids": ["e3", "e4"],
                     "confidence": 0.75, "rationale": "'he' = Matt; Spanish echo adds no new state"},
                    {"op": "affirm_matter", "matter_id": matt,
                     "confidence": 0.9, "rationale": "still waiting, unchanged"},
                ]}

    result, stub = await s.consolidate(build)
    assert result.error == "" and result.rejected == []
    assert not _accepted_by(result, "new_matter"), \
        "four references must mint zero new matters"
    covered = set()
    for o in result.accepted:
        covered.update(o.data.get("evidence", {}).get("message_ids", []))
        covered.update(o.data.get("message_ids", []))
    assert {"e1", "e2", "e3", "e4"} <= covered, \
        "every reference turn must be accounted for in the delta"
    assert all(w["would_apply"] for w in result.would_apply)


# ── failure / recovery ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_adapter_holds_state_for_retry(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-noadapter")
    await s.turn("seed1", "ashley", "Matt has surgery tomorrow.",
                 _loop(key="m1", text="Matt has surgery tomorrow.",
                       title="Matt surgery tomorrow, waiting for news", refs=["Matt"]))
    await s.begin_session()
    await s.turn("e1", "ashley", "How's he doing now?", None)
    before = await s.state()
    async with async_session_maker() as db:
        result = await consolidate_session(
            db, workspace_id=s.ws, session_id="session-1",
            transcript=s._transcript_since_snap(),
            start_snapshot=s._snap, adapter=None)
    assert result.error == "no_adapter" and result.accepted == []
    after = await s.state()
    assert len(before["loops"]) == len(after["loops"])
    async with async_session_maker() as db:
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == s.ws,
            ExtractionTrace.stage == "session_consolidation"))).scalars().all()
    assert traces and traces[-1].status == "error"


@pytest.mark.asyncio
async def test_invalid_ops_rejected_nothing_mutates(async_client, monkeypatch):
    s = Session(async_client, monkeypatch, "ws-cons-invalid")
    await s.turn("seed1", "ashley", "Matt has surgery tomorrow.",
                 _loop(key="m1", text="Matt has surgery tomorrow.",
                       title="Matt surgery tomorrow, waiting for news", refs=["Matt"]))
    await s.begin_session()
    await s.turn("e1", "ashley", "How's he doing now?", None)

    class BadStub:
        async def generate_structured(self, **kw):
            return {"session_summary": "bad", "ops": [
                {"op": "teleport_matter", "confidence": 0.9, "rationale": "x"},
                {"op": "resolve_matter", "matter_id": "00000000-0000-0000-0000-000000000000",
                 "via": "completed",
                 "evidence": {"message_ids": ["e1"],
                              "spans": [{"message_id": "e1", "span": "he doing"}]},
                 "confidence": 0.9, "rationale": "ghost target"},
                {"op": "affirm_matter", "matter_id": "00000000-0000-0000-0000-000000000000",
                 "confidence": 0.9, "rationale": "ghost"},
                {"op": "new_matter", "title": "Fabricated", "matter_kind": "obligation",
                 "evidence": {"message_ids": ["nope"],
                              "spans": [{"message_id": "nope", "span": "zzz"}]},
                 "confidence": 0.9, "rationale": "bad evidence"},
            ]}

    async with async_session_maker() as db:
        before = await s._fingerprint(db)
        result = await consolidate_session(
            db, workspace_id=s.ws, session_id="session-1",
            transcript=s._transcript_since_snap(),
            start_snapshot=s._snap, adapter=BadStub())
        after = await s._fingerprint(db)
    assert result.accepted == []
    assert len(result.rejected) == 4
    assert before == after


@pytest.mark.asyncio
async def test_empty_transcript_no_change(async_client, monkeypatch):
    async with async_session_maker() as db:
        result = await consolidate_session(
            db, workspace_id="ws-cons-empty", session_id="session-1",
            transcript=[], start_snapshot=StartSnapshot(), adapter=_SessionStub(
                lambda p: (_ for _ in ()).throw(AssertionError("no call expected"))))
    assert result.summary.startswith("empty session") and result.accepted == []


@pytest.mark.asyncio
async def test_kill_switch_disables_consolidation(async_client, monkeypatch):
    monkeypatch.setenv("SESSION_CONSOLIDATION_ENABLED", "0")
    async with async_session_maker() as db:
        result = await consolidate_session(
            db, workspace_id="ws-cons-kill", session_id="session-1",
            transcript=[{"message_id": "m1", "speaker": "ashley", "text": "hello there friend"}],
            start_snapshot=StartSnapshot(), adapter=_SessionStub(
                lambda p: (_ for _ in ()).throw(AssertionError("no call expected"))))
    assert result.error == "disabled" and result.accepted == []


@pytest.mark.asyncio
async def test_consolidate_endpoint_shadow_shape(async_client, monkeypatch):
    from src.services import semantic_judge
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: _SessionStub(
        lambda prompt: {"session_summary": "endpoint check",
                        "ops": [{"op": "incidental", "message_ids": ["m1"],
                                 "confidence": 0.9, "rationale": "smoke"}]}))
    r = await async_client.post(
        "/v1/sessions/consolidate",
        json={"workspace_id": "ws-cons-http", "session_id": "session-1",
              "transcript": [{"message_id": "m1", "speaker": "ashley",
                              "text": "just thinking out loud here"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "shadow"
    assert body["accepted"] == [{"op": "incidental", "data": {"message_ids": ["m1"]},
                                "confidence": 0.9, "rationale": "smoke"}]
