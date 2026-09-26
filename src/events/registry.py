from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


@lru_cache(maxsize=1)
def pilot_events() -> dict[str, dict[str, Any]]:
    """Load the single source of truth for processed pilot-event metadata."""
    raw = load_yaml(PROJECT_ROOT / "config" / "pilot_events.yaml")
    events: dict[str, dict[str, Any]] = {}
    for label, metadata in raw.items():
        item = dict(metadata)
        timestamp = pd.Timestamp(item.pop("time_utc"))
        if timestamp.tzinfo is None:
            raise ValueError(f"pilot event {label!r} must have a timezone-aware timestamp")
        item["time"] = timestamp.tz_convert("UTC")
        events[label] = item
    return events
