"""Tick-level split of a midpoint path into quote-driven and trade-driven moves.

The proposal's first-quote statistic asks whether the very first book record
after the scheduled second moved the midpoint. In practice that record is
almost always a depth-only update, so the statistic is zero for every event
type. This module keeps the same economic question (did the price move because
liquidity providers revised their quotes, or because aggressive orders traded
through them?) but answers it for every midpoint change, so that the answer
can be summed over any window.

Attribution rule (fixed in ``config/q1_short_horizon_prereg.yaml``):

A book update is *trade-attributed* when it belongs to a trade's own book
effect, and *quote-attributed* otherwise. Operationally, let ``T`` be the most
recent trade record that precedes the update in feed order for the same
instrument. The update is trade-attributed if

* it carries the same exchange timestamp as ``T`` (one matching-engine event), or
* it is the first book update after ``T`` and its exchange timestamp is no more
  than the tolerance later.

The tolerance is chosen per instrument-window from the feed format alone, never
from prices. Since mid-2017 (and in the millisecond-stamped 2015 history) a
trade and its book effect carry the same timestamp, so the tolerance is zero.
From December 2015 to May 2017 the two were stamped about 15-40 microseconds
apart; there the tolerance is ``SAME_EVENT_TOLERANCE_NS``. The format is
detected as the share of trades whose first following book update carries the
same timestamp (``same_timestamp_share``; at least 0.5 means same-stamped).

A midpoint change across an invalid (locked, crossed or one-sided) book is
assigned to neither side; it is reported separately as the ``gap`` component.

Nothing here identifies a causal share of public versus private information.
The split is an accounting of how the displayed midpoint moved.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.microstructure.tick_arrays import InstrumentTicks

QUOTE, TRADE, GAP = 0, 1, 2
SAME_EVENT_TOLERANCE_NS = 100_000
SAME_STAMP_THRESHOLD = 0.5
NS = 1_000_000_000


@dataclass
class MidpointPath:
    symbol: str
    tick: float
    timestamp_resolution_ns: int
    same_timestamp_share: float
    tolerance_ns: int
    first_ts: int
    last_ts: int
    # Book-state rows in feed order.
    book_ts: np.ndarray
    book_valid: np.ndarray
    book_logmid: np.ndarray
    book_bid: np.ndarray
    book_ask: np.ndarray
    book_bid_size: np.ndarray
    book_ask_size: np.ndarray
    book_trade_attributed: np.ndarray
    book_stream_index: np.ndarray
    # One row per valid book state that has an earlier valid state.
    change_ts: np.ndarray
    change_bp: np.ndarray
    change_attr: np.ndarray
    change_stream_index: np.ndarray
    cum_bp: np.ndarray        # shape (n_changes + 1, 3): running sum per attribution
    cum_abs_bp: np.ndarray    # same, for absolute changes
    # Trades in feed order.
    trade_ts: np.ndarray
    trade_side: np.ndarray
    trade_size: np.ndarray
    trade_price: np.ndarray
    trade_stream_index: np.ndarray
    cum_trade_volume: np.ndarray   # shape (n_trades + 1, 3): buy, sell, unknown


def trade_attribution(
    ts: np.ndarray,
    is_trade: np.ndarray,
    is_book: np.ndarray,
    tolerance_ns: int = SAME_EVENT_TOLERANCE_NS,
) -> np.ndarray:
    """Boolean per stream record: True for book updates that belong to a trade."""
    n = ts.shape[0]
    index = np.arange(n)
    last_trade = np.maximum.accumulate(np.where(is_trade, index, -1))
    last_book = np.maximum.accumulate(np.where(is_book, index, -1))
    previous_book = np.concatenate(([-1], last_book[:-1]))
    has_trade = last_trade >= 0
    trade_time = ts[np.maximum(last_trade, 0)]
    same_timestamp = has_trade & (ts == trade_time)
    first_after_trade = has_trade & (last_trade > previous_book)
    close = (ts - trade_time) <= tolerance_ns
    return is_book & (same_timestamp | (first_after_trade & close))


def same_timestamp_share(ts: np.ndarray, is_trade: np.ndarray, is_book: np.ndarray) -> float:
    """Share of trades whose first following book update carries the trade's own timestamp."""
    n = ts.shape[0]
    index = np.arange(n)
    last_trade = np.maximum.accumulate(np.where(is_trade, index, -1))
    last_book = np.maximum.accumulate(np.where(is_book, index, -1))
    previous_book = np.concatenate(([-1], last_book[:-1]))
    first_after_trade = is_book & (last_trade >= 0) & (last_trade > previous_book)
    if not first_after_trade.any():
        return float("nan")
    return float((ts[first_after_trade] == ts[last_trade[first_after_trade]]).mean())


