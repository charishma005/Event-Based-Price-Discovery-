"""Synthetic one-second FOMC books for the strategy tests (no real data needed).

Each event gets a jump in the first five minutes and a liquidity drop whose size
("stress") drives how much of the move continues from +5 to +20 minutes, so a
correct pipeline should find a positive stress effect.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.microstructure.tick_arrays import tick_size

PRICE = {"ES.v.0": 4000.0, "NQ.v.0": 14000.0, "ZN.v.0": 115.0}
SIZE = {"ES.v.0": 40.0, "NQ.v.0": 6.0, "ZN.v.0": 900.0}


def synthetic_book(n_dev: int = 24, n_hold: int = 10, seed: int = 0, first: int = -300, last: int = 2399):
    rng = np.random.default_rng(seed)
    dates = list(pd.date_range("2015-01-28", "2022-12-14", periods=n_dev).normalize()) + \
        list(pd.date_range("2023-02-01", "2026-06-17", periods=n_hold).normalize())
    seconds = np.arange(first, last + 1)
    frames, meetings = [], []
    for i, date in enumerate(dates):
        event = f"fomc_{date:%Y%m%d}"
        meetings.append({"meeting": event, "meeting_date": date.strftime("%Y-%m-%d"),
                         "statement_time_utc": f"{date:%Y-%m-%d}T19:00:00Z"})
        news = rng.normal()
        stress = rng.uniform(0, 1)
        for instrument in PRICE:
            tick = tick_size(instrument)
            sign = -1 if instrument == "ZN.v.0" else 1
            move = sign * news * 30e-4                                  # ~30 bp first move
            path = np.zeros(len(seconds))
            post = seconds > 0
            path[post] = move * np.minimum(seconds[post], 300) / 300
            follow = move * (2 * stress - 0.6)                         # stressed books continue, calm ones fade
            late = seconds > 300
            path[late] += follow * np.minimum(seconds[late] - 300, 900) / 900
            path += np.cumsum(rng.normal(0, 0.3e-4, len(seconds)))
            mid = PRICE[instrument] * np.exp(path)
            depth_factor = np.where(seconds < 0, 1.0, np.where(seconds <= 300, 1 - 0.8 * stress, 1.0))
            depth_factor = depth_factor * (1 + 0.1 * rng.normal(size=len(seconds))).clip(0.2)
            spread_ticks = np.where((seconds >= 0) & (seconds <= 300), 1 + np.round(3 * stress), 1)
            half = spread_ticks * tick / 2
            bid = np.floor((mid - half) / tick) * tick
            ask = bid + spread_ticks * tick
            frames.append(pd.DataFrame({
                "kind": "fomc", "id": event, "instrument": instrument, "second": seconds.astype(np.int32),
                "bid": bid, "ask": ask,
                "bid_size": np.maximum(1, np.round(SIZE[instrument] * depth_factor * rng.uniform(0.7, 1.3, len(seconds)))),
                "ask_size": np.maximum(1, np.round(SIZE[instrument] * depth_factor * rng.uniform(0.7, 1.3, len(seconds)))),
            }))
    return pd.concat(frames, ignore_index=True), pd.DataFrame(meetings)
