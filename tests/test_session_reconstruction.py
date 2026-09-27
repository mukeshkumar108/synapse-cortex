"""V2 reconstruction — deterministic contract/validator/translator tests.

No model calls here (stub adapters only). Live-model semantic capability is
covered separately in test_session_reconstruction_live.py (gated).
"""
import pytest

from src.db import async_session_maker
from src.models.operational_state import ExtractionTrace
from sqlmodel import select

from src.services import semantic_judge
from src.services.session_consolidation import (
    SessionTurn,
    SnapshotMatter,
    StartSnapshot,
)
from src.services.session_reconstruction import (
    build_reconstruction_prompt,
    reconstruct_session,
    translate_to_ops,
    validate_reconstruction,
)

T = [SessionTurn(message_id="e1", speaker="ashley",
                 text="Carlos still owes me the remaining balance, about twenty one hundred."),
     SessionTurn(message_id="e2", speaker="bank_feed",
                 text="Incoming payment £1,900 from Carlos."),
     SessionTurn(message_id="e3", speaker="ashley",
                 text="Did that ever come through?")]


def _snap():
    return StartSnapshot(
        matters=[SnapshotMatter(id="11111111-1111-1111-1111-111111111111",
                                kind="open_loop",
                                title="Carlos still owes £2,100 from the event",
                                status="OPEN", owner="ashley")],
        people=["Carlos"])


def _matter(pid="m1", **kw):
    d = {"pid": pid, "kind": "watch", "title": "Carlos debt watch",
         "status": "open", "owner": "user", "basis": "existing",
         "matter_id": "11111111-1111-1111-1111-111111111111",
         "evidence": {"message_ids": ["e1"],
                      "spans": [{"message_id": "e1",
                                 "span": "remaining balance"}]},
         "confidence": 0.8, "rationale": "fixture"}
    d.update(kw)
    return d


def test_prompt_orders_evidence_before_provisional():
    snap = _snap()
    prov = [SnapshotMatter(id="22222222-2222-2222-2222-222222222222",
                           kind="open_loop", title="Inquire about arrival status",
                           status="OPEN", owner="")]
    prompt = build_reconstruction_prompt(snap, T, prov)
    assert prompt.index("FULL RAW SESSION EVIDENCE") < prompt.index("UNTRUSTED PROVISIONAL")
    assert "[provisional 22222222" in prompt
    assert "[matter 11111111" in prompt
    assert "[msg:e1]" in prompt and "[msg:e3]" in prompt


def test_validate_new_matter_with_spans_and_owner():
    raw = {"session_summary": "s",
           "matters": [_matter(pid="m1", basis="new", matter_id="",
                               owner="external:carlos",
                               title="Carlos owes £2,100",
                               evidence={"message_ids": ["e1"],
                                         "spans": [{"message_id": "e1",
                                                    "span": "twenty one hundred"}]})]}
    # external:carlos must be grounded: add the speaker to the transcript
    t = T + [SessionTurn(message_id="e0", speaker="external:carlos",
                         text="I'll send it tomorrow.")]
    validated, rejected = validate_reconstruction(
        raw, snapshot=_snap(), transcript=t, provisional_ids=set())
    assert rejected == []
    assert validated["matters"][0]["owner"] == "external:carlos"


def test_basis_existing_without_id_coerces_to_new():
    entry = _matter(basis="new", matter_id="",
                    title="Carlos owes £2,100", owner="user",
                    evidence={"message_ids": ["e1"],
                              "spans": [{"message_id": "e1",
                                         "span": "twenty one hundred"}]})
    entry = dict(entry, basis="existing", matter_id="")
    raw = {"session_summary": "s", "matters": [entry]}
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert r == []
    assert v["matters"][0]["basis"] == "new"
    assert v["matters"][0]["repaired_basis"] is True


def test_pure_continuation_may_cite_nothing():
    entry = _matter(status="open",
                    evidence={"message_ids": [], "spans": []})
    raw = {"session_summary": "s", "matters": [entry]}
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert r == []
    assert len(v["matters"]) == 1