def build_midpoint_path(ticks: InstrumentTicks, tolerance_ns: int | None = None) -> MidpointPath:
    """Attribute every midpoint change. ``tolerance_ns=None`` picks it from the feed format."""
    share = same_timestamp_share(ticks.ts, ticks.is_trade, ticks.is_book)
    if tolerance_ns is None:
        separately_stamped = np.isfinite(share) and share < SAME_STAMP_THRESHOLD
        tolerance_ns = SAME_EVENT_TOLERANCE_NS if separately_stamped else 0
    attributed = trade_attribution(ticks.ts, ticks.is_trade, ticks.is_book, tolerance_ns)
    book = np.flatnonzero(ticks.is_book)
    valid = ticks.book_valid[book]
    with np.errstate(invalid="ignore", divide="ignore"):
        logmid = np.where(valid, np.log((ticks.bid[book] + ticks.ask[book]) / 2), np.nan)

    position = np.arange(book.shape[0])
    last_valid = np.maximum.accumulate(np.where(valid, position, -1))
    previous_valid = np.concatenate(([-1], last_valid[:-1]))
    rows = np.flatnonzero(valid & (previous_valid >= 0))
    before = previous_valid[rows]
    change = 1e4 * (logmid[rows] - logmid[before])
    attr = np.where(attributed[book][rows], TRADE, QUOTE).astype(np.int8)
    attr[before != rows - 1] = GAP   # an invalid state lies between the two quotes

    cum = np.zeros((rows.shape[0] + 1, 3))
    cum_abs = np.zeros((rows.shape[0] + 1, 3))
    for kind in (QUOTE, TRADE, GAP):
        values = np.where(attr == kind, change, 0.0)
        cum[1:, kind] = np.cumsum(values)
        cum_abs[1:, kind] = np.cumsum(np.abs(values))

    trades = np.flatnonzero(ticks.is_trade)
    side = ticks.side[trades]
    size = ticks.size[trades].astype(np.float64)
    cum_volume = np.zeros((trades.shape[0] + 1, 3))
    cum_volume[1:, 0] = np.cumsum(np.where(side > 0, size, 0.0))
    cum_volume[1:, 1] = np.cumsum(np.where(side < 0, size, 0.0))
    cum_volume[1:, 2] = np.cumsum(np.where(side == 0, size, 0.0))
    return MidpointPath(
        symbol=ticks.symbol,
        tick=ticks.tick,
        timestamp_resolution_ns=ticks.timestamp_resolution_ns,
        same_timestamp_share=share,
        tolerance_ns=int(tolerance_ns),
        first_ts=int(ticks.ts[0]) if len(ticks) else 0,
        last_ts=int(ticks.ts[-1]) if len(ticks) else 0,
        book_ts=ticks.ts[book],
        book_valid=valid,
        book_logmid=logmid,
        book_bid=ticks.bid[book],
        book_ask=ticks.ask[book],
        book_bid_size=ticks.bid_size[book],
        book_ask_size=ticks.ask_size[book],
        book_trade_attributed=attributed[book],
        book_stream_index=book,
        change_ts=ticks.ts[book][rows],
        change_bp=change,
        change_attr=attr,
        change_stream_index=book[rows],
        cum_bp=cum,
        cum_abs_bp=cum_abs,
        trade_ts=ticks.ts[trades],
        trade_side=side,
        trade_size=size,
        trade_price=ticks.price[trades],
        trade_stream_index=trades,
        cum_trade_volume=cum_volume,
    )


def _book_position(path: MidpointPath, t_ns: int, *, strictly_before: bool) -> int:
    side = "left" if strictly_before else "right"
    return int(np.searchsorted(path.book_ts, t_ns, side=side)) - 1


