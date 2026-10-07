"""One-second afternoon panels around every FOMC statement and matched control day.

Inputs are the ``bbo-1s`` (and, on meeting days, ``trades``) files requested by
``build_fomc_session_windows.py``. Output: ``data/processed/fomc_sessions/panel.parquet``
with one row per session, instrument and second from 30 minutes before to 120
minutes after the 2:00 p.m. clock.

The same extraction serves any registry of one-second windows, for example the
unscheduled arrivals:
    python -m scripts.extract_session_panels --registry unscheduled_windows.csv \
        --output unscheduled --start-seconds -1800 --end-seconds 960

Clock handling. ``bbo-1s`` samples the book on the vendor's receive clock. In
the cached history that clock equals the exchange clock to well under a
millisecond, except from 9 May to 3 August 2018, when it runs exactly one second
ahead (see reports/timestamp_latency_census.csv). The whole-second offset is
detected per file from the low end of the receive-minus-exchange gap, rounded to
whole seconds, and removed, so every row is on the exchange clock. Trades are bucketed by exchange timestamp.
"""
from __future__ import annotations

import argparse
import os
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.raw_index import build_raw_index, find_raw_file
from src.utils.config import PROJECT_ROOT

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
OUTPUT = PROJECT_ROOT / "data" / "processed" / "fomc_sessions"
START_SECONDS, END_SECONDS = -1800, 7200
NS = 1_000_000_000
UNDEF = np.iinfo(np.int64).max


def _symbol_ids(store) -> dict[str, int]:
    return {symbol: int(intervals[0]["symbol"]) for symbol, intervals in store.metadata.mappings.items() if intervals}


