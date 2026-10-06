"""Event-level measurements built on the attributed midpoint path.

One pass over a raw window yields, for every instrument and event clock:

* ``event_measures``: the legacy first-quote facts, fixed-clock quote/trade
  components, first-passage (clock-free) components and arrival-anchored
  short-horizon components;
* ``liquidity_measures``: elapsed-time-weighted depth and spread windows;
* ``second_panel`` / ``fine_panel``: cumulative state at regular boundaries, so
  later analyses never need to re-read the raw ticks.

Window conventions follow ``quote_revision``: the pre-event state is the last
state strictly before the event clock; a horizon endpoint is the last state at
or before it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.microstructure.quote_revision import (
    GAP, NS, QUOTE, TRADE, MidpointPath, bounded_share, components, first_passage,
    initial_sequence, state_at, trade_flow,
)

FIXED_WINDOWS = (
    ("50ms", 0.05), ("100ms", 0.1), ("250ms", 0.25), ("500ms", 0.5), ("1s", 1.0), ("2s", 2.0),
    ("5s", 5.0), ("10s", 10.0), ("30s", 30.0), ("60s", 60.0), ("300s", 300.0),
)
PASSAGE_FRACTIONS = (0.10, 0.25, 0.50, 0.75, 0.90)
REFERENCE_HORIZONS = (60.0, 300.0)
ARRIVAL_WINDOWS = (("0ms", 0.0), ("50ms", 0.05), ("100ms", 0.1), ("250ms", 0.25),
                   ("500ms", 0.5), ("1s", 1.0))
ARRIVAL_SEARCH_SECONDS = 10.0
BURST_SECONDS = 0.1
LIQUIDITY_WINDOWS = (
    ("baseline", -240.0, -60.0), ("pre60", -60.0, 0.0), ("pre10", -10.0, 0.0),
    ("pre1", -1.0, 0.0), ("post5", 0.0, 5.0), ("post60", 0.0, 60.0),
    ("post60_300", 60.0, 300.0), ("late", 240.0, 300.0),
)


def _ns(seconds: float) -> int:
    return int(round(seconds * NS))


@dataclass
class BookIntegrals:
    """Running time integrals of the displayed book (zero weight while invalid)."""
    ts: np.ndarray
    last_valid: np.ndarray
    values: dict[str, np.ndarray]
    cumulative: dict[str, np.ndarray]

    def at(self, name: str, t_ns: np.ndarray) -> np.ndarray:
        t_ns = np.asarray(t_ns, dtype=np.int64)
        position = np.searchsorted(self.ts, t_ns, side="right") - 1
        safe = np.maximum(position, 0)
        elapsed = (t_ns - self.ts[safe]) / NS
        return np.where(position >= 0, self.cumulative[name][safe] + elapsed * self.values[name][safe], 0.0)


def book_integrals(path: MidpointPath) -> BookIntegrals:
    valid = path.book_valid.astype(float)
    spread_ticks = np.where(path.book_valid, (path.book_ask - path.book_bid) / path.tick, 0.0)
    values = {
        "valid": valid,
        "depth": valid * (path.book_bid_size + path.book_ask_size),
        "bid_size": valid * path.book_bid_size,
        "ask_size": valid * path.book_ask_size,
        "spread_ticks": spread_ticks,
        "one_tick": valid * (np.abs(spread_ticks - 1.0) < 1e-6),
    }
    seconds = np.diff(path.book_ts) / NS if path.book_ts.size > 1 else np.zeros(0)
    cumulative = {
        name: np.concatenate(([0.0], np.cumsum(seconds * series[:-1]))) if series.size else np.zeros(0)
        for name, series in values.items()
    }
    position = np.arange(path.book_ts.shape[0])
    last_valid = np.maximum.accumulate(np.where(path.book_valid, position, -1))
    return BookIntegrals(path.book_ts, last_valid, values, cumulative)


def time_weighted(integrals: BookIntegrals, start_ns: int, end_ns: int) -> dict[str, float]:
    """Elapsed-time-weighted means over ``[start_ns, end_ns)``; invalid time carries no weight."""
    if integrals.ts.size == 0:
        return {"coverage": 0.0, "depth": np.nan, "bid_size": np.nan, "ask_size": np.nan,
                "spread_ticks": np.nan, "one_tick_share": np.nan}
    edges = np.array([start_ns, end_ns], dtype=np.int64)
    span = {name: float(np.diff(integrals.at(name, edges))[0]) for name in integrals.values}
    valid_seconds = span["valid"]
    out = {"coverage": valid_seconds / ((end_ns - start_ns) / NS)}
    for name, label in (("depth", "depth"), ("bid_size", "bid_size"), ("ask_size", "ask_size"),
                        ("spread_ticks", "spread_ticks"), ("one_tick", "one_tick_share")):
        out[label] = span[name] / valid_seconds if valid_seconds > 0 else np.nan
    return out


def liquidity_measures(path: MidpointPath, event_ns: int, integrals: BookIntegrals | None = None) -> dict[str, float]:
    integrals = integrals or book_integrals(path)
    out: dict[str, float] = {}
    for label, start, end in LIQUIDITY_WINDOWS:
        covered = path.first_ts <= event_ns + _ns(start) and path.last_ts >= event_ns + _ns(end)
        stats = time_weighted(integrals, event_ns + _ns(start), event_ns + _ns(end))
        for key, value in stats.items():
            out[f"{label}_{key}"] = value if covered else np.nan
        out[f"{label}_covered"] = bool(covered)
    base = out["baseline_depth"]
    for label in ("pre60", "pre10", "pre1", "post5", "post60", "late"):
        out[f"{label}_depth_ratio"] = out[f"{label}_depth"] / base if base and np.isfinite(base) else np.nan
        out[f"{label}_spread_change_ticks"] = out[f"{label}_spread_ticks"] - out["baseline_spread_ticks"]
    # Legacy message-weighted ratio (mean over valid quote records), kept for comparison.
    seconds = (path.book_ts - event_ns) / NS
    depth = (path.book_bid_size + path.book_ask_size).astype(float)
    base_rows = path.book_valid & (seconds >= -600) & (seconds < -60)
    pre_rows = path.book_valid & (seconds >= -60) & (seconds < 0)
    out["legacy_message_depth_ratio"] = (
        float(depth[pre_rows].mean() / depth[base_rows].mean())
        if base_rows.any() and pre_rows.any() and depth[base_rows].mean() > 0 else np.nan
    )
    out["pre60_book_updates"] = int(((seconds >= -60) & (seconds < 0)).sum())
    out["baseline_book_updates"] = int(((seconds >= -240) & (seconds < -60)).sum())
    return out


def _largest_burst(path: MidpointPath, start_ns: int, end_ns: int, burst_ns: int) -> tuple[int | None, float]:
    """Start time of the ``burst_ns`` window with the largest absolute net midpoint change."""
    lo = int(np.searchsorted(path.change_ts, start_ns, side="left"))
    hi = int(np.searchsorted(path.change_ts, end_ns, side="right"))
    if hi <= lo:
        return None, np.nan
    total = path.cum_bp.sum(axis=1)
    starts = path.change_ts[lo:hi]
    stop = np.searchsorted(path.change_ts, starts + burst_ns, side="right")
    net = total[stop] - total[lo:hi]
    k = int(np.argmax(np.abs(net)))
    return int(starts[k]), float(net[k])


def _largest_single_event(path: MidpointPath, start_ns: int, end_ns: int) -> dict[str, float]:
    """Largest midpoint move carried by one exchange timestamp (one matching-engine event)."""
    lo = int(np.searchsorted(path.change_ts, start_ns, side="left"))
    hi = int(np.searchsorted(path.change_ts, end_ns, side="right"))
    out = {"seconds": np.nan, "bp": np.nan, "trade_share": np.nan}
    if hi <= lo:
        return out
    ts, change, attr = path.change_ts[lo:hi], path.change_bp[lo:hi], path.change_attr[lo:hi]
    boundaries = np.flatnonzero(np.diff(ts) != 0) + 1
    groups = np.concatenate(([0], boundaries))
    net = np.add.reduceat(change, groups)
    trade = np.add.reduceat(np.where(attr == TRADE, change, 0.0), groups)
    k = int(np.argmax(np.abs(net)))
    out["seconds"] = float((ts[groups[k]] - start_ns) / NS)
    out["bp"] = float(net[k])
    out["trade_share"] = float(trade[k] / net[k]) if abs(net[k]) > 1e-12 else np.nan
    return out


def _store(out: dict[str, object], prefix: str, parts: dict[str, float]) -> None:
    out[f"{prefix}_total_bp"] = parts["total_bp"]
    out[f"{prefix}_quote_bp"] = parts["quote_bp"]
    out[f"{prefix}_trade_bp"] = parts["trade_bp"]
    out[f"{prefix}_gap_bp"] = parts["gap_bp"]
    out[f"{prefix}_quote_share"] = bounded_share(parts["quote_bp"], parts["trade_bp"])


def event_measures(
    path: MidpointPath, event_ns: int, alt_path: MidpointPath | None = None
) -> dict[str, object]:
    """All tick-level Q1 measurements for one instrument at one event clock.

    ``alt_path`` is the same stream attributed with the 100-microsecond
    tolerance regardless of feed format. When given, the primary and the key
    secondary window are also reported under that rule as a sensitivity check.
    """
    out: dict[str, object] = {
        "timestamp_resolution_ns": path.timestamp_resolution_ns,
        "same_timestamp_share": path.same_timestamp_share,
        "attribution_tolerance_ns": path.tolerance_ns,
        "pre_seconds_available": (event_ns - path.first_ts) / NS,
        "post_seconds_available": (path.last_ts - event_ns) / NS,
    }
    out.update(initial_sequence(path, event_ns))
    pre = state_at(path, event_ns, strictly_before=True)
    out["pre_logmid"] = pre["logmid"]
    out["pre_spread_ticks"] = (pre["ask"] - pre["bid"]) / path.tick if pre["has_state"] else np.nan
    out["pre_bid_size"], out["pre_ask_size"] = pre["bid_size"], pre["ask_size"]

    # Fixed windows on the scheduled clock.
    for label, seconds in FIXED_WINDOWS:
        end_ns = event_ns + _ns(seconds)
        covered = path.last_ts >= end_ns
        parts = components(path, event_ns, end_ns)
        flow = trade_flow(path, event_ns, end_ns)
        endpoint = state_at(path, end_ns)
        prefix = f"w{label}"
        if covered:
            _store(out, prefix, parts)
            out[f"{prefix}_abs_quote_bp"] = parts["abs_quote_bp"]
            out[f"{prefix}_abs_trade_bp"] = parts["abs_trade_bp"]
            for key, value in flow.items():
                out[f"{prefix}_{key}"] = value
        else:
            for suffix in ("total_bp", "quote_bp", "trade_bp", "gap_bp", "quote_share",
                           "abs_quote_bp", "abs_trade_bp", *flow.keys()):
                out[f"{prefix}_{suffix}"] = np.nan
        out[f"{prefix}_covered"] = bool(covered)
        out[f"{prefix}_endpoint_valid"] = bool(endpoint["state_valid"]) and covered

    # Clock-free first-passage components, relative to the 60 s and 300 s move.
    for reference in REFERENCE_HORIZONS:
        ref_label = f"{int(reference)}s"
        target = out[f"w{ref_label}_total_bp"]
        passage = first_passage(path, event_ns, event_ns + _ns(reference), target, PASSAGE_FRACTIONS)
        for fraction, values in passage.items():
            prefix = f"fp{ref_label}_{int(round(fraction * 100))}"
            out[f"{prefix}_seconds"] = values["seconds"]
            _store(out, prefix, values)
            out[f"{prefix}_crossing_attr"] = values["crossing_attr"]
            out[f"{prefix}_crossing_bp"] = values["crossing_bp"]

    # Arrival-anchored short horizons. Two anchors, both fixed before any outcome is examined:
    #   fp25  - the update that first carries the midpoint past 25% of its 300 s move;
    #   burst - the start of the 100 ms window with the largest absolute net move in the first 10 s.
    anchors: dict[str, int | None] = {}
    seconds_25 = out["fp300s_25_seconds"]
    anchors["fp25"] = None if not np.isfinite(seconds_25) else event_ns + _ns(float(seconds_25))
    burst_start, burst_bp = _largest_burst(
        path, event_ns, event_ns + _ns(ARRIVAL_SEARCH_SECONDS), _ns(BURST_SECONDS)
    )
    anchors["burst"] = burst_start
    out["burst_bp"] = burst_bp
    # The same search over the ten seconds before the scheduled clock: a within-window placebo.
    _, out["pre_burst_bp"] = _largest_burst(
        path, event_ns - _ns(ARRIVAL_SEARCH_SECONDS), event_ns - 1 - _ns(BURST_SECONDS), _ns(BURST_SECONDS)
    )
    for name, anchor in anchors.items():
        out[f"arr_{name}_seconds"] = np.nan if anchor is None else (anchor - event_ns) / NS
        for label, seconds in ARRIVAL_WINDOWS:
            prefix = f"arr_{name}_{label}"
            if anchor is None or path.last_ts < anchor + _ns(seconds):
                for suffix in ("total_bp", "quote_bp", "trade_bp", "gap_bp", "quote_share",
                               "trade_count", "volume", "signed_volume", "unknown_volume"):
                    out[f"{prefix}_{suffix}"] = np.nan
                continue
            _store(out, prefix, components(path, anchor, anchor + _ns(seconds)))
            flow = trade_flow(path, anchor, anchor + _ns(seconds))
            out[f"{prefix}_trade_count"] = flow["trade_count"]
            out[f"{prefix}_volume"] = flow["buy_volume"] + flow["sell_volume"] + flow["unknown_volume"]
            out[f"{prefix}_signed_volume"] = flow["signed_volume"]
            out[f"{prefix}_unknown_volume"] = flow["unknown_volume"]
        if anchor is not None:
            # What had already happened between the scheduled second and the anchor.
            before = components(path, event_ns, anchor - 1)
            out[f"arr_{name}_prior_total_bp"] = before["total_bp"]
            out[f"arr_{name}_prior_trade_count"] = trade_flow(path, event_ns, anchor - 1)["trade_count"]
        else:
            out[f"arr_{name}_prior_total_bp"] = np.nan
            out[f"arr_{name}_prior_trade_count"] = np.nan

    if alt_path is not None:
        if burst_start is not None and alt_path.last_ts >= burst_start + _ns(BURST_SECONDS):
            _store(out, "alt_arr_burst_100ms",
                   components(alt_path, burst_start, burst_start + _ns(BURST_SECONDS)))
        target = out["w300s_total_bp"]
        alternative = first_passage(alt_path, event_ns, event_ns + _ns(300.0), target, (0.50,))[0.50]
        _store(out, "alt_fp300s_50", alternative)

    single = _largest_single_event(path, event_ns, event_ns + _ns(ARRIVAL_SEARCH_SECONDS))
    out["max_event_seconds"], out["max_event_bp"] = single["seconds"], single["bp"]
    out["max_event_trade_share"] = single["trade_share"]
    return out


def second_panel(
    path: MidpointPath, anchor_ns: int, start_seconds: int, end_seconds: int,
    integrals: BookIntegrals | None = None, step_seconds: float = 1.0,
) -> pd.DataFrame:
    """Cumulative state at regular boundaries (last state at or before each boundary)."""
    integrals = integrals or book_integrals(path)
    count = int(round((end_seconds - start_seconds) / step_seconds)) + 1
    seconds = start_seconds + step_seconds * np.arange(count)
    boundary = anchor_ns + np.round(seconds * NS).astype(np.int64)
    inside = (boundary >= path.first_ts) & (boundary <= path.last_ts)
    position = np.searchsorted(path.book_ts, boundary, side="right") - 1
    has_state = position >= 0
    safe = np.maximum(position, 0)
    state_valid = has_state & path.book_valid[safe] if path.book_ts.size else np.zeros(count, bool)
    last_valid = integrals.last_valid[safe] if path.book_ts.size else np.full(count, -1)
    logmid = np.where(has_state & (last_valid >= 0), path.book_logmid[np.maximum(last_valid, 0)], np.nan)
    changes = np.searchsorted(path.change_ts, boundary, side="right")
    trades = np.searchsorted(path.trade_ts, boundary, side="right")
    frame = pd.DataFrame({
        "seconds": seconds,
        "inside_window": inside,
        "state_valid": state_valid,
        "logmid": logmid,
        "bid": np.where(has_state, path.book_bid[safe], np.nan),
        "ask": np.where(has_state, path.book_ask[safe], np.nan),
        "bid_size": np.where(has_state, path.book_bid_size[safe], np.nan),
        "ask_size": np.where(has_state, path.book_ask_size[safe], np.nan),
        "cum_quote_bp": path.cum_bp[changes, QUOTE],
        "cum_trade_bp": path.cum_bp[changes, TRADE],
        "cum_gap_bp": path.cum_bp[changes, GAP],
        "cum_abs_quote_bp": path.cum_abs_bp[changes, QUOTE],
        "cum_abs_trade_bp": path.cum_abs_bp[changes, TRADE],
        "cum_trades": trades,
        "cum_buy_volume": path.cum_trade_volume[trades, 0],
        "cum_sell_volume": path.cum_trade_volume[trades, 1],
        "cum_unknown_volume": path.cum_trade_volume[trades, 2],
        "cum_book_updates": position + 1,
    })
    for name in ("valid", "depth", "bid_size", "ask_size", "spread_ticks", "one_tick"):
        frame[f"int_{name}"] = integrals.at(name, boundary) if path.book_ts.size else 0.0
    return frame


def fine_panel(path: MidpointPath, event_ns: int, start_seconds: float = -1.0,
               end_seconds: float = 10.0, step_seconds: float = 0.02) -> pd.DataFrame:
    """Sub-second cumulative path around one event clock, for figures."""
    frame = second_panel(path, event_ns, start_seconds, end_seconds, step_seconds=step_seconds)
    keep = ["seconds", "inside_window", "state_valid", "logmid", "cum_quote_bp", "cum_trade_bp",
            "cum_gap_bp", "cum_trades", "cum_buy_volume", "cum_sell_volume", "cum_unknown_volume",
            "bid_size", "ask_size", "bid", "ask"]
    return frame[keep]
