"""Effective liquidity stress (ELS) and execution fills on a one-second top-of-book panel.

ELS is the log of depth per tick of spread, relative to a baseline window of the
same session:

    ELS(window) = log(mean touch depth / baseline mean depth)
                - log(mean spread in ticks / baseline mean spread)

so ELS = log(depth ratio) - log(spread ratio) = log of the "depth per tick of
spread" ratio in tables/h4_tick_constraint_by_period.csv. Zero is the baseline;
negative is worse liquidity. For ES and ZN, whose spread is one tick almost all the
time, ELS is close to the log depth ratio; for NQ the spread term matters.

Every function works on one session-instrument at a time, as numpy arrays indexed
by ``second - first_second``. Nothing here looks past the second it is evaluated at
unless its name says so (``window_mean`` over a closed window is used only for
windows that end before the quantity is used).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TICK = {"ES.v.0": 0.25, "NQ.v.0": 0.25, "ZN.v.0": 1 / 64}


@dataclass
class Book:
    """One session-instrument, one row per whole second."""

    seconds: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray
    tick: float

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, instrument: str, ffill_seconds: int = 5) -> "Book":
        """Build from panel rows of one session and instrument (columns as in extract_session_panels).

        Invalid seconds (crossed, empty or missing book) are filled from the last valid
        second for at most ``ffill_seconds``; longer gaps stay missing.
        """
        frame = frame.sort_values("seconds")
        seconds = frame["seconds"].to_numpy(np.int64)
        full = np.arange(seconds.min(), seconds.max() + 1)
        data = frame.set_index("seconds").reindex(full)
        valid = data["valid"].fillna(False).astype(bool).to_numpy()
        columns = {}
        for name in ("bid", "ask", "bid_size", "ask_size"):
            values = pd.Series(np.where(valid, data[name].to_numpy(float), np.nan))
            columns[name] = values.ffill(limit=ffill_seconds).to_numpy()
        return cls(seconds=full, tick=TICK[instrument], **columns)

    def index(self, second: int) -> int | None:
        i = int(second - self.seconds[0])
        return i if 0 <= i < len(self.seconds) else None

    @property
    def mid(self) -> np.ndarray:
        return (self.bid + self.ask) / 2

    @property
    def logmid(self) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.log(self.mid)

    @property
    def spread_ticks(self) -> np.ndarray:
        return (self.ask - self.bid) / self.tick

    @property
    def depth(self) -> np.ndarray:
        """Mean of best-bid and best-ask size."""
        return (self.bid_size + self.ask_size) / 2

    def at(self, values: np.ndarray, second: int) -> float:
        i = self.index(second)
        return float(values[i]) if i is not None else np.nan

    def window_mean(self, values: np.ndarray, start: int, end: int) -> float:
        """Mean over seconds start <= s < end, ignoring missing seconds; NaN if under half are present."""
        i, j = self.index(start), self.index(end - 1)
        if i is None or j is None or j < i:
            return np.nan
        chunk = values[i : j + 1]
        present = np.isfinite(chunk)
        if present.sum() < max(1, len(chunk) // 2):
            return np.nan
        return float(chunk[present].mean())


def els(book: Book, start: int, end: int, baseline: tuple[int, int]) -> dict[str, float]:
    """ELS and its two parts over seconds [start, end), relative to the baseline window."""
    base_depth = book.window_mean(book.depth, *baseline)
    base_spread = book.window_mean(book.spread_ticks, *baseline)
    depth = book.window_mean(book.depth, start, end)
    spread = book.window_mean(book.spread_ticks, start, end)
    with np.errstate(invalid="ignore", divide="ignore"):
        log_depth = np.log(depth / base_depth)
        log_spread = np.log(spread / base_spread)
    return {"log_depth_ratio": float(log_depth), "log_spread_ratio": float(log_spread),
            "els": float(log_depth - log_spread)}


def trailing_els(book: Book, window: int, baseline: tuple[int, int]) -> np.ndarray:
    """ELS over the trailing ``window`` seconds ending at each second (inclusive): usable live.

    Seconds whose trailing window has under half of its seconds present are NaN.
    """
    base_depth = book.window_mean(book.depth, *baseline)
    base_spread = book.window_mean(book.spread_ticks, *baseline)

    def rolling(values: np.ndarray) -> np.ndarray:
        present = np.isfinite(values)
        total = np.concatenate([[0.0], np.cumsum(np.where(present, values, 0.0))])
        count = np.concatenate([[0], np.cumsum(present)])
        hi = np.arange(1, len(values) + 1)
        lo = np.maximum(hi - window, 0)
        n = count[hi] - count[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            out = (total[hi] - total[lo]) / n
        out[n < max(1, window // 2)] = np.nan
        return out

    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(rolling(book.depth) / base_depth) - np.log(rolling(book.spread_ticks) / base_spread)


def log_return_bp(book: Book, start: int, end: int) -> float:
    """Midpoint log return from second ``start`` to second ``end``, in basis points."""
    return (book.at(book.logmid, end) - book.at(book.logmid, start)) * 1e4


def realized_vol_bp(book: Book, start: int, end: int, step: int) -> float:
    """Square root of the sum of squared ``step``-second midpoint log returns over [start, end], in bp."""
    i, j = book.index(start), book.index(end)
    if i is None or j is None:
        return np.nan
    sampled = book.logmid[i : j + 1 : step]
    returns = np.diff(sampled)
    returns = returns[np.isfinite(returns)]
    if len(returns) < max(1, (len(sampled) - 1) // 2):
        return np.nan
    return float(np.sqrt(np.sum(returns**2)) * 1e4)


# ---------------------------------------------------------------- execution

def fill(book: Book, second: int, quantity: float, side: int, search: int = 30) -> dict | None:
    """Fill ``quantity`` at the first valid second at or after ``second`` (up to ``search`` seconds later).

    side +1 buys at the ask, -1 sells at the bid. When the quantity exceeds the size
    shown at the touch, each further multiple of that size is assumed to fill one tick
    worse (average price touch + tick * (levels - 1) / 2). That is an approximation:
    the panel has only the best level, and a real check of larger orders needs MBP-10.
    """
    if quantity <= 0:
        return None
    for s in range(second, second + search + 1):
        i = book.index(s)
        if i is None:
            return None
        touch = book.ask[i] if side > 0 else book.bid[i]
        size = book.ask_size[i] if side > 0 else book.bid_size[i]
        mid = book.mid[i]
        if np.isfinite(touch) and np.isfinite(size) and size > 0 and np.isfinite(mid):
            levels = int(np.ceil(quantity / size))
            price = touch + side * book.tick * (levels - 1) / 2
            return {"second": s, "quantity": quantity, "price": float(price), "mid": float(mid), "levels": levels}
    return None


def schedule_fixed(slots: dict[int, float], total: float) -> list[tuple[int, float]]:
    """A fixed schedule: {second: weight} scaled to ``total``."""
    weight = sum(slots.values())
    return [(int(s), total * w / weight) for s, w in sorted(slots.items())]


def schedule_twap(start: int, end: int, step: int, total: float,
                  blackout: tuple[int, int] | None = None) -> list[tuple[int, float]]:
    """Equal slices every ``step`` seconds over [start, end); slots inside ``blackout`` are dropped."""
    slots = [s for s in range(start, end, step) if blackout is None or not (blackout[0] <= s < blackout[1])]
    return [(s, total / len(slots)) for s in slots]


def run_adaptive(book: Book, live_els: np.ndarray, base: list[tuple[int, float]], threshold: float,
                 deadline: int, step: int, side: int) -> list[dict]:
    """Follow ``base`` but defer any slice while trailing ELS is below ``threshold``.

    Deferred quantity is added to the next slot where ELS is at or above the
    threshold. After the last base slot the backlog is retried every ``step`` seconds
    and everything left is traded at ``deadline`` regardless of ELS. Missing ELS
    counts as stressed (defer).
    """
    planned = dict(base)
    last = max(planned)
    check = sorted(set(planned) | set(range(last + step, deadline, step)) | {deadline})
    fills, backlog = [], 0.0
    for second in check:
        backlog += planned.get(second, 0.0)
        if backlog <= 0:
            continue
        value = book.at(live_els, second)
        if second >= deadline or (np.isfinite(value) and value >= threshold):
            done = fill(book, second, backlog, side)
            if done is not None:
                fills.append(done)
                backlog = 0.0
    if backlog > 0:  # the deadline second had no valid quote within the search window
        return []
    return fills


def run_schedule(book: Book, schedule: list[tuple[int, float]], side: int) -> list[dict]:
    fills = [fill(book, s, q, side) for s, q in schedule]
    return [] if any(f is None for f in fills) else fills


def shortfall(fills: list[dict], arrival_mid: float, side: int) -> dict[str, float]:
    """Implementation shortfall against the arrival midpoint, split into spread/impact and timing, in bp.

    is_bp = spread_cost_bp + timing_bp, where spread_cost is what was paid over the
    midpoint at each fill and timing is how far the midpoint had moved since arrival.
    For a buy and a sell of the same schedule the timing parts cancel, so the average
    of the two shortfalls is the average spread cost.
    """
    if not fills or not np.isfinite(arrival_mid):
        return {"is_bp": np.nan, "spread_cost_bp": np.nan, "timing_bp": np.nan, "completion_second": np.nan}
    q = np.array([f["quantity"] for f in fills])
    w = q / q.sum()
    price = np.array([f["price"] for f in fills])
    mid = np.array([f["mid"] for f in fills])
    spread_cost = float(np.sum(w * side * (price - mid)) / arrival_mid * 1e4)
    timing = float(np.sum(w * side * (mid - arrival_mid)) / arrival_mid * 1e4)
    return {"is_bp": spread_cost + timing, "spread_cost_bp": spread_cost, "timing_bp": timing,
            "completion_second": float(max(f["second"] for f in fills))}


# ---------------------------------------------------------------- statistics

def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Area under the ROC curve (Mann-Whitney form, ties counted half)."""
    from scipy.stats import rankdata

    scores, labels = np.asarray(scores, float), np.asarray(labels, bool)
    keep = np.isfinite(scores)
    scores, labels = scores[keep], labels[keep]
    n_pos, n_neg = labels.sum(), (~labels).sum()
    if n_pos == 0 or n_neg == 0:
        return np.nan
    ranks = rankdata(scores)
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
