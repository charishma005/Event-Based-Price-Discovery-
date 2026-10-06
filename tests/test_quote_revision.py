import numpy as np
import pytest

from src.microstructure.quote_revision import (
    GAP, QUOTE, TRADE, bounded_share, build_midpoint_path, components, first_passage,
    initial_sequence, state_at, trade_attribution, trade_flow,
)
from src.microstructure.tick_arrays import InstrumentTicks, timestamp_resolution_ns

EVENT = 1_700_000_000 * 1_000_000_000
US = 1_000
MS = 1_000_000


def ticks(rows, symbol="ES.v.0"):
    """rows: (offset_ns, action, bid, ask, bid_size, ask_size[, side, size, price])."""
    n = len(rows)
    ts = np.array([EVENT + r[0] for r in rows], dtype=np.int64)
    action = np.array([r[1].encode() for r in rows])
    bid = np.array([r[2] for r in rows], dtype=float)
    ask = np.array([r[3] for r in rows], dtype=float)
    bid_size = np.array([r[4] for r in rows], dtype=np.int64)
    ask_size = np.array([r[5] for r in rows], dtype=np.int64)
    side = np.array([r[6] if len(r) > 6 else 0 for r in rows], dtype=np.int8)
    size = np.array([r[7] if len(r) > 7 else 1 for r in rows], dtype=np.int64)
    price = np.array([r[8] if len(r) > 8 else np.nan for r in rows], dtype=float)
    is_trade = action == b"T"
    is_book = np.isin(action, (b"A", b"C", b"M", b"R"))
    valid = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > bid) & (bid_size > 0) & (ask_size > 0)
    return InstrumentTicks(
        symbol=symbol, instrument_id=1, ts=ts, ts_recv=ts, is_trade=is_trade, is_book=is_book,
        side=side, price=price, size=size, sequence=np.arange(n), flags=np.zeros(n, np.uint8),
        bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size, book_valid=valid,
        timestamp_resolution_ns=timestamp_resolution_ns(ts), other_action_count=0,
    )


def bp(a, b):
    return 1e4 * np.log(b / a)


def test_same_timestamp_updates_belong_to_the_trade_and_later_ones_do_not():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "T", 100.0, 100.25, 5, 5, 1, 5, 100.25),
        (MS, "C", 100.0, 100.50, 5, 9),          # the trade's own book effect
        (MS, "A", 100.25, 100.50, 2, 9),         # remainder rests: still the same event
        (MS + 5 * US, "M", 100.25, 100.75, 2, 4),  # an independent requote 5 microseconds later
    ])
    path = build_midpoint_path(t)
    assert path.change_attr.tolist() == [TRADE, TRADE, QUOTE]
    c = components(path, EVENT, EVENT + 10 * MS)
    assert c["trade_bp"] == pytest.approx(bp(100.125, 100.375))
    assert c["quote_bp"] == pytest.approx(bp(100.375, 100.5))
    assert c["total_bp"] == pytest.approx(bp(100.125, 100.5))


def test_first_update_within_tolerance_handles_separately_stamped_feeds():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "T", 100.0, 100.25, 5, 5, 1, 5, 100.25),
        (MS + 16 * US, "M", 100.0, 100.50, 5, 9),   # 2016-style: effect stamped 16 us later
        (MS + 40 * US, "M", 100.0, 100.75, 5, 4),   # second update is not the trade's
    ])
    path = build_midpoint_path(t)                   # format detected from the stream itself
    assert path.same_timestamp_share == 0.0 and path.tolerance_ns == 100_000
    assert path.change_attr.tolist() == [TRADE, QUOTE]
    assert build_midpoint_path(t, tolerance_ns=0).change_attr.tolist() == [QUOTE, QUOTE]


