from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "event_id", "event_date", "scheduled_time_et", "scheduled_time_utc",
    "source_agency", "event_name", "event_category", "representation_class",
    "scheduled_indicator", "numeric_or_narrative", "expected_value",
    "realized_value", "prior_value", "forecast_dispersion",
    "standardized_surprise", "authoritative_source_url", "notes",
}
REPRESENTATION_CLASSES = {
    "scalar_numeric", "multi_dimensional_numeric", "narrative_text",
    "extemporaneous_speech",
}


def load_event_calendar(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"event_id": "string"})
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"event calendar missing columns: {sorted(missing)}")
    if frame["event_id"].duplicated().any():
        raise ValueError("event_id must be unique")
    unknown = set(frame["representation_class"].dropna()) - REPRESENTATION_CLASSES
    if unknown:
        raise ValueError(f"unknown representation classes: {sorted(unknown)}")
    frame["scheduled_time_utc"] = pd.to_datetime(
        frame["scheduled_time_utc"], utc=True, errors="coerce"
    )
    frame["scheduled_time_et"] = pd.to_datetime(
        frame["scheduled_time_et"], utc=True, errors="coerce", format="mixed"
    ).dt.tz_convert("America/New_York")
    if frame["scheduled_time_utc"].isna().any():
        bad = frame.loc[frame["scheduled_time_utc"].isna(), "event_id"].tolist()
        raise ValueError(f"missing/invalid UTC timestamps: {bad}")
    return frame
