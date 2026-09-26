from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _matching_raw_file(event: dict[str, object], instrument: str) -> Path | None:
    raw_dir = PROJECT_ROOT / "data" / "raw" / "databento"
    for metadata_path in raw_dir.glob("GLBX.MDP3-mbp-10-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == pd.Timestamp(event["request_start_utc"])
            and pd.Timestamp(metadata["end"]) == pd.Timestamp(event["request_end_utc"])
            and set(metadata["symbols"]) == {instrument}
        ):
            path = metadata_path.with_suffix("").with_suffix("")
            if path.exists():
                return path
    return None


def _book_states(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["ts_event"] = pd.to_datetime(frame.index, utc=True)
    required = {"bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"MBP-10 frame is missing required columns: {missing}")
    levels = [
        level
        for level in range(10)
        if {f"bid_sz_{level:02d}", f"ask_sz_{level:02d}"}.issubset(frame.columns)
    ]
    if len(levels) < 10:
        raise ValueError(f"Expected ten MBP levels; found {len(levels)}")
    frame = frame.loc[
        frame["bid_px_00"].gt(0) & frame["ask_px_00"].gt(frame["bid_px_00"])
    ].copy()
    frame["midpoint"] = (frame["bid_px_00"] + frame["ask_px_00"]) / 2
    frame["spread"] = frame["ask_px_00"] - frame["bid_px_00"]
    for depth in (1, 5, 10):
        bid_columns = [f"bid_sz_{level:02d}" for level in levels[:depth]]
        ask_columns = [f"ask_sz_{level:02d}" for level in levels[:depth]]
        frame[f"bid_depth_l{depth}"] = frame[bid_columns].sum(axis=1)
        frame[f"ask_depth_l{depth}"] = frame[ask_columns].sum(axis=1)
        frame[f"total_depth_l{depth}"] = (
            frame[f"bid_depth_l{depth}"] + frame[f"ask_depth_l{depth}"]
        )
        denominator = frame[f"total_depth_l{depth}"].replace(0, np.nan)
        frame[f"imbalance_l{depth}"] = (
            frame[f"bid_depth_l{depth}"] - frame[f"ask_depth_l{depth}"]
        ) / denominator
    keep = ["ts_event", "midpoint", "spread"]
    for depth in (1, 5, 10):
        keep.extend(
            [
                f"bid_depth_l{depth}", f"ask_depth_l{depth}",
                f"total_depth_l{depth}", f"imbalance_l{depth}",
            ]
        )
    return frame[keep].sort_values("ts_event", kind="stable")


def _interval_summary(
    states: pd.DataFrame, event_time: pd.Timestamp, event_id: str, instrument: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    one_second = (
        states.set_index("ts_event")
        .resample("1s")
        .last()
        .ffill()
        .reset_index()
    )
    one_second["event_id"] = event_id
    one_second["instrument"] = instrument
    one_second["event_seconds"] = (
        one_second["ts_event"] - event_time
    ).dt.total_seconds()
    baseline = one_second.loc[
        one_second["ts_event"].ge(event_time - pd.Timedelta(minutes=5))
        & one_second["ts_event"].lt(event_time - pd.Timedelta(minutes=1))
    ]
    pre60 = one_second.loc[
        one_second["ts_event"].ge(event_time - pd.Timedelta(minutes=1))
        & one_second["ts_event"].lt(event_time)
    ]
    row: dict[str, object] = {
        "event_id": event_id,
        "instrument": instrument,
        "event_time_utc": event_time,
        "book_update_count": len(states),
        "baseline_second_count": len(baseline),
        "pre60_second_count": len(pre60),
    }
    for depth in (1, 5, 10):
        column = f"total_depth_l{depth}"
        baseline_mean = float(baseline[column].mean())
        pre60_mean = float(pre60[column].mean())
        row[f"baseline_depth_l{depth}_mean"] = baseline_mean
        row[f"pre60_depth_l{depth}_mean"] = pre60_mean
        row[f"pre60_to_baseline_depth_l{depth}_ratio"] = (
            np.nan if baseline_mean == 0 else pre60_mean / baseline_mean
        )
    return one_second, row


def main() -> None:
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc
    config = load_yaml(PROJECT_ROOT / "config" / "depth_sample.yaml")
    interval_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    for event in config["events"]:
        event_time = pd.Timestamp(event["event_time_utc"])
        for instrument in INSTRUMENTS:
            path = _matching_raw_file(event, instrument)
            if path is None:
                print(
                    f"Skipping {event['event_id']}/{instrument}: "
                    "matching immutable DBN is not cached"
                )
                continue
            frame = db.DBNStore.from_file(path).to_df()
            raw = frame.loc[frame["symbol"].eq(instrument)]
            if raw.empty:
                del frame
                continue
            states = _book_states(raw)
            intervals, summary = _interval_summary(
                states, event_time, str(event["event_id"]), instrument
            )
            interval_frames.append(intervals)
            summary_rows.append(summary)
            coverage_rows.append(
                {
                    "event_id": event["event_id"],
                    "instrument": instrument,
                    "raw_file": str(path.relative_to(PROJECT_ROOT)),
                    "record_count": len(raw),
                    "valid_book_state_count": len(states),
                    "first_state_utc": states["ts_event"].min(),
                    "last_state_utc": states["ts_event"].max(),
                }
            )
            del frame
    if not summary_rows:
        raise RuntimeError("No configured MBP-10 files were available")
    output = PROJECT_ROOT / "data" / "processed" / "depth_sample"
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "depth_intervals_1s": pd.concat(interval_frames, ignore_index=True),
        "depth_summary": pd.DataFrame(summary_rows),
        "raw_coverage": pd.DataFrame(coverage_rows),
    }
    for name, product in products.items():
        product.to_parquet(output / f"{name}.parquet", index=False)
        if name != "depth_intervals_1s":
            product.to_csv(output / f"{name}.csv", index=False)
    print(
        f"Processed {products['depth_summary']['event_id'].nunique()} MBP-10 events "
        f"and {len(products['depth_summary'])} event-instrument summaries."
    )


if __name__ == "__main__":
    main()
