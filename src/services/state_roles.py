"""Structural state roles: zero-to-many, time-varying, derived.

Roles are computed from durable status + relation overlays, never stored.
There is deliberately no family column anywhere: a claim/row can be
obligation-related, unresolved, predictive, and attention-relevant at once,
and shed roles as relations land (fulfils/resolves strip obligation).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

ASSERTIONAL = "assertional"
OBLIGATION = "obligation"
UNRESOLVED = "unresolved"
PREDICTIVE = "predictive"
ATTENTIONAL = "attentional"


def _key(kind: str, row_id: Any) -> str:
    return f"{kind}:{row_id}"


def _shed(roles: List[str], *drop: str) -> List[str]:
    return [r for r in roles if r not in drop]


def derive_roles(
    *,
    expectations: List[Any] = (),
    open_loops: List[Any] = (),
    commitments: List[Any] = (),
    clarifications: List[Any] = (),
    attentions: List[Any] = (),
    relations: List[Any] = (),
    claims: List[Any] = (),
    now: Optional[datetime] = None,
) -> Dict[str, List[str]]:
    """Pure structural mapping. Relation overlays match durable rows to claim
    nodes by normalized content equality (titles are the claim text the
    deterministic writers promoted)."""
    from src.models.semantic import normalize_claim_content

    out: Dict[str, List[str]] = {}
    claim_by_content = {normalize_claim_content(c.content): str(c.id) for c in claims}
    rels = [r for r in relations if str(getattr(r, "status", "active")) == "active"]
    targets_of: Dict[str, set] = {}
    sources_of: Dict[str, set] = {}
    for r in rels:
        t = str(getattr(r, "rel_type", ""))
        targets_of.setdefault(str(getattr(r, "to_claim_id", "")), set()).add(t)
        sources_of.setdefault(str(getattr(r, "from_claim_id", "")), set()).add(t)

    def overlay(title: str, roles: List[str]) -> List[str]:
        cid = claim_by_content.get(normalize_claim_content(title or ""))
        if cid is None:
            return roles
        t = targets_of.get(cid, set())
        s = sources_of.get(cid, set())
        if t & {"fulfils", "resolves"}:
            roles = _shed(roles, OBLIGATION, UNRESOLVED)
        if "supersedes" in t:
            roles = _shed(roles, OBLIGATION)
        if s & {"depends_on", "conditioned_on", "blocks"}:
            if PREDICTIVE not in roles:
                roles = roles + [PREDICTIVE]
        if "reopens" in s and UNRESOLVED not in roles:
            roles = roles + [UNRESOLVED]
        return roles

    for exp in expectations:
        state = str(getattr(exp, "outcome_state", "unknown"))
        roles = [ASSERTIONAL]
        if "unknown" in state:
            roles += [OBLIGATION, UNRESOLVED]
            if _has_future_temporal(exp, now):
                roles.append(PREDICTIVE)
        out[_key("expectation", exp.id)] = sorted(set(
            overlay(getattr(exp, "title", ""), roles)))

    for loop in open_loops:
        state = str(getattr(loop, "status", "open"))
        roles = [ASSERTIONAL, UNRESOLVED, ATTENTIONAL] if "open" in state else [ASSERTIONAL]
        out[_key("open_loop", loop.id)] = sorted(set(
            overlay(getattr(loop, "title", ""), roles)))

    for cand in commitments:
        status = str(getattr(cand, "status", "pending"))
        authority = str(getattr(cand, "authority", "ask"))
        if "pending" in status:
            roles = [OBLIGATION, UNRESOLVED] if "act" in authority else [ATTENTIONAL]
        else:
            roles = [ASSERTIONAL]
        out[_key("commitment", cand.id)] = sorted(set(roles))

    for clar in clarifications:
        status = str(getattr(clar, "status", "pending"))
        roles = [UNRESOLVED, ATTENTIONAL] if "pending" in status else [ASSERTIONAL]
        out[_key("clarification", clar.id)] = sorted(set(roles))

    for att in attentions:
        status = str(getattr(att, "status", "active"))
        roles = [ATTENTIONAL] if ("active" in status or "surfaced" in status) else [ASSERTIONAL]
        out[_key("attention", att.id)] = sorted(set(roles))

    return out


def _has_future_temporal(exp: Any, now: Optional[datetime]) -> bool:
    for attr in ("hard_deadline_at", "expected_window_end", "expected_window_start"):
        value = getattr(exp, attr, None)
        if value is None:
            continue
        moment = value if value.tzinfo is None else value.replace(tzinfo=None)
        ref = now.replace(tzinfo=None) if (now is not None and now.tzinfo) else now
        if ref is not None and moment >= ref:
            return True
        if ref is None:
            return True
    return False
