from __future__ import annotations

import argparse
import asyncio
import json

from app.config import settings
from app.orchestrator import Orchestrator
from app.storage import Storage


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run thorough deep analysis for any US stock")
    parser.add_argument("symbol", nargs="?", default="NVDA", help="Ticker symbol, e.g., NVDA, AAPL, MSFT")
    parser.add_argument("--horizon-days", type=int, default=365)
    parser.add_argument("--no-macro", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of readable narrative")
    args = parser.parse_args()

    storage = Storage(settings.database_url)
    orchestrator = Orchestrator(settings, storage)

    payload = {
        "symbol": args.symbol.upper(),
        "horizon_days": args.horizon_days,
        "depth": "deep",
        "include_macro": not args.no_macro,
        "valuation_modes": ["dcf", "multiples", "scenarios"],
    }

    job_id = storage.create_job(symbol=payload["symbol"], request_payload=payload)
    await orchestrator.run_job(job_id, payload)

    status = storage.get_job(job_id)
    report = storage.get_report(job_id)
    if args.json:
        print(json.dumps({"job": status, "report": report}, indent=2))
        return

    if not status:
        print("No job status found.")
        return
    print(f"Job {status['job_id']} status: {status['status']}")
    if status.get("error"):
        print(f"Error: {status['error']}")
        return
    if not report:
        print("No report generated.")
        return

    print()
    en = report.get("narrative_en", report.get("narrative", report.get("thesis", "No narrative available.")))
    zh = report.get("narrative_zh", en)
    print("[English]")
    print(en)
    print()
    print("[中文]")
    print(zh)
    print()
    print("Sources:")
    for cite in report.get("citations", [])[:8]:
        print(f"- {cite.get('source')}: {cite.get('url')}")


if __name__ == "__main__":
    asyncio.run(main())
