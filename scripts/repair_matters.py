"""One-time Matter repair (docs/COGNITION_ARCHITECTURE.md): fold twins and relabel raw titles, with the MODEL deciding.

Code nominates candidate pairs by cheap title similarity (nomination only, never a decision); the bounded `same_matter` judge decides; merges
use the existing non-destructive `merge_matters` (the dropped Matter is archived with `merged_into_id`). Raw-utterance titles are relabelled by a
model into a short neutral label. Every change is printed old -> new. Dry run by default.

  python scripts/repair_matters.py --owner-prefix user_5377a025 [--apply]
"""
import argparse
import asyncio
import json
import sys
from difflib import SequenceMatcher

from sqlmodel import select

sys.path.insert(0, ".")
from src.db import async_session_maker  # noqa: E402
from src.models.matter import Matter  # noqa: E402
from src.runtime_model import get_agenda_adapter  # noqa: E402
from src.services import matter_service, semantic_judge  # noqa: E402

import os
LABEL_MODEL = os.getenv("SYNAPSE_EXTRACTOR_MODEL") or "deepseek/deepseek-v4-flash"
NOMINATE_RATIO = 0.55
LONG_TITLE = 90


async def relabel(adapter, title: str) -> str | None:
    try:
        raw = await _label_call(adapter, title)
    except Exception as exc:
        print(f"    (label call failed: {type(exc).__name__})")
        return None
    label = str((raw or {}).get("label") or "").strip().strip('"')
    return label if 3 <= len(label) <= 80 else None


async def _label_call(adapter, title: str):
    return await adapter.generate_structured(
        system=("Give a short neutral label (at most 8 words, same language as the text) for the matter described. Keep its meaning; add no facts; "
                "no quotes."),
        prompt=f"TEXT: {title}", json_schema={"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]},
        model_id=LABEL_MODEL, max_tokens=60, temperature=0.0, strict=True, timeout=20.0)


async def main(owner_prefix: str, apply: bool) -> None:
    adapter = get_agenda_adapter()
    if adapter is None:
        raise SystemExit("no model credentials")
    async with async_session_maker() as db:
        rows = [m for m in (await db.execute(select(Matter).where(Matter.status.in_(["active", "dormant"]), Matter.merged_into_id.is_(None)))).scalars().all()
                if (m.owner_peer_id or "").startswith(owner_prefix)]
        print(f"{len(rows)} live matters for {owner_prefix}*")
        merged: set = set()
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.id in merged or b.id in merged or a.owner_peer_id != b.owner_peer_id:
                    continue
                if SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio() < NOMINATE_RATIO:
                    continue
                verdict = await semantic_judge.judge(kind="same_matter", earlier=a.title, later=b.title, adapter=adapter)
                print(f"  nominated: {a.title[:60]!r} <-> {b.title[:60]!r} -> {'SAME' if verdict else 'different'}")
                if verdict:
                    keep, drop = (a, b) if a.first_seen <= b.first_seen else (b, a)
                    if apply:
                        await matter_service.merge_matters(db, keep.id, drop.id)
                    merged.add(drop.id)
                    print(f"    {'merged' if apply else 'would merge'} {drop.title[:60]!r} into {keep.title[:60]!r}")
        for m in rows:
            if m.id in merged or len(m.title) <= LONG_TITLE:
                continue
            label = await relabel(adapter, m.title)
            print(f"  relabel: {m.title[:80]!r}... -> {label!r}")
            if apply and label:
                m.title = label
                db.add(m)
        if apply:
            await db.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-prefix", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.owner_prefix, args.apply))
