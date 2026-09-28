"""Minimal Runtime-facing interface: ask_longitudinal(...).

Closer to ask_longitudinal(question, scope, temporal_cutoff, matter_refs?)
than to get_user_profile(). Boundedness is explicit (scope + need required);
provenance/audit is possible (provenance on every evidence item, joins
listed, cutoff + excluded IDs on the read).

Shadow mode: callers log the question, retrieve, synthesise, score, record
what WOULD have been returned — and do not feed it into behaviour. Reads are
ephemeral; this function persists nothing (asserted: no writes, no cache
that survives as truth).
"""

from __future__ import annotations

from typing import List, Optional

from src.longitudinal_read import cortex_joins, retrieval
from src.longitudinal_read.models import ReadRequest, RecruitedRead
from src.longitudinal_read.query_discipline import validate_bounded
from src.longitudinal_read.synthesis import synthesize


def ask_longitudinal(
    question: str,
    scope: str,
    temporal_cutoff: str,
    matter_refs: Optional[List[str]] = None,
    need: str = "",
    question_id: str = "",
    query_terms: Optional[List[str]] = None,
    evidence_limit: int = 8,
    exclude_matters: Optional[List[str]] = None,
) -> RecruitedRead:
    req = ReadRequest(
        question=question, scope=scope, temporal_cutoff=temporal_cutoff,
        matter_refs=list(matter_refs or []), need=need,
        evidence_limit=evidence_limit,
    )
    validate_bounded(req.question, req.scope, req.need)
    terms = list(query_terms) if query_terms else None
    if not terms and question_id and question_id in retrieval.DEFAULT_TERMS:
        terms = retrieval.DEFAULT_TERMS[question_id]
    if not terms:
        terms = [w for w in question.split() if len(w) > 3][:12]
    matters = list(matter_refs or [])
    if not matters and question_id and question_id in retrieval.DEFAULT_MATTERS:
        matters = retrieval.DEFAULT_MATTERS[question_id]
    result = retrieval.fixture_search(
        query_terms=terms, matter_refs=matters,
        limit=evidence_limit, exclude_matters=exclude_matters,
    )
    joins = cortex_joins.joins_for_matters(matters, temporal_cutoff, result.items)
    return synthesize(
        question_id=question_id or "ADHOC",
        question=question, scope=scope, cutoff_iso=temporal_cutoff,
        evidence=result.items, joins=joins, backend=result.backend,
    )
