"""Small historical-corpus adapter used by ``scripts/historical_replay.py``.

Source databases are opened in read-only transactions.  The returned corpus
is plain JSON so replay never needs credentials and never writes to history.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


@dataclass
class HistoricalTurn:
    message_id: str
    role: str
    text: str
    created_at: str


@dataclass
class HistoricalSession:
    source_session_id: str
    started_at: str
    ended_at: str
    turns: list[HistoricalTurn] = field(default_factory=list)
    boundary: str = "source_session"


@dataclass
class HistoricalCorpus:
    schema_version: int
    source: str
    source_locator: str
    subject_id: str
    companion_id: str
    sessions: list[HistoricalSession]
    provenance: dict[str, Any] = field(default_factory=dict)

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))


def load_corpus(path: Path) -> HistoricalCorpus:
    raw = json.loads(path.read_text())
    sessions = [HistoricalSession(
        source_session_id=s["source_session_id"],
        started_at=s["started_at"], ended_at=s["ended_at"],
        boundary=s.get("boundary", "source_session"),
        turns=[HistoricalTurn(**t) for t in s.get("turns", [])],
    ) for s in raw["sessions"]]
    return HistoricalCorpus(
        schema_version=int(raw.get("schema_version", 1)), source=raw["source"],
        source_locator=raw["source_locator"], subject_id=raw["subject_id"],
        companion_id=raw["companion_id"], sessions=sessions,
        provenance=raw.get("provenance", {}),
    )


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _rpd2_text(parts: Any) -> str:
    if isinstance(parts, str):
        try:
            parts = json.loads(parts)
        except json.JSONDecodeError:
            return ""
    if not isinstance(parts, list):
        return ""
    return "\n".join(
        str(p.get("text") or "") for p in parts
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


def split_on_idle(turns: Iterable[HistoricalTurn], idle_minutes: int = 30,
                  prefix: str = "scene") -> list[HistoricalSession]:
    """Split only at observed timestamp gaps; never infer semantic scenes."""
    groups: list[list[HistoricalTurn]] = []
    for turn in turns:
        stamp = datetime.fromisoformat(turn.created_at)
        if not groups:
            groups.append([turn])
            continue
        prior = datetime.fromisoformat(groups[-1][-1].created_at)
        if stamp - prior >= timedelta(minutes=idle_minutes):
            groups.append([])
        groups[-1].append(turn)
    return [HistoricalSession(
        source_session_id=f"{prefix}:{i + 1}",
        started_at=g[0].created_at, ended_at=g[-1].created_at, turns=g,
        boundary=f"observed_idle_gap_{idle_minutes}m",
    ) for i, g in enumerate(groups) if g]


async def export_sophie(database_url: str, *, user_id: str, persona_id: str,
                        min_messages: int = 2, limit: int = 8) -> HistoricalCorpus:
    import asyncpg
    conn = await asyncpg.connect(database_url.replace(
        "postgresql+asyncpg://", "postgresql://"), ssl="require")
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch('''
                select s.id, s."startedAt", s."lastActivityAt", m.id message_id,
                       m.role::text role, m.content, m."createdAt"
                from "Session" s
                join "Message" m
                  on coalesce(m.metadata->>'sessionId', m.metadata->>'session_id') = s.id
                where s."userId"=$1 and s."personaId"=$2
                order by s."startedAt", m."createdAt", m.id
            ''', user_id, persona_id)
    finally:
        await conn.close()
    grouped: dict[str, list[Any]] = {}
    meta: dict[str, tuple[Any, Any]] = {}
    for row in rows:
        grouped.setdefault(row["id"], []).append(row)
        meta[row["id"]] = (row["startedAt"], row["lastActivityAt"])
    eligible = [(sid, rs) for sid, rs in grouped.items() if len(rs) >= min_messages]
    eligible = eligible[-limit:]
    sessions = [HistoricalSession(
        source_session_id=sid, started_at=_iso(meta[sid][0]),
        ended_at=_iso(meta[sid][1]), boundary="source_session",
        turns=[HistoricalTurn(str(r["message_id"]), str(r["role"]),
                              str(r["content"] or ""), _iso(r["createdAt"]))
               for r in rs if str(r["content"] or "").strip()],
    ) for sid, rs in eligible]
    return HistoricalCorpus(
        schema_version=1, source="old-sophie-postgres",
        source_locator="Session + Message.metadata.sessionId",
        subject_id=user_id, companion_id=persona_id, sessions=sessions,
        provenance={"selection": "latest explicit linked sessions",
                    "min_messages": min_messages, "limit": limit},
    )


async def export_rpd2(database_url: str, *, chat_id: str,
                      idle_minutes: int = 30) -> HistoricalCorpus:
    import asyncpg
    conn = await asyncpg.connect(database_url.replace(
        "postgresql+asyncpg://", "postgresql://"), ssl="require")
    try:
        async with conn.transaction(readonly=True):
            chat = await conn.fetchrow(
                'select id,"userId","characterId",title from "Chat" where id=$1::uuid',
                chat_id)
            if chat is None:
                raise ValueError(f"RPD2 chat not found: {chat_id}")
            rows = await conn.fetch('''
                select id, role, parts, "createdAt" from "Message_v2"
                where "chatId"=$1::uuid order by "createdAt", id
            ''', chat_id)
    finally:
        await conn.close()
    turns = [HistoricalTurn(str(r["id"]), str(r["role"]), _rpd2_text(r["parts"]),
                            _iso(r["createdAt"])) for r in rows]
    turns = [t for t in turns if t.text]
    sessions = split_on_idle(turns, idle_minutes, prefix=f"{chat_id}:scene")
    return HistoricalCorpus(
        schema_version=1, source="rpd2-backup-postgres",
        source_locator="Chat + Message_v2",
        subject_id=str(chat["userId"]), companion_id=str(chat["characterId"]),
        sessions=sessions,
        provenance={"chat_id": chat_id, "title": chat["title"],
                    "boundary_rule": f"observed gap >= {idle_minutes} minutes"},
    )


def lexical_future_references(titles: Iterable[str], future_text: str) -> list[dict[str, Any]]:
    """Cheap observable lead only; explicitly not a semantic score."""
    future = re.sub(r"[^a-z0-9 ]+", " ", future_text.lower())
    refs = []
    stop = {"that", "this", "with", "from", "have", "will", "about", "thing",
            "user", "matter", "watch", "event", "uncertainty", "need"}
    for title in titles:
        words = [w for w in re.findall(r"[a-z0-9]+", title.lower())
                 if len(w) >= 4 and w not in stop]
        hits = sorted({w for w in words if re.search(rf"\b{re.escape(w)}\b", future)})
        if hits:
            refs.append({"title": title, "matched_terms": hits[:8]})
    return refs
