"""Track E live boundary — bounded semantic turn interpretation.

The extractor emits ZERO candidates for pure references ("What happened
with the paperwork?", "Did that ever come through?", "How's he doing?"),
so every downstream path starves and the turn vanishes. This suite proves
the entry-point judgement: one bounded model decision over (raw utterance
+ live matters), with code owning validation, ambiguity policy, mutation.

Recall AND precision: silence on everything is failure; turning everything
into durable state is also failure.
"""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import ExtractionTrace
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services import semantic_judge
from src.services.turn_interpretation import (
    LiveMatter,
    build_prompt,
    interpret_turn,
)

NOW = "2026-09-28T10:00:00+01:00"


class _DualStub:
    """Scripted adapter serving both the turn interpreter (by utterance) and
    the legacy semantic judge (by kind). Records every call for budget
    assertions. `interp` maps utterance -> response dict."""

    MARK = "TURN INTERPRETER"

    def __init__(self, interp: dict, kinds: dict | None = None):
        self.interp = interp
        self.kinds = kinds or {}
        self.calls: list = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        self.calls.append(prompt)
        if self.MARK in prompt:
            utter = prompt.split("UTTERANCE:\n", 1)[1].split("\n\nDecide")[0].strip()
            resp = self.interp.get(utter)
            if resp is None:
                return {"decision": "incidental", "primary_index": None,
                        "also_plausible": [], "confidence": 0.9,
                        "evidence_span": "", "rationale": "unstubbed->incidental"}
            return dict(resp)
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
                "rationale": "live-boundary-fixture"}

    def interp_calls(self):
        return [c for c in self.calls if self.MARK in c]


def _ref(idx: int, span: str, also: list | None = None, conf: float = 0.85):
    return {"decision": "reference", "primary_index": idx,
            "also_plausible": also or [], "confidence": conf,
            "evidence_span": span, "rationale": "fixture"}


def _new(span: str, conf: float = 0.8):
    return {"decision": "new", "primary_index": None,
            "also_plausible": [], "confidence": conf,
            "evidence_span": span, "rationale": "fixture"}


def _incidental():
    return {"decision": "incidental", "primary_index": None,
            "also_plausible": [], "confidence": 0.9,
            "evidence_span": "", "rationale": "fixture"}


def _uncertain(span: str, primary: int | None = None, also: list | None = None):
    return {"decision": "uncertain", "primary_index": primary,
            "also_plausible": also or [], "confidence": 0.7,
            "evidence_span": span, "rationale": "fixture"}


def _loop_candidate(*, key: str, text: str, title: str, refs: list,
                    confidence: float = 0.9) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, open_loop_hint=title,
        operational_kind="open_loop", subject_refs=refs,
        confidence=confidence, formation="explicit",
        extractor_version="live-boundary",
    )


async def _send(async_client, monkeypatch, *, workspace_id: str, sender: str,
                message_id: str, text: str,
                candidate: ExtractionCandidate | None,
                stub: _DualStub, session_id: str = "session-1"):
    """Zero-yield turns pass candidate=None (the live extractor shape for
    pure references); seeding turns pass a real candidate."""
    monkeypatch.setattr(semantic_judge, "_adapter", lambda: stub)
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *args, **kwargs: ([candidate] if candidate is not None else []),
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={"workspace_id": workspace_id, "session_id": session_id,
              "honcho_message_id": message_id, "peer_id": sender,
              "text": text, "now": NOW, "timezone": "Europe/London"},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _state(workspace_id: str):
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
        ).order_by(OpenLoop.created_at))).scalars().all()
        attentions = (await db.execute(select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == workspace_id,
        ))).scalars().all()
        clarifications = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == workspace_id,
        ))).scalars().all()
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == workspace_id,
            ExtractionTrace.stage == "turn_interpretation",
        ))).scalars().all()
        return loops, attentions, clarifications, traces


def _open(loops):
    return [l for l in loops if l.status == OpenLoopStatus.OPEN]


