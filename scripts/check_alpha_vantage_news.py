from __future__ import annotations

import argparse

from src.data.alphavantage_client import AlphaVantageClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache a narrow historical news sample")
    parser.add_argument(
        "--ticker",
        default="NVDA",
        help="One ticker only. Alpha Vantage comma filters require all tickers to co-occur.",
    )
    args = parser.parse_args()
    client = AlphaVantageClient()
    payload = client.news_sentiment(
        tickers=args.ticker,
        time_from="20250917T1730",
        time_to="20250917T1930",
        limit=1000,
    )
    feed = payload.get("feed", [])
    print(f"Cached {len(feed)} articles; inspect metadata, timestamp resolution, and duplicates before research use.")


if __name__ == "__main__":
    main()
