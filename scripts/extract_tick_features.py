"""Replay cached MBP-1 windows into event-level tick features (resumable).

Each raw request window is read once. Per window the script writes three small
part files (event measures, a one-second cumulative panel, a 20 ms panel around
each event clock); ``--merge`` concatenates the parts into
``data/processed/tick_features/``.

Out-of-sample guard: windows outside the development sample are processed only
after ``config/q1_short_horizon_prereg.yaml`` is marked frozen and the SHA-256
of the measure code still matches the hash recorded at freeze time.

Examples
    python -m scripts.extract_tick_features --samples development
    python -m scripts.extract_tick_features --max-seconds 150 --workers 3
    python -m scripts.extract_tick_features --merge
"""
from __future__ import annotations

import argparse
import hashlib
import os
import time
from multiprocessing import get_context
from pathlib import Path

import pandas as pd

from src.data.raw_index import build_raw_index, find_raw_file
from src.utils.config import PROJECT_ROOT, load_yaml

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
MEASURE_CODE = (
    "src/microstructure/tick_arrays.py",
    "src/microstructure/quote_revision.py",
    "src/microstructure/event_features.py",
)
PREREGISTRATION = "config/q1_short_horizon_prereg.yaml"
OUTPUT = PROJECT_ROOT / "data" / "processed" / "tick_features"
ID_COLUMNS = [
    "event_id", "family", "subevent", "event_types", "representation_class", "scheduled",
    "is_control", "event_time_utc", "cluster", "matched_event", "sep_release",
    "policy_change_bps", "concurrent_release", "dataset_condition", "quality_flag", "sample",
    "event_date",
]


def measure_code_hash() -> str:
    digest = hashlib.sha256()
    for name in MEASURE_CODE:
        digest.update(name.encode())
        digest.update((PROJECT_ROOT / name).read_bytes())
    return digest.hexdigest()


def frozen_hash() -> str | None:
    path = PROJECT_ROOT / PREREGISTRATION
    if not path.exists():
        return None
    spec = load_yaml(path)
    if spec.get("status") != "frozen":
        return None
    return str(spec.get("measure_code_sha256"))


