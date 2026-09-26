from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT


PAIRINGS = {
    "ppi_20250910": ("placebo_20250909_0830", False),
    "cpi_20250911": ("placebo_20250909_0830", False),
    "retail_sales_20250916": ("placebo_20250909_0830", True),
    "industrial_production_20250916": ("placebo_20250909_0915", True),
    "housing_20250917": ("placebo_20250909_0830", False),
    "statement": ("placebo_20250910_1400", True),
}
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _heatmap(frame: pd.DataFrame, value: str, title: str, label: str, output: str) -> None:
    table = frame.pivot(index="event", columns="instrument", values=value).reindex(columns=INSTRUMENTS)
    values = table.to_numpy(float)
    finite = np.abs(values[np.isfinite(values)])
    limit = float(finite.max()) if finite.size else 1.0
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    image = ax.imshow(values, aspect="auto", cmap="RdBu_r", vmin=-limit, vmax=limit)
    ax.set_xticks(range(len(table.columns)), table.columns)
    ax.set_yticks(range(len(table.index)), [name.replace("_", " ") for name in table.index])
    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            if np.isfinite(values[row, col]):
                ax.text(col, row, f"{values[row, col]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title(title)
    colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
    colorbar.set_label(label)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    root = PROJECT_ROOT / "data" / "processed" / "fomc_pilot"
    timing = pd.read_parquet(root / "timing_liquidity_summary.parquet")
    horizons = pd.read_parquet(root / "event_response_horizons.parquet")
    returns60 = horizons.loc[horizons["horizon_seconds"].eq(60)].copy()
    rows: list[dict[str, object]] = []
    for event, (placebo, same_weekday) in PAIRINGS.items():
        for instrument in INSTRUMENTS:
            actual_timing = timing.loc[
                timing["event"].eq(event) & timing["instrument"].eq(instrument)
            ].iloc[0]
            placebo_timing = timing.loc[
                timing["event"].eq(placebo) & timing["instrument"].eq(instrument)
            ].iloc[0]
            actual_return = returns60.loc[
                returns60["event"].eq(event) & returns60["instrument"].eq(instrument),
                "log_return_bp",
            ].iloc[0]
            placebo_return = returns60.loc[
                returns60["event"].eq(placebo) & returns60["instrument"].eq(instrument),
                "log_return_bp",
            ].iloc[0]
            rows.append(
                {
                    "event": event,
                    "instrument": instrument,
                    "placebo_event": placebo,
                    "same_weekday": same_weekday,
                    "event_dataset_condition": actual_timing["dataset_condition"],
                    "event_pre60_depth_ratio": actual_timing["pre60_to_baseline_depth_ratio"],
                    "placebo_pre60_depth_ratio": placebo_timing["pre60_to_baseline_depth_ratio"],
                    "depth_ratio_difference": actual_timing["pre60_to_baseline_depth_ratio"]
                    - placebo_timing["pre60_to_baseline_depth_ratio"],
                    "event_return_60s_bp": actual_return,
                    "placebo_return_60s_bp": placebo_return,
                    "absolute_return_difference_bp": abs(actual_return) - abs(placebo_return),
                }
            )
    comparison = pd.DataFrame(rows)
    output_dir = PROJECT_ROOT / "data" / "processed" / "macro_panel"
    figure_dir = PROJECT_ROOT / "figures" / "macro_panel"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_parquet(output_dir / "placebo_comparison.parquet", index=False)
    comparison.to_csv(output_dir / "placebo_comparison.csv", index=False)
    _heatmap(
        comparison,
        "depth_ratio_difference",
        "Pre-event depth relative to matched-clock placebos",
        "event minus placebo depth ratio",
        str(figure_dir / "placebo_depth_difference.png"),
    )
    _heatmap(
        comparison,
        "absolute_return_difference_bp",
        "Absolute 60-second response relative to placebos",
        "event minus placebo absolute return (bp)",
        str(figure_dir / "placebo_return_difference.png"),
    )
    print(f"Wrote {len(comparison)} event-instrument placebo comparisons.")


if __name__ == "__main__":
    main()
