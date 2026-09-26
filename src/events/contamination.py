from __future__ import annotations

import re

import pandas as pd


def _direct_company_mention(text: pd.Series, aliases: list[str]) -> pd.Series:
    if not aliases:
        return pd.Series(False, index=text.index)
    pattern = "|".join(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])" for alias in aliases)
    return text.fillna("").str.contains(pattern, case=False, regex=True, na=False)


def build_event_news_flags(
    news: pd.DataFrame,
    events: pd.DataFrame,
    tickers: list[str],
    *,
    pre_minutes: int = 120,
    post_minutes: int = 120,
    queried_tickers: set[str] | None = None,
    aliases: dict[str, list[str]] | None = None,
    minimum_relevance: float = 0.60,
    high_confidence_relevance: float = 0.80,
) -> pd.DataFrame:
    """Summarize ticker news near each scheduled event without treating missing coverage as zero."""
    queried_tickers = queried_tickers or set()
    aliases = aliases or {}
    data = news.copy()
    if not data.empty:
        data["time_published_utc"] = pd.to_datetime(
            data["time_published_utc"], utc=True, errors="coerce"
        )
        if "validated_event_time_utc" in data:
            data["validated_event_time_utc"] = pd.to_datetime(
                data["validated_event_time_utc"], utc=True, errors="coerce"
            )
            data["analysis_time_utc"] = data["validated_event_time_utc"].fillna(
                data["time_published_utc"]
            )
        else:
            data["analysis_time_utc"] = data["time_published_utc"]
    rows: list[dict[str, object]] = []
    for event in events.itertuples(index=False):
        event_time = pd.Timestamp(event.scheduled_time_utc)
        start = event_time - pd.Timedelta(minutes=pre_minutes)
        end = event_time + pd.Timedelta(minutes=post_minutes)
        for ticker in tickers:
            if data.empty:
                matched = data
            else:
                matched = data.loc[
                    data["ticker"].eq(ticker)
                    & data["analysis_time_utc"].between(start, end, inclusive="both")
                ].copy()
            if not matched.empty:
                text = matched["title"].fillna("") + " " + matched["summary"].fillna("")
                matched["direct_company_mention"] = _direct_company_mention(
                    text, aliases.get(ticker, [])
                )
                matched["passes_relevance"] = matched["ticker_relevance_score"].ge(
                    minimum_relevance
                )
                screened = matched.loc[
                    matched["direct_company_mention"] & matched["passes_relevance"]
                ].copy()
                high_confidence = screened.loc[
                    screened["ticker_relevance_score"].ge(high_confidence_relevance)
                ].copy()
            else:
                screened = matched
                high_confidence = matched
            if high_confidence.empty:
                closest_seconds = None
                earliest = None
                max_relevance = None
                max_abs_sentiment = None
                sources = ""
                article_ids = ""
            else:
                differences = (
                    high_confidence["analysis_time_utc"] - event_time
                ).dt.total_seconds()
                closest_seconds = differences.iloc[differences.abs().argmin()]
                earliest = high_confidence["analysis_time_utc"].min()
                max_relevance = high_confidence["ticker_relevance_score"].max()
                max_abs_sentiment = high_confidence["ticker_sentiment_score"].abs().max()
                sources = "|".join(
                    sorted(set(high_confidence["source"].dropna().astype(str)))
                )
                article_ids = "|".join(
                    sorted(set(high_confidence["article_id"].astype(str)))
                )
            covered = ticker in queried_tickers
            rows.append(
                {
                    "event_id": event.event_id,
                    "event_time_utc": event_time,
                    "instrument": ticker,
                    "window_pre_minutes": pre_minutes,
                    "window_post_minutes": post_minutes,
                    "alpha_vantage_query_coverage": covered,
                    "article_count_raw_candidates": int(len(matched)),
                    "article_count_review_candidates": int(len(screened)),
                    "article_count": int(len(high_confidence)),
                    "minimum_ticker_relevance": minimum_relevance,
                    "high_confidence_ticker_relevance": high_confidence_relevance,
                    "candidate_company_news_contamination": bool(len(screened))
                    if covered
                    else pd.NA,
                    "company_news_contamination": bool(len(high_confidence))
                    if covered
                    else pd.NA,
                    "earliest_article_utc": earliest,
                    "closest_article_seconds": closest_seconds,
                    "max_ticker_relevance": max_relevance,
                    "max_abs_ticker_sentiment": max_abs_sentiment,
                    "sources": sources,
                    "article_ids": article_ids,
                }
            )
    return pd.DataFrame(rows)
