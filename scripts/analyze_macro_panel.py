from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.event_summary import mechanism_estimates, second_intervals
from src.events.registry import pilot_events
from src.microstructure.mechanism import fit_order_flow_impact
from src.utils.config import PROJECT_ROOT


EVENTS = pilot_events()
FUTURES = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _load_messages(event: str, instrument: str) -> pd.DataFrame | None:
    path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fomc_pilot"
        / event
        / f"{instrument}_messages.parquet"
    )
    return pd.read_parquet(path) if path.exists() else None


def _training_intervals(event: str, instrument: str) -> pd.DataFrame | None:
    """Return a clean pre-event interval sample for one available-quality event."""
    metadata = EVENTS[event]
    if metadata["dataset_condition"]["futures"] != "available":
        return None
    messages = _load_messages(event, instrument)
    if messages is None:
        return None
    event_time = metadata["time"]
    intervals = second_intervals(messages)
    sample = intervals.loc[
        (intervals.index >= event_time - pd.Timedelta(seconds=540))
        & (intervals.index < event_time - pd.Timedelta(seconds=60))
    ].copy()
    if sample.empty:
        return None
    sample["training_event"] = event
    return sample


def _fit_leave_one_event_out(
    focal_event: str, instrument: str
) -> tuple[dict[str, object], pd.DataFrame]:
    pieces: list[pd.DataFrame] = []
    labels: list[str] = []
    for candidate in EVENTS:
        if candidate == focal_event or candidate == "press_conference":
            continue
        sample = _training_intervals(candidate, instrument)
        if sample is not None:
            pieces.append(sample)
            labels.append(candidate)
    if not pieces:
        raise ValueError(f"no leave-one-event-out training data for {focal_event}/{instrument}")
    training = pd.concat(pieces, axis=0)
    diagnostics, fitted = fit_order_flow_impact(training)
    diagnostics.update(
        {
            "focal_event": focal_event,
            "instrument": instrument,
            "training_event_count": len(labels),
            "training_events": "|".join(labels),
        }
    )
    return diagnostics, fitted


def _heatmap(
    frame: pd.DataFrame,
    *,
    value: str,
    title: str,
    colorbar_label: str,
    output: Path,
    symmetric: bool = True,
) -> None:
    table = frame.pivot(index="event", columns="instrument", values=value)
    table = table.reindex(columns=list(FUTURES))
    values = table.to_numpy(float)
    finite = np.abs(values[np.isfinite(values)])
    limit = float(finite.max()) if finite.size else 1.0
    if symmetric:
        vmin, vmax, cmap = -limit, limit, "RdBu_r"
    else:
        vmin, vmax, cmap = 0, limit, "viridis"
    fig_height = max(4.5, 0.55 * len(table) + 1.8)
    fig, ax = plt.subplots(figsize=(7.5, fig_height))
    image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(table.columns)), table.columns)
    ax.set_yticks(range(len(table.index)), [x.replace("_", " ") for x in table.index])
    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            if np.isfinite(values[row, col]):
                ax.text(col, row, f"{values[row, col]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title(title)
    bar = fig.colorbar(image, ax=ax, shrink=0.8)
    bar.set_label(colorbar_label)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    output_dir = PROJECT_ROOT / "data" / "processed" / "macro_panel"
    figure_dir = PROJECT_ROOT / "figures" / "macro_panel"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    diagnostic_rows: list[dict[str, object]] = []
    mechanism_frames: list[pd.DataFrame] = []
    for event, metadata in EVENTS.items():
        if metadata["event_type"] == "matched_placebo":
            continue
        for instrument in FUTURES:
            messages = _load_messages(event, instrument)
            if messages is None:
                continue
            impact, _ = _fit_leave_one_event_out(event, instrument)
            diagnostic_rows.append(impact)
            estimates = mechanism_estimates(
                messages,
                metadata["time"],
                instrument,
                event,
                impact,
            )
            condition = metadata["dataset_condition"]["futures"]
            estimates["dataset_condition"] = condition
            estimates["eligible_primary_q1"] = (
                estimates["valid_mechanically"] & (condition == "available")
            )
            estimates["impact_training_method"] = "leave_one_event_out_pooled_pre_event_1s"
            estimates["impact_training_events"] = impact["training_events"]
            mechanism_frames.append(estimates)

    diagnostics = pd.DataFrame(diagnostic_rows)
    mechanisms = pd.concat(mechanism_frames, ignore_index=True)
    diagnostics.to_parquet(output_dir / "impact_coefficients_loo.parquet", index=False)
    diagnostics.to_csv(output_dir / "impact_coefficients_loo.csv", index=False)
    mechanisms.to_parquet(output_dir / "mechanism_estimates_loo.parquet", index=False)
    mechanisms.to_csv(output_dir / "mechanism_estimates_loo.csv", index=False)

    sixty = mechanisms.loc[mechanisms["horizon_seconds"].eq(60)].copy()
    _heatmap(
        sixty,
        value="total_adjustment_bp",
        title="Midpoint response 60 seconds after each release",
        colorbar_label="log midpoint return (bp)",
        output=figure_dir / "event_return_heatmap_60s.png",
    )
    _heatmap(
        sixty,
        value="component_coverage_ratio",
        title="Quote-plus-flow component coverage at 60 seconds",
        colorbar_label="component sum / total adjustment",
        output=figure_dir / "component_coverage_heatmap_60s.png",
    )
    print(
        f"Wrote {len(diagnostics)} leave-one-event-out impact fits and "
        f"{len(mechanisms)} event-horizon mechanism estimates."
    )


if __name__ == "__main__":
    main()
