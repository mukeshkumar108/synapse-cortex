"""Bounded, read-only, fail-open Honcho REST client for the v3 API.

Honcho is evidence/memory. This client is the only path cortex uses to read it.
Every method is bounded (small limits), cached with a short TTL, and fail-open:
an unavailable Honcho degrades the prior-context digest, never the user turn.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 3.0
_DEFAULT_TTL = 60.0


class HonchoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
        ttl_seconds: float = _DEFAULT_TTL,
        max_cache: int = 64,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout
        self.ttl_seconds = ttl_seconds
        self.max_cache = max_cache
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._order: List[str] = []
        self.last_error: Optional[str] = None
        self.last_call: Optional[str] = None

    # ── low-level ────────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, *, params=None, body=None) -> Any:
        self.last_call = path
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(
                    method,
                    f"{self.base_url}/v3{path}",
                    headers=self.headers,
                    params=params,
                    json=body,
                )
                resp.raise_for_status()
                self.last_error = None
                return resp.json()
        except Exception as err:  # fail-open
            self.last_error = f"{type(err).__name__}: {err}"[:300]
            logger.warning("Honcho %s %s failed: %s", method, path, self.last_error)
            return None

    def _cached(self, key: str, ttl: float | None = None):
        if ttl is None:
            ttl = self.ttl_seconds
        entry = self._cache.get(key)
        if entry and entry[0] > time.monotonic() - ttl:
            return entry[1]
        return None

    def _remember(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        self._cache[key] = (time.monotonic(), value)
        self._order.append(key)
        while len(self._order) > self.max_cache:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)

    async def _get_json(self, key: str, fetcher) -> Any:
        cached = self._cached(key)
        if cached is not None:
            return cached
        value = await fetcher()
        if value is not None:
            self._remember(key, value)
        return value

    # ── bounded reads ────────────────────────────────────────────────────────

    async def recent_messages(
        self, workspace_id: str, session_id: str, limit: int = 6
    ) -> Optional[List[Dict[str, Any]]]:
        """Most recent messages in a session (reverse chronological).

        Live conversation window: deliberately NOT TTL-cached so a rapid
        multi-turn run sees fresh prior evidence on every turn.
        """
        data = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/sessions/{session_id}/messages/list",
            params={"page": 1, "size": limit, "reverse": True},
            body={},
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return None
        return [
            {
                "id": item.get("id"),
                "content": item.get("content"),
                "peer_id": item.get("peer_id"),
                "created_at": item.get("created_at"),
                "metadata": item.get("metadata") or {},
            }
            for item in data["items"][:limit]
        ]

    async def search_messages(
        self,
        workspace_id: str,
        session_id: str,
        query: str,
        limit: int = 6,
    ) -> Optional[List[Dict[str, Any]]]:
        """Semantic message search for the CURRENT turn. Relevance-based rather
        than recency-based, so the digest admits evidence tied to *this* turn.
        Live conversation window: not TTL-cached.
        """
        if not query or not query.strip():
            return None
        data = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/sessions/{session_id}/search",
            body={"query": query[:500], "limit": limit},
        )
        if not isinstance(data, list):
            return None
        return [
            {
                "id": item.get("id"),
                "content": item.get("content"),
                "peer_id": item.get("peer_id"),
                "created_at": item.get("created_at"),
                "metadata": item.get("metadata") or {},
            }
            for item in data[:limit]
        ]

    async def session_summaries(
        self, workspace_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Short/long session summaries, content only (bounded)."""
        key = f"summaries:{workspace_id}:{session_id}"

        async def fetch():
            data = await self._request(
                "GET",
                f"/workspaces/{workspace_id}/sessions/{session_id}/summaries",
            )
            if not isinstance(data, dict):
                return None
            return {
                "short_summary": (data.get("short_summary") or {}).get("content"),
                "long_summary": (data.get("long_summary") or {}).get("content"),
            }

        return await self._get_json(key, fetch)

    async def conclusions(
        self, workspace_id: str, observed: Optional[str] = None, limit: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """Recent conclusions, optionally scoped to a subject peer."""
        key = f"conclusions:{workspace_id}:{observed or '*'}:{limit}"

        async def fetch():
            filters = {"observed_id": observed} if observed else {}
            data = await self._request(
                "POST",
                f"/workspaces/{workspace_id}/conclusions/list",
                params={"page": 1, "size": limit},
                body={"filters": filters},
            )
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                return None
            return [
                {
                    "id": item.get("id"),
                    "content": item.get("content"),
                    "observer_id": item.get("observer_id"),
                    "observed_id": item.get("observed_id"),
                    "level": item.get("level"),
                    "created_at": item.get("created_at"),
                }
                for item in data["items"][:limit]
            ]

        return await self._get_json(key, fetch)