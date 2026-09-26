import pandas as pd

from src.events.registry import pilot_events


def test_pilot_event_registry_has_timezone_and_conditions() -> None:
    events = pilot_events()
    required = {
        "statement",
        "press_conference",
        "ppi_20250910",
        "cpi_20250911",
        "retail_sales_20250916",
        "industrial_production_20250916",
        "housing_20250917",
    }
    assert required.issubset(events)
    assert all(isinstance(event["time"], pd.Timestamp) for event in events.values())
    assert all(event["time"].tzinfo is not None for event in events.values())
    assert events["housing_20250917"]["dataset_condition"]["futures"] == "degraded"


def test_statement_and_press_conference_remain_distinct() -> None:
    events = pilot_events()
    assert events["statement"]["event_id"] != events["press_conference"]["event_id"]
    assert events["statement"]["time"] == pd.Timestamp("2025-09-17T18:00:00Z")
    assert events["press_conference"]["time"] == pd.Timestamp("2025-09-17T18:30:00Z")


def test_source_verified_news_and_placebo_are_distinct() -> None:
    events = pilot_events()
    news = events["nvda_intel_announcement"]
    placebo = events["nvda_intel_placebo_20250917"]
    assert news["event_type"] == "unscheduled_corporate_news"
    assert news["representation_class"] == "narrative_text"
    assert news["source_timestamp_status"] == "source_time_verified_alpha_mismatch"
    assert news["time"] == pd.Timestamp("2025-09-18T11:00:00Z")
    assert placebo["event_type"] == "matched_placebo"
    assert placebo["time"] == pd.Timestamp("2025-09-17T11:00:00Z")
