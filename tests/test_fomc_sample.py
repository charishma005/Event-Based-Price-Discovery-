from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


def test_fomc_clocks_are_timezone_aware_and_ordered() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "fomc_sample.yaml")
    assert len(config["meetings"]) == 14
    for meeting in config["meetings"]:
        statement = pd.Timestamp(meeting["statement_time_utc"])
        press = pd.Timestamp(meeting["press_conference_time_utc"])
        start = pd.Timestamp(meeting["request_start_utc"])
        end = pd.Timestamp(meeting["request_end_utc"])
        assert statement.tz is not None
        assert start < statement < press < end


def test_placebos_exclude_known_two_pm_treasury_dates() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "fomc_placebos.yaml")
    assert len(config["placebos"]) == 24
    dates = {
        pd.Timestamp(value["placebo_time_utc"]).date().isoformat()
        for value in config["placebos"]
    }
    assert "2025-03-12" not in dates
    assert "2025-06-11" not in dates
    for placebo in config["placebos"]:
        event = pd.Timestamp(placebo["placebo_time_utc"])
        start = pd.Timestamp(placebo["request_start_utc"])
        end = pd.Timestamp(placebo["request_end_utc"])
        assert start == event - pd.Timedelta(minutes=5)
        assert end == event + pd.Timedelta(minutes=10)


def test_processed_depth_comparison_has_one_row_per_meeting_instrument() -> None:
    path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fomc_placebos"
        / "matched_depth_comparison.parquet"
    )
    if not path.exists():
        return
    frame = pd.read_parquet(path)
    assert len(frame) >= 36
    assert frame[["matched_meeting", "instrument"]].duplicated().sum() == 0
    assert frame["placebo_count"].ge(1).all()


def test_macro_sample_has_official_clocks_and_one_declared_bundle() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "macro_sample.yaml")
    events = config["events"]
    assert len(events) == 32
    assert len({(event["request_start_utc"], event["request_end_utc"]) for event in events}) == 31
    may15 = [event for event in events if event["event_date"] == "2025-05-15"]
    assert {event["event_type"] for event in may15} == {"ppi", "retail_sales"}
    for event in events:
        clock = pd.Timestamp(event["event_time_utc"])
        assert clock.tz is not None
        assert pd.Timestamp(event["request_start_utc"]) == clock - pd.Timedelta(minutes=5)
        assert pd.Timestamp(event["request_end_utc"]) == clock + pd.Timedelta(minutes=6)


def test_macro_placebos_are_timezone_aware_and_exact_clock_controls() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "macro_placebos.yaml")
    assert len(config["placebos"]) == 20
    assert {value["matched_month"] for value in config["placebos"]} == {
        *(f"2024-{month:02d}" for month in range(1, 13)),
        *(f"2025-{month:02d}" for month in range(1, 9)),
    }
    for placebo in config["placebos"]:
        event = pd.Timestamp(placebo["placebo_time_utc"])
        start = pd.Timestamp(placebo["request_start_utc"])
        end = pd.Timestamp(placebo["request_end_utc"])
        assert event.tzinfo is not None
        assert event - start == pd.Timedelta(minutes=5)
        assert end - event == pd.Timedelta(minutes=6)
