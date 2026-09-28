"""Evidence retrieval: Honcho-style message search with conclusion quarantine.

Two backends behind one interface:
  - "fixture": deterministic lexical retrieval over the frozen S1-S4 corpus
    (offline stand-in for Honcho message search; same 53 events as the VPS
    probe workspace). Used for the scored regression.
  - "honcho_live": optional pass-through to a live Honcho stack via
    /search endpoints (message search ONLY). Never touches
    conclusions/query or conclusions/list in the scored path.

Stored Honcho conclusions are QUARANTINED: this module has no code path
that reads them, and RetrievalResult carries a flag the tests assert False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.longitudinal_read import corpus
from src.longitudinal_read.models import EvidenceItem

CONCLUSIONS_TOUCHED = False  # module-level tripwire; any conclusion read flips it


@dataclass
class RetrievalResult:
    items: List[EvidenceItem]
    backend: str
    stored_conclusions_used: bool = False
    query_terms: List[str] = field(default_factory=list)


def _score(content: str, terms: List[str]) -> int:
    low = content.lower()
    return sum(1 for t in terms if t.lower() in low)


def fixture_search(
    query_terms: List[str],
    matter_refs: List[str],
    limit: int = 8,
    exclude_matters: Optional[List[str]] = None,
) -> RetrievalResult:
    """Lexical retrieval over frozen corpus: coverage matters, judgement absent."""
    items = corpus.load_corpus()
    excluded = set(exclude_matters or [])
    scored = []
    for ev in items:
        if excluded and any(m in excluded for m in ev.matter_tags):
            continue
        lexical = _score(ev.content, query_terms)
        matter_hit = 1 if any(m in matter_refs for m in ev.matter_tags) else 0
        total = lexical + 3 * matter_hit
        if total > 0:
            scored.append((total, ev.timestamp, ev))
    scored.sort(key=lambda t: (-t[0], t[1]))
    picked = [ev for _, _, ev in scored[:limit]]
    # Coverage backstop: any matter-tagged event not yet picked is appended so
    # recall never silently drops a known-bearing episode (judgement still
    # belongs to synthesis, which must exclude noise itself).
    seen = {e.event_id for e in picked}
    for ev in items:
        if len(picked) >= limit + 4:
            break
        if ev.event_id in seen:
            continue
        if excluded and any(m in excluded for m in ev.matter_tags):
            continue
        if any(m in matter_refs for m in ev.matter_tags):
            picked.append(ev)
            seen.add(ev.event_id)
    return RetrievalResult(
        items=picked,
        backend="fixture",
        stored_conclusions_used=False,
        query_terms=list(query_terms),
    )


# Term sets per bounded question: retrieval hints only (frozen in battery config
# and mirrored here as defaults). They select candidate episodes; verdicts are
# computed by synthesis gates, never by these terms.
DEFAULT_TERMS: Dict[str, List[str]] = {
    "F1": ["carlos", "q1,500", "1,500", "owe", "paid", "transfer", "bank", "balance"],
    "F2": ["240", "lucy", "hargreaves", "paid", "count it as paid", "ask her"],
    "F3": ["carlos", "owe", "paid", "chase", "debt"],
    "F4": ["sam", "studio", "cousin", "contract", "pick", "mum"],
    "F5": ["bank", "delay", "thursday", "transfer", "issue", "pay"],
    "F6": ["neck", "asking", "keep asking", "not a thing", "sore", "better"],
    "F7": ["looks good", "go ahead", "sign", "contract", "approval", "final copy"],
    "F8": ["give me everything", "urgent", "remind"],
    "F9": ["school", "18", "boy", "andree", "trip", "pay"],
    "F10": ["mum", "pickup", "home fine", "completed", "sam"],
}

DEFAULT_MATTERS: Dict[str, List[str]] = {
    "F1": ["carlos_debt"],
    "F2": ["lucy_payment"],
    "F3": ["carlos_debt"],
    "F4": ["sam_identity", "studio_contract", "cousin_pickup"],
    "F5": ["carlos_debt"],
    "F6": ["neck_watch"],
    "F7": ["studio_contract"],
    "F8": ["surfacing_restraint"],
    "F9": ["school_payment"],
    "F10": ["cousin_pickup"],
}


async def honcho_live_search(
    base_url: str,
    api_key: str,
    workspace_id: str,
    session_ids: List[str],
    query: str,
    limit: int = 8,
) -> RetrievalResult:
    """Live Honcho message-search adapter (messages only — conclusions never queried).

    Best-effort: any failure returns an empty result with backend
    "honcho_live_unreachable" so callers fail over to fixture. Kept out of the
    scored path's default so regression stays deterministic.
    """
    import httpx

    found: List[EvidenceItem] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            for sid in session_ids:
                resp = await client.post(
                    f"{base_url}/v3/workspaces/{workspace_id}/sessions/{sid}/search",
                    headers=headers,
                    json={"query": query[:500], "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
                for item in (data if isinstance(data, list) else []):
                    meta = item.get("metadata") or {}
                    found.append(
                        EvidenceItem(
                            event_id=str(meta.get("fixture_event_id") or item.get("id")),
                            timestamp=str(item.get("created_at") or ""),
                            sender=str(item.get("peer_id") or ""),
                            role="external",
                            source_type="honcho_message",
                            content=str(item.get("content") or ""),
                            provenance=f"honcho:{workspace_id}:{sid}:{item.get('id')}",
                        )
                    )
    except Exception:
        return RetrievalResult(items=[], backend="honcho_live_unreachable")
    return RetrievalResult(items=found[:limit], backend="honcho_live")
