from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import databento as db
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from scripts.build_fomc_pilot import normalize_mbp1
from src.analysis.event_summary import valid_quotes
from src.utils.config import PROJECT_ROOT, load_yaml


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
THRESHOLDS_BP = (0.5, 1.0, 2.0)
WINDOW_SECONDS = 30
GRID = "100ms"
LAGS_100MS = range(-10, 11)


def _matching_raw_file(meeting: dict[str, object]) -> Path | None:
    raw_dir = PROJECT_ROOT / "data" / "raw" / "databento"
    start = pd.Timestamp(meeting["request_start_utc"])
    end = pd.Timestamp(meeting["request_end_utc"])
    for metadata_path in raw_dir.glob("GLBX.MDP3-mbp-1-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == start
            and pd.Timestamp(metadata["end"]) == end
            and set(metadata["symbols"]) == set(INSTRUMENTS)
        ):
            path = metadata_path.with_suffix("").with_suffix("")
            if path.exists():
                return path
    return None


def _quote_path(messages: pd.DataFrame, event_time: pd.Timestamp) -> pd.DataFrame:
    quotes = valid_quotes(messages).sort_values(["ts_event", "sequence"], kind="stable")
    pre = quotes.loc[quotes["ts_event"].lt(event_time)]
    if pre.empty:
        return pd.DataFrame()
    reference = float(pre.iloc[-1]["midpoint"])
    path = quotes.loc[
        quotes["ts_event"].between(
            event_time, event_time + pd.Timedelta(seconds=WINDOW_SECONDS), inclusive="both"
        )
    ].copy()
    path["delay_ms"] = (path["ts_event"] - event_time).dt.total_seconds() * 1000
    path["return_bp"] = 1e4 * np.log(path["midpoint"] / reference)
    path["reference_midpoint"] = reference
    return path


