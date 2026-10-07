"""Q1 contrasts with the vendor's day flags applied to every sample (a check added after the freeze).

The development windows (2024-01 to 2025-09) were replayed before the vendor's
per-day conditions were merged into the event registry. Their rows in
``events.parquet`` therefore carry no condition, and the frozen analysis reads
a missing condition as available. Two development clocks that the registry now
marks as degraded are in the development tables for that reason: the FOMC
meeting of 17 September 2025 and the control afternoon of 24 September 2025.
Out-of-sample windows were replayed with the flags in place.

This script leaves the frozen analysis untouched. It repeats the pre-declared
contrasts and the trend twice, as pre-declared and with every clock the
registry does not mark as available left out, and writes the two side by side.

Output: ``tables/q1_vendor_flag_check.csv`` (and ``.tex``).
"""
from __future__ import annotations

import argparse

import pandas as pd

from scripts.analyze_q1_short_horizon import PRIMARY, contrasts, in_sample, load_events, trend
from src.utils.config import PROJECT_ROOT

TABLES = PROJECT_ROOT / "tables"
SAMPLES = ("development", "oos_backward", "oos_forward")
KEEP = ["contrast", "n_left", "n_right", "estimate", "p_two_sided", "holm_p"]


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    events = load_events()
    registry = pd.read_csv(PROJECT_ROOT / "data" / "events" / "event_registry.csv", keep_default_na=False)
    flagged = set(registry.loc[registry["dataset_condition"].ne("available"), "event_id"])
    strict = events.copy()
    strict["eligible"] = strict["eligible"] & ~strict["event_id"].isin(flagged)
    newly_left_out = events.loc[events["eligible"] & events["event_id"].isin(flagged)]
    rows = []
    for sample in SAMPLES:
        declared = contrasts(in_sample(events, sample), PRIMARY)[KEEP]
        flags = contrasts(in_sample(strict, sample), PRIMARY)[KEEP]
        both = declared.merge(flags, on="contrast", suffixes=("", "_flags_applied"))
        both.loc[len(both)] = {"contrast": "trend across classes (Spearman rho)",
                               **{f"{name}{suffix}": value for suffix, frame in (("", events), ("_flags_applied", strict))
                                  for name, value in (("n_left", trend(in_sample(frame, sample), PRIMARY)["events"]),
                                                      ("estimate", trend(in_sample(frame, sample), PRIMARY)["spearman_rho"]),
                                                      ("p_two_sided", trend(in_sample(frame, sample), PRIMARY)["p_two_sided"]))}}
        both.insert(0, "clocks_left_out_by_the_flags", in_sample(newly_left_out, sample)["event_id"].nunique())
        both.insert(0, "sample", sample)
        rows.append(both)
    table = pd.concat(rows, ignore_index=True)
    table.to_csv(TABLES / "q1_vendor_flag_check.csv", index=False)
    table.to_latex(TABLES / "q1_vendor_flag_check.tex", index=False, float_format="%.4f")
    print("Clocks treated as available that the registry marks otherwise:",
          ", ".join(sorted(newly_left_out["event_id"].unique())) or "none")
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", lambda v: f"{v:.4f}"):
        changed = table.loc[table["clocks_left_out_by_the_flags"] > 0]
        print(changed.drop(columns=["clocks_left_out_by_the_flags"]).to_string(index=False))
        same = table.loc[table["clocks_left_out_by_the_flags"].eq(0)]
        identical = same[["estimate", "p_two_sided"]].round(12).equals(
            same[["estimate_flags_applied", "p_two_sided_flags_applied"]].round(12).rename(columns=lambda c: c.replace("_flags_applied", "")))
        print(f"\nSamples without such clocks ({', '.join(same['sample'].unique())}): identical in both versions: {identical}")


if __name__ == "__main__":
    main()
