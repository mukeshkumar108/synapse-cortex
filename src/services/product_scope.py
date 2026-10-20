"""The product boundary, established where a request enters Cortex.

Invariant: Cortex is shared technology, not shared personal memory. Products are
independent: their users, conversations, notebooks, arcs, operational records,
attention actions and prepared context are isolated by default, even when two
products happen to use the same user id or workspace name.

How it is enforced (not by scattered query filters):
- the product comes from the caller's trusted credential (a per-product token), never
  from a field the client supplies. A product token cannot claim another product.
  (The legacy shared token is an internal operator/Runtime credential: its product claim
  is accepted, and it is the one documented bypass.)
- the caller's workspace is rewritten ONCE, here, to `<product>::<workspace>` for every
  product except the original (Sophie keeps her existing, unprefixed workspace, so no
  existing row is migrated or re-owned). Every table, job, lock, cache and query below
  already filters by workspace, so they all inherit the boundary.
- the separator is reserved: no caller can submit a workspace containing it, so a
  namespace cannot be forged or entered from outside.
- product-token callers are default-denied everywhere except an explicit route list.
"""
from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException, Request

from src.config import settings
from src.services import product_memory

SEP = "::"
DEFAULT_PRODUCT = "sophie"      # the original product: its workspace stays unprefixed (no data migration)

# The only routes a product credential may call. Everything else is denied before any handler runs.
PRODUCT_ROUTES = (
    ("POST", re.compile(r"^/v1/memory/consolidate$")),
    ("GET", re.compile(r"^/v1/memory/run/[^/]+$")),
    ("GET", re.compile(r"^/v1/memory/preparation$")),
    ("POST", re.compile(r"^/v1/memory/prepare$")),
    ("GET", re.compile(r"^/v1/memory/state$")),
)


def product_tokens() -> Dict[str, str]:
    """`SYNAPSE_PRODUCT_TOKENS="bloom=tokA,sophie=tokB"` -> {"bloom": "tokA", ...}."""
    out: Dict[str, str] = {}
    for part in str(getattr(settings, "SYNAPSE_PRODUCT_TOKENS", "") or "").split(","):
        name, _, tok = part.strip().partition("=")
        if name.strip() and tok.strip():
            out[name.strip().lower()] = tok.strip()
    return out


def product_for_token(authorization: str) -> Optional[str]:
    for name, tok in product_tokens().items():
        if hmac.compare_digest(authorization, f"Bearer {tok}"):
            return name
    return None


def route_allowed_for_product(method: str, path: str) -> bool:
    return path == "/health" or any(m == method.upper() and rx.match(path) for m, rx in PRODUCT_ROUTES)


def clean_workspace(workspace_id: str) -> str:
    ws = str(workspace_id or "").strip()
    if not ws:
        raise HTTPException(status_code=422, detail="workspace_id required")
    if SEP in ws:
        raise HTTPException(status_code=422, detail=f"workspace_id may not contain '{SEP}' (reserved for product namespaces)")
    return ws


def scoped_workspace(product: str, workspace_id: str) -> str:
    return workspace_id if product == DEFAULT_PRODUCT else f"{product}{SEP}{workspace_id}"


def product_of_workspace(workspace_id: str) -> str:
    return str(workspace_id).split(SEP, 1)[0] if SEP in str(workspace_id) else DEFAULT_PRODUCT


def assert_scoped(product: str, workspace_id: str) -> None:
    """Defence in depth inside the pipeline: a product may only ever operate on its own namespace."""
    if product_of_workspace(workspace_id) != product:
        raise ValueError(f"workspace '{workspace_id}' is not in product '{product}' namespace")


@dataclass(frozen=True)
class Scope:
    product: str
    workspace: str              # the effective, namespaced workspace every downstream operation uses
    authenticated: bool         # True when the product came from a product credential


def resolve_scope(request: Request, workspace_id: str, companion_id: Optional[str]) -> Scope:
    ws = clean_workspace(workspace_id)
    authed = getattr(request.state, "product", None)
    claimed = str(companion_id or "").strip().lower() or None
    if authed:
        if claimed and claimed != authed:
            raise HTTPException(status_code=403, detail="product_mismatch: this credential is not valid for that product")
        product = authed
    else:
        try:
            product = product_memory.get(claimed).name        # legacy/internal credential: claim accepted (documented bypass)
        except KeyError:
            raise HTTPException(status_code=422, detail=f"unknown_memory_product:{claimed}; known: {', '.join(product_memory.known())}")
    try:
        product_memory.get(product)
    except KeyError:
        raise HTTPException(status_code=403, detail=f"product_not_configured:{product}")
    return Scope(product=product, workspace=scoped_workspace(product, ws), authenticated=bool(authed))
