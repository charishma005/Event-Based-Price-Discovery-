"""Step 4: build the canonical ES/NQ/ZN FOMC strategy dataset from the one-second book.

Reads data/processed/fomc_book_seconds/fomc (from scripts.extract_fomc_book_seconds) and writes
data/processed/fomc_strategy/:
  features.parquet      one row per FOMC event x instrument: identifiers, decision features
                        (<= +5:00; ZN extras <= +10:00), targets and executable quotes
  minute_paths.parquet  per-minute depth and spread ratios (figures only)
  seconds.parquet       second-level microstructure panel (strategy 10)

No USMPD surprise or rate action is read here.

Run: python -m scripts.build_fomc_strategy_features
"""

from __future__ import annotations

import pandas as pd

from scripts.extract_fomc_book_seconds import load
from src.strategies.fomc_features import (
    FEATURE_COLUMNS, TARGET_COLUMNS, build_event_features, minute_paths, second_level_panel,
)
from src.utils.config import PROJECT_ROOT, load_yaml

OUT = PROJECT_ROOT / "data" / "processed" / "fomc_strategy"


def meetings(config: str = "fomc_sample_2015_2026.yaml") -> pd.DataFrame:
    rows = [m for m in load_yaml(PROJECT_ROOT / "config" / config)["meetings"]
            if m.get("dataset_condition", "available") == "available"]
    return pd.DataFrame({"meeting": [m["label"] for m in rows], "meeting_date": [m["meeting_date"] for m in rows],
                         "statement_time_utc": [m["statement_time_utc"] for m in rows]})


def main() -> None:
    book = load("fomc")
    OUT.mkdir(parents=True, exist_ok=True)
    features = build_event_features(book, meetings())
    leaked = set(FEATURE_COLUMNS) & set(TARGET_COLUMNS)
    assert not leaked, f"target columns listed as features: {leaked}"
    features.to_parquet(OUT / "features.parquet", index=False)
    minute_paths(book).to_parquet(OUT / "minute_paths.parquet", index=False)
    second_level_panel(book).to_parquet(OUT / "seconds.parquet", index=False)
    counts = features.groupby(["sample", "instrument"])["event_id"].nunique().unstack()
    print(f"Wrote {len(features)} event x instrument rows to {OUT}")
    print(counts.to_string())
    missing = features[["ret_0_5m", "depth_ratio_5m", "spread_ratio_5m", "ret_5_20m"]].isna().sum()
    print("Missing values in key columns:\n" + missing.to_string())


if __name__ == "__main__":
    main()
