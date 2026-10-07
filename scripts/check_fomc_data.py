"""Report which FOMC raw windows and processed outputs exist versus what the configs expect.

Run: python -m scripts.check_fomc_data
Raw files are matched to windows by schema, start, end and symbols in each
*.metadata.json, the same rule the processing scripts use.
"""

from __future__ import annotations

import pandas as pd

from scripts.download_fomc_extensions import extension_windows
from src.data.raw_index import build_raw_index
from src.utils.config import PROJECT_ROOT, load_yaml

PROCESSED = PROJECT_ROOT / "data" / "processed"
SYMBOLS = "ES.v.0|NQ.v.0|ZN.v.0"


def _lookup(index: pd.DataFrame, schema: str) -> dict[tuple[pd.Timestamp, pd.Timestamp], int]:
    rows = index.loc[index["schema"].eq(schema) & index["symbols"].eq(SYMBOLS)]
    return {
        (pd.Timestamp(r.start), pd.Timestamp(r.end)): (r.record_count if pd.notna(r.record_count) else 1)
        for r in rows.itertuples()
    }


def report(name: str, items: list[tuple[str, str, str]], cache: dict) -> set[str]:
    """Print coverage for (label, start, end) windows; return the labels that are cached."""
    have, missing, empty = set(), [], []
    for label, start, end in items:
        records = cache.get((pd.Timestamp(start), pd.Timestamp(end)))
        if records is None:
            missing.append(label)
            continue
        have.add(label)
        if records == 0:
            empty.append(label)
    print(f"\n{name}: {len(have)}/{len(items)} windows cached")
    if empty:
        print(f"  empty (no records; likely closed market): {', '.join(empty)}")
    if missing:
        print(f"  MISSING ({len(missing)}): {', '.join(missing[:15])}{' ...' if len(missing) > 15 else ''}")
    return have


def main() -> None:
    index = build_raw_index()
    mbp1, bbo = _lookup(index, "mbp-1"), _lookup(index, "bbo-1s")
    print(f"Raw cache: {len(mbp1)} ES/NQ/ZN mbp-1 windows and {len(bbo)} bbo-1s windows")

    meetings = load_yaml(PROJECT_ROOT / "config" / "fomc_sample_2015_2026.yaml")["meetings"]
    base = report(
        "[tick] FOMC meetings 2015-2026, original windows (expected 93)",
        [(m["label"], m["request_start_utc"], m["request_end_utc"]) for m in meetings],
        mbp1,
    )
    extensions = extension_windows()
    extended = report(
        f"[tick] Statement-only meetings extended to +40 min (expected {len(extensions)})",
        [(w["label"], w["request_start_utc"], w["request_end_utc"]) for w in extensions],
        mbp1,
    )
    with_press = {m["label"] for m in meetings if "press_conference_time_utc" in m}
    to_40 = (with_press & base) | extended
    usable = {m["label"] for m in meetings if m.get("dataset_condition", "available") == "available"}
    print(f"  => meetings covering -5 to +40 min: {len(to_40)}/93 "
          f"({len(to_40 & usable)} usable; {len(meetings) - len(usable)} flagged degraded)")

    placebo_path = PROJECT_ROOT / "config" / "fomc_placebos_2015_2023.yaml"
    if placebo_path.exists():
        placebos = load_yaml(placebo_path)["placebos"]
        report(
            "[tick] Controls 2015-2023 (expected 142)",
            [(p["placebo_id"], p["request_start_utc"], p["request_end_utc"]) for p in placebos],
            mbp1,
        )

    registry_path = PROJECT_ROOT / "data" / "events" / "fomc_session_windows.csv"
    if registry_path.exists():
        registry = pd.read_csv(registry_path)
        for family, label in (("fomc", "FOMC afternoons"), ("fomc_control", "control afternoons")):
            rows = registry.loc[registry["family"].eq(family)]
            report(
                f"[bbo-1s] {label}, 1:30-4:00 p.m. (expected {len(rows)})",
                list(zip(rows["event_id"], rows["request_start_utc"], rows["request_end_utc"])),
                bbo,
            )

    print("\nProcessed outputs:")
    for folder, files in {
        "fomc_sample_2015_2026": ["timing_liquidity", "response_horizons"],
        "fomc_placebos_2015_2023": ["timing_liquidity", "matched_depth_comparison", "depth_inference"],
        "fomc_sessions": ["panel"],
    }.items():
        for stem in files:
            path = PROCESSED / folder / f"{stem}.parquet"
            print(f"  {'OK     ' if path.exists() else 'MISSING'} data/processed/{folder}/{stem}.parquet")
    for folder in ("fomc_depth_profile", "fomc_depth_sides"):
        for kind in ("fomc", "control"):
            cache = PROCESSED / folder / "cache" / kind
            files = sorted(cache.glob("*.parquet")) if cache.exists() else []
            note = ""
            if folder == "fomc_depth_sides" and kind == "fomc":
                full = sum(f.stem.endswith("_to39") for f in files)
                note = f" ({full} cover to +40 min)"
            print(f"  {len(files):>4} per-event results in data/processed/{folder}/cache/{kind}{note}")


if __name__ == "__main__":
    main()
