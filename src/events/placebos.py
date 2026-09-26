from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def matched_placebo_times(
    event_time_utc: pd.Timestamp,
    *,
    excluded_dates: Iterable[str | pd.Timestamp],
    candidate_trading_dates: Iterable[str | pd.Timestamp],
    count: int = 3,
) -> list[pd.Timestamp]:
    """Return nearby same-clock, same-weekday dates, excluding event dates."""
    event = pd.Timestamp(event_time_utc)
    if event.tzinfo is None:
        raise ValueError("event_time_utc must be timezone-aware")
    event = event.tz_convert("UTC")
    excluded = {pd.Timestamp(d).date() for d in excluded_dates}
    candidates: list[pd.Timestamp] = []
    for value in candidate_trading_dates:
        day = pd.Timestamp(value)
        if day.date() in excluded or day.weekday() != event.weekday():
            continue
        candidate = pd.Timestamp.combine(day.date(), event.time()).tz_localize("UTC")
        candidates.append(candidate)
    candidates.sort(key=lambda value: abs(value - event))
    return candidates[:count]

