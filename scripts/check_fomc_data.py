"""Report which FOMC raw windows and processed outputs exist versus what the configs expect.

Run: python -m scripts.check_fomc_data
Raw files are matched to windows by the start/end/symbols in each *.metadata.json,
the same rule the processing scripts use.
"""

from __future__ import annotations

import json

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml

RAW = PROJECT_ROOT / "data" / "raw" / "databento"
PROCESSED = PROJECT_ROOT / "data" / "processed"
SYMBOLS = {"ES.v.0", "NQ.v.0", "ZN.v.0"}


def cached_windows() -> dict[tuple[pd.Timestamp, pd.Timestamp], dict]:
    found = {}
    for path in RAW.glob("GLBX.MDP3-mbp-1-*.metadata.json"):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if set(meta["symbols"]) != SYMBOLS:
            continue
        found[(pd.Timestamp(meta["start"]), pd.Timestamp(meta["end"]))] = meta
    return found


def report(name: str, items: list[tuple[str, str, str]], cache: dict) -> None:
    missing, empty = [], []
    for label, start, end in items:
        meta = cache.get((pd.Timestamp(start), pd.Timestamp(end)))
        if meta is None:
            missing.append(label)
        elif meta.get("record_count", 1) == 0:
            empty.append(label)
    have = len(items) - len(missing)
    print(f"\n{name}: {have}/{len(items)} windows cached")
    if empty:
        print(f"  empty (no records; likely closed market): {', '.join(empty)}")
    if missing:
        print(f"  MISSING ({len(missing)}): {', '.join(missing[:15])}{' ...' if len(missing) > 15 else ''}")


def main() -> None:
    cache = cached_windows()
    print(f"Raw cache: {len(cache)} ES/NQ/ZN mbp-1 windows in {RAW}")
    meetings = load_yaml(PROJECT_ROOT / "config" / "fomc_sample_2015_2026.yaml")["meetings"]
    report(
        "FOMC meetings 2015-2026 (expected 93)",
        [(m["label"], m["request_start_utc"], m["request_end_utc"]) for m in meetings],
        cache,
    )
    placebo_path = PROJECT_ROOT / "config" / "fomc_placebos_2015_2023.yaml"
    if placebo_path.exists():
        placebos = load_yaml(placebo_path)["placebos"]
        report(
            "Controls 2015-2023 (expected 142)",
            [(p["placebo_id"], p["request_start_utc"], p["request_end_utc"]) for p in placebos],
            cache,
        )
    else:
        print("\nControls: config/fomc_placebos_2015_2023.yaml missing; run build_fomc_placebo_config")

    print("\nProcessed outputs:")
    for folder, files in {
        "fomc_sample_2015_2026": ["timing_liquidity", "response_horizons"],
        "fomc_placebos_2015_2023": ["timing_liquidity", "matched_depth_comparison", "depth_inference"],
    }.items():
        for stem in files:
            path = PROCESSED / folder / f"{stem}.parquet"
            print(f"  {'OK     ' if path.exists() else 'MISSING'} data/processed/{folder}/{stem}.parquet")


if __name__ == "__main__":
    main()
