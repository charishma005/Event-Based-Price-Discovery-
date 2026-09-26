import numpy as np
import pandas as pd

from src.analysis.event_summary import flow_intervals
from src.microstructure.mechanism import (
    aggregate_signed_flow,
    fit_order_flow_impact,
    identify_initial_quote_revision,
    mechanism_components,
)


EVENT = pd.Timestamp("2025-09-17T18:00:00Z")


def test_quote_revision_without_intervening_trade():
    messages = pd.DataFrame(
        [
            {"ts_event": EVENT - pd.Timedelta("1ns"), "sequence": 1, "record_type": "quote", "bid": 99, "ask": 101},
            {"ts_event": EVENT + pd.Timedelta("1ns"), "sequence": 2, "record_type": "quote", "bid": 101, "ask": 103},
            {"ts_event": EVENT + pd.Timedelta("2ns"), "sequence": 3, "record_type": "trade", "bid": np.nan, "ask": np.nan},
        ]
    )
    result = identify_initial_quote_revision(messages, EVENT)
    assert result.valid_for_primary_q1
    assert result.quote_revision_component == 2


def test_intervening_trade_is_flagged():
    messages = pd.DataFrame(
        [
            {"ts_event": EVENT - pd.Timedelta("1ns"), "sequence": 1, "record_type": "quote", "bid": 99, "ask": 101},
            {"ts_event": EVENT, "sequence": 2, "record_type": "trade", "bid": np.nan, "ask": np.nan},
            {"ts_event": EVENT + pd.Timedelta("1ns"), "sequence": 3, "record_type": "quote", "bid": 101, "ask": 103},
        ]
    )
    result = identify_initial_quote_revision(messages, EVENT)
    assert result.intervening_trade
    assert not result.valid_for_primary_q1


def test_same_timestamp_without_sequence_is_ambiguous():
    messages = pd.DataFrame(
        [
            {"ts_event": EVENT - pd.Timedelta("1ns"), "record_type": "quote", "bid": 99, "ask": 101},
            {"ts_event": EVENT, "record_type": "quote", "bid": 101, "ask": 103},
            {"ts_event": EVENT, "record_type": "trade", "bid": np.nan, "ask": np.nan},
        ]
    )
    result = identify_initial_quote_revision(messages, EVENT)
    assert result.sequencing_ambiguous
    assert not result.valid_for_primary_q1


def test_signed_flow_uses_explicit_side_only():
    trades = pd.DataFrame(
        [
            {"ts_event": EVENT, "side": "B", "size": 3, "price": 100},
            {"ts_event": EVENT + pd.Timedelta("50ms"), "side": "A", "size": 1, "price": 101},
            {"ts_event": EVENT + pd.Timedelta("60ms"), "side": "N", "size": 8, "price": 102},
        ]
    )
    result = aggregate_signed_flow(trades, EVENT, [100]).iloc[0]
    assert result["signed_volume"] == 2
    assert result["known_side_fraction"] == 2 / 3


def test_pathological_share_is_retained_and_flagged():
    result = mechanism_components(
        quote_revision=2,
        cumulative_signed_flow=-1,
        impact_coefficient=1,
        total_adjustment=0.5,
    )
    assert result["mechanism_share"] == 2
    assert "opposing_component_signs" in result["quality_flags"]
    assert "mechanism_share_outside_unit_interval" in result["quality_flags"]


def test_linear_impact_fit_recovers_slope():
    intervals = pd.DataFrame(
        {"signed_volume": [-2, -1, 0, 1, 2], "return": [-0.03, -0.01, 0.01, 0.03, 0.05]}
    )
    diagnostics, fitted = fit_order_flow_impact(intervals)
    assert abs(diagnostics["impact_coefficient"] - 0.02) < 1e-12
    assert fitted["fitted_order_flow_return"].notna().all()


def test_subsecond_intervals_retain_lagged_touch_depth():
    messages = pd.DataFrame(
        [
            {"ts_event": EVENT - pd.Timedelta("200ms"), "sequence": 1, "record_type": "quote", "bid": 99.0, "ask": 101.0, "bid_size": 4, "ask_size": 6, "side": "N", "size": 0, "price": 0},
            {"ts_event": EVENT + pd.Timedelta("50ms"), "sequence": 2, "record_type": "trade", "bid": 99.0, "ask": 101.0, "bid_size": 4, "ask_size": 6, "side": "B", "size": 3, "price": 101},
            {"ts_event": EVENT + pd.Timedelta("80ms"), "sequence": 3, "record_type": "quote", "bid": 100.0, "ask": 102.0, "bid_size": 2, "ask_size": 3, "side": "N", "size": 0, "price": 0},
        ]
    )
    intervals = flow_intervals(messages, "100ms")
    event_bucket = intervals.loc[EVENT]
    assert event_bucket["signed_volume"] == 3
    assert event_bucket["touch_depth"] == 5
    assert event_bucket["lag_touch_depth"] == 10
