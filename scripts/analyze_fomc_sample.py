from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.microstructure.mechanism import fit_order_flow_impact, mechanism_components
from src.utils.config import PROJECT_ROOT


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
HORIZONS = (5.0, 30.0, 60.0, 300.0)


def _leave_one_meeting_out_impact(
    intervals: pd.DataFrame, focal_meeting: str, instrument: str
) -> tuple[dict[str, float | int], list[str]]:
    sample = intervals.loc[
        intervals["instrument"].eq(instrument)
        & intervals["dataset_condition"].eq("available")
        & intervals["meeting"].ne(focal_meeting)
        & intervals["statement_event_seconds"].ge(-240)
        & intervals["statement_event_seconds"].lt(-60)
    ].copy()
    meetings = sorted(sample["meeting"].unique())
    diagnostics, _ = fit_order_flow_impact(sample)
    return diagnostics, meetings


def _mechanism_rows(
    timing: pd.DataFrame, horizons: pd.DataFrame, intervals: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    impact_rows: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for meeting in sorted(timing.loc[timing["dataset_condition"].eq("available"), "meeting"].unique()):
        for instrument in INSTRUMENTS:
            impact, training_meetings = _leave_one_meeting_out_impact(
                intervals, meeting, instrument
            )
            impact_rows.append(
                {
                    "focal_meeting": meeting,
                    "instrument": instrument,
                    **impact,
                    "training_meeting_count": len(training_meetings),
                    "training_meetings": "|".join(training_meetings),
                }
            )
            for subevent in ("statement", "press_conference"):
                timing_rows = timing.loc[
                    timing["meeting"].eq(meeting)
                    & timing["instrument"].eq(instrument)
                    & timing["subevent"].eq(subevent)
                ]
                if timing_rows.empty:  # e.g. no press conference before 2019
                    continue
                timing_row = timing_rows.iloc[0]
                event_horizons = horizons.loc[
                    horizons["meeting"].eq(meeting)
                    & horizons["instrument"].eq(instrument)
                    & horizons["subevent"].eq(subevent)
                    & horizons["horizon_seconds"].isin(HORIZONS)
                ]
                for horizon in event_horizons.itertuples(index=False):
                    total = float(horizon.log_return_bp) / 10_000
                    signed_volume = float(horizon.signed_volume)
                    for definition, quote_bp in (
                        ("first_valid_quote", timing_row.first_quote_revision_bp),
                        ("last_pretrade_quote", timing_row.last_pretrade_quote_revision_bp),
                    ):
                        quote = np.nan if pd.isna(quote_bp) else float(quote_bp) / 10_000
                        if not np.isfinite(quote):
                            continue
                        components = mechanism_components(
                            quote_revision=quote,
                            cumulative_signed_flow=signed_volume,
                            impact_coefficient=float(impact["impact_coefficient"]),
                            total_adjustment=total,
                        )
                        denominator = float(components["component_denominator"])
                        coverage = np.nan if abs(total) <= 1e-12 else denominator / total
                        flags = list(components["quality_flags"])
                        if abs(total * 10_000) < 0.10:
                            flags.append("near_zero_total_adjustment")
                        if np.isfinite(coverage) and abs(coverage) < 0.25:
                            flags.append("low_component_coverage")
                        rows.append(
                            {
                                "meeting": meeting,
                                "subevent": subevent,
                                "instrument": instrument,
                                "representation_class": timing_row.representation_class,
                                "sep_release": bool(timing_row.sep_release),
                                "policy_change_bps": int(timing_row.policy_change_bps),
                                "horizon_seconds": float(horizon.horizon_seconds),
                                "quote_definition": definition,
                                "eligible_primary_q1": bool(timing_row.eligible_primary_q1),
                                "impact_training_nobs": int(impact["nobs"]),
                                "impact_training_r_squared": float(impact["r_squared"]),
                                "impact_coefficient": float(impact["impact_coefficient"]),
                                "signed_volume": signed_volume,
                                "known_side_fraction": horizon.known_side_fraction,
                                "total_adjustment_bp": total * 10_000,
                                "quote_revision_bp": quote * 10_000,
                                "order_flow_component_bp": float(components["order_flow_component"]) * 10_000,
                                "residual_component_bp": float(components["residual_component"]) * 10_000,
                                "mechanism_share": components["mechanism_share"],
                                "component_coverage_ratio": coverage,
                                "quality_flags": "|".join(dict.fromkeys(flags)),
                            }
                        )
    return pd.DataFrame(impact_rows), pd.DataFrame(rows)


def _summary_table(mechanisms: pd.DataFrame) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["horizon_seconds"].eq(60)
    ].copy()
    return (
        sample.groupby(["subevent", "instrument"], as_index=False)
        .agg(
            observations=("meeting", "size"),
            median_abs_total_move_bp=("total_adjustment_bp", lambda x: x.abs().median()),
            mean_quote_revision_bp=("quote_revision_bp", "mean"),
            median_mechanism_share=("mechanism_share", "median"),
            median_component_coverage=("component_coverage_ratio", "median"),
            median_abs_residual_bp=("residual_component_bp", lambda x: x.abs().median()),
        )
    )


