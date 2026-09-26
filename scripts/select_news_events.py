from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


CATEGORY_PATTERNS = {
    "earnings_guidance": r"\b(?:earnings|quarterly results|financial results|revenue|profit|guidance|outlook|forecast)\b",
    "merger_acquisition": r"\b(?:acqui(?:re|res|red|sition)|merger|takeover|buyout|deal to buy)\b",
    "product_strategy": r"\b(?:launch(?:es|ed)?|unveil(?:s|ed)?|product|platform|chip|model|service|partnership|investment)\b",
    "regulation_litigation": r"\b(?:lawsuit|litigation|antitrust|regulat(?:or|ory|ion)|investigation|settlement|fine|court)\b",
    "capital_distribution": r"\b(?:dividend|buyback|repurchase|stock split|share split)\b",
    "management_operations": r"\b(?:appoint(?:s|ed)?|resign(?:s|ed)?|chief executive|CEO|layoffs?|plant|factory|production)\b",
}


def _mention_pattern(ticker: str, aliases: list[str]) -> str:
    values = list(dict.fromkeys([ticker, *aliases]))
    return "|".join(
        rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])" for value in values
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a diverse, high-relevance corporate-news audit sample"
    )
    parser.add_argument("--target", type=int, default=44)
    parser.add_argument("--minimum-relevance", type=float, default=0.80)
    parser.add_argument("--maximum-per-ticker", type=int, default=3)
    args = parser.parse_args()
    news = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "alpha_vantage_news.parquet"
    )
    aliases = load_yaml(PROJECT_ROOT / "config" / "news_aliases.yaml")["aliases"]
    sample = news.loc[
        news["ticker"].eq(news["query_ticker"])
        & news["ticker_relevance_score"].ge(args.minimum_relevance)
    ].copy()
    text = sample["title"].fillna("") + " " + sample["summary"].fillna("")
    direct = pd.Series(False, index=sample.index)
    for ticker, ticker_aliases in aliases.items():
        mask = sample["ticker"].eq(ticker)
        if mask.any():
            direct.loc[mask] = text.loc[mask].str.contains(
                _mention_pattern(ticker, ticker_aliases), case=False, regex=True, na=False
            )
    sample = sample.loc[direct].copy()
    text = sample["title"].fillna("") + " " + sample["summary"].fillna("")
    sample["announcement_category"] = "other_material_company_news"
    for category, pattern in CATEGORY_PATTERNS.items():
        matched = text.str.contains(pattern, case=False, regex=True, na=False)
        sample.loc[
            matched & sample["announcement_category"].eq("other_material_company_news"),
            "announcement_category",
        ] = category
    sample["material_keyword_match"] = sample["announcement_category"].ne(
        "other_material_company_news"
    )
    source_bonus = sample["source_domain"].fillna("").str.contains(
        r"businesswire|globenewswire|prnewswire|sec\.gov|investor|ir\.",
        case=False,
        regex=True,
    ).astype(float)
    sample["selection_score"] = (
        sample["ticker_relevance_score"].fillna(0)
        + 0.25 * sample["ticker_sentiment_score"].abs().fillna(0)
        + 0.20 * sample["material_keyword_match"].astype(float)
        + 0.15 * source_bonus
    )
    sample = sample.sort_values(
        ["selection_score", "time_published_utc"], ascending=[False, True]
    ).drop_duplicates(["duplicate_story_group", "ticker"])
    sample = sample.groupby("ticker", group_keys=False).head(args.maximum_per_ticker)
    if len(sample) > args.target:
        # Round-robin selection preserves cross-sectional coverage before taking
        # additional high-score events from names with several candidates.
        sample["ticker_rank"] = sample.groupby("ticker")["selection_score"].rank(
            method="first", ascending=False
        )
        sample = sample.sort_values(
            ["ticker_rank", "selection_score"], ascending=[True, False]
        ).head(args.target)
    sample = sample.sort_values("time_published_utc").reset_index(drop=True)
    sample.insert(0, "candidate_id", [f"news_{index:03d}" for index in range(1, len(sample) + 1)])
    sample["source_timestamp_audit_status"] = np.where(
        sample["timestamp_validation_status"].isin(
            ["verified_match", "source_time_verified_alpha_mismatch"]
        ),
        "manually_verified",
        "pending_source_check",
    )
    keep = [
        "candidate_id", "article_id", "ticker", "time_published_utc",
        "validated_event_time_utc", "source_timestamp_audit_status",
        "announcement_category", "ticker_relevance_score", "ticker_sentiment_score",
        "overall_sentiment_score", "title", "source", "source_domain", "url",
        "selection_score", "timestamp_quality", "first_publication_verified",
    ]
    output = PROJECT_ROOT / "data" / "processed" / "news_event_candidates.csv"
    sample[keep].to_csv(output, index=False)
    print(
        f"Selected {len(sample)} candidates across {sample['ticker'].nunique()} tickers "
        f"and {sample['announcement_category'].nunique()} announcement categories."
    )
    print(sample["announcement_category"].value_counts().to_string())


if __name__ == "__main__":
    main()
