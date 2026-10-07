"""One-second top-of-book panels around FOMC statements and matched control days.

Reads each cached MBP-1 window once (streamed in chunks) and writes, per event and
instrument, the best bid, best ask and their sizes in force at every whole second
from -5 minutes to the end of the window. Spread (plot_fomc_spread) and price
paths for H5/H6 (plot_fomc_price_paths) both read this, so the slow raw read
happens once.

Second s holds the last valid quote at or before event + s seconds, where a valid
quote has bid > 0 and ask > bid. Output, resumable per event:
    data/processed/fomc_book_seconds/<kind>/<id>_to<last minute>.parquet

Run: python -m scripts.extract_fomc_book_seconds
"""

from __future__ import annotations

import argparse
import gc

import numpy as np
import pandas as pd

from scripts.plot_fomc_depth_sides import control_windows, meeting_windows
from src.utils.config import PROJECT_ROOT

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
OUT = PROJECT_ROOT / "data" / "processed" / "fomc_book_seconds"
COLUMNS = {"bid_px_00": "bid", "ask_px_00": "ask", "bid_sz_00": "bid_size", "ask_sz_00": "ask_size"}


def read_quotes(path, chunk_rows: int = 2_000_000) -> pd.DataFrame:
    """Valid top-of-book quotes (no trades, no crossed or empty books), four fields per row."""
    import databento as db

    keep = []
    for chunk in db.DBNStore.from_file(path).to_df(count=chunk_rows):
        if chunk.empty:
            continue
        chunk = chunk.reset_index()
        action = chunk["action"].astype(str).str.upper()
        valid = ~action.eq("T") & chunk["bid_px_00"].gt(0) & chunk["ask_px_00"].gt(chunk["bid_px_00"])
        keep.append(chunk.loc[valid, ["ts_event", "symbol", *COLUMNS]].rename(columns=COLUMNS))
        del chunk
    if not keep:
        return pd.DataFrame()
    quotes = pd.concat(keep, ignore_index=True)
    quotes["ts_event"] = pd.to_datetime(quotes["ts_event"], utc=True)
    return quotes


def to_seconds(quotes: pd.DataFrame, event: pd.Timestamp, first_minute: int, last_minute: int) -> pd.DataFrame:
    """As-of sample of each instrument's book at every whole second of the window."""
    seconds = np.arange(first_minute * 60, (last_minute + 1) * 60)
    grid = (event + pd.to_timedelta(seconds, unit="s")).asi8
    frames = []
    for instrument, group in quotes.groupby("symbol"):
        if instrument not in INSTRUMENTS:
            continue
        group = group.sort_values("ts_event", kind="stable")
        stamps = group["ts_event"].astype("int64").to_numpy()
        position = np.searchsorted(stamps, grid, side="right") - 1
        has = position >= 0
        rows = group.iloc[np.maximum(position, 0)]
        frame = pd.DataFrame({"instrument": instrument, "second": seconds.astype(np.int32)})
        for column in COLUMNS.values():
            frame[column] = np.where(has, rows[column].to_numpy(float), np.nan)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract(windows: list[dict], kind: str) -> int:
    folder = OUT / kind
    folder.mkdir(parents=True, exist_ok=True)
    done = 0
    for i, window in enumerate(windows, 1):
        tag = f"[{kind} {i}/{len(windows)}] {window['id']}"
        target = folder / f"{window['id']}_to{window['last']}.parquet"
        if target.exists():
            print(f"{tag}: cached")
            done += 1
            continue
        quotes = read_quotes(window["path"])
        frame = to_seconds(quotes, window["event"], window["first"], window["last"]) if not quotes.empty else pd.DataFrame()
        if not frame.empty:
            frame.insert(0, "id", window["id"])
            frame.insert(0, "kind", kind)
        frame.to_parquet(target, index=False)  # empty results are cached too
        print(tag if not frame.empty else f"{tag}: no usable quotes")
        done += 1
        del quotes, frame
        gc.collect()
    return done


def load(kind: str) -> pd.DataFrame:
    """All cached one-second panels of one kind ("fomc" or "control")."""
    files = sorted((OUT / kind).glob("*.parquet"))
    frames = [pd.read_parquet(f) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise RuntimeError(f"No one-second panels in {OUT / kind}; run scripts.extract_fomc_book_seconds first")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml")
    parser.add_argument("--placebos", default="fomc_placebos_2015_2023.yaml")
    args = parser.parse_args()
    n_fomc = extract(meeting_windows(args.config), "fomc")
    n_control = extract(control_windows(args.placebos), "control")
    print(f"\nOne-second panels: {n_fomc} FOMC meetings, {n_control} control days in {OUT}")


if __name__ == "__main__":
    main()
