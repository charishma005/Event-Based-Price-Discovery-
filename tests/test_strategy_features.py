import numpy as np
import pandas as pd
import pytest

from src.strategies.fomc_features import (
    DECISION, EXECUTION_COLUMNS, FEATURE_COLUMNS, TARGET_COLUMNS, ZN10_FEATURE_COLUMNS, build_event_features,
    decision_features, prepare, second_level_panel,
)
from tests.strategy_synthetic import synthetic_book


@pytest.fixture(scope="module")
def book():
    return synthetic_book(n_dev=6, n_hold=3, last=1860)


@pytest.fixture(scope="module")
def features(book):
    return build_event_features(*book)


def _flat(instrument="ES.v.0", first=-300, last=400):
    seconds = np.arange(first, last + 1)
    return pd.DataFrame({"id": "e", "instrument": instrument, "second": seconds, "bid": 100.0, "ask": 100.25,
                         "bid_size": 10.0, "ask_size": 30.0})


def test_one_row_per_event_instrument_with_split(features):
    assert not features.duplicated(["event_id", "instrument"]).any()
    assert len(features) == 9 * 3
    assert set(features["sample"]) == {"development", "holdout"}
    assert (features.loc[features["sample"].eq("holdout"), "event_date"] >= "2023-01-01").all()


def test_feature_target_and_execution_columns_are_disjoint():
    assert not set(FEATURE_COLUMNS) & set(TARGET_COLUMNS)
    assert not set(FEATURE_COLUMNS) & set(EXECUTION_COLUMNS)
    assert not set(ZN10_FEATURE_COLUMNS) & set(TARGET_COLUMNS)


def test_all_feature_columns_present(features):
    assert set(FEATURE_COLUMNS) <= set(features.columns)
    zn = features.loc[features["instrument"].eq("ZN.v.0"), ZN10_FEATURE_COLUMNS]
    assert zn.notna().all().all()
    assert features.loc[features["instrument"].ne("ZN.v.0"), ZN10_FEATURE_COLUMNS].isna().all().all()


def test_flat_book_ratios_are_one_and_returns_zero():
    g = prepare(_flat())
    f = decision_features(g.loc[g["second"].le(DECISION)])
    for k in ("30s", "1m", "3m", "5m"):
        assert f[f"ret_0_{k}"] == 0
        assert np.isclose(f[f"depth_ratio_{k}"], 1) and np.isclose(f[f"spread_ratio_{k}"], 1)
    assert np.isclose(f["book_imbalance_5m"], -0.5)
    assert np.isclose(f["baseline_spread_ticks"], 1) and np.isclose(f["baseline_depth"], 40)
    assert np.isclose(f["depth_recovery_slope_1_5"], 0, atol=1e-9)


def test_trailing_window_is_30_seconds():
    raw = _flat()
    raw.loc[raw["second"].between(271, 300), ["bid_size", "ask_size"]] = 20.0      # last 30 s doubled
    raw.loc[raw["second"].between(241, 270), ["bid_size", "ask_size"]] = 1000.0    # just outside: ignored
    g = prepare(raw)
    f = decision_features(g.loc[g["second"].le(300)])
    assert np.isclose(f["depth_ratio_5m"], 1.0)    # (20+20) / baseline (10+30) = 1
    assert np.isclose(f["bid_depth_ratio_5m"], 2.0) and np.isclose(f["ask_depth_ratio_5m"], 20 / 30)


def test_second_zero_is_the_reference_mid():
    raw = _flat()
    raw.loc[raw["second"].ge(1), ["bid", "ask"]] = [101.0, 101.25]
    g = prepare(raw)
    f = decision_features(g.loc[g["second"].le(300)])
    assert np.isclose(f["ret_0_5m"], 1e4 * np.log(101.125 / 100.125))


def test_continuation_sign(features):
    expected = np.sign(features["ret_0_5m"]) * features["ret_5_20m"]
    assert np.allclose(features["continuation_5_20"], expected, equal_nan=True)


def test_entry_is_one_second_after_decision(book):
    raw, meetings = book
    f = build_event_features(raw, meetings).iloc[0]
    g = prepare(raw)
    row = g.loc[g["id"].eq(f["event_id"]) & g["instrument"].eq(f["instrument"]) & g["second"].eq(301)].iloc[0]
    assert f["ask_entry5"] == row["ask"] and f["bid_entry5"] == row["bid"]


def test_second_level_targets_are_future_and_features_past(book):
    raw, _ = book
    panel = second_level_panel(raw.loc[raw["id"].eq(raw["id"].iloc[0])])
    g = prepare(raw.loc[raw["id"].eq(raw["id"].iloc[0]) & raw["instrument"].eq("ES.v.0")]).set_index("second")
    row = panel.loc[panel["instrument"].eq("ES.v.0") & panel["second"].eq(100)].iloc[0]
    assert np.isclose(row["fut_ret_5s"], 1e4 * np.log(g.loc[105, "mid"] / g.loc[100, "mid"]))
    assert np.isclose(row["past_ret_5s"], 1e4 * np.log(g.loc[100, "mid"] / g.loc[95, "mid"]))
    assert panel["second"].between(60, 1740).all()