# ── unit: contract validation ───────────────────────────────────────────────

def _matters():
    return [LiveMatter(id="a", title="Sam contract"),
            LiveMatter(id="b", title="Solicitor forms")]


@pytest.mark.asyncio
async def test_unit_truncates_live_set_to_budget():
    many = [LiveMatter(id=str(i), title=f"matter number {i} with a long tail") for i in range(6)]
    prompt = build_prompt("What happened?", many)
    assert "[4]" not in prompt and "[3]" in prompt
    assert len(prompt) <= 2000


@pytest.mark.asyncio
async def test_unit_rejects_bad_index_span_confidence():
    text = "What happened with the paperwork?"
    m = _matters()

    class S:
        def __init__(self, resp):
            self.resp = resp

        async def generate_structured(self, **kw):
            return self.resp

    assert await interpret_turn(text, m, adapter=S(
        {"decision": "reference", "primary_index": 9, "also_plausible": [],
         "confidence": 0.9, "evidence_span": text, "rationale": "x"})) is None
    assert await interpret_turn(text, m, adapter=S(
        {"decision": "reference", "primary_index": 0, "also_plausible": [],
         "confidence": 0.9, "evidence_span": "not in the utterance", "rationale": "x"})) is None
    assert await interpret_turn(text, m, adapter=S(
        {"decision": "reference", "primary_index": 0, "also_plausible": [],
         "confidence": 0.2, "evidence_span": text, "rationale": "x"})) is None
    assert await interpret_turn(text, m, adapter=S(
        {"decision": "vibes", "primary_index": None, "also_plausible": [],
         "confidence": 0.9, "evidence_span": "", "rationale": "x"})) is None
    assert await interpret_turn(text, m, adapter=None) is None
    assert await interpret_turn("ok", m, adapter=S(
        {"decision": "new", "primary_index": None, "also_plausible": [],
         "confidence": 0.9, "evidence_span": "ok", "rationale": "x"})) is None
    good = await interpret_turn(text, m, adapter=S(
        {"decision": "reference", "primary_index": 1, "also_plausible": [0],
         "confidence": 0.8, "evidence_span": text, "rationale": "x"}))
    assert good is not None and good.primary_id == "b" and good.also_ids == ["a"]


# ── recall: listed soak cases ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paperwork_reference_reuses_solo_matter(async_client, monkeypatch):
    ws = "ws-live-paperwork"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Studio Sam is sending the revised contract.",
                candidate=_loop_candidate(
                    key="s1", text="Studio Sam is sending the revised contract.",
                    title="Studio Sam revised contract pending", refs=["Studio Sam"]),
                stub=seed)
    stub = _DualStub(interp={
        "What happened with the paperwork?": _ref(0, "What happened with the paperwork?")})
    body = await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                       message_id="m2", text="What happened with the paperwork?",
                       candidate=None, stub=stub)
    assert body["turn_interpretation"]["interpreted"] is True
    assert len(stub.interp_calls()) == 1, "exactly one bounded judgement per turn"
    loops, attentions, clarifications, traces = await _state(ws)
    live = _open(loops)
    assert len(live) == 1 and "contract" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []
    assert {t.status for t in traces} == {"accepted_reference"}


@pytest.mark.asyncio
async def test_paperwork_ambiguous_contract_vs_solicitor_holds(async_client, monkeypatch):
    ws = "ws-live-ambig"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Studio Sam is sending the revised contract.",
                candidate=_loop_candidate(
                    key="s1", text="Studio Sam is sending the revised contract.",
                    title="Studio Sam revised contract pending", refs=["Studio Sam"]),
                stub=seed)
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="Solicitor forms need signing this week.",
                candidate=_loop_candidate(
                    key="s2", text="Solicitor forms need signing this week.",
                    title="Solicitor forms need signing", refs=["solicitor"]),
                stub=seed)
    stub = _DualStub(interp={
        "What happened with the paperwork?": _uncertain(
            "What happened with the paperwork?", primary=0, also=[1])})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m3", text="What happened with the paperwork?",
                candidate=None, stub=stub)
    loops, attentions, clarifications, traces = await _state(ws)
    assert len(_open(loops)) == 2, "no merge, no fresh loop"
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions
    held = " ".join((a.content or "") for a in attentions).lower()
    assert "contract" in held and "solicitor" in held
    assert {t.status for t in traces} == {"held_uncertain"}


