"""H4 slide with matched control days: FOMC statement depth withdrawal, 2015-2023.

Updates slide 15 (make_slide_figures.slide_15_depth), whose right panel had no
controls. Left: mean depth ratio on FOMC days against the mean of each meeting's
matched 2:00 p.m. control days, with one-sided sign-test p-values. Right: every
meeting and every control day, so the overlap (or its absence) is visible.

Depth ratio = touch depth in the final minute before 2:00 p.m. / the prior four
minutes (pre60_to_baseline_depth_ratio), statements only.

Inputs:
- data/processed/fomc_sample_2015_2026/timing_liquidity.csv (committed)
- data/processed/fomc_placebos_2015_2023/{timing_liquidity,depth_inference}.parquet
  (from process_fomc_placebos.py; not committed)

Run: python -m scripts.plot_h4_depth_controls
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from scripts.make_slide_figures import (
    BLUE, GRID, HALO, INK, INK_2, INSTRUMENT_COLOR, INSTRUMENT_NAME, MUTED, ROOT, SURFACE,
    _figure, _grid, _save,
)
from src.utils.config import PROJECT_ROOT

RATIO = "pre60_to_baseline_depth_ratio"
ORDER = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _p_label(p: float) -> str:
    if p < 1e-4:
        exponent = int(np.floor(np.log10(p)))
        return f"p = {p / 10 ** exponent:.0f}e{exponent}"
    return f"p = {p:.3f}" if p >= 0.001 else f"p = {p:.4f}"


def load(placebo_root) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fomc = pd.read_csv(ROOT / "timing_liquidity.csv")
    controls = pd.read_parquet(placebo_root / "timing_liquidity.parquet")
    inference = pd.read_parquet(placebo_root / "depth_inference.parquet")
    matched = set(controls["matched_meeting"])
    fomc = fomc.loc[
        fomc["subevent"].eq("statement") & fomc["dataset_condition"].eq("available") & fomc["meeting"].isin(matched)
    ]
    controls = controls.loc[~controls["placebo_quality_flag"].str.contains("secondary_control", na=False)]
    return fomc, controls, inference


def plot(fomc: pd.DataFrame, controls: pd.DataFrame, inference: pd.DataFrame) -> None:
    meetings = inference["meeting_pairs"].max()
    fig, (left, right) = _figure(
        "Depth is pulled before FOMC statements, not on normal days",
        "Depth ratio = touch depth in the final minute / the prior four minutes. Below 1 = depth withdrawn.",
        ncols=2,
        widths=[1, 1.35],
        left=0.10,
    )
    fig.subplots_adjust(bottom=0.18)  # room for the two-line source note

    # Left: means, FOMC day against matched control days, with sign tests.
    rows = [("All three", "meeting_cluster_average")] + [(INSTRUMENT_NAME[i], i) for i in ORDER]
    stats = inference.set_index("instrument")
    for y, (label, key) in enumerate(reversed(rows)):
        row = stats.loc[key]
        event, control = row["mean_event_depth_ratio"], row["mean_placebo_depth_ratio"]
        left.plot([event, control], [y, y], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
        left.scatter(control, y, s=110, color=MUTED, edgecolor=SURFACE, linewidth=2, zorder=3)
        left.scatter(event, y, s=110, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        close = abs(control - event) < 0.12  # side-by-side labels would overlap
        left.text(event - (0.02 if close else 0), y + 0.2, f"{event:.2f}", ha="right" if close else "center",
                  color=INK, fontsize=12)
        left.text(control + (0.02 if close else 0), y + 0.2, f"{control:.2f}", ha="left" if close else "center",
                  color=INK_2, fontsize=12)
        lower, pairs = int(row["event_lower_pair_count"]), int(row["meeting_pairs"])
        verdict = _p_label(row["one_sided_sign_test_p"]) if row["one_sided_sign_test_p"] < 0.05 else "not significant"
        left.text(0.02, y - 0.3, f"lower in {lower} of {pairs}; {verdict}", color=INK_2, fontsize=10.5)
    left.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
    left.set_ylim(-0.7, len(rows) - 0.3)
    left.set_xlim(0, 1.25)
    left.axvline(1, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    left.set_xlabel("Mean depth ratio")
    left.set_title(f"{meetings} meetings vs matched control days, 2015-2023", loc="left", fontsize=15, pad=14)
    left.text(0.17, len(rows) - 0.55, "FOMC day", color=BLUE, fontsize=12, fontweight="bold")
    left.text(1.05, len(rows) - 0.55, "Control day", color=INK_2, fontsize=12, fontweight="bold", ha="center")
    _grid(left, "x")

    # Right: every FOMC statement and every control day, per instrument.
    rng = np.random.default_rng(7)
    for i, instrument in enumerate(ORDER):
        for offset, frame, color, alpha in ((-0.22, fomc, INSTRUMENT_COLOR[instrument], 0.6), (0.22, controls, MUTED, 0.45)):
            values = frame.loc[frame["instrument"].eq(instrument), RATIO].dropna()
            values = values.loc[values > 0]
            x = 1.4 * i + offset
            right.scatter(x + rng.uniform(-0.16, 0.16, len(values)), values, s=14, color=color, alpha=alpha, linewidth=0)
            median = values.median()
            right.plot([x - 0.2, x + 0.2], [median, median], color=INK, linewidth=2.5, solid_capstyle="round")
            above = median < 0.6
            right.text(x, median * (1.13 if above else 0.82), f"{median:.2f}", ha="center", fontsize=11.5,
                       color=INK, fontweight="bold", path_effects=HALO)
    right.set_yscale("log")
    right.set_yticks([0.05, 0.1, 0.25, 0.5, 1, 2], ["0.05", "0.1", "0.25", "0.5", "1", "2"])
    right.set_ylim(0.03, 3)
    right.axhline(1, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    positions = [1.4 * i + d for i in range(len(ORDER)) for d in (-0.22, 0.22)]
    right.set_xticks(positions, ["FOMC", "Control"] * len(ORDER), fontsize=11)
    for i, instrument in enumerate(ORDER):
        right.text(1.4 * i, 2.35, INSTRUMENT_NAME[instrument], ha="center", fontsize=14, fontweight="bold",
                   color=INSTRUMENT_COLOR[instrument] if instrument != "ZN.v.0" else "#128a5f")
    right.set_ylabel("Depth ratio (log scale); bar = median")
    right.set_title(
        f"Each statement ({len(fomc['meeting'].unique())}) and control day ({controls['placebo_id'].nunique()})",
        loc="left", fontsize=15, pad=14,
    )
    _grid(right)
    _save(
        fig,
        "slide_15b_h4_depth_vs_controls.png",
        "Controls: same weekday and clock 1-2 weeks before each meeting; other 2 p.m. releases not screened. One-sided sign tests.\n"
        "Same result in 2024-2025 (paper 4.6): 0.56 vs 1.03, lower in 12 of 12. Source: fomc_placebos_2015_2023, timing_liquidity.csv.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--placebo-root", default=str(PROJECT_ROOT / "data" / "processed" / "fomc_placebos_2015_2023"))
    args = parser.parse_args()
    from pathlib import Path

    plot(*load(Path(args.placebo_root)))


if __name__ == "__main__":
    main()
