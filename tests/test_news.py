from __future__ import annotations

import pandas as pd

from src.data.news import (
    apply_timestamp_validations,
    canonicalize_url,
    normalize_news_payload,
)
from src.events.contamination import build_event_news_flags


def sample_payload() -> dict:
    return {
        "feed": [
            {
                "title": "Company updates outlook",
                "url": "https://example.test/story",
                "time_published": "20250917T175959",
                "authors": ["Reporter"],
                "summary": "An update.",
                "source": "Example Wire",
                "source_domain": "example.test",
                "topics": [{"topic": "Earnings", "relevance_score": "0.9"}],
                "overall_sentiment_score": "-0.2",
                "overall_sentiment_label": "Somewhat-Bearish",
                "ticker_sentiment": [
                    {
                        "ticker": "NVDA",
                        "relevance_score": "0.8",
                        "ticker_sentiment_score": "-0.3",
                        "ticker_sentiment_label": "Bearish",
                    }
                ],
            }
        ]
    }


def test_normalize_alpha_vantage_news() -> None:
    result = normalize_news_payload(sample_payload(), query_ticker="NVDA")
    assert len(result) == 1
    assert result.loc[0, "ticker"] == "NVDA"
    assert result.loc[0, "timestamp_precision"] == "second"
    assert result.loc[0, "time_published_utc"] == pd.Timestamp(
        "2025-09-17T17:59:59Z"
    )
    assert result.loc[0, "ticker_relevance_score"] == 0.8
    assert not bool(result.loc[0, "eligible_as_unscheduled_event"])


def test_canonical_url_removes_tracking_parameters() -> None:
    one = "https://www.example.com/story?gaa_sig=one&utm_source=x&id=7"
    two = "https://example.com/story?id=7&gaa_sig=two&utm_source=y"
    assert canonicalize_url(one) == canonicalize_url(two)


def test_contamination_uses_coverage_not_false_zero() -> None:
    news = normalize_news_payload(sample_payload(), query_ticker="NVDA")
    events = pd.DataFrame(
        {
            "event_id": ["fomc"],
            "scheduled_time_utc": [pd.Timestamp("2025-09-17T18:00:00Z")],
        }
    )
    flags = build_event_news_flags(
        news, events, ["NVDA", "JPM"], pre_minutes=5, post_minutes=5,
        queried_tickers={"NVDA"}, aliases={"NVDA": ["Company"]},
    ).set_index("instrument")
    assert bool(flags.loc["NVDA", "company_news_contamination"])
    assert flags.loc["NVDA", "closest_article_seconds"] == -1
    assert pd.isna(flags.loc["JPM", "company_news_contamination"])


def test_source_timestamp_overrides_bad_provider_clock() -> None:
    news = normalize_news_payload(sample_payload(), query_ticker="NVDA")
    article_id = news.loc[0, "article_id"]
    checked = apply_timestamp_validations(
        news,
        {
            article_id: {
                "source_time_utc": "2025-09-17T18:01:00Z",
                "validation_status": "source_time_verified_alpha_mismatch",
            }
        },
    )
    assert checked.loc[0, "validated_event_time_utc"] == pd.Timestamp(
        "2025-09-17T18:01:00Z"
    )
    assert checked.loc[0, "alpha_minus_source_seconds"] == -61
    assert bool(checked.loc[0, "eligible_as_unscheduled_event"])