def test_same_stamped_feed_uses_zero_tolerance():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "T", 100.0, 100.25, 5, 5, 1, 2, 100.25),
        (MS, "M", 100.0, 100.25, 5, 3),             # the trade's own size update, same stamp
        (2 * MS, "T", 100.0, 100.25, 5, 3, 0, 1, 100.10),   # implied trade, no book effect
        (2 * MS + 30 * US, "C", 100.0, 100.50, 5, 9),       # unrelated requote 30 us later
    ])
    path = build_midpoint_path(t)
    assert path.same_timestamp_share == 0.5 and path.tolerance_ns == 0
    assert path.change_attr.tolist() == [TRADE, QUOTE]
    assert build_midpoint_path(t, tolerance_ns=100_000).change_attr.tolist() == [TRADE, TRADE]


def test_update_long_after_a_trade_is_a_quote_revision():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "T", 100.0, 100.25, 5, 5, 0, 3, 100.10),   # e.g. an implied trade with no book effect
        (6 * MS, "C", 100.0, 100.50, 5, 9),
    ])
    assert build_midpoint_path(t).change_attr.tolist() == [QUOTE]
    flags = trade_attribution(t.ts, t.is_trade, t.is_book)
    assert not flags.any()


def test_millisecond_stamps_attribute_same_millisecond_updates_to_the_trade():
    t = ticks([
        (-MS, "M", 100.0, 100.25, 5, 5),
        (2 * MS, "T", 100.0, 100.25, 5, 5, 1, 5, 100.25),
        (2 * MS, "M", 100.0, 100.50, 5, 9),
        (2 * MS, "M", 100.0, 100.75, 5, 9),      # cannot be separated at this clock resolution
    ])
    assert t.timestamp_resolution_ns == 1_000_000
    assert build_midpoint_path(t).change_attr.tolist() == [TRADE, TRADE]


def test_invalid_book_creates_a_gap_component_and_components_telescope():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "M", 100.25, 100.50, 5, 5),
        (2 * MS, "M", 101.0, 100.50, 5, 5),      # crossed: no valid midpoint
        (3 * MS, "M", 101.0, 100.75, 5, 5),      # still crossed
        (9 * MS, "A", 101.0, 101.25, 5, 5),
    ])
    path = build_midpoint_path(t)
    assert path.change_attr.tolist() == [QUOTE, GAP]
    c = components(path, EVENT, EVENT + 20 * MS)
    assert c["gap_bp"] == pytest.approx(bp(100.375, 101.125))
    assert c["total_bp"] == pytest.approx(bp(100.125, 101.125))
    during = state_at(path, EVENT + 5 * MS)
    assert not during["state_valid"] and during["logmid"] == pytest.approx(np.log(100.375))


def test_window_edges_strictly_before_start_and_at_or_before_end():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (0, "M", 100.25, 100.50, 5, 5),          # exactly on the event clock: inside the window
        (5 * MS, "M", 100.50, 100.75, 5, 5),     # exactly on the end: inside the window
        (5 * MS + 1, "M", 100.75, 101.0, 5, 5),
    ])
    path = build_midpoint_path(t)
    c = components(path, EVENT, EVENT + 5 * MS)
    assert c["n_changes"] == 2 and c["total_bp"] == pytest.approx(bp(100.125, 100.625))
    assert state_at(path, EVENT, strictly_before=True)["logmid"] == pytest.approx(np.log(100.125))


def test_first_passage_counts_the_crossing_sweep_in_full():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (10 * MS, "M", 100.0, 100.50, 5, 5),                       # quote: +0.125
        (20 * MS, "T", 100.0, 100.50, 5, 5, 1, 5, 100.50),
        (20 * MS, "C", 100.0, 102.50, 5, 5),                       # sweep: +1.0
        (900 * MS, "M", 100.5, 102.50, 5, 5),                      # quote: +0.25
    ])
    path = build_midpoint_path(t)
    target = bp(100.125, 101.5)
    out = first_passage(path, EVENT, EVENT + 10**9, target, (0.05, 0.5, 0.99, 2.0))
    assert out[0.05]["seconds"] == pytest.approx(0.010) and out[0.05]["crossing_attr"] == QUOTE
    assert out[0.5]["seconds"] == pytest.approx(0.020) and out[0.5]["crossing_attr"] == TRADE
    assert out[0.5]["trade_bp"] == pytest.approx(bp(100.25, 101.25))
    assert out[0.5]["quote_bp"] == pytest.approx(bp(100.125, 100.25))
    assert out[0.99]["seconds"] == pytest.approx(0.900)
    assert np.isnan(out[2.0]["seconds"])
    negative = first_passage(path, EVENT, EVENT + 10**9, -target, (0.5,))
    assert np.isnan(negative[0.5]["seconds"])