@pytest.mark.asyncio
async def test_two_carlos_payments_hold(async_client, monkeypatch):
    ws = "ws-live-twopay"
    seed = _DualStub(interp={}, kinds={"same_matter": "no"})
    for i, (key, title) in enumerate(
            [("q1", "Carlos owes £2,100 event debt"),
             ("q2", "Carlos flight reimbursement outstanding")]):
        await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                    message_id=f"m{i}", text=title,
                    candidate=_loop_candidate(key=key, text=title, title=title,
                                              refs=["Carlos"]),
                    stub=seed)
    stub = _DualStub(interp={
        "Did that ever come through?": _uncertain("Did that ever come through?")})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m3", text="Did that ever come through?",
                candidate=None, stub=stub)
    loops, attentions, clarifications, _ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    assert len(_open(loops)) == 2


@pytest.mark.asyncio
async def test_pronoun_two_people_hold(async_client, monkeypatch):
    ws = "ws-live-mattmark"
    seed = _DualStub(interp={}, kinds={"same_matter": "no"})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Matt has surgery tomorrow.",
                candidate=_loop_candidate(
                    key="d1", text="Matt has surgery tomorrow.",
                    title="Matt surgery tomorrow, waiting for news", refs=["Matt"]),
                stub=seed)
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="Mark is waiting on his test results.",
                candidate=_loop_candidate(
                    key="d2", text="Mark is waiting on his test results.",
                    title="Mark waiting on test results", refs=["Mark"]),
                stub=seed)
    stub = _DualStub(interp={
        "How's he doing now?": _uncertain("How's he doing now?", primary=0, also=[1])})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m3", text="How's he doing now?",
                candidate=None, stub=stub)
    loops, attentions, clarifications, _ = await _state(ws)
    assert len(_open(loops)) == 2, "must not guess between two people"
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions


@pytest.mark.asyncio
async def test_spanish_reference_reuses(async_client, monkeypatch):
    ws = "ws-live-spanish"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Carlos still owes me the rest.",
                candidate=_loop_candidate(
                    key="c1", text="Carlos still owes me the rest.",
                    title="Carlos still owes the rest", refs=["Carlos"]),
                stub=seed)
    stub = _DualStub(interp={
        "¿Y eso, llegó al final?": _ref(0, "¿Y eso, llegó al final?")})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="¿Y eso, llegó al final?",
                candidate=None, stub=stub)
    loops, _, clarifications, _ = await _state(ws)
    live = _open(loops)
    assert len(live) == 1 and "carlos" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []


# ── precision: incidental must vanish, novelty must track ───────────────────

@pytest.mark.asyncio
async def test_lunch_incidental_drops_quietly(async_client, monkeypatch):
    ws = "ws-live-lunch"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Studio Sam is sending the revised contract.",
                candidate=_loop_candidate(
                    key="s1", text="Studio Sam is sending the revised contract.",
                    title="Studio Sam revised contract pending", refs=["Studio Sam"]),
                stub=seed)
    stub = _DualStub(interp={
        "Not sure whether I'll get lunch there.": _incidental()})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="Not sure whether I'll get lunch there.",
                candidate=None, stub=stub)
    loops, attentions, clarifications, traces = await _state(ws)
    assert len(loops) == 1 and attentions == [] and clarifications == []
    assert {t.status for t in traces} == {"incidental_drop"}