def process_session(task: dict) -> pd.DataFrame:
    import databento as db

    event_ns = pd.Timestamp(task["event_time_utc"]).value
    grid = np.arange(task.get("start_seconds", START_SECONDS), task.get("end_seconds", END_SECONDS) + 1)
    boundary = event_ns + grid.astype(np.int64) * NS
    store = db.DBNStore.from_file(task["bbo_path"])
    records = store.to_ndarray()
    gap = records["ts_recv"].astype(np.int64) - records["ts_event"].astype(np.int64)
    known = gap[records["ts_event"] != np.iinfo(np.uint64).max]
    # Whole seconds only: sub-millisecond clock skew (either sign) is not an offset.
    offset_seconds = int(np.rint(np.percentile(known, 5) / NS)) if known.size else 0
    trades = None
    if task.get("trades_path"):
        trade_store = db.DBNStore.from_file(task["trades_path"])
        trades = (trade_store.to_ndarray(), _symbol_ids(trade_store))
    frames = []
    for symbol, instrument_id in _symbol_ids(store).items():
        rows = records[records["instrument_id"] == instrument_id]
        if rows.shape[0] == 0:
            continue
        # A record stamped B on the receive clock is the book at exchange time B - offset.
        stamp = rows["ts_recv"].astype(np.int64) - offset_seconds * NS
        order = np.argsort(stamp, kind="stable")
        rows, stamp = rows[order], stamp[order]
        position = np.searchsorted(stamp, boundary, side="right") - 1
        has = position >= 0
        safe = np.maximum(position, 0)
        bid_raw, ask_raw = rows["bid_px_00"][safe], rows["ask_px_00"][safe]
        bid = np.where(bid_raw == UNDEF, np.nan, bid_raw * 1e-9)
        ask = np.where(ask_raw == UNDEF, np.nan, ask_raw * 1e-9)
        bid_size = rows["bid_sz_00"][safe].astype(float)
        ask_size = rows["ask_sz_00"][safe].astype(float)
        with np.errstate(invalid="ignore"):
            valid = has & np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > bid) & (bid_size > 0) & (ask_size > 0)
            logmid = np.where(valid, np.log((bid + ask) / 2), np.nan)
        inside = (boundary >= stamp[0]) & (boundary <= stamp[-1] + NS)
        frame = pd.DataFrame({
            "seconds": grid.astype(np.int32),
            "inside_window": inside,
            "valid": valid & inside,
            "logmid": np.where(inside, logmid, np.nan),
            "bid": np.where(inside, bid, np.nan), "ask": np.where(inside, ask, np.nan),
            "bid_size": np.where(inside, bid_size, np.nan).astype(np.float32),
            "ask_size": np.where(inside, ask_size, np.nan).astype(np.float32),
        })
        for name in ("buy_volume", "sell_volume", "unknown_volume", "trade_count"):
            frame[name] = np.float32(np.nan)
        if trades is not None:
            trade_rows, trade_ids = trades
            mine = trade_rows[trade_rows["instrument_id"] == trade_ids.get(symbol, -1)]
            # Trades in (boundary[k-1], boundary[k]] are assigned to row k: flow up to that second.
            bucket = np.searchsorted(boundary, mine["ts_event"].astype(np.int64), side="left")
            keep = (bucket >= 1) & (bucket < len(grid))
            size = mine["size"].astype(float)
            side = mine["side"]
            for name, mask in (("buy_volume", side == b"B"), ("sell_volume", side == b"A"), ("unknown_volume", side == b"N")):
                frame[name] = np.bincount(bucket[keep & mask], weights=size[keep & mask], minlength=len(grid)).astype(np.float32)
            frame["trade_count"] = np.bincount(bucket[keep], minlength=len(grid)).astype(np.float32)
        frame.insert(0, "instrument", symbol)
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    for column in ("event_id", "family", "cluster", "sample", "event_time_utc", "dataset_condition", "quality_flag"):
        out[column] = task[column]
    out["receive_clock_offset_seconds"] = offset_seconds
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default="fomc_session_windows.csv")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--force", action="store_true", help="Recompute sessions that already have parts")
    parser.add_argument("--output", default=OUTPUT.name, help="Folder under data/processed/")
    parser.add_argument("--start-seconds", type=int, default=START_SECONDS)
    parser.add_argument("--end-seconds", type=int, default=END_SECONDS)
    args = parser.parse_args()
    output = OUTPUT.parent / args.output
    parts = output / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    if args.merge:
        files = sorted(parts.glob("*.parquet"))
        meta_columns = ["event_id", "family", "cluster", "sample", "event_time_utc", "dataset_condition",
                        "quality_flag", "receive_clock_offset_seconds"]
        frames, sessions = [], []
        for file in files:
            frame = pd.read_parquet(file)
            sessions.append(frame[meta_columns].iloc[[0]])
            frames.append(frame.drop(columns=[c for c in meta_columns if c != "event_id"]))
        panel = pd.concat(frames, ignore_index=True)
        # Repeated strings as categories: the panel then fits comfortably in memory.
        for column in ("event_id", "instrument"):
            panel[column] = panel[column].astype("category")
        sessions = pd.concat(sessions, ignore_index=True)
        for name, table in (("panel", panel), ("sessions", sessions)):
            target = output / f"{name}.parquet"
            table.to_parquet(target.with_name(target.name + ".part"), index=False)
            os.replace(target.with_name(target.name + ".part"), target)
        sessions.to_csv(output / "sessions.csv", index=False)
        print(f"panel: {len(panel):,} rows from {len(files)} sessions; "
              f"receive-clock offsets {sessions['receive_clock_offset_seconds'].value_counts().to_dict()}")
        return
    registry = pd.read_csv(
        PROJECT_ROOT / "data" / "events" / args.registry,
        parse_dates=["event_time_utc", "request_start_utc", "request_end_utc"], keep_default_na=False,
    )
    index = build_raw_index()
    tasks = []
    for row in registry.itertuples(index=False):
        if not args.force and (parts / f"{row.event_id}.parquet").exists():
            continue
        window = dict(start=row.request_start_utc, end=row.request_end_utc, symbols=INSTRUMENTS, index=index)
        bbo = find_raw_file(schema="bbo-1s", **window)
        if bbo is None:
            continue
        trade_path = find_raw_file(schema="trades", **window)
        tasks.append({"bbo_path": str(bbo), "trades_path": None if trade_path is None else str(trade_path),
                      "event_id": row.event_id, "family": row.family, "cluster": row.cluster, "sample": row.sample,
                      "event_time_utc": row.event_time_utc, "dataset_condition": row.dataset_condition,
                      "quality_flag": row.quality_flag, "start_seconds": args.start_seconds, "end_seconds": args.end_seconds})
    print(f"{len(tasks)} sessions to process", flush=True)
    started = time.time()
    with get_context("fork").Pool(max(1, args.workers), maxtasksperchild=16) as pool:
        for done, frame in enumerate(pool.imap_unordered(process_session, tasks, chunksize=1), start=1):
            target = parts / f"{frame['event_id'].iloc[0]}.parquet"
            frame.to_parquet(target.with_name(target.name + ".part"), index=False)
            os.replace(target.with_name(target.name + ".part"), target)
            if args.max_seconds and time.time() - started > args.max_seconds:
                print(f"Time budget reached after {done} sessions; rerun to continue.", flush=True)
                pool.terminate()
                break
    print(f"Done in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