def _speed_metrics(intervals: pd.DataFrame, horizons: pd.DataFrame) -> pd.DataFrame:
    """Describe first crossing and sustained convergence to the five-minute move."""
    rows: list[dict[str, object]] = []
    terminal = horizons.loc[
        horizons["horizon_seconds"].eq(300)
        & horizons["dataset_condition"].eq("available")
    ]
    for target in terminal.itertuples(index=False):
        event_zero = 0.0 if target.subevent == "statement" else 1800.0
        sample = intervals.loc[
            intervals["meeting"].eq(target.meeting)
            & intervals["instrument"].eq(target.instrument)
            & intervals["statement_event_seconds"].ge(event_zero)
            & intervals["statement_event_seconds"].le(event_zero + 300)
        ].sort_values("statement_event_seconds")
        if sample.empty:
            continue
        path = sample["return"].fillna(0.0).cumsum() * 10_000
        event_seconds = sample["statement_event_seconds"].to_numpy(float) - event_zero
        terminal_bp = float(target.log_return_bp)
        near_zero = abs(terminal_bp) < 1.0

        def first_crossing(fraction: float) -> float | None:
            if near_zero:
                return None
            threshold = fraction * terminal_bp
            reached = path.ge(threshold) if terminal_bp > 0 else path.le(threshold)
            return None if not reached.any() else float(event_seconds[np.flatnonzero(reached)[0]])

        if near_zero:
            stable = None
        else:
            tolerance = max(0.1 * abs(terminal_bp), 0.5)
            within = np.abs(path.to_numpy(float) - terminal_bp) <= tolerance
            suffix_all = np.logical_and.accumulate(within[::-1])[::-1]
            stable = (
                None
                if not suffix_all.any()
                else float(event_seconds[np.flatnonzero(suffix_all)[0]])
            )
        peak_position = int(np.nanargmax(np.abs(path.to_numpy(float))))
        peak_bp = float(path.iloc[peak_position])
        rows.append(
            {
                "meeting": target.meeting,
                "subevent": target.subevent,
                "instrument": target.instrument,
                "representation_class": target.representation_class,
                "sep_release": bool(target.sep_release),
                "policy_change_bps": int(target.policy_change_bps),
                "terminal_300s_bp": terminal_bp,
                "near_zero_terminal": near_zero,
                "first_crossing_50_seconds": first_crossing(0.5),
                "first_crossing_90_seconds": first_crossing(0.9),
                "stable_within_10pct_seconds": stable,
                "peak_absolute_return_bp": peak_bp,
                "peak_absolute_return_seconds": float(event_seconds[peak_position]),
                "overshoot_ratio": np.nan
                if near_zero
                else float(abs(peak_bp) / abs(terminal_bp)),
            }
        )
    return pd.DataFrame(rows)


def _response_figure(horizons: pd.DataFrame, output) -> None:
    sample = horizons.loc[
        horizons["dataset_condition"].eq("available")
        & horizons["horizon_seconds"].eq(60)
    ].copy()
    table = sample.pivot_table(
        index="meeting", columns=["subevent", "instrument"], values="log_return_bp"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharey=True)
    for ax, subevent in zip(axes, ("statement", "press_conference")):
        subset = table[subevent].reindex(columns=INSTRUMENTS)
        values = subset.to_numpy(float)
        limit = max(5.0, float(np.nanmax(np.abs(values))))
        image = ax.imshow(values, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
        ax.set_xticks(range(len(subset.columns)), subset.columns)
        ax.set_yticks(range(len(subset.index)), subset.index)
        ax.set_title(subevent.replace("_", " "))
        for row in range(values.shape[0]):
            for col in range(values.shape[1]):
                ax.text(col, row, f"{values[row, col]:.1f}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=ax, shrink=0.75, label="60-second midpoint return (bp)")
    fig.suptitle("FOMC response across available-quality meetings")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze processed FOMC tick summaries")
    parser.add_argument("--config", default="fomc_sample.yaml", help="Config whose output to analyze")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    args = parser.parse_args()
    name = args.root or args.config.removesuffix(".yaml")
    root = PROJECT_ROOT / "data" / "processed" / name
    timing = pd.read_parquet(root / "timing_liquidity.parquet")
    horizons = pd.read_parquet(root / "response_horizons.parquet")
    intervals = pd.read_parquet(root / "one_second_intervals.parquet")
    impacts, mechanisms = _mechanism_rows(timing, horizons, intervals)
    summary = _summary_table(mechanisms)
    speed = _speed_metrics(intervals, horizons)
    for table, frame in (
        ("impact_coefficients_loo", impacts),
        ("mechanism_estimates_loo", mechanisms),
        ("mechanism_summary_60s", summary),
        ("speed_metrics", speed),
    ):
        frame.to_parquet(root / f"{table}.parquet", index=False)
        frame.to_csv(root / f"{table}.csv", index=False)
    figure_dir = PROJECT_ROOT / "figures" / name
    figure_dir.mkdir(parents=True, exist_ok=True)
    _response_figure(horizons, figure_dir / "fomc_response_60s_heatmap.png")
    print(
        f"Wrote {len(impacts)} leave-one-meeting-out impact fits and "
        f"{len(mechanisms)} mechanism estimates."
    )


if __name__ == "__main__":
    main()
