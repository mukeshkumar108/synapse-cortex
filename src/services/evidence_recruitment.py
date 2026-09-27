"""Targeted history recruitment for ambiguous reconciliation.

When the event-driven semantic pass finds plausible live matters but the
current turn's evidence alone cannot ground a decision, Cortex may recruit
narrowly relevant history BEFORE mutating state or escalating uncertainty
(Canon principles 12-13: resolve privately before escalating socially;
history is an evidence source for live uncertainty).

Boundaries (deliberate, not incidental):
- ONE logical retrieval per turn: a single query built from the current
  evidence plus the already-plausible matter titles, fanning out to at most
  peer_search with a search_messages fallback. No wandering, no RAG.
- Token overlap retrieves (which history to pull, which pairs to re-judge);
  it never decides. Durable mutation still requires the existing grounded
  semantic judge (verdict=yes + confidence floor + verbatim span) AND a
  single confirmed winner. Two winners == hold, exactly like the
  commitment fulfilment path's ambiguity posture.
- Provenance travels with every recruited hit and lands in the existing
  audit structures (ExtractionTrace detail, resolution_evidence,
  SemanticRelation source_key). No new ledger.
- Fail-open throughout: no provider, no hits, no adapter, judge unconvinced,
  or any exception -> today's hold behaviour, no mutation, no clarification.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Kill-switch: SEMANTIC_RECRUIT_HISTORY=0 restores pre-tranche behaviour.
RECRUIT_ENABLED_ENV = "SEMANTIC_RECRUIT_HISTORY"

MAX_HITS = 4
MAX_REJUDGE_PAIRS = 2
QUERY_CHAR_CAP = 500
HISTORY_CONTEXT_CAP = 2000
HIT_TEXT_CAP = 500


@dataclass
class HistoryHit:
    """One recruited evidence fragment with enough provenance to audit."""

    text: str
    provenance: str  # e.g. honcho_peer:<peer>:<id> / honcho_message:<session>:<id>
    source: str  # peer_search | search_messages
    extra: Dict[str, Any] = field(default_factory=dict)


HistoryProvider = Callable[[str, str, str, str, int], Any]
# (workspace_id, session_id, peer_id, query, limit) -> awaitable[list[HistoryHit]]


def recruit_enabled() -> bool:
    return os.getenv(RECRUIT_ENABLED_ENV, "1") == "1"


_cached_client: Any = None


def default_history_provider() -> Optional[HistoryProvider]:
    """Production provider built on the existing HonchoClient.

    Returns None when history context is disabled, so callers keep today's
    behaviour with zero additional calls. The client honours the existing
    per-call timeout (HONCHO_TIMEOUT_SECONDS); all failures yield [].
    """
    from src.config import settings

    if not recruit_enabled():
        return None
    if not settings.HONCHO_CONTEXT_ENABLED:
        return None
    global _cached_client
    if _cached_client is None:
        from src.clients.honcho_client import HonchoClient

        _cached_client = HonchoClient(
            base_url=settings.HONCHO_BASE_URL,
            api_key=settings.HONCHO_API_KEY,
            timeout=settings.HONCHO_TIMEOUT_SECONDS,
        )
    client = _cached_client

    async def provide(workspace_id: str, session_id: str, peer_id: str,
                      query: str, limit: int) -> List[HistoryHit]:
        hits: List[HistoryHit] = []
        try:
            found = await client.peer_search(
                workspace_id, peer_id, query, limit=limit)
        except Exception as err:
            logger.warning("recruitment peer_search failed (fail-open): %s", err)
            found = None
        for item in found or []:
            content = " ".join(str(item.get("content") or "").split())
            if content:
                hits.append(HistoryHit(
                    text=content[:HIT_TEXT_CAP],
                    provenance=(
                        f"honcho_peer:{item.get('peer_id') or peer_id}"
                        f":{item.get('id') or '?'}"
                        f"@{item.get('session_id') or '?'}"),
                    source="peer_search",
                    extra={"created_at": str(item.get("created_at") or "")},
                ))
        if hits:
            return hits[:limit]
        try:
            found = await client.search_messages(
                workspace_id, session_id, query, limit=limit)
        except Exception as err:
            logger.warning("recruitment search_messages failed (fail-open): %s", err)
            return []
        for item in (found or []):
            content = " ".join(str(item.get("content") or "").split())
            if content:
                hits.append(HistoryHit(
                    text=content[:HIT_TEXT_CAP],
                    provenance=(
                        f"honcho_message:{session_id}:{item.get('id') or '?'}"),
                    source="search_messages",
                    extra={"created_at": str(item.get("created_at") or "")},
                ))
        return hits[:limit]

    return provide


def build_query(text: str, matters: List[str]) -> str:
    """One query targeting the intersection of current evidence and the
    already-plausible live matters. Retrieval hint only, never authority."""
    parts = [" ".join((text or "").split())]
    for matter in matters[:MAX_REJUDGE_PAIRS]:
        clean = " ".join((matter or "").split())
        if clean:
            parts.append(clean)
    return " ".join(p for p in parts if p)[:QUERY_CHAR_CAP]


def history_block(hits: List[HistoryHit]) -> str:
    lines = [f"[{h.source} {h.provenance}] {h.text}" for h in hits]
    return "\n".join(lines)[:HISTORY_CONTEXT_CAP]


async def recruit_and_rejudge(
    *,
    workspace_id: str,
    session_id: str,
    peer_id: str,
    message_id: str,
    text: str,
    rejected: List[Dict[str, Any]],
    adapter: Any,
    history_provider: HistoryProvider,
) -> Dict[str, Any]:
    """One bounded recruitment round over already-rejected pairs.

    Returns {"recruited": n_hits, "recruit_judged": n, "recruit_accepted": n,
    "winner": {pair, judgement, hits} | None, "holds": [reasons]}.
    Never mutates; the caller applies the single winner through its existing
    deterministic apply path, or holds.
    """
    from src.services import semantic_judge

    outcome: Dict[str, Any] = {
        "recruited": 0, "recruit_judged": 0, "recruit_accepted": 0,
        "winner": None, "holds": [],
    }
    if adapter is None or not rejected:
        outcome["holds"].append("no_adapter_or_no_candidates")
        return outcome
    shortlist = rejected[:MAX_REJUDGE_PAIRS]
    query = build_query(text, [p.get("matter", "") for p in shortlist])
    if not query.strip():
        outcome["holds"].append("empty_query")
        return outcome
    try:
        hits = await history_provider(
            workspace_id, session_id, peer_id, query, MAX_HITS)
    except Exception as err:
        logger.warning("recruitment provider failed (fail-open): %s", err)
        outcome["holds"].append("provider_failed")
        return outcome
    hits = [h for h in (hits or []) if (h.text or "").strip()]
    outcome["recruited"] = len(hits)
    if not hits:
        outcome["holds"].append("no_history")
        return outcome
    context = history_block(hits)
    combined = f"{text}\n{context}"
    winners: List[Dict[str, Any]] = []
    for pair in shortlist:
        kind = pair.get("kind")
        matter = pair.get("matter", "")
        try:
            adjudication = await semantic_judge.adjudicate(
                kind=kind, earlier=matter, later=text,
                context=context, adapter=adapter)
        except Exception as err:
            logger.warning("recruitment re-judge failed (fail-open): %s", err)
            continue
        outcome["recruit_judged"] += 1
        span = (adjudication.evidence_span or "").strip()
        if adjudication.accepted and span and span in combined:
            outcome["recruit_accepted"] += 1
            winners.append({
                "pair": pair,
                "judgement": adjudication,
                "span_in_current": span in text,
                "hits": hits,
                "query": query,
            })
    if len(winners) == 1:
        outcome["winner"] = winners[0]
    elif len(winners) > 1:
        # Ambiguous match is worse than a missed one: hold everything.
        outcome["holds"].append("multiple_winners")
    else:
        outcome["holds"].append("judge_unconvinced")
    return outcome
