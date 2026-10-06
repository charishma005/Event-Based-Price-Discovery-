"""Lean array view of a Databento MBP-1 file, one object per instrument.

``DBNStore.to_df`` builds several object columns and needs roughly ten times
the memory of the raw records. The tick-level measures only need a handful of
numeric arrays, so this module reads the structured record array directly.

Conventions (identical to the publication-methods pass):

* ``ts`` is the exchange timestamp ``ts_event`` in integer nanoseconds (UTC).
* Only add, cancel, modify and clear records change the displayed book. A
  trade record carries the book *before* its own effect; the book update that
  follows it shows the effect. Fill and unknown records are neither.
* A book state is valid when both sides are present, positive and not locked
  or crossed. Invalid states are kept so that they terminate the prior quote.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

UNDEF_PRICE = np.iinfo(np.int64).max
PRICE_SCALE = 1e-9
BOOK_ACTIONS = (b"A", b"C", b"M", b"R")
TICK_SIZE = {"ES": 0.25, "NQ": 0.25, "ZN": 1 / 64}


def tick_size(symbol: str) -> float:
    root = symbol.split(".")[0]
    if root not in TICK_SIZE:
        raise KeyError(f"No tick size registered for {symbol}")
    return TICK_SIZE[root]


@dataclass
class InstrumentTicks:
    symbol: str
    instrument_id: int
    ts: np.ndarray
    ts_recv: np.ndarray
    is_trade: np.ndarray
    is_book: np.ndarray
    side: np.ndarray          # +1 buyer-initiated, -1 seller-initiated, 0 unknown
    price: np.ndarray
    size: np.ndarray
    sequence: np.ndarray
    flags: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray
    book_valid: np.ndarray
    timestamp_resolution_ns: int
    other_action_count: int

    def __len__(self) -> int:
        return int(self.ts.shape[0])

    @property
    def tick(self) -> float:
        return tick_size(self.symbol)


def _price(values: np.ndarray) -> np.ndarray:
    out = values.astype(np.float64) * PRICE_SCALE
    out[values == UNDEF_PRICE] = np.nan
    return out


def timestamp_resolution_ns(ts: np.ndarray) -> int:
    """Finest observed granularity of the exchange clock: 1, 1_000 or 1_000_000 ns."""
    if ts.size == 0:
        return 1
    remainder = ts % 1_000_000
    if np.any(remainder % 1_000 != 0):
        return 1
    if np.any(remainder != 0):
        return 1_000
    return 1_000_000


def instrument_ticks(records: np.ndarray, symbol: str, instrument_id: int) -> InstrumentTicks:
    """Slice one instrument out of a structured MBP-1 record array."""
    rows = records[records["instrument_id"] == instrument_id]
    # Feed order: exchange time, then venue sequence, then order of receipt.
    order = np.lexsort((np.arange(rows.shape[0]), rows["sequence"], rows["ts_event"]))
    rows = rows[order]
    action = rows["action"]
    is_trade = action == b"T"
    is_book = np.isin(action, BOOK_ACTIONS)
    side_raw = rows["side"]
    side = np.zeros(rows.shape[0], dtype=np.int8)
    side[side_raw == b"B"] = 1
    side[side_raw == b"A"] = -1
    bid, ask = _price(rows["bid_px_00"]), _price(rows["ask_px_00"])
    bid_size = rows["bid_sz_00"].astype(np.int64)
    ask_size = rows["ask_sz_00"].astype(np.int64)
    with np.errstate(invalid="ignore"):
        valid = (
            np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > bid)
            & (bid_size > 0) & (ask_size > 0)
        )
    ts = rows["ts_event"].astype(np.int64)
    return InstrumentTicks(
        symbol=symbol,
        instrument_id=int(instrument_id),
        ts=ts,
        ts_recv=rows["ts_recv"].astype(np.int64),
        is_trade=is_trade,
        is_book=is_book,
        side=side,
        price=_price(rows["price"]),
        size=rows["size"].astype(np.int64),
        sequence=rows["sequence"].astype(np.int64),
        flags=rows["flags"].astype(np.uint8),
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        book_valid=valid,
        timestamp_resolution_ns=timestamp_resolution_ns(ts),
        other_action_count=int((~is_trade & ~is_book).sum()),
    )


def load_mbp1(path: str | Path) -> dict[str, InstrumentTicks]:
    """Read a cached MBP-1 DBN file into one ``InstrumentTicks`` per requested symbol.

    Continuous symbols are resolved with the file's own symbology. A window
    that spans a roll would map one symbol to two instruments; every window in
    this project lies inside one session, so that case raises instead of
    silently mixing contracts.
    """
    import databento as db

    store = db.DBNStore.from_file(str(path))
    records = store.to_ndarray()
    out: dict[str, InstrumentTicks] = {}
    for symbol, intervals in store.metadata.mappings.items():
        ids = sorted({int(item["symbol"]) for item in intervals})
        if not ids:
            continue
        if len(ids) > 1:
            present = [i for i in ids if np.any(records["instrument_id"] == i)]
            if len(present) > 1:
                raise ValueError(f"{path}: {symbol} maps to several instruments {present}")
            ids = present or ids[:1]
        ticks = instrument_ticks(records, symbol, ids[0])
        if len(ticks):
            out[symbol] = ticks
    return out
