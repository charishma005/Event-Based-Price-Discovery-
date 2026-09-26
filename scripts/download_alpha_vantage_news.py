from __future__ import annotations

import argparse
import time

from src.data.alphavantage_client import AlphaVantageClient
from src.utils.config import PROJECT_ROOT, load_yaml


def universe_tickers() -> list[str]:
    config = load_yaml(PROJECT_ROOT / "config" / "universe.yaml")
    return [item["ticker"] for item in config["securities"]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache Alpha Vantage NEWS_SENTIMENT once per ticker."
    )
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument(
        "--topics",
        nargs="*",
        default=None,
        help="Topic queries made separately because comma-separated topics also use AND semantics.",
    )
    parser.add_argument("--time-from", default="20250908T0000")
    parser.add_argument("--time-to", default="20250920T0000")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=13.0,
        help="Pause between uncached-looking calls to respect conservative rate limits.",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Make requests; otherwise print the plan."
    )
    args = parser.parse_args()
    tickers = [value.upper() for value in (args.tickers or universe_tickers())]
    topics = args.topics
    if topics is None:
        topics = ["economy_monetary", "economy_macro", "financial_markets"]
    request_count = len(tickers) + len(topics)
    if request_count > args.max_requests:
        raise SystemExit(
            f"Planned {request_count} requests, above --max-requests={args.max_requests}."
        )
    print(
        "Alpha Vantage NEWS_SENTIMENT plan\n"
        f"  Period: {args.time_from} through {args.time_to} UTC\n"
        f"  Tickers: {', '.join(tickers)}\n"
        f"  Topics: {', '.join(topics) if topics else '(none)'}\n"
        f"  Requests: {request_count} (one per filter; comma filters are AND, not OR)\n"
        f"  Limit per request: {args.limit}\n"
        f"  Execute: {args.execute}"
    )
    if not args.execute:
        return
    client = AlphaVantageClient()
    total = 0
    completed = 0
    for ticker in tickers:
        payload = client.news_sentiment(
            tickers=ticker,
            time_from=args.time_from,
            time_to=args.time_to,
            limit=args.limit,
        )
        count = len(payload.get("feed", []))
        total += count
        suffix = " (possible truncation)" if count >= args.limit else ""
        print(f"  {ticker}: {count} articles{suffix}")
        completed += 1
        if completed < request_count and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)
    for topic in topics:
        payload = client.news_sentiment(
            topics=topic,
            time_from=args.time_from,
            time_to=args.time_to,
            limit=args.limit,
        )
        count = len(payload.get("feed", []))
        total += count
        suffix = " (possible truncation)" if count >= args.limit else ""
        print(f"  topic:{topic}: {count} articles{suffix}")
        completed += 1
        if completed < request_count and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)
    print(f"Completed {request_count} queries; {total} article responses before deduplication.")


if __name__ == "__main__":
    main()
