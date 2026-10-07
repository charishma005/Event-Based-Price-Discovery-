import numpy as np
import pandas as pd

from src.strategies.backtest import event_returns
from src.strategies.execution import dollars_per_contract, trade_returns


def _one(direction, instrument="ES.v.0", fee=0.0):
    # entry book 4000.00 / 4000.25, exit book 4010.00 / 4010.25
    return trade_returns([direction], [4000.0], [4000.25], [4000.125], [4010.0], [4010.25], [4010.125],
                         [instrument], fee_bp_per_side=fee).iloc[0]


def test_long_buys_ask_sells_bid():
    r = _one(1)
    assert np.isclose(r["executable_bp"], 1e4 * np.log(4010.0 / 4000.25))
    assert np.isclose(r["gross_bp"], 1e4 * np.log(4010.125 / 4000.125))
    assert r["executable_bp"] < r["gross_bp"]
    assert np.isclose(r["cost_bp"], r["gross_bp"] - r["executable_bp"])


def test_short_sells_bid_buys_ask():
    r = _one(-1)
    assert np.isclose(r["executable_bp"], 1e4 * np.log(4000.0 / 4010.25))
    assert np.isclose(r["gross_bp"], -1e4 * np.log(4010.125 / 4000.125))
    assert r["executable_bp"] < r["gross_bp"]


def test_one_tick_slippage_each_side():
    long_, short = _one(1), _one(-1)
    assert np.isclose(long_["net_slip_bp"], 1e4 * np.log((4010.0 - 0.25) / (4000.25 + 0.25)))
    assert np.isclose(short["net_slip_bp"], 1e4 * np.log((4000.0 - 0.25) / (4010.25 + 0.25)))
    assert long_["net_slip_bp"] < long_["executable_bp"]


def test_fees_are_zero_by_default_and_subtract_per_side():
    assert np.isclose(_one(1)["net_bp"], _one(1)["executable_bp"])
    assert np.isclose(_one(1, fee=0.5)["net_bp"], _one(1)["executable_bp"] - 1.0)


def test_zn_tick_used_for_slippage():
    r = trade_returns([1], [110.0], [110 + 1 / 64], [110 + 1 / 128], [111.0], [111 + 1 / 64], [111 + 1 / 128],
                      ["ZN.v.0"]).iloc[0]
    assert np.isclose(r["net_slip_bp"], 1e4 * np.log((111.0 - 1 / 64) / (110 + 2 / 64)))


def test_no_trade_rows_are_nan():
    r = trade_returns([0, np.nan], [1, 1], [2, 2], [1.5, 1.5], [1, 1], [2, 2], [1.5, 1.5], ["ES.v.0", "ES.v.0"])
    assert r.isna().all().all()


def test_event_returns_weight_legs_within_event():
    legs = pd.DataFrame({"event_id": ["a", "a", "b"], "weight": [1.0, 3.0, 1.0], "net_bp": [4.0, 8.0, -2.0]})
    out = event_returns(legs, "net_bp")
    assert np.isclose(out["a"], 7.0) and np.isclose(out["b"], -2.0)


def test_dollars_per_contract():
    assert np.isclose(dollars_per_contract([1], [4000.0], [4001.0], ["ES.v.0"])[0], 50.0)
    assert np.isclose(dollars_per_contract([-1], [14000.0], [13999.0], ["NQ.v.0"])[0], 20.0)