def state_at(path: MidpointPath, t_ns: int, *, strictly_before: bool = False) -> dict[str, float | bool]:
    """Displayed book at ``t_ns``: the current state and the last valid midpoint.

    ``state_valid`` is False when the state in force is locked, crossed or
    one-sided. ``logmid`` is then the last valid midpoint, returned so callers
    can decide whether to use or discard it; it is never silently substituted.
    """
    position = _book_position(path, t_ns, strictly_before=strictly_before)
    if position < 0:
        return {"state_valid": False, "logmid": np.nan, "bid": np.nan, "ask": np.nan,
                "bid_size": np.nan, "ask_size": np.nan, "has_state": False}
    valid = bool(path.book_valid[position])
    logmid = path.book_logmid[position]
    if not valid:
        earlier = np.flatnonzero(path.book_valid[: position + 1])
        logmid = path.book_logmid[earlier[-1]] if earlier.size else np.nan
    return {"state_valid": valid, "logmid": float(logmid),
            "bid": float(path.book_bid[position]), "ask": float(path.book_ask[position]),
            "bid_size": float(path.book_bid_size[position]),
            "ask_size": float(path.book_ask_size[position]), "has_state": True}


def components(path: MidpointPath, start_ns: int, end_ns: int) -> dict[str, float]:
    """Attributed midpoint change over the closed window ``[start_ns, end_ns]`` in bp.

    The window starts from the last state strictly before ``start_ns`` and ends
    with the last state at or before ``end_ns``.
    """
    lo = int(np.searchsorted(path.change_ts, start_ns, side="left"))
    hi = int(np.searchsorted(path.change_ts, end_ns, side="right"))
    hi = max(hi, lo)
    net = path.cum_bp[hi] - path.cum_bp[lo]
    gross = path.cum_abs_bp[hi] - path.cum_abs_bp[lo]
    return {
        "quote_bp": float(net[QUOTE]), "trade_bp": float(net[TRADE]), "gap_bp": float(net[GAP]),
        "total_bp": float(net.sum()),
        "abs_quote_bp": float(gross[QUOTE]), "abs_trade_bp": float(gross[TRADE]),
        "abs_gap_bp": float(gross[GAP]), "n_changes": hi - lo,
    }


def trade_flow(path: MidpointPath, start_ns: int, end_ns: int) -> dict[str, float]:
    """Trades with ``start_ns <= ts <= end_ns``."""
    lo = int(np.searchsorted(path.trade_ts, start_ns, side="left"))
    hi = int(np.searchsorted(path.trade_ts, end_ns, side="right"))
    hi = max(hi, lo)
    buy, sell, unknown = path.cum_trade_volume[hi] - path.cum_trade_volume[lo]
    return {"trade_count": hi - lo, "buy_volume": float(buy), "sell_volume": float(sell),
            "unknown_volume": float(unknown), "signed_volume": float(buy - sell)}


def bounded_share(quote_bp: float, trade_bp: float) -> float:
    """|QR| / (|QR| + |TR|): in [0, 1], undefined when the window has no attributed move."""
    denominator = abs(quote_bp) + abs(trade_bp)
    return float("nan") if denominator <= 1e-12 else abs(quote_bp) / denominator


