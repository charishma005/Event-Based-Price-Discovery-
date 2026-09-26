from __future__ import annotations

import argparse
from pathlib import Path

from src.data.news import apply_timestamp_validations, normalize_cached_news
from src.events.calendar import load_event_calendar
from src.events.contamination import build_event_news_flags
from src.utils.config import PROJECT_ROOT, load_yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize cached Alpha Vantage news and build event contamination flags."
    )
    parser.add_argument("--pre-minutes", type=int, default=120)
    parser.add_argument("--post-minutes", type=int, default=120)
    args = parser.parse_args()
    raw_dir = PROJECT_ROOT / "data" / "raw" / "alphavantage"
    payloads = sorted(
        path
        for path in raw_dir.glob("news_sentiment-*.json")
        if not path.name.endswith(".metadata.json")
    )
    if not payloads:
        raise SystemExit(
            "No cached Alpha Vantage news payloads found. Run "
            "`python -m scripts.download_alpha_vantage_news --execute` first."
        )
    news, queries = normalize_cached_news(payloads)
    validations = load_yaml(
        PROJECT_ROOT / "config" / "news_timestamp_validations.yaml"
    )
    news = apply_timestamp_validations(news, validations)
    processed = PROJECT_ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    news_path = processed / "alpha_vantage_news.parquet"
    query_path = processed / "alpha_vantage_news_queries.csv"
    flags_path = processed / "event_news_contamination.parquet"
    flags_csv = processed / "event_news_contamination.csv"
    news.to_parquet(news_path, index=False)
    queries.to_csv(query_path, index=False)

    universe = load_yaml(PROJECT_ROOT / "config" / "universe.yaml")
    tickers = [item["ticker"] for item in universe["securities"]]
    aliases = load_yaml(PROJECT_ROOT / "config" / "news_aliases.yaml")["aliases"]
    settings = load_yaml(PROJECT_ROOT / "config" / "settings.yaml")
    minimum_relevance = float(settings["news"]["minimum_ticker_relevance_for_review"])
    high_confidence_relevance = float(
        settings["news"]["high_confidence_ticker_relevance"]
    )
    events = load_event_calendar(PROJECT_ROOT / "data" / "events" / "event_calendar.csv")
    queried = set(queries["query_ticker"].dropna().astype(str))
    flags = build_event_news_flags(
        news,
        events,
        tickers,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        queried_tickers=queried,
        aliases=aliases,
        minimum_relevance=minimum_relevance,
        high_confidence_relevance=high_confidence_relevance,
    )
    flags.to_parquet(flags_path, index=False)
    flags.to_csv(flags_csv, index=False)
    invalid_times = int(news["time_published_utc"].isna().sum())
    duplicates = int(news.duplicated(["duplicate_story_group", "ticker"]).sum())
    print(
        f"Wrote {len(news)} article-ticker rows to {news_path}\n"
        f"Wrote {len(flags)} event-instrument flags to {flags_path}\n"
        f"Timestamp parse failures: {invalid_times}; repeated-title rows: {duplicates}"
    )


if __name__ == "__main__":
    main()
