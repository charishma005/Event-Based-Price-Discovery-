from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


def test_source_verified_sample_matches_timestamp_registry() -> None:
    sample = load_yaml(PROJECT_ROOT / "config" / "unscheduled_news_sample.yaml")
    validations = load_yaml(PROJECT_ROOT / "config" / "news_timestamp_validations.yaml")
    for event in sample["events"]:
        validation = validations[event["article_id"]]
        assert validation["ticker"] == event["instrument"]
        assert pd.Timestamp(validation["source_time_utc"]) == pd.Timestamp(
            event["event_time_utc"]
        )
        assert validation["validation_status"] in {
            "verified_match",
            "source_time_verified_alpha_mismatch",
        }


def test_matched_news_controls_have_no_high_confidence_article_within_hour() -> None:
    summary = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "unscheduled_news"
        / "source_verified_summary.csv"
    )
    assert len(summary) == 6
    assert summary["placebo_high_confidence_articles_pm60m"].eq(0).all()
    assert summary["event_high_confidence_articles_pm60m"].eq(1).all()


def test_source_verified_summary_preserves_mechanical_failures() -> None:
    summary = pd.read_csv(
        PROJECT_ROOT
        / "data"
        / "processed"
        / "unscheduled_news"
        / "source_verified_summary.csv"
    )
    assert summary["valid_mechanically"].sum() == 3
    failures = summary.loc[~summary["valid_mechanically"]]
    assert failures["quality_flags"].str.contains("trade_before_first_post_event_quote").all()