def first_passage(
    path: MidpointPath, start_ns: int, end_ns: int, target_bp: float, fractions: tuple[float, ...]
) -> dict[float, dict[str, float]]:
    """First time the midpoint has covered each fraction of ``target_bp``.

    The path is measured from the last state strictly before ``start_ns``.
    Components are cumulated from ``start_ns`` through the crossing update
    itself, so a single sweep that jumps past the threshold is counted in full.
    """
    lo = int(np.searchsorted(path.change_ts, start_ns, side="left"))
    hi = int(np.searchsorted(path.change_ts, end_ns, side="right"))
    out: dict[float, dict[str, float]] = {}
    empty = {"seconds": np.nan, "quote_bp": np.nan, "trade_bp": np.nan, "gap_bp": np.nan,
             "total_bp": np.nan, "crossing_attr": np.nan, "crossing_bp": np.nan}
    if hi <= lo or not np.isfinite(target_bp) or target_bp == 0:
        return {fraction: dict(empty) for fraction in fractions}
    cumulative = path.cum_bp[lo + 1: hi + 1].sum(axis=1) - path.cum_bp[lo].sum()
    signed = np.sign(target_bp) * cumulative
    for fraction in fractions:
        reached = np.flatnonzero(signed >= fraction * abs(target_bp) - 1e-12)
        if reached.size == 0:
            out[fraction] = dict(empty)
            continue
        k = lo + int(reached[0])
        net = path.cum_bp[k + 1] - path.cum_bp[lo]
        out[fraction] = {
            "seconds": float((path.change_ts[k] - start_ns) / NS),
            "quote_bp": float(net[QUOTE]), "trade_bp": float(net[TRADE]),
            "gap_bp": float(net[GAP]), "total_bp": float(net.sum()),
            "crossing_attr": float(path.change_attr[k]), "crossing_bp": float(path.change_bp[k]),
        }
    return out


def initial_sequence(path: MidpointPath, event_ns: int) -> dict[str, float | bool]:
    """Who moves first after the scheduled second: the legacy and the new timing facts."""
    book_after = int(np.searchsorted(path.book_ts, event_ns, side="left"))
    valid_after = np.flatnonzero(path.book_valid[book_after:])
    trade_after = int(np.searchsorted(path.trade_ts, event_ns, side="left"))
    pre = state_at(path, event_ns, strictly_before=True)
    out: dict[str, float | bool] = {
        "pre_state_valid": bool(pre["state_valid"]),
        "first_quote_ms": np.nan, "first_trade_ms": np.nan, "first_quote_revision_bp": np.nan,
        "trade_before_first_quote": False, "same_event_first_quote_trade": False,
        "last_pretrade_revision_bp": np.nan, "pretrade_quote_count": 0,
        "first_change_ms": np.nan, "first_change_bp": np.nan, "first_change_attr": np.nan,
        "trades_before_first_change": np.nan, "volume_before_first_change": np.nan,
    }
    has_trade = trade_after < path.trade_ts.shape[0]
    if has_trade:
        first_trade_ts = int(path.trade_ts[trade_after])
        first_trade_stream = int(path.trade_stream_index[trade_after])
        out["first_trade_ms"] = (first_trade_ts - event_ns) / 1e6
    if valid_after.size:
        q = book_after + int(valid_after[0])
        out["first_quote_ms"] = float((path.book_ts[q] - event_ns) / 1e6)
        if np.isfinite(pre["logmid"]):
            out["first_quote_revision_bp"] = float(1e4 * (path.book_logmid[q] - pre["logmid"]))
        if has_trade:
            out["trade_before_first_quote"] = bool(first_trade_stream < path.book_stream_index[q])
            out["same_event_first_quote_trade"] = bool(path.book_trade_attributed[q])
    if has_trade and np.isfinite(pre["logmid"]):
        # Valid quotes after the scheduled second and before the first trade.
        before_trade = np.flatnonzero(
            (path.book_stream_index[book_after:] < first_trade_stream) & path.book_valid[book_after:]
        )
        out["pretrade_quote_count"] = int(before_trade.size)
        if before_trade.size:
            last = book_after + int(before_trade[-1])
            out["last_pretrade_revision_bp"] = float(1e4 * (path.book_logmid[last] - pre["logmid"]))
    change_after = int(np.searchsorted(path.change_ts, event_ns, side="left"))
    moving = np.flatnonzero(np.abs(path.change_bp[change_after:]) > 1e-9)
    if moving.size:
        k = change_after + int(moving[0])
        out["first_change_ms"] = float((path.change_ts[k] - event_ns) / 1e6)
        out["first_change_bp"] = float(path.change_bp[k])
        out["first_change_attr"] = float(path.change_attr[k])
        # Trades after the scheduled second that precede this update in feed order.
        earlier = (path.trade_ts >= event_ns) & (path.trade_stream_index < path.change_stream_index[k])
        out["trades_before_first_change"] = float(earlier.sum())
        out["volume_before_first_change"] = float(path.trade_size[earlier].sum())
    return out
