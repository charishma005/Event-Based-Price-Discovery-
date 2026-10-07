"""Trade returns at the midpoint, at executable quotes, net of fees, and with extra slippage.

A long buys at the ask and sells at the bid; a short sells at the bid and buys
back at the ask. Returns are in bp of the entry price, signed so that positive
is a profit. Fees are a per-side amount in bp (zero by default: fees are ignored
for now); slippage adds one further adverse tick on each side.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.microstructure.tick_arrays import tick_size

FEE_BP_PER_SIDE = 0.0
MULTIPLIER = {"ES.v.0": 50.0, "NQ.v.0": 20.0, "ZN.v.0": 1000.0}  # dollars per point


def _bp(entry: np.ndarray, exit_: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1e4 * np.log(exit_ / entry)


def trade_returns(direction, entry_bid, entry_ask, entry_mid, exit_bid, exit_ask, exit_mid, instrument,
                  fee_bp_per_side: float = FEE_BP_PER_SIDE) -> pd.DataFrame:
    """Per-trade returns in bp. ``direction`` is +1 (long), -1 (short) or 0/NaN (no trade)."""
    d = np.asarray(direction, float)
    tick = np.asarray(pd.Series(instrument).map(tick_size), float)
    eb, ea, em = (np.asarray(x, float) for x in (entry_bid, entry_ask, entry_mid))
    xb, xa, xm = (np.asarray(x, float) for x in (exit_bid, exit_ask, exit_mid))
    long_ = d > 0
    gross = d * _bp(em, xm)
    executable = np.where(long_, _bp(ea, xb), _bp(xa, eb))
    slipped = np.where(long_, _bp(ea + tick, xb - tick), _bp(xa + tick, eb - tick))
    net = executable - 2 * fee_bp_per_side
    out = pd.DataFrame({
        "gross_bp": gross,
        "executable_bp": executable,
        "net_bp": net,
        "net_slip_bp": slipped - 2 * fee_bp_per_side,
        "cost_bp": gross - executable,
    })
    out.loc[~(np.abs(d) > 0)] = np.nan
    return out


def dollars_per_contract(direction, entry_price, exit_price, instrument) -> np.ndarray:
    multiplier = np.asarray(pd.Series(instrument).map(MULTIPLIER), float)
    return np.asarray(direction, float) * (np.asarray(exit_price, float) - np.asarray(entry_price, float)) * multiplier