@pytest.mark.asyncio
async def test_nervous_meeting_new_tracks_without_interrogation(async_client, monkeypatch):
    ws = "ws-live-meeting"
    stub = _DualStub(interp={
        "I've got that meeting tomorrow and I'm a bit nervous.": _new(
            "I've got that meeting tomorrow and I'm a bit nervous.")})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="e1",
                text="I've got that meeting tomorrow and I'm a bit nervous.",
                candidate=None, stub=stub)
    loops, _, clarifications, traces = await _state(ws)
    assert len(_open(loops)) == 1
    assert [c for c in clarifications if c.status == "pending"] == []
    assert {t.status for t in traces} == {"created_new"}


@pytest.mark.asyncio
async def test_chitchat_incidental_and_tiny_turn_skipped(async_client, monkeypatch):
    ws = "ws-live-chit"
    stub = _DualStub(interp={"lol thanks!": _incidental()})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="z1", text="lol thanks!", candidate=None, stub=stub)
    assert len(stub.interp_calls()) == 1
    loops, attentions, clarifications, _ = await _state(ws)
    assert loops == [] and attentions == [] and clarifications == []
    # Budget floor: sub-content turns never spend a call at all.
    stub2 = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="z2", text="ok", candidate=None, stub=stub2)
    assert stub2.interp_calls() == []


@pytest.mark.asyncio
async def test_explicit_statement_never_reaches_interpreter(async_client, monkeypatch):
    """The boundary itself: turns WITH extractor candidates never spend an
    interpretation call. Extraction and interpretation are separate jobs."""
    ws = "ws-live-boundary"

    class LoudStub(_DualStub):
        async def generate_structured(self, *, system, prompt, model_id, **kw):
            if self.MARK in prompt:
                raise AssertionError("interpreter must not fire on yielding turns")
            return await super().generate_structured(
                system=system, prompt=prompt, model_id=model_id, **kw)

    stub = LoudStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Carlos still owes me £2,100 from the event.",
                candidate=_loop_candidate(
                    key="b1", text="Carlos still owes me £2,100 from the event.",
                    title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
                stub=stub)
    loops, _, _, traces = await _state(ws)
    assert len(_open(loops)) == 1
    assert traces == []


@pytest.mark.asyncio
async def test_broken_judgement_fails_closed(async_client, monkeypatch):
    ws = "ws-live-broken"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Studio Sam is sending the revised contract.",
                candidate=_loop_candidate(
                    key="s1", text="Studio Sam is sending the revised contract.",
                    title="Studio Sam revised contract pending", refs=["Studio Sam"]),
                stub=seed)
    # Model names a matter index that does not exist: fail closed, touch nothing.
    stub = _DualStub(interp={
        "What happened with the paperwork?": _ref(9, "What happened with the paperwork?")})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="What happened with the paperwork?",
                candidate=None, stub=stub)
    loops, attentions, clarifications, _ = await _state(ws)
    assert len(_open(loops)) == 1
    assert attentions == [] and clarifications == []


@pytest.mark.asyncio
async def test_kill_switch_restores_silence(async_client, monkeypatch):
    ws = "ws-live-kill"
    seed = _DualStub(interp={})
    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m1", text="Studio Sam is sending the revised contract.",
                candidate=_loop_candidate(
                    key="s1", text="Studio Sam is sending the revised contract.",
                    title="Studio Sam revised contract pending", refs=["Studio Sam"]),
                stub=seed)
    monkeypatch.setenv("TURN_INTERPRETATION_ENABLED", "0")

    class LoudStub(_DualStub):
        async def generate_structured(self, *, system, prompt, model_id, **kw):
            if self.MARK in prompt:
                raise AssertionError("kill-switch must prevent the call")
            return await super().generate_structured(
                system=system, prompt=prompt, model_id=model_id, **kw)

    await _send(async_client, monkeypatch, workspace_id=ws, sender="ashley",
                message_id="m2", text="What happened with the paperwork?",
                candidate=None, stub=LoudStub(interp={}))
    loops, attentions, clarifications, traces = await _state(ws)
    assert len(_open(loops)) == 1
    assert attentions == [] and clarifications == [] and traces == []