def _window_key(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return f"{start:%Y%m%dT%H%M%S}_{end:%Y%m%dT%H%M%S}"


def process_window(task: dict) -> dict:
    """Worker: one raw file -> event rows, one-second panel, fine panel."""
    import numpy as np

    from src.microstructure.event_features import (
        book_integrals, event_measures, fine_panel, liquidity_measures, second_panel,
    )
    from src.microstructure.quote_revision import NS, SAME_EVENT_TOLERANCE_NS, build_midpoint_path
    from src.microstructure.tick_arrays import load_mbp1

    started = time.time()
    events = task["events"]
    ticks = load_mbp1(task["path"])
    start_ns, end_ns = pd.Timestamp(task["start"]).value, pd.Timestamp(task["end"]).value
    anchor_ns = min(pd.Timestamp(event["event_time_utc"]).value for event in events)
    event_rows, second_frames, fine_frames = [], [], []
    for instrument in INSTRUMENTS:
        if instrument not in ticks:
            continue
        stream = ticks[instrument]
        path = build_midpoint_path(stream)
        alt_path = build_midpoint_path(stream, tolerance_ns=SAME_EVENT_TOLERANCE_NS)
        integrals = book_integrals(path)
        shared = {
            "instrument": instrument, "instrument_id": stream.instrument_id, "window_key": task["key"],
            "raw_file": Path(task["path"]).name, "message_count": len(stream),
            "trade_record_count": int(stream.is_trade.sum()), "other_action_count": stream.other_action_count,
            "invalid_book_record_share": float(1 - stream.book_valid[stream.is_book].mean()) if stream.is_book.any() else np.nan,
        }
        for event in events:
            event_ns = pd.Timestamp(event["event_time_utc"]).value
            row = {**{key: event[key] for key in ID_COLUMNS}, **shared}
            row.update(event_measures(path, event_ns, alt_path))
            row.update(liquidity_measures(path, event_ns, integrals))
            event_rows.append(row)
            fine = fine_panel(path, event_ns)
            fine.insert(0, "instrument", instrument)
            fine.insert(0, "event_id", event["event_id"])
            fine_frames.append(fine)
        panel = second_panel(
            path, anchor_ns,
            int(np.floor((start_ns - anchor_ns) / NS)), int(np.ceil((end_ns - anchor_ns) / NS)), integrals,
        )
        panel.insert(0, "anchor_time_utc", pd.Timestamp(anchor_ns, tz="UTC"))
        panel.insert(0, "instrument", instrument)
        panel.insert(0, "window_key", task["key"])
        second_frames.append(panel)
    return {
        "key": task["key"],
        "events": pd.DataFrame(event_rows),
        "seconds": pd.concat(second_frames, ignore_index=True) if second_frames else pd.DataFrame(),
        "fine": pd.concat(fine_frames, ignore_index=True) if fine_frames else pd.DataFrame(),
        "elapsed": time.time() - started,
    }


def _write(frame: pd.DataFrame, target: Path) -> None:
    partial = target.with_name(target.name + ".part")
    frame.to_parquet(partial, index=False)
    os.replace(partial, target)


def merge(parts: Path) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ("events", "seconds", "fine"):
        files = sorted(parts.glob(f"*.{name}.parquet"))
        if not files:
            continue
        frame = pd.concat([pd.read_parquet(file) for file in files], ignore_index=True)
        _write(frame, OUTPUT / f"{name}.parquet")
        print(f"{name}: {len(frame):,} rows from {len(files)} windows")
    events = pd.read_parquet(OUTPUT / "events.parquet")
    events.to_csv(OUTPUT / "events.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default="event_registry.csv", help="File under data/events/")
    parser.add_argument("--samples", nargs="*", default=["development", "oos_backward", "oos_forward"])
    parser.add_argument("--families", nargs="*")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-seconds", type=float, help="Stop submitting new windows after this long")
    parser.add_argument("--force", action="store_true", help="Recompute windows that already have parts")
    parser.add_argument("--merge", action="store_true", help="Only concatenate existing parts")
    parser.add_argument("--allow-post-freeze-change", action="store_true",
                        help="Process out-of-sample windows although the measure code changed after the freeze")
    args = parser.parse_args()
    parts = OUTPUT / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    if args.merge:
        merge(parts)
        return

    registry = pd.read_csv(
        PROJECT_ROOT / "data" / "events" / args.registry,
        parse_dates=["event_time_utc", "request_start_utc", "request_end_utc"], keep_default_na=False,
    )
    registry = registry.loc[registry["sample"].isin(args.samples)]
    if args.families:
        registry = registry.loc[registry["family"].isin(args.families)]
    code_hash = measure_code_hash()
    if registry["sample"].ne("development").any():
        recorded = frozen_hash()
        if recorded is None:
            raise SystemExit(
                f"{PREREGISTRATION} is not frozen: only the development sample may be processed. "
                "Use --samples development."
            )
        if recorded != code_hash and not args.allow_post_freeze_change:
            raise SystemExit("Measure code differs from the frozen hash; see --allow-post-freeze-change.")

    index = build_raw_index()
    tasks, missing = [], 0
    for (start, end), group in registry.groupby(["request_start_utc", "request_end_utc"], sort=True):
        key = _window_key(start, end)
        if not args.force and (parts / f"{key}.events.parquet").exists():
            continue
        path = find_raw_file(start=start, end=end, symbols=INSTRUMENTS, index=index)
        if path is None:
            missing += 1
            continue
        tasks.append({"key": key, "path": str(path), "start": start, "end": end,
                      "events": group[ID_COLUMNS].to_dict("records")})
    print(f"{len(tasks)} windows to process; {missing} windows have no cached raw file; code hash {code_hash[:12]}", flush=True)
    if not tasks:
        return
    started = time.time()
    done = 0
    context = get_context("fork")
    with context.Pool(max(1, args.workers), maxtasksperchild=8) as pool:
        for result in pool.imap_unordered(process_window, tasks, chunksize=1):
            events = result["events"]
            if not events.empty:
                events["measure_code_sha256"] = code_hash
                _write(result["seconds"], parts / f"{result['key']}.seconds.parquet")
                _write(result["fine"], parts / f"{result['key']}.fine.parquet")
                _write(events, parts / f"{result['key']}.events.parquet")
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print(f"{done}/{len(tasks)} windows, {time.time() - started:.0f}s", flush=True)
            if args.max_seconds and time.time() - started > args.max_seconds:
                print(f"Time budget reached after {done} windows; rerun to continue.", flush=True)
                pool.terminate()
                break
    print(f"Processed {done} windows in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
