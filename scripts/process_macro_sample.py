from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from scripts.build_fomc_pilot import normalize_mbp1
from src.analysis.event_summary import (
    flow_intervals,
    second_intervals,
    summarize_horizons,
    timing_and_liquidity_summary,
)
from src.utils.config import PROJECT_ROOT, load_yaml


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _raw_file(start: str, end: str) -> Path | None:
    for metadata_path in (PROJECT_ROOT / "data" / "raw" / "databento").glob(
        "GLBX.MDP3-mbp-1-*.metadata.json"
    ):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == pd.Timestamp(start)
            and pd.Timestamp(metadata["end"]) == pd.Timestamp(end)
            and set(metadata["symbols"]) == set(INSTRUMENTS)
        ):
            path = metadata_path.with_suffix("").with_suffix("")
            if path.exists():
                return path
    return None


def _bundles(events: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for event in events:
        grouped[(event["request_start_utc"], event["request_end_utc"])].append(event)
    return list(grouped.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a configured macro sample")
    parser.add_argument("--config", default="macro_sample.yaml", help="File under config/")
    parser.add_argument("--conditions", default="macro_dataset_conditions.json", help="File under reports/")
    parser.add_argument("--output", default="macro_sample", help="Directory under data/processed/")
    args = parser.parse_args()
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc
    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    condition_path = PROJECT_ROOT / "reports" / args.conditions
    condition_report = json.loads(condition_path.read_text(encoding="utf-8"))
    conditions = {
        row["date"]: row["condition"] for row in condition_report["conditions"]
    }
    timing_rows: list[dict[str, object]] = []
    horizon_frames: list[pd.DataFrame] = []
    interval_frames: list[pd.DataFrame] = []
    subsecond_frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []

    for events in _bundles(config["events"]):
        first = events[0]
        path = _raw_file(first["request_start_utc"], first["request_end_utc"])
        if path is None:
            print(f"Skipping {first['event_date']}: matching immutable DBN is not cached")
            continue
        frame = db.DBNStore.from_file(path).to_df()
        event_time = pd.Timestamp(first["event_time_utc"])
        if any(pd.Timestamp(event["event_time_utc"]) != event_time for event in events):
            raise ValueError("A request bundle contains different event clocks")
        bundle_id = f"macro_{first['event_date'].replace('-', '')}_0830"
        event_ids = "|".join(event["event_id"] for event in events)
        event_types = "|".join(dict.fromkeys(event["event_type"] for event in events))
        representations = list(
            dict.fromkeys(event["representation_class"] for event in events)
        )
        representation = (
            representations[0] if len(representations) == 1 else "mixed_numeric_bundle"
        )
        concurrent = [
            str(event["concurrent_release"])
            for event in events
            if event.get("concurrent_release")
        ]
        condition = conditions.get(first["event_date"], "unverified")
        for instrument in INSTRUMENTS:
            raw = frame.loc[frame["symbol"].eq(instrument)]
            if raw.empty:
                continue
            messages = normalize_mbp1(raw)
            shared = {
                "bundle_id": bundle_id,
                "event_ids": event_ids,
                "event_types": event_types,
                "representation_class": representation,
                "concurrent_release": "|".join(dict.fromkeys(concurrent)),
                "dataset_condition": condition,
            }
            timing = timing_and_liquidity_summary(
                messages, event_time, instrument, bundle_id
            )
            timing.update(shared)
            timing["eligible_primary_q1"] = bool(
                timing["valid_mechanically"] and condition == "available"
            )
            timing_rows.append(timing)
            horizons = summarize_horizons(messages, event_time, instrument, bundle_id)
            for key, value in shared.items():
                horizons[key] = value
            horizon_frames.append(horizons)
            intervals = second_intervals(messages).reset_index().rename(
                columns={"ts_event": "second_utc", "index": "second_utc"}
            )
            intervals["bundle_id"] = bundle_id
            intervals["instrument"] = instrument
            intervals["event_seconds"] = (
                pd.to_datetime(intervals["second_utc"], utc=True) - event_time
            ).dt.total_seconds()
            intervals["event_types"] = event_types
            intervals["representation_class"] = representation
            intervals["dataset_condition"] = condition
            interval_frames.append(intervals)
            for frequency in ("100ms", "250ms", "500ms"):
                subsecond = flow_intervals(messages, frequency).reset_index().rename(
                    columns={"ts_event": "bucket_utc", "index": "bucket_utc"}
                )
                subsecond["bundle_id"] = bundle_id
                subsecond["instrument"] = instrument
                subsecond["frequency"] = frequency
                subsecond["event_seconds"] = (
                    pd.to_datetime(subsecond["bucket_utc"], utc=True) - event_time
                ).dt.total_seconds()
                subsecond["event_types"] = event_types
                subsecond["representation_class"] = representation
                subsecond["dataset_condition"] = condition
                subsecond_frames.append(subsecond)
            coverage_rows.append(
                {
                    **shared,
                    "instrument": instrument,
                    "raw_file": str(path.relative_to(PROJECT_ROOT)),
                    "message_count": len(messages),
                    "first_message_utc": messages["ts_event"].min(),
                    "last_message_utc": messages["ts_event"].max(),
                }
            )
        del frame

    if not timing_rows:
        raise RuntimeError("No macro sample files were processed")
    output = PROJECT_ROOT / "data" / "processed" / args.output
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "timing_liquidity": pd.DataFrame(timing_rows),
        "response_horizons": pd.concat(horizon_frames, ignore_index=True),
        "one_second_intervals": pd.concat(interval_frames, ignore_index=True),
        "subsecond_intervals": pd.concat(subsecond_frames, ignore_index=True),
        "raw_coverage": pd.DataFrame(coverage_rows),
    }
    for name, product in products.items():
        product.to_parquet(output / f"{name}.parquet", index=False)
        if name not in {"one_second_intervals", "subsecond_intervals"}:
            product.to_csv(output / f"{name}.csv", index=False)
    print(
        f"Processed {products['raw_coverage']['bundle_id'].nunique()} macro bundles, "
        f"{len(products['timing_liquidity'])} timing rows, and "
        f"{len(products['response_horizons'])} horizon rows."
    )


if __name__ == "__main__":
    main()