def test_initial_sequence_reproduces_the_first_quote_facts():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (2 * MS, "A", 100.0, 100.25, 6, 5),                        # depth only: revision is zero
        (4 * MS, "M", 100.0, 100.50, 6, 5),                        # last quote before the first trade
        (7 * MS, "T", 100.0, 100.50, 6, 5, -1, 6, 100.0),
        (7 * MS, "C", 99.75, 100.50, 3, 5),
    ])
    seq = initial_sequence(build_midpoint_path(t), EVENT)
    assert seq["first_quote_ms"] == pytest.approx(2.0) and seq["first_quote_revision_bp"] == pytest.approx(0.0)
    assert not seq["trade_before_first_quote"]
    assert seq["first_trade_ms"] == pytest.approx(7.0) and seq["pretrade_quote_count"] == 2
    assert seq["last_pretrade_revision_bp"] == pytest.approx(bp(100.125, 100.25))
    assert seq["first_change_ms"] == pytest.approx(4.0) and seq["first_change_attr"] == QUOTE
    assert seq["trades_before_first_change"] == 0


def test_trade_before_first_quote_and_trade_initiated_first_change():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (3 * MS, "T", 100.0, 100.25, 5, 5, 1, 5, 100.25),
        (3 * MS, "C", 100.0, 100.50, 5, 9),
    ])
    seq = initial_sequence(build_midpoint_path(t), EVENT)
    assert seq["trade_before_first_quote"] and seq["same_event_first_quote_trade"]
    assert seq["first_change_attr"] == TRADE and seq["trades_before_first_change"] == 1
    assert seq["pretrade_quote_count"] == 0 and np.isnan(seq["last_pretrade_revision_bp"])


def test_trade_flow_and_bounded_share():
    t = ticks([
        (-MS, "A", 100.0, 100.25, 5, 5),
        (MS, "T", 100.0, 100.25, 5, 5, 1, 4, 100.25),
        (2 * MS, "T", 100.0, 100.25, 5, 5, -1, 1, 100.0),
        (3 * MS, "T", 100.0, 100.25, 5, 5, 0, 7, 100.1),
    ])
    flow = trade_flow(build_midpoint_path(t), EVENT, EVENT + 2 * MS)
    assert flow == {"trade_count": 2, "buy_volume": 4.0, "sell_volume": 1.0,
                    "unknown_volume": 0.0, "signed_volume": 3.0}
    assert bounded_share(3.0, 1.0) == pytest.approx(0.75)
    assert bounded_share(-3.0, 1.0) == pytest.approx(0.75)
    assert np.isnan(bounded_share(0.0, 0.0))