def test_validate_rejects_change_without_verbatim_spans():
    raw = {"session_summary": "s",
           "matters": [_matter(status="resolved", via="completed",
                               evidence={"message_ids": ["e1"], "spans": []})]}
    validated, rejected = validate_reconstruction(
        raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert validated["matters"] == []
    assert rejected == [{"where": "matters[m1]", "reason": "change_needs_verbatim_spans"}]


def test_validate_rejects_ungrounded_external_owner():
    raw = {"session_summary": "s",
           "matters": [_matter(basis="new", matter_id="", owner="external:nobody",
                               title="Mystery debt",
                               evidence={"message_ids": ["e1"],
                                         "spans": [{"message_id": "e1",
                                                    "span": "remaining balance"}]})]}
    validated, rejected = validate_reconstruction(
        raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert validated["matters"] == []
    assert rejected[0]["reason"] == "ungrounded_owner"


def test_validate_rejects_unknown_matter_and_bad_pid():
    dup_a = _matter(pid="m1")
    dup_b = _matter(pid="m1", title="second claim on m1")
    raw = {"session_summary": "s",
           "matters": [
               _matter(pid="m0", matter_id="00000000-0000-0000-0000-000000000000"),
               dup_a, dup_b,
               {"pid": "m2", "kind": "nope", "title": "x", "status": "open",
                "owner": "user", "basis": "new",
                "evidence": {"message_ids": ["e1"], "spans": []},
                "confidence": 0.9, "rationale": "x"},
           ]}
    validated, rejected = validate_reconstruction(
        raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    # first m1 accepted, second m1 rejected as duplicate
    assert [m["pid"] for m in validated["matters"]] == ["m1"]
    reasons = {r["reason"] for r in rejected}
    assert {"unknown_matter_id", "bad_or_duplicate_pid", "bad_kind_status_title_basis"} <= reasons


def test_uncertainty_grounding_rule():
    base = {"content": "which payment?", "confidence": 0.7, "rationale": "x"}
    # bare: no spans, no link, no mids -> rejected (the V1 hole, fixed)
    raw = {"session_summary": "s", "matters": [],
           "uncertainties": [dict(base, evidence={"message_ids": [], "spans": []})]}
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert v["uncertainties"] == [] and r[0]["reason"] == "ungrounded_no_spans_no_link"
    # spans alone suffice
    raw["uncertainties"] = [dict(
        base, evidence={"message_ids": ["e3"],
                        "spans": [{"message_id": "e3", "span": "come through"}]})]
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert len(v["uncertainties"]) == 1 and r == []
    # link + cited mid suffices without spans
    raw["uncertainties"] = [dict(
        base, related_pids=["11111111-1111-1111-1111-111111111111"],
        evidence={"message_ids": ["e3"], "spans": []})]
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert len(v["uncertainties"]) == 1 and r == []


def test_suppress_needs_spans_and_review_targets_provisional():
    raw = {"session_summary": "s", "matters": [],
           "suppressions": [{"topic_or_entity": "neck", "reason": "boundary",
                             "evidence": {"message_ids": ["e1"], "spans": []},
                             "confidence": 0.9, "rationale": "x"}],
           "provisional_review": [{"matter_id": "nope", "verdict": "redundant",
                                   "reason": "x", "confidence": 0.9}]}
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert v["suppressions"] == [] and v["provisional_review"] == []
    assert {x["reason"] for x in r} == {"suppress_needs_spans", "bad_review_target"}


def test_redundant_status_marks_discard():
    raw = {"session_summary": "s",
           "matters": [_matter(status="redundant",
                               evidence={"message_ids": ["e3"],
                                         "spans": [{"message_id": "e3",
                                                    "span": "come through"}]})]}
    v, r = validate_reconstruction(raw, snapshot=_snap(), transcript=T, provisional_ids=set())
    assert r == []
    assert v["matters"][0]["status"] == "redundant"
    # junky status strings are still rejected, not smuggled
    bad = dict(_matter(), status="junked")
    v2, r2 = validate_reconstruction(
        {"session_summary": "s", "matters": [bad]},
        snapshot=_snap(), transcript=T, provisional_ids=set())
    assert v2["matters"] == []
    assert r2[0]["reason"] == "bad_kind_status_title_basis"
    # redundant on a non-existing basis is rejected
    newb = dict(_matter(), status="redundant", basis="new", matter_id="")
    v3, r3 = validate_reconstruction(
        {"session_summary": "s", "matters": [newb]},
        snapshot=_snap(), transcript=T, provisional_ids=set())
    assert v3["matters"] == []
    assert r3[0]["reason"] == "redundant_needs_existing"


def test_translate_diff_covers_lifecycle():
    start = {"11111111-1111-1111-1111-111111111111": _snap().matters[0]}
    pidmap = {}
    # unchanged -> affirm
    ops, _disc = translate_to_ops(
        {"matters": [_matter(status="open")], "uncertainties": [],
         "attentions": [], "suppressions": [], "incidental_mids": [],
         "provisional_review": []},
        start_by_id=start, pid_to_uuid=pidmap)
    assert [o.op for o in ops] == ["affirm_matter"]
    # resolved -> resolve with via
    ops, _disc = translate_to_ops(
        {"matters": [_matter(status="resolved", via="completed",
                             evidence={"message_ids": ["e2"],
                                       "spans": [{"message_id": "e2",
                                                  "span": "£1,900"}]})],
         "uncertainties": [], "attentions": [], "suppressions": [],
         "incidental_mids": [], "provisional_review": []},
        start_by_id=start, pid_to_uuid=pidmap)
    assert ops[0].op == "resolve_matter" and ops[0].data["via"] == "completed"
    # partial -> partial with remainder
    ops, _disc = translate_to_ops(
        {"matters": [_matter(status="partial", remainder="£200 left",
                             evidence={"message_ids": ["e2"],
                                       "spans": [{"message_id": "e2",
                                                  "span": "£1,900"}]})],
         "uncertainties": [], "attentions": [], "suppressions": [],
         "incidental_mids": [], "provisional_review": []},
        start_by_id=start, pid_to_uuid=pidmap)
    assert ops[0].op == "partial_fulfilment" and "200" in ops[0].data["remainder"]
    # new + follow_up -> new_matter (with owner) + attend
    ops, _disc = translate_to_ops(
        {"matters": [_matter(pid="m9", basis="new", matter_id="",
                             title="Fever watch", kind="watch", owner="unknown",
                             status="open", follow_up="check fever tomorrow",
                             evidence={"message_ids": ["e1"],
                                       "spans": [{"message_id": "e1",
                                                  "span": "remaining balance"}]})],
         "uncertainties": [], "attentions": [], "suppressions": [],
         "incidental_mids": [], "provisional_review": []},
        start_by_id=start, pid_to_uuid=pidmap)
    assert [o.op for o in ops] == ["new_matter", "attend"]
    assert ops[0].data["owner"] == "unknown"


class _Stub:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def generate_structured(self, **kw):
        self.calls += 1
        return self.payload


@pytest.mark.asyncio
async def test_reconstruct_shadow_end_to_end_with_stub():
    payload = {"session_summary": "partial payment",
               "matters": [_matter(status="partial", remainder="£200 left",
                                   evidence={"message_ids": ["e2"],
                                             "spans": [{"message_id": "e2",
                                                        "span": "£1,900"}]})],
               "incidental_mids": ["e3"]}
    stub = _Stub(payload)
    async with async_session_maker() as db:
        result = await reconstruct_session(
            db, workspace_id="ws-v2-det", session_id="s",
            transcript=[{"message_id": t.message_id, "speaker": t.speaker,
                         "text": t.text} for t in T],
            start_snapshot=_snap(), adapter=stub)
    assert result.error == "" and stub.calls == 1
    assert [o.op for o in result.accepted] == ["partial_fulfilment", "incidental"]
    by_op = {w["op"]: w for w in result.would_apply}
    assert by_op["partial_fulfilment"]["would_apply"] is False, \
        "target row does not exist in this empty DB: guards must refuse"
    assert by_op["incidental"]["would_apply"] is True
    async with async_session_maker() as db:
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == "ws-v2-det",
            ExtractionTrace.stage == "session_reconstruction"))).scalars().all()
    assert traces and traces[-1].status == "shadow"


@pytest.mark.asyncio
async def test_reconstruct_fail_closed_paths_traced():
    async with async_session_maker() as db:
        r = await reconstruct_session(
            db, workspace_id="ws-v2-err", session_id="s",
            transcript=[{"message_id": "e1", "speaker": "a", "text": "hello there friend"}],
            start_snapshot=StartSnapshot(), adapter=None)
        assert r.error == "no_adapter" and r.accepted == []
        r2 = await reconstruct_session(
            db, workspace_id="ws-v2-err", session_id="s",
            transcript=[{"message_id": "e1", "speaker": "a", "text": "hello there friend"}],
            start_snapshot=StartSnapshot(), adapter=_Stub({"nope": 1}))
        assert r2.error == "malformed" and r2.retries == 2, \
            "one initial attempt plus one retry, then fail-closed"
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == "ws-v2-err",
            ExtractionTrace.stage == "session_reconstruction"))).scalars().all()
    assert {t.status for t in traces} == {"error"}
    _ = semantic_judge  # keep import referenced (adapter default path)
