from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.build_fomc_pilot import normalize_mbp1
from src.analysis.event_summary import (
    second_intervals,
    summarize_horizons,
    timing_and_liquidity_summary,
)
from src.utils.config import PROJECT_ROOT, load_yaml


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
# Statements also get 10/20/30-minute horizons for the multi-horizon H5 test.
# The press conference starts 30 minutes after the statement, so 30 minutes is
# the last horizon before new information; statement-only meetings (15-minute
# windows) report those horizons as not covered.
STATEMENT_HORIZONS = (0.1, 0.25, 0.5, 1, 5, 30, 60, 300, 600, 1200, 1800)


def _matching_raw_file(meeting: dict[str, object]) -> Path | None:
    raw_dir = PROJECT_ROOT / "data" / "raw" / "databento"
    expected_start = pd.Timestamp(meeting["request_start_utc"])
    expected_end = pd.Timestamp(meeting["request_end_utc"])
    for metadata_path in raw_dir.glob("GLBX.MDP3-mbp-1-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == expected_start
            and pd.Timestamp(metadata["end"]) == expected_end
            and set(metadata["symbols"]) == set(INSTRUMENTS)
        ):
            dbn_path = metadata_path.with_suffix("").with_suffix("")
            if dbn_path.exists():
                return dbn_path
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build cross-meeting FOMC tick summaries from cached MBP-1 files"
    )
    parser.add_argument(
        "--meetings", nargs="*", help="Optional meeting labels; default processes every cached meeting"
    )
    parser.add_argument("--config", default="fomc_sample.yaml", help="File under config/")
    parser.add_argument(
        "--output-name", default="fomc_sample", help="Folder under data/processed/"
    )
    args = parser.parse_args()
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc

    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    selected = set(args.meetings or [])
    timing_rows: list[dict[str, object]] = []
    horizon_frames: list[pd.DataFrame] = []
    interval_frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []

    total = len(config["meetings"])
    for number, meeting in enumerate(config["meetings"], start=1):
        label = meeting["label"]
        if selected and label not in selected:
            continue
        path = _matching_raw_file(meeting)
        if path is None:
            print(f"Skipping {label}: matching immutable DBN file is not cached.")
            continue
        print(f"[{number}/{total}] {label}", flush=True)
        frame = db.DBNStore.from_file(path).to_df()
        for instrument in INSTRUMENTS:
            instrument_frame = frame.loc[frame["symbol"].eq(instrument)]
            if instrument_frame.empty:
                print(f"Skipping {label}/{instrument}: no records after symbol mapping.")
                continue
            messages = normalize_mbp1(instrument_frame)
            condition = meeting.get("dataset_condition", "available")
            coverage_rows.append(
                {
                    "meeting": label,
                    "instrument": instrument,
                    "raw_file": str(path.relative_to(PROJECT_ROOT)),
                    "dataset_condition": condition,
                    "message_count": len(messages),
                    "first_message_utc": messages["ts_event"].min(),
                    "last_message_utc": messages["ts_event"].max(),
                    "resolved_symbols": "|".join(
                        sorted(set(instrument_frame["symbol"].dropna().astype(str)))
                    ),
                }
            )
            statement_time = pd.Timestamp(meeting["statement_time_utc"])
            subevents = [("statement", statement_time, "narrative_text")]
            # Before 2019 most meetings had no press conference.
            if meeting.get("press_conference_time_utc"):
                subevents.append(
                    (
                        "press_conference",
                        pd.Timestamp(meeting["press_conference_time_utc"]),
                        "extemporaneous_speech",
                    )
                )
            for subevent, event_time, representation in subevents:
                event_label = f"{label}_{subevent}"
                timing = timing_and_liquidity_summary(
                    messages, event_time, instrument, event_label
                )
                timing.update(
                    {
                        "meeting": label,
                        "subevent": subevent,
                        "representation_class": representation,
                        "sep_release": bool(meeting["sep_release"]),
                        "policy_change_bps": int(meeting["policy_change_bps"]),
                        "dataset_condition": condition,
                        "eligible_primary_q1": bool(
                            timing["valid_mechanically"] and condition == "available"
                        ),
                    }
                )
                timing_rows.append(timing)
                horizons = summarize_horizons(
                    messages, event_time, instrument, event_label,
                    **({"horizons_seconds": STATEMENT_HORIZONS} if subevent == "statement" else {}),
                )
                horizons["meeting"] = label
                horizons["subevent"] = subevent
                horizons["representation_class"] = representation
                horizons["sep_release"] = bool(meeting["sep_release"])
                horizons["policy_change_bps"] = int(meeting["policy_change_bps"])
                horizons["dataset_condition"] = condition
                horizon_frames.append(horizons)

            intervals = second_intervals(messages).reset_index().rename(
                columns={"ts_event": "second_utc", "index": "second_utc"}
            )
            intervals["meeting"] = label
            intervals["instrument"] = instrument
            intervals["statement_event_seconds"] = (
                pd.to_datetime(intervals["second_utc"], utc=True) - statement_time
            ).dt.total_seconds()
            intervals["dataset_condition"] = condition
            interval_frames.append(intervals)
        del frame

    if not timing_rows:
        raise RuntimeError("No cached FOMC sample files matched the configured windows")
    output = PROJECT_ROOT / "data" / "processed" / args.output_name
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "timing_liquidity": pd.DataFrame(timing_rows),
        "response_horizons": pd.concat(horizon_frames, ignore_index=True),
        "one_second_intervals": pd.concat(interval_frames, ignore_index=True),
        "raw_coverage": pd.DataFrame(coverage_rows),
    }
    for name, data in products.items():
        data.to_parquet(output / f"{name}.parquet", index=False)
        if name != "one_second_intervals":
            data.to_csv(output / f"{name}.csv", index=False)
    print(
        f"Processed {products['raw_coverage']['meeting'].nunique()} meetings, "
        f"{len(products['timing_liquidity'])} event-instrument timing rows, and "
        f"{len(products['response_horizons'])} horizon rows."
    )


if __name__ == "__main__":
    main()
