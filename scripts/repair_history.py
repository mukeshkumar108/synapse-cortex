"""CLI: python -m scripts.repair_history --workspace WS [--apply]
Dry-run by default. Never deletes evidence."""
import argparse
import asyncio
import json
from datetime import datetime, timezone

from src.services.historical_repair import HistoricalRepairService
from src.db import async_session_maker


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    async with async_session_maker() as session:
        report = await HistoricalRepairService().classify_and_repair(
            session,
            workspace_id=args.workspace,
            now=datetime.now(timezone.utc),
            apply=args.apply,
            owner_peer_id=args.owner,
        )
    print(json.dumps(report.summary(), indent=2))
    for action in report.actions:
        print(f"{action.classification:22} {action.action:22} "
              f"{action.target_type}:{action.target_id[:8]} {action.title!r} "
              f"- {action.reason}")


if __name__ == "__main__":
    asyncio.run(main())