def _first_move_rows(
    paths: dict[str, pd.DataFrame], meeting: str, subevent: str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for instrument, path in paths.items():
        for threshold in THRESHOLDS_BP:
            crossed = path.loc[path["return_bp"].abs().ge(threshold)]
            row = crossed.iloc[0] if not crossed.empty else None
            rows.append(
                {
                    "meeting": meeting,
                    "subevent": subevent,
                    "instrument": instrument,
                    "threshold_bp": threshold,
                    "crossed_within_30s": row is not None,
                    "first_crossing_delay_ms": np.nan if row is None else float(row["delay_ms"]),
                    "return_at_crossing_bp": np.nan if row is None else float(row["return_bp"]),
                    "quote_timestamp_utc": pd.NaT if row is None else row["ts_event"],
                }
            )
    return rows


def _grid_returns(path: pd.DataFrame, event_time: pd.Timestamp) -> pd.Series:
    if path.empty:
        return pd.Series(dtype=float)
    pre_value = float(path.iloc[0]["reference_midpoint"])
    anchor = pd.DataFrame(
        {"ts_event": [event_time - pd.Timedelta(milliseconds=100)], "midpoint": [pre_value]}
    )
    sample = pd.concat([anchor, path[["ts_event", "midpoint"]]], ignore_index=True)
    grid = (
        sample.set_index("ts_event")["midpoint"]
        .resample(GRID)
        .last()
        .ffill()
    )
    returns = np.log(grid).diff()
    return returns.loc[
        (returns.index >= event_time) &
        (returns.index <= event_time + pd.Timedelta(seconds=WINDOW_SECONDS))
    ].fillna(0.0)


def _correlation_rows(
    paths: dict[str, pd.DataFrame], meeting: str, subevent: str, event_time: pd.Timestamp
) -> list[dict[str, object]]:
    returns = {instrument: _grid_returns(path, event_time) for instrument, path in paths.items()}
    rows: list[dict[str, object]] = []
    for first, second in combinations(INSTRUMENTS, 2):
        aligned = pd.concat([returns[first], returns[second]], axis=1, keys=[first, second]).fillna(0.0)
        for lag in LAGS_100MS:
            # Positive lag compares first(t) with second(t + lag), so the first
            # instrument is the leader candidate.
            follower = aligned[second].shift(-lag)
            usable = pd.concat([aligned[first], follower], axis=1).dropna()
            correlation = (
                np.nan
                if usable.empty or usable.iloc[:, 0].std() == 0 or usable.iloc[:, 1].std() == 0
                else usable.iloc[:, 0].corr(usable.iloc[:, 1])
            )
            rows.append(
                {
                    "meeting": meeting,
                    "subevent": subevent,
                    "first_instrument": first,
                    "second_instrument": second,
                    "lag_100ms": lag,
                    "lag_ms": lag * 100,
                    "correlation": correlation,
                    "positive_lag_means": "first_instrument_precedes_second_instrument",
                }
            )
    return rows


def _delay_inference(first_moves: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (subevent, threshold), sample in first_moves.groupby(["subevent", "threshold_bp"]):
        wide = sample.pivot(index="meeting", columns="instrument", values="first_crossing_delay_ms")
        for first, second in combinations(INSTRUMENTS, 2):
            paired = wide[[first, second]].dropna()
            difference = (paired[first] - paired[second]).to_numpy(float)
            nonzero = difference[~np.isclose(difference, 0)]
            rows.append(
                {
                    "subevent": subevent,
                    "threshold_bp": threshold,
                    "first_instrument": first,
                    "second_instrument": second,
                    "paired_meetings": len(difference),
                    "median_first_delay_ms": paired[first].median(),
                    "median_second_delay_ms": paired[second].median(),
                    "median_first_minus_second_ms": np.median(difference) if len(difference) else np.nan,
                    "first_faster_count": int((nonzero < 0).sum()),
                    "one_sided_sign_p_first_faster": (
                        np.nan if not len(nonzero)
                        else float(binomtest((nonzero < 0).sum(), len(nonzero), 0.5, alternative="greater").pvalue)
                    ),
                    "one_sided_wilcoxon_p_first_faster": (
                        np.nan if not len(nonzero)
                        else float(wilcoxon(nonzero, alternative="less", method="auto").pvalue)
                    ),
                }
            )
    return pd.DataFrame(rows)


def _correlation_summary(correlations: pd.DataFrame) -> pd.DataFrame:
    best = (
        correlations.assign(abs_correlation=correlations["correlation"].abs())
        .sort_values(["meeting", "subevent", "first_instrument", "second_instrument", "abs_correlation"], ascending=[True, True, True, True, False])
        .groupby(["meeting", "subevent", "first_instrument", "second_instrument"], as_index=False)
        .first()
    )
    return (
        best.groupby(["subevent", "first_instrument", "second_instrument"], as_index=False)
        .agg(
            meetings=("meeting", "nunique"),
            median_best_lag_ms=("lag_ms", "median"),
            zero_lag_count=("lag_ms", lambda value: int((value == 0).sum())),
            positive_lag_count=("lag_ms", lambda value: int((value > 0).sum())),
            negative_lag_count=("lag_ms", lambda value: int((value < 0).sum())),
            median_abs_correlation=("abs_correlation", "median"),
        )
    )


def _figure(first_moves: pd.DataFrame, output: Path) -> None:
    sample = first_moves.loc[first_moves["crossed_within_30s"]].copy()
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.5), sharey="row")
    colors = {"ES.v.0": "#1f77b4", "NQ.v.0": "#ff7f0e", "ZN.v.0": "#2ca02c"}
    for row, subevent in enumerate(("statement", "press_conference")):
        for col, threshold in enumerate(THRESHOLDS_BP):
            ax = axes[row, col]
            cell = sample.loc[
                sample["subevent"].eq(subevent) & sample["threshold_bp"].eq(threshold)
            ]
            values = [
                cell.loc[cell["instrument"].eq(instrument), "first_crossing_delay_ms"].dropna() / 1000
                for instrument in INSTRUMENTS
            ]
            box = ax.boxplot(values, tick_labels=[x.replace(".v.0", "") for x in INSTRUMENTS], patch_artist=True)
            for patch, instrument in zip(box["boxes"], INSTRUMENTS):
                patch.set_facecolor(colors[instrument]); patch.set_alpha(0.55)
            for position, value in enumerate(values, start=1):
                ax.text(
                    position,
                    0.98,
                    f"n={len(value)}",
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=8,
                    color="#444444",
                )
            ax.set_yscale("log")
            ax.grid(axis="y", alpha=0.25)
            ax.set_title(f"{subevent.replace('_', ' ')}, {threshold:g} bp")
            if col == 0:
                ax.set_ylabel("first crossing delay (seconds, log scale)")
    fig.suptitle("Subsecond first-material-move timing across clean FOMC meetings")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "fomc_sample.yaml")
    first_move_rows: list[dict[str, object]] = []
    correlation_rows: list[dict[str, object]] = []
    processed = 0
    for meeting in config["meetings"]:
        if meeting.get("dataset_condition", "available") != "available":
            continue
        path = _matching_raw_file(meeting)
        if path is None:
            continue
        frame = db.DBNStore.from_file(path).to_df()
        messages = {
            instrument: normalize_mbp1(frame.loc[frame["symbol"].eq(instrument)])
            for instrument in INSTRUMENTS
        }
        for subevent, time_field in (
            ("statement", "statement_time_utc"),
            ("press_conference", "press_conference_time_utc"),
        ):
            event_time = pd.Timestamp(meeting[time_field])
            paths = {instrument: _quote_path(value, event_time) for instrument, value in messages.items()}
            first_move_rows.extend(_first_move_rows(paths, meeting["label"], subevent))
            correlation_rows.extend(_correlation_rows(paths, meeting["label"], subevent, event_time))
        processed += 1
        del frame

    first_moves = pd.DataFrame(first_move_rows)
    correlations = pd.DataFrame(correlation_rows)
    delay_inference = _delay_inference(first_moves)
    correlation_summary = _correlation_summary(correlations)
    output = PROJECT_ROOT / "data" / "processed" / "fomc_price_discovery"
    figures = PROJECT_ROOT / "figures" / "paper"
    output.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    products = {
        "first_material_move": first_moves,
        "first_material_move_inference": delay_inference,
        "cross_correlation_100ms": correlations,
        "cross_correlation_100ms_summary": correlation_summary,
    }
    for name, frame in products.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
        frame.to_csv(output / f"{name}.csv", index=False)
    _figure(first_moves, figures / "fomc_subsecond_first_move.png")
    print(
        f"Processed {processed} clean meetings; wrote {len(first_moves)} first-move rows "
        f"and {len(correlations)} 100 ms lag correlations."
    )


if __name__ == "__main__":
    main()
