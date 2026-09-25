"""B.1 relation-backed reads — pure functions, no foreground wiring.

Proves the durable graph answers reconciliation questions that the
per-primitive state cannot. Nothing here is imported by packet, attention,
or projection paths yet; that is the operationalisation decision, not this.
"""

from __future__ import annotations

import json
from typing import Dict, List, Set

from src.models.semantic import (
    RelationStatus,
    RelationType,
    SemanticClaim,
    SemanticRelation,
    normalize_claim_content,
)

SELF_SUBJECTS = frozenset({"user", "sophie"})

_SETTLING = frozenset({"fulfils", "resolves"})
_WAIT_EDGES = frozenset({"depends_on", "conditioned_on", "blocks"})
_CHAIN_EDGES = frozenset({"supersedes", "refines", "part_of"})


def _rel_type(r: SemanticRelation) -> str:
    t = r.rel_type
    return t.value if isinstance(t, RelationType) else str(t)


def _status(r: SemanticRelation) -> str:
    s = r.status
    return s.value if isinstance(s, RelationStatus) else str(s)


def active(relations: List[SemanticRelation]) -> List[SemanticRelation]:
    return [r for r in relations if _status(r) == "active"]


def _subjects(claim: SemanticClaim) -> Set[str]:
    try:
        parsed = json.loads(claim.subjects_json or "[]")
    except (ValueError, TypeError):
        return set()
    return {str(s).lower() for s in parsed} if isinstance(parsed, list) else set()


def _by_id(claims: List[SemanticClaim]) -> Dict[str, SemanticClaim]:
    return {str(c.id): c for c in claims}


def _targets(rels: List[SemanticRelation], types: Set[str]) -> Set[str]:
    return {str(r.to_claim_id) for r in rels if _rel_type(r) in types}


def _sources(rels: List[SemanticRelation], types: Set[str]) -> Set[str]:
    return {str(r.from_claim_id) for r in rels if _rel_type(r) in types}


def contents_for(claims: List[SemanticClaim], ids: Set[str]) -> List[str]:
    by_id = _by_id(claims)
    return sorted({by_id[i].content for i in ids if i in by_id})


def fulfilled_matters(claims: List[SemanticClaim],
                      relations: List[SemanticRelation]) -> List[str]:
    """What has actually been fulfilled? (partial fulfilment excluded.)"""
    return contents_for(claims, _targets(active(relations), {"fulfils"}))


def partially_fulfilled_matters(claims: List[SemanticClaim],
                                relations: List[SemanticRelation]) -> List[str]:
    """Partial progress that is still outstanding."""
    done = _targets(active(relations), _SETTLING)
    partial = _targets(active(relations), {"partially_fulfils"})
    return contents_for(claims, partial - done)


def resolved_matters(claims: List[SemanticClaim],
                     relations: List[SemanticRelation]) -> List[str]:
    """Which open matter was resolved (incl. across vocabulary change)?"""
    return contents_for(claims, _targets(active(relations), {"resolves"}))


def waiting_on(claims: List[SemanticClaim],
               relations: List[SemanticRelation]) -> List[str]:
    """What is still waiting on someone/something? Sources of wait-edges
    that no settling edge has retired."""
    edges = active(relations)
    settled = _targets(edges, _SETTLING)
    waiting = _sources(edges, _WAIT_EDGES) - settled
    return contents_for(claims, waiting)


def dependencies_of(content: str,
                    claims: List[SemanticClaim],
                    relations: List[SemanticRelation]) -> List[str]:
    """What does this matter depend on? One hop over wait-edges."""
    by_content = {c.content: c for c in claims}
    claim = by_content.get(normalize_claim_content(content))
    if claim is None:
        return []
    by_id = _by_id(claims)
    out = set()
    for r in active(relations):
        if str(r.from_claim_id) == str(claim.id) and _rel_type(r) in _WAIT_EDGES:
            target = by_id.get(str(r.to_claim_id))
            if target is not None:
                out.add(target.content)
    return sorted(out)


def revision_chain(content: str,
                   claims: List[SemanticClaim],
                   relations: List[SemanticRelation]) -> List[str]:
    """Which claim superseded/refined/composed this one (and what it became)?
    Follows chain edges forward from the given content."""
    by_content = {c.content: c for c in claims}
    by_id = _by_id(claims)
    start = by_content.get(normalize_claim_content(content))
    if start is None:
        return []
    seen, frontier, chain = {str(start.id)}, [str(start.id)], []
    while frontier:
        current = frontier.pop(0)
        for r in active(relations):
            if str(r.from_claim_id) == current and _rel_type(r) in _CHAIN_EDGES:
                nxt = str(r.to_claim_id)
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
                    if nxt in by_id:
                        chain.append(by_id[nxt].content)
    return chain


def background_candidates(claims: List[SemanticClaim],
                          relations: List[SemanticRelation]) -> List[str]:
    """Which items should disappear from active attention WITHOUT being
    deleted? Targets of settling/superseding edges: remembered, not salient."""
    settled = _targets(active(relations), _SETTLING | {"supersedes"})
    return contents_for(claims, settled)


def third_party_open(claims: List[SemanticClaim],
                     relations: List[SemanticRelation]) -> List[str]:
    """Which third-party obligation still matters? Non-self-subject claims
    touching active edges, unsettled by any settling edge."""
    edges = active(relations)
    settled = _targets(edges, _SETTLING)
    touched = _targets(edges, {_rel_type(r) for r in edges}) | _sources(
        edges, {_rel_type(r) for r in edges})
    out = []
    for c in claims:
        if str(c.id) not in touched or str(c.id) in settled:
            continue
        if _subjects(c) - SELF_SUBJECTS:
            out.append(c.content)
    return sorted(set(out))