def test_event_measures_identities_on_a_synthetic_arrival():
    from src.microstructure.event_features import (
        book_integrals, event_measures, liquidity_measures, second_panel, time_weighted,
    )

    second = 10**9
    rows = [(-300 * second, "A", 100.0, 100.25, 10, 10)]
    rows += [(-200 * second, "M", 100.0, 100.25, 20, 20), (-30 * second, "M", 100.0, 100.25, 5, 5)]
    rows += [(-5 * second, "M", 100.0, 100.50, 5, 5), (-5 * second + 50 * MS, "M", 100.0, 100.25, 5, 5)]
    arrival = 1 * second + 30 * MS
    rows += [
        (20 * MS, "A", 100.0, 100.25, 6, 5),                            # depth-only first quote
        (arrival, "T", 100.0, 100.25, 6, 5, 1, 5, 100.25),
        (arrival, "C", 100.0, 101.25, 6, 5),                            # sweep: +0.5 midpoint
        (arrival + 40 * MS, "M", 100.75, 101.25, 6, 5),                 # requote: +0.375
        (200 * second, "M", 100.75, 101.50, 6, 5),                      # late drift: +0.125
        (360 * second, "M", 100.75, 101.50, 7, 5),
    ]
    path = build_midpoint_path(ticks(rows))
    alternative = build_midpoint_path(ticks(rows), tolerance_ns=100_000)
    m = event_measures(path, EVENT, alternative)
    assert m["first_quote_revision_bp"] == pytest.approx(0.0) and not m["trade_before_first_quote"]
    assert m["first_change_attr"] == TRADE and m["trades_before_first_change"] == 1
    # Every covered fixed window is an exact accounting identity.
    for label in ("1s", "2s", "60s", "300s"):
        total = m[f"w{label}_quote_bp"] + m[f"w{label}_trade_bp"] + m[f"w{label}_gap_bp"]
        assert total == pytest.approx(m[f"w{label}_total_bp"])
    assert m["w1s_total_bp"] == pytest.approx(0.0)                      # nothing before the arrival
    assert m["w300s_total_bp"] == pytest.approx(bp(100.125, 101.125))
    # Burst anchor finds the arrival; half of the 300 s move is crossed by the sweep itself.
    assert m["arr_burst_seconds"] == pytest.approx(1.03)
    assert m["arr_burst_100ms_trade_bp"] == pytest.approx(bp(100.125, 100.625))
    assert m["arr_burst_100ms_quote_bp"] == pytest.approx(bp(100.625, 101.0))
    assert m["arr_burst_100ms_trade_count"] == 1 and m["arr_burst_100ms_volume"] == 5
    assert m["fp300s_50_seconds"] == pytest.approx(1.03) and m["fp300s_50_quote_bp"] == pytest.approx(0.0)
    assert m["fp300s_90_seconds"] == pytest.approx(200.0)
    assert m["alt_arr_burst_100ms_trade_bp"] == pytest.approx(m["arr_burst_100ms_trade_bp"])
    assert m["attribution_tolerance_ns"] == 0 and m["same_timestamp_share"] == 1.0
    # Pre-event placebo burst: the +/-0.125 flicker five seconds before the clock.
    assert abs(m["pre_burst_bp"]) == pytest.approx(abs(bp(100.125, 100.25)))

    integrals = book_integrals(path)
    base = time_weighted(integrals, EVENT - 240 * second, EVENT - 60 * second)
    baseline = (20 * 40 + 40 * 140) / 180          # 20 lots for 40 s, then 40 lots for 140 s
    assert base["depth"] == pytest.approx(baseline) and base["coverage"] == pytest.approx(1.0)
    liq = liquidity_measures(path, EVENT, integrals)
    assert liq["baseline_depth"] == pytest.approx(baseline)
    assert liq["pre60_depth"] == pytest.approx((40 * 30 + 10 * 30) / 60)
    assert liq["pre60_depth_ratio"] == pytest.approx(25.0 / baseline)
    assert liq["baseline_one_tick_share"] == pytest.approx(1.0)
    panel = second_panel(path, EVENT, -5, 5, integrals)
    at = panel.set_index("seconds")
    assert at.loc[1.0, "cum_trades"] == 0 and at.loc[2.0, "cum_trades"] == 1
    moved = at.loc[2.0, ["cum_quote_bp", "cum_trade_bp"]].sum() - at.loc[0.0, ["cum_quote_bp", "cum_trade_bp"]].sum()
    assert moved == pytest.approx(bp(100.125, 101.0))
    assert at.loc[2.0, "logmid"] == pytest.approx(np.log(101.0))
