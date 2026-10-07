"""Decision-time features from the one-second FOMC book (no look-ahead by construction).

Input: one-second panels from ``scripts/extract_fomc_book_seconds.py`` with
columns id, instrument, second, bid, ask, bid_size, ask_size. Second s holds the
last valid quote at or before statement + s seconds, so second 0 is the book in
force at 2:00:00.000 (before the news).

Every feature function takes an explicit ``as_of`` second and is passed only the
rows with second <= as_of, so nothing after the decision time can enter.

Conventions
- Returns: 10,000 x ln(mid_b / mid_a) in bp.
- Liquidity at horizon h: mean over the trailing 30 seconds (h-30, h], divided by
  the H4 baseline, the mean over seconds -240 to -61 (the same window as
  ``src.microstructure.event_features.LIQUIDITY_WINDOWS``, "baseline").
- Depth = bid size + ask size at the touch; spread in ticks; imbalance =
  (bid - ask) / (bid + ask).
- depth_recovery_1_5 = depth_ratio_5m - depth_ratio_1m (positive = replenishment);
  spread_recovery_1_5 = spread_ratio_1m - spread_ratio_5m (positive = narrowing).
- Recovery slopes: least-squares slope of the per-second ratio on minutes over
  seconds 60..300 (depth: up = replenishing; spread slope is sign-flipped so up =
  narrowing).
Targets and execution prices are kept in separate columns (TARGET_COLUMNS,
EXECUTION_COLUMNS) and never enter FEATURE_COLUMNS.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.microstructure.tick_arrays import tick_size

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
BASELINE = (-240, -61)          # seconds, inclusive; H4 baseline window
TRAIL = 30                      # seconds in each trailing liquidity window
DECISION = 300                  # primary decision time (+5:00)
ZN_DECISION = 600               # ZN-specific secondary decision time (+10:00)
LATENCY = 1                     # entry fills at the book one second after the decision
EXITS = {"10m": 600, "20m": 1200, "30m": 1800}
HOLDOUT_START = pd.Timestamp("2023-01-01")

RETURN_HORIZONS = {"30s": 30, "1m": 60, "3m": 180, "5m": 300}
DEPTH_HORIZONS = {"30s": 30, "1m": 60, "3m": 180, "5m": 300}
SIDE_HORIZONS = {"1m": 60, "3m": 180, "5m": 300}

FEATURE_COLUMNS = (
    [f"ret_0_{k}" for k in RETURN_HORIZONS] + [f"abs_ret_0_{k}" for k in RETURN_HORIZONS]
    + [f"depth_ratio_{k}" for k in DEPTH_HORIZONS]
    + [f"bid_depth_ratio_{k}" for k in SIDE_HORIZONS] + [f"ask_depth_ratio_{k}" for k in SIDE_HORIZONS]
    + [f"spread_ratio_{k}" for k in DEPTH_HORIZONS] + [f"book_imbalance_{k}" for k in SIDE_HORIZONS]
    + ["depth_recovery_1_5", "spread_recovery_1_5", "depth_recovery_slope_1_5", "spread_recovery_slope_1_5",
       "baseline_depth", "baseline_spread_ticks"]
)
ZN10_FEATURE_COLUMNS = ["depth_ratio_10m", "spread_ratio_10m", "depth_recovery_1_10", "spread_recovery_1_10"]
TARGET_COLUMNS = ["ret_5_10m", "ret_5_20m", "ret_5_30m", "ret_10_20m",
                  "continuation_5_10", "continuation_5_20", "continuation_5_30", "continuation_10_20"]
EXECUTION_COLUMNS = [f"{side}_{t}" for t in ("entry5", "entry10", "exit10m", "exit20m", "exit30m")
                     for side in ("bid", "ask", "mid")]


def prepare(book: pd.DataFrame) -> pd.DataFrame:
    """Add mid, depth, spread in ticks and imbalance; drop rows without a valid two-sided book."""
    data = book.loc[book["bid"].gt(0) & book["ask"].gt(book["bid"])].copy()
    tick = data["instrument"].map(tick_size)
    data["mid"] = (data["bid"] + data["ask"]) / 2
    data["depth"] = data["bid_size"] + data["ask_size"]
    data["spread_ticks"] = (data["ask"] - data["bid"]) / tick
    data["imbalance"] = (data["bid_size"] - data["ask_size"]) / data["depth"].where(data["depth"] > 0)
    return data.sort_values(["id", "instrument", "second"]).reset_index(drop=True)


def _at(g: pd.DataFrame, second: int, column: str) -> float:
    row = g.loc[g["second"].eq(second), column]
    return float(row.iloc[0]) if len(row) else np.nan


def _mean(g: pd.DataFrame, start: int, end: int, column: str) -> float:
    values = g.loc[g["second"].between(start, end), column]
    return float(values.mean()) if values.notna().any() else np.nan


def _ret(a: float, b: float) -> float:
    return float(1e4 * np.log(b / a)) if a > 0 and b > 0 else np.nan


def _slope(g: pd.DataFrame, column: str, base: float, start: int = 60, end: int = 300) -> float:
    window = g.loc[g["second"].between(start, end), ["second", column]].dropna()
    if len(window) < 30 or not base or not np.isfinite(base):
        return np.nan
    minutes = window["second"].to_numpy(float) / 60
    return float(np.polyfit(minutes, window[column].to_numpy(float) / base, 1)[0])


def decision_features(g: pd.DataFrame, as_of: int = DECISION) -> dict[str, float]:
    """Features for one event x instrument from rows with second <= as_of only."""
    if g["second"].max() > as_of:
        raise ValueError(f"decision_features was given data after as_of={as_of}")
    out: dict[str, float] = {}
    mid0 = _at(g, 0, "mid")
    base_depth = _mean(g, *BASELINE, "depth")
    base_bid = _mean(g, *BASELINE, "bid_size")
    base_ask = _mean(g, *BASELINE, "ask_size")
    base_spread = _mean(g, *BASELINE, "spread_ticks")
    out["baseline_depth"], out["baseline_spread_ticks"] = base_depth, base_spread

    def ratio(column, h, base):
        value = _mean(g, h - TRAIL + 1, h, column)
        return value / base if base and np.isfinite(base) and base > 0 else np.nan

    for k, h in RETURN_HORIZONS.items():
        if h > as_of:
            continue
        out[f"ret_0_{k}"] = _ret(mid0, _at(g, h, "mid"))
        out[f"abs_ret_0_{k}"] = abs(out[f"ret_0_{k}"])
    for k, h in DEPTH_HORIZONS.items():
        if h > as_of:
            continue
        out[f"depth_ratio_{k}"] = ratio("depth", h, base_depth)
        out[f"spread_ratio_{k}"] = ratio("spread_ticks", h, base_spread)
    for k, h in SIDE_HORIZONS.items():
        if h > as_of:
            continue
        out[f"bid_depth_ratio_{k}"] = ratio("bid_size", h, base_bid)
        out[f"ask_depth_ratio_{k}"] = ratio("ask_size", h, base_ask)
        out[f"book_imbalance_{k}"] = _mean(g, h - TRAIL + 1, h, "imbalance")
    if as_of >= 300:
        out["depth_recovery_1_5"] = out["depth_ratio_5m"] - out["depth_ratio_1m"]
        out["spread_recovery_1_5"] = out["spread_ratio_1m"] - out["spread_ratio_5m"]
        out["depth_recovery_slope_1_5"] = _slope(g, "depth", base_depth)
        slope = _slope(g, "spread_ticks", base_spread)
        out["spread_recovery_slope_1_5"] = -slope if np.isfinite(slope) else np.nan
    if as_of >= 600:
        out["depth_ratio_10m"] = ratio("depth", 600, base_depth)
        out["spread_ratio_10m"] = ratio("spread_ticks", 600, base_spread)
        out["depth_recovery_1_10"] = out["depth_ratio_10m"] - out["depth_ratio_1m"]
        out["spread_recovery_1_10"] = out["spread_ratio_1m"] - out["spread_ratio_10m"]
    return out


def targets_and_execution(g: pd.DataFrame) -> dict[str, float]:
    """Future returns (targets) and executable quotes. Never used as features."""
    out: dict[str, float] = {}
    for name, second in (("entry5", DECISION + LATENCY), ("entry10", ZN_DECISION + LATENCY),
                         *((f"exit{k}", s) for k, s in EXITS.items())):
        for side in ("bid", "ask", "mid"):
            out[f"{side}_{name}"] = _at(g, second, side)
    m5, m10 = _at(g, DECISION, "mid"), _at(g, ZN_DECISION, "mid")
    for k, s in EXITS.items():
        out[f"ret_5_{k}"] = _ret(m5, _at(g, s, "mid"))
    out["ret_10_20m"] = _ret(m10, _at(g, EXITS["20m"], "mid"))
    return out


def build_event_features(book: pd.DataFrame, meetings: pd.DataFrame) -> pd.DataFrame:
    """One row per FOMC event x instrument: identifiers, features, targets, execution quotes.

    ``meetings`` needs columns meeting, meeting_date, statement_time_utc.
    """
    data = prepare(book)
    info = meetings.set_index("meeting")
    rows = []
    for (event, instrument), g in data.groupby(["id", "instrument"], sort=True):
        if event not in info.index:
            continue
        row = {"event_id": event, "event_date": pd.Timestamp(info.loc[event, "meeting_date"]),
               "instrument": instrument, "statement_timestamp": info.loc[event, "statement_time_utc"]}
        row.update(decision_features(g.loc[g["second"].le(DECISION)], DECISION))
        if instrument == "ZN.v.0":
            zn = decision_features(g.loc[g["second"].le(ZN_DECISION)], ZN_DECISION)
            row.update({k: zn[k] for k in ZN10_FEATURE_COLUMNS})
        row.update(targets_and_execution(g))
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["sample"] = np.where(frame["event_date"] < HOLDOUT_START, "development", "holdout")
    direction = np.sign(frame["ret_0_5m"])
    for k in EXITS:
        frame[f"continuation_5_{k[:-1]}"] = direction * frame[f"ret_5_{k}"]
    frame["continuation_10_20"] = direction * frame["ret_10_20m"]
    return frame


def minute_paths(book: pd.DataFrame) -> pd.DataFrame:
    """Per-minute depth and spread ratios (H4 baseline), -5..+39 min, for figures only."""
    data = prepare(book)
    data["minute"] = np.floor(data["second"] / 60).astype(int)
    base = (
        data.loc[data["second"].between(*BASELINE)].groupby(["id", "instrument"])[["depth", "spread_ticks"]].mean()
        .rename(columns={"depth": "base_depth", "spread_ticks": "base_spread"})
    )
    minute = data.groupby(["id", "instrument", "minute"])[["depth", "spread_ticks"]].mean().reset_index()
    minute = minute.join(base, on=["id", "instrument"])
    minute["depth_ratio"] = minute["depth"] / minute["base_depth"]
    minute["spread_ratio"] = minute["spread_ticks"] / minute["base_spread"]
    return minute[["id", "instrument", "minute", "depth_ratio", "spread_ratio"]]


def second_level_panel(book: pd.DataFrame, lookbacks=(5, 10, 30, 60), leads=(5, 30, 60),
                       start: int = 60, end: int = 1740) -> pd.DataFrame:
    """Per-second microstructure features (past only) and future returns (targets), seconds start..end.

    Features at second t use seconds <= t; targets fut_ret_{L}s use t..t+L. ``end`` + 60 <= 1800 keeps
    every target before the press conference.
    """
    data = prepare(book)
    frames = []
    for (event, instrument), g in data.groupby(["id", "instrument"]):
        g = g.set_index("second").reindex(range(int(g["second"].min()), int(g["second"].max()) + 1)).ffill()
        base_depth = g.loc[BASELINE[0]:BASELINE[1], "depth"].mean()
        base_bid = g.loc[BASELINE[0]:BASELINE[1], "bid_size"].mean()
        base_ask = g.loc[BASELINE[0]:BASELINE[1], "ask_size"].mean()
        frame = pd.DataFrame(index=g.index)
        frame["depth"] = g["depth"] / base_depth
        frame["bid_depth"] = g["bid_size"] / base_bid
        frame["ask_depth"] = g["ask_size"] / base_ask
        frame["imbalance"] = g["imbalance"]
        frame["spread"] = g["spread_ticks"]
        logmid = np.log(g["mid"])
        for k in lookbacks:
            for col in ("depth", "bid_depth", "ask_depth", "imbalance", "spread"):
                frame[f"d_{col}_{k}s"] = frame[col] - frame[col].shift(k)
            frame[f"past_ret_{k}s"] = 1e4 * (logmid - logmid.shift(k))
        for lead in leads:
            frame[f"fut_ret_{lead}s"] = 1e4 * (logmid.shift(-lead) - logmid)
        frame = frame.loc[start:end].reset_index().rename(columns={"index": "second"})
        frame.insert(0, "instrument", instrument)
        frame.insert(0, "event_id", event)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
