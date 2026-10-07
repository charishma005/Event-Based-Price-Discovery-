"""Meeting groupings shared by FOMC plots: rate action and surprise-size terciles.

Surprise terciles use the same rule as ``surprise_terciles`` in
``scripts/analyze_fomc_h5_horizons.py``: |USMPD statement surprise| ranked over
every available meeting in the config, then cut into equal-count thirds. Cutting
on the full sample keeps the groups identical across figures and subsamples.
"""

from __future__ import annotations

import pandas as pd

from src.events.surprises import build_surprise_panel
from src.utils.config import PROJECT_ROOT, load_yaml

ACTIONS = ("hike", "hold", "cut")
SURPRISES = ("small", "medium", "large")


def rate_action(policy_change_bps: float) -> str:
    if policy_change_bps > 0:
        return "hike"
    if policy_change_bps < 0:
        return "cut"
    return "hold"


def meeting_groups(config_name: str = "fomc_sample_2015_2026.yaml", measure: str = "STMT") -> pd.DataFrame:
    """One row per meeting: action, surprise value and small/medium/large bucket."""
    meetings = pd.DataFrame(
        [
            {
                "meeting": m["label"],
                "meeting_date": m["meeting_date"],
                "dataset_condition": m.get("dataset_condition", "available"),
                "policy_change_bps": m.get("policy_change_bps", 0),
            }
            for m in load_yaml(PROJECT_ROOT / "config" / config_name)["meetings"]
        ]
    )
    panel = build_surprise_panel(meetings)
    panel["action"] = panel["policy_change_bps"].map(rate_action)
    available = panel.loc[panel["dataset_condition"].eq("available")]
    magnitude = available.set_index("meeting")[measure].abs().dropna()
    buckets = pd.qcut(magnitude.rank(method="first"), 3, labels=list(SURPRISES)).astype(str)
    panel["surprise"] = panel["meeting"].map(buckets)
    return panel[["meeting", "meeting_date", "dataset_condition", "action", measure, "surprise"]].rename(
        columns={measure: "surprise_value"}
    )
