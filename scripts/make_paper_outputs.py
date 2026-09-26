from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


COLORS = {"ES.v.0": "#1f77b4", "NQ.v.0": "#ff7f0e", "ZN.v.0": "#2ca02c"}


def _save_table(frame: pd.DataFrame, name: str, directory: Path) -> None:
    frame.to_csv(directory / f"{name}.csv", index=False)
    (directory / f"{name}.tex").write_text(
        frame.to_latex(index=False, float_format=lambda value: f"{value:.3f}"),
        encoding="utf-8",
    )


def _event_table(horizons: pd.DataFrame) -> pd.DataFrame:
    sample = horizons.loc[
        horizons["dataset_condition"].eq("available")
        & horizons["horizon_seconds"].eq(60)
    ]
    table = sample.pivot_table(
        index=["meeting", "subevent"],
        columns="instrument",
        values="log_return_bp",
    ).reset_index()
    return table.rename(
        columns={
            "ES.v.0": "ES return (bp)",
            "NQ.v.0": "NQ return (bp)",
            "ZN.v.0": "ZN return (bp)",
        }
    )


def _depth_figure(comparison: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    for ax, instrument in zip(axes, COLORS):
        sample = comparison.loc[comparison["instrument"].eq(instrument)].reset_index(drop=True)
        x = np.arange(len(sample))
        for position, row in sample.iterrows():
            ax.plot(
                [position, position],
                [row.placebo_pre60_depth_ratio, row.event_pre60_depth_ratio],
                color="#b5b5b5",
                linewidth=1.2,
                zorder=1,
            )
        ax.scatter(
            x,
            sample["placebo_pre60_depth_ratio"],
            marker="o",
            facecolors="white",
            edgecolors="#555555",
            label="matched controls",
            zorder=2,
        )
        ax.scatter(
            x,
            sample["event_pre60_depth_ratio"],
            marker="o",
            color=COLORS[instrument],
            label="FOMC",
            zorder=3,
        )
        ax.axhline(1.0, color="#777777", linestyle="--", linewidth=0.8)
        ax.set_title(instrument.replace(".v.0", ""))
        ax.set_xticks(
            x,
            [
                f"{value[5:9]}-{value[9:11]}"
                for value in sample["matched_meeting"]
            ],
            rotation=45,
        )
        ax.set_xlabel("meeting year-month")
    axes[0].set_ylabel("depth in final minute / prior four-minute mean")
    axes[-1].legend(frameon=False, loc="upper right")
    fig.suptitle("Displayed touch depth withdraws before scheduled FOMC statements")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _speed_figure(speed: pd.DataFrame, output: Path) -> None:
    sample = speed.loc[~speed["near_zero_terminal"]].copy()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, metric, title in zip(
        axes,
        ("first_crossing_50_seconds", "first_crossing_90_seconds"),
        ("First crossing of 50%", "First crossing of 90%"),
    ):
        positions = []
        values = []
        labels = []
        colors = []
        position = 1
        for subevent in ("statement", "press_conference"):
            for instrument in COLORS:
                group = sample.loc[
                    sample["subevent"].eq(subevent)
                    & sample["instrument"].eq(instrument),
                    metric,
                ].dropna()
                values.append(group.to_numpy(float))
                positions.append(position)
                labels.append(f"{subevent.replace('_conference', '')}\n{instrument[:2]}")
                colors.append(COLORS[instrument])
                position += 1
            position += 0.7
        boxes = ax.boxplot(values, positions=positions, widths=0.65, patch_artist=True)
        for patch, color in zip(boxes["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
        ax.set_xticks(positions, labels, fontsize=8)
        ax.set_title(title)
        ax.set_ylabel("seconds after sub-event")
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    fig.suptitle("Price discovery is slower at the press-conference opening")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _mechanism_figure(mechanisms: pd.DataFrame, output: Path) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["horizon_seconds"].eq(60)
    ].copy()
    summary = (
        sample.groupby(["subevent", "instrument"], as_index=False)
        .agg(
            observations=("meeting", "size"),
            median_abs_total_bp=("total_adjustment_bp", lambda x: x.abs().median()),
            median_abs_quote_bp=("quote_revision_bp", lambda x: x.abs().median()),
            median_abs_flow_bp=("order_flow_component_bp", lambda x: x.abs().median()),
            median_abs_residual_bp=("residual_component_bp", lambda x: x.abs().median()),
        )
    )
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True)
    components = (
        ("median_abs_quote_bp", "first quote", "#4c78a8"),
        ("median_abs_flow_bp", "fitted flow", "#f58518"),
        ("median_abs_residual_bp", "residual", "#a0a0a0"),
    )
    for ax, subevent in zip(axes, ("statement", "press_conference")):
        panel = summary.loc[summary["subevent"].eq(subevent)].set_index("instrument").reindex(COLORS)
        x = np.arange(len(panel))
        width = 0.23
        for offset, (column, label, color) in zip((-width, 0, width), components):
            ax.bar(x + offset, panel[column], width, label=label, color=color)
        ax.plot(x, panel["median_abs_total_bp"], "kD", label="observed total")
        ax.set_xticks(x, [value.replace(".v.0", "") for value in panel.index])
        ax.set_title(subevent.replace("_", " "))
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    axes[0].set_ylabel("median absolute 60-second component (bp)")
    axes[-1].legend(frameon=False, fontsize=8)
    fig.suptitle("The literal first quote contributes little; fitted flow does not exhaust the move")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return summary


def _macro_depth_figure(comparison: pd.DataFrame, output: Path) -> None:
    monthly = (
        comparison.groupby(["matched_month", "instrument"], as_index=False)
        .agg(
            event_pre60_depth_ratio=("event_pre60_depth_ratio", "mean"),
            control_pre60_depth_ratio=("control_pre60_depth_ratio", "first"),
        )
    )
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    for ax, instrument in zip(axes, COLORS):
        sample = monthly.loc[monthly["instrument"].eq(instrument)].reset_index(drop=True)
        x = np.arange(len(sample))
        for position, row in sample.iterrows():
            ax.plot(
                [position, position],
                [row.control_pre60_depth_ratio, row.event_pre60_depth_ratio],
                color="#b5b5b5",
                linewidth=1.2,
                zorder=1,
            )
        ax.scatter(x, sample["control_pre60_depth_ratio"], facecolors="white", edgecolors="#555555", label="quiet clock", zorder=2)
        ax.scatter(x, sample["event_pre60_depth_ratio"], color="#2f6b9a", label="macro releases", zorder=3)
        ax.axhline(1.0, color="#777777", linestyle="--", linewidth=0.8)
        labels = sample["matched_month"].str.replace("2024-", "'24-", regex=False).str.replace("2025-", "'25-", regex=False)
        ax.set_xticks(x, labels, fontsize=7, rotation=90)
        ax.set_xlabel("matched month")
        ax.set_title(instrument.replace(".v.0", ""))
    axes[0].set_ylabel("depth in final minute / prior four-minute mean")
    axes[-1].legend(frameon=False, loc="upper right", fontsize=8)
    fig.suptitle("Pre-release depth withdrawal is concentrated in ES and ZN")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _macro_response_table(horizons: pd.DataFrame) -> pd.DataFrame:
    sample = horizons.loc[horizons["horizon_seconds"].eq(60)].copy()
    sample["release"] = sample["event_types"].str.split("|").str[0]
    return (
        sample.groupby(["release", "instrument"], as_index=False)
        .agg(
            events=("bundle_id", "nunique"),
            median_abs_60s_bp=("log_return_bp", lambda value: value.abs().median()),
        )
    )


def _deeper_book_figure(summary: pd.DataFrame, output: Path) -> None:
    events = list(summary["event_id"].drop_duplicates())
    fig, axes = plt.subplots(1, len(events), figsize=(12, 4.2), sharey=True)
    axes = np.atleast_1d(axes)
    levels = (1, 5, 10)
    x = np.arange(len(levels))
    for ax, event_id in zip(axes, events):
        panel = summary.loc[summary["event_id"].eq(event_id)]
        for instrument, color in COLORS.items():
            row = panel.loc[panel["instrument"].eq(instrument)]
            if row.empty:
                continue
            values = [float(row.iloc[0][f"pre60_to_baseline_depth_l{level}_ratio"]) for level in levels]
            ax.plot(x, values, marker="o", color=color, label=instrument.replace(".v.0", ""))
        ax.axhline(1.0, color="#777777", linestyle="--", linewidth=0.8)
        ax.set_xticks(x, [f"L{level}" for level in levels])
        ax.set_title(event_id.replace("_", " "))
        ax.set_xlabel("cumulative book depth")
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    axes[0].set_ylabel("final-minute depth / prior four-minute mean")
    axes[-1].legend(frameon=False, fontsize=8)
    fig.suptitle("Depth withdrawal extends beyond the best quote in selected MBP-10 windows")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    data = PROJECT_ROOT / "data" / "processed" / "fomc_sample"
    placebo_data = PROJECT_ROOT / "data" / "processed" / "fomc_placebos"
    table_dir = PROJECT_ROOT / "tables"
    figure_dir = PROJECT_ROOT / "figures" / "paper"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    horizons = pd.read_parquet(data / "response_horizons.parquet")
    mechanisms = pd.read_parquet(data / "mechanism_estimates_loo.parquet")
    speed = pd.read_parquet(data / "speed_metrics.parquet")
    comparison = pd.read_parquet(placebo_data / "matched_depth_comparison.parquet")
    inference = pd.read_parquet(placebo_data / "depth_inference.parquet")
    macro_data = PROJECT_ROOT / "data" / "processed" / "macro_multiyear"
    macro_sample_roots = [
        PROJECT_ROOT / "data" / "processed" / "macro_sample",
        PROJECT_ROOT / "data" / "processed" / "macro_sample_2024",
    ]
    macro_placebos = PROJECT_ROOT / "data" / "processed" / "macro_placebos"
    macro_horizons = pd.concat(
        [pd.read_parquet(root / "response_horizons.parquet") for root in macro_sample_roots],
        ignore_index=True,
    )
    macro_h1 = pd.read_parquet(macro_data / "h1_summary_300s.parquet")
    macro_depth = pd.read_parquet(macro_placebos / "depth_inference.parquet")
    macro_comparison = pd.read_parquet(macro_placebos / "matched_depth_comparison.parquet")
    deeper_book = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "depth_sample" / "depth_summary.parquet"
    )

    _save_table(_event_table(horizons), "fomc_60s_returns", table_dir)
    _save_table(inference, "fomc_depth_inference", table_dir)
    mechanism_summary = _mechanism_figure(
        mechanisms, figure_dir / "fomc_mechanism_components.png"
    )
    _save_table(mechanism_summary, "fomc_mechanism_components", table_dir)
    _depth_figure(comparison, figure_dir / "fomc_depth_withdrawal.png")
    _speed_figure(speed, figure_dir / "fomc_price_discovery_speed.png")
    _macro_depth_figure(macro_comparison, figure_dir / "macro_depth_withdrawal.png")
    _save_table(_macro_response_table(macro_horizons), "macro_60s_response_summary", table_dir)
    _save_table(macro_h1, "macro_h1_quote_fraction", table_dir)
    _save_table(macro_depth, "macro_depth_inference", table_dir)
    _deeper_book_figure(deeper_book, figure_dir / "deeper_book_depth.png")
    _save_table(deeper_book, "deeper_book_depth", table_dir)
    print("Wrote five paper figures and seven CSV/LaTeX tables.")


if __name__ == "__main__":
    main()
