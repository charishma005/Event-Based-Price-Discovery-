from __future__ import annotations

import pandas as pd

from scripts.build_fomc_sample_config import build_meetings
from src.utils.config import PROJECT_ROOT, load_yaml


def test_generated_meetings_match_hand_built_2024_2025_config() -> None:
    generated = {m["label"]: m for m in build_meetings("2015-01-01", "2025-12-31")}
    for meeting in load_yaml(PROJECT_ROOT / "config" / "fomc_sample.yaml")["meetings"]:
        new = generated[meeting["label"]]
        for key in ("statement_time_utc", "press_conference_time_utc", "sep_release", "policy_change_bps"):
            assert new[key] == meeting[key], (meeting["label"], key)


def test_pre_2019_meetings_without_press_use_statement_window() -> None:
    meetings = {m["label"]: m for m in build_meetings("2015-01-01", "2025-12-31")}
    assert len(meetings) == 87
    january = meetings["fomc_20150128"]
    assert "press_conference_time_utc" not in january
    end = pd.Timestamp(january["request_end_utc"]) - pd.Timestamp(january["statement_time_utc"])
    assert end == pd.Timedelta(minutes=15)
    assert "press_conference_time_utc" in meetings["fomc_20150318"]
    assert all(m["label"] != "fomc_20200315" for m in meetings.values())  # unscheduled


def test_conditions_mark_degraded_dates() -> None:
    meetings = build_meetings("2024-09-01", "2024-09-30", {"2024-09-18": "degraded"})
    assert meetings[0]["dataset_condition"] == "degraded"
