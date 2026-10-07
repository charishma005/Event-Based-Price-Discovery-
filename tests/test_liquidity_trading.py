from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import analyze_liquidity_trading as lt
from src.microstructure import liquidity_stress as ls
from src.utils.config import PROJECT_ROOT, load_yaml


def _book(depth: np.ndarray, spread_ticks: np.ndarray, mid: np.ndarray | None = None, first: int = -900) -> ls.Book:
    n = len(depth)
    mid = np.full(n, 100.0) if mid is None else mid
    tick = 0.25
    return ls.Book(seconds=np.arange(first, first + n), bid=mid - spread_ticks * tick / 2,
                   ask=mid + spread_ticks * tick / 2, bid_size=depth.astype(float), ask_size=depth.astype(float), tick=tick)


def test_els_is_log_depth_ratio_minus_log_spread_ratio() -> None:
    seconds = np.arange(-900, 901)
    depth = np.where((seconds >= -60) & (seconds < 0), 25.0, 100.0)
    spread = np.where((seconds >= -60) & (seconds < 0), 2.0, 1.0)
    book = _book(depth, spread)
    parts = ls.els(book, -60, 0, (-240, -60))
    assert parts["log_depth_ratio"] == pytest.approx(np.log(0.25))
    assert parts["log_spread_ratio"] == pytest.approx(np.log(2.0))
    assert parts["els"] == pytest.approx(np.log(0.25 / 2.0))


def test_trailing_els_only_uses_the_past() -> None:
    seconds = np.arange(-900, 901)
    depth = np.where(seconds >= 0, 10.0, 100.0)
    book = _book(depth, np.ones(len(seconds)))
    live = ls.trailing_els(book, 30, (-900, -300))
    assert book.at(live, -1) == pytest.approx(0.0)        # before the drop, no trace of it
    assert book.at(live, 29) == pytest.approx(np.log(0.1))  # window [0, 29] fully after the drop


def test_fill_walks_one_tick_per_extra_touch_multiple_and_skips_invalid_seconds() -> None:
    depth = np.full(100, 10.0)
    book = _book(depth, np.ones(100), first=0)
    book.ask[5] = np.nan
    f = ls.fill(book, 5, 25, side=1)
    assert f["second"] == 6 and f["levels"] == 3
    assert f["price"] == pytest.approx(book.ask[6] + 0.25)
    sell = ls.fill(book, 6, 5, side=-1)
    assert sell["price"] == pytest.approx(book.bid[6])


def test_shortfall_parts_add_up_and_cancel_across_sides() -> None:
    mid = np.linspace(100, 101, 1801)
    book = _book(np.full(1801, 1000.0), np.ones(1801), mid=mid)
    plan = ls.schedule_twap(-300, 600, 30, 100)
    arrival = book.at(book.mid, -300)
    buy = ls.shortfall(ls.run_schedule(book, plan, 1), arrival, 1)
    sell = ls.shortfall(ls.run_schedule(book, plan, -1), arrival, -1)
    assert buy["is_bp"] == pytest.approx(buy["spread_cost_bp"] + buy["timing_bp"])
    assert buy["timing_bp"] == pytest.approx(-sell["timing_bp"])
    assert (buy["is_bp"] + sell["is_bp"]) / 2 == pytest.approx(buy["spread_cost_bp"])


def test_calendar_drops_blackout_slots_and_keeps_the_total() -> None:
    plan = ls.schedule_twap(-300, 600, 30, 100, blackout=(-120, 60))
    assert all(not (-120 <= s < 60) for s, _ in plan)
    assert sum(q for _, q in plan) == pytest.approx(100)


def test_adaptive_defers_while_stressed_and_finishes_by_the_deadline() -> None:
    seconds = np.arange(-900, 1201)
    stressed = (seconds >= -120) & (seconds < 2000)  # never recovers
    book = _book(np.where(stressed, 5.0, 100.0), np.ones(len(seconds)))
    live = ls.trailing_els(book, 30, (-900, -300))
    plan = ls.schedule_twap(-300, 600, 30, 100)
    fills = ls.run_adaptive(book, live, plan, -0.5, 900, 30, side=1)
    assert sum(f["quantity"] for f in fills) == pytest.approx(100)
    assert max(f["second"] for f in fills) == 900
    assert all(f["second"] < -60 or f["second"] == 900 for f in fills)


def test_auc() -> None:
    assert ls.auc(np.array([0.1, 0.2, 0.8, 0.9]), np.array([0, 0, 1, 1])) == 1.0
    assert ls.auc(np.array([0.5, 0.5]), np.array([0, 1])) == 0.5


# ---------------------------------------------------------------- end to end on a synthetic panel

def _synthetic(tmp_path) -> dict:
    rng = np.random.default_rng(0)
    seconds = np.arange(-1800, 1501)
    rows, registry = [], []
    for k in range(48):
        year = 2015 + k % 12
        for is_event in (True, False):
            event_id = f"{'fomc' if is_event else 'placebo'}_{year}_{k}"
            registry.append({"event_id": event_id, "family": "fomc" if is_event else "fomc_control",
                             "dataset_condition": "available", "sample": "oos_backward",
                             "event_date": f"{year}-0{1 + k % 9}-15", "sep_release": str(k % 2 == 0),
                             "press_conference_time_utc": "x" if year >= 2019 else ""})
            stress = rng.uniform(0.1, 0.7) if is_event else 1.0
            jump = rng.normal(0, 20) * (1.5 - stress) if is_event else 0.0
            for instrument, base_depth in (("ES.v.0", 200), ("NQ.v.0", 20), ("ZN.v.0", 2000)):
                window = (seconds >= -120) & (seconds < 120)
                depth = np.where(window, base_depth * stress, base_depth) * rng.uniform(0.9, 1.1, len(seconds))
                spread = np.where(window & is_event & (instrument == "NQ.v.0"), 3.0 / stress, 1.0)
                logmid = np.log(5000) + np.cumsum(rng.normal(0, 0.2, len(seconds))) * 1e-4 + (seconds >= 1) * jump * 1e-4
                mid = np.exp(logmid)
                half = spread * 0.25 / 2
                rows.append(pd.DataFrame({"event_id": event_id, "instrument": instrument, "seconds": seconds,
                                          "valid": True, "bid": mid - half, "ask": mid + half,
                                          "bid_size": depth, "ask_size": depth}))
    panel = pd.concat(rows, ignore_index=True)
    panel.to_parquet(tmp_path / "panel.parquet", index=False)
    pd.DataFrame(registry).to_csv(tmp_path / "registry.csv", index=False)
    spec = load_yaml(PROJECT_ROOT / lt.PREREGISTRATION)
    spec["data"]["panel"] = str(tmp_path / "panel.parquet")
    spec["data"]["registry"] = str(tmp_path / "registry.csv")
    spec["data"]["implied_vol_used"] = "never"
    return spec


def test_end_to_end_on_synthetic_panel(tmp_path) -> None:
    spec = _synthetic(tmp_path)
    meta, books = lt.load(spec)
    assert meta["is_event"].sum() == 48 and len(books) == 96 * 3
    features = lt.build_features(meta, books, spec)
    events = features.loc[features["is_event"]]
    assert (events["els_pre"] < -0.1).all()            # the synthetic withdrawal shows up
    assert features.loc[~features["is_event"], "els_pre"].abs().max() < 0.1

    a = lt.part_a(features, spec)
    assert set(a["test"]) == {"move_size", "continuation", "continuation_slope"}
    es = a.loc[a["test"].eq("move_size") & a["instrument"].eq("ES.v.0") & a["horizon"].eq("0-300s")].iloc[0]
    assert es["coef"] < 0                               # built in: more stress, bigger jump

    b_summary, predictions = lt.part_b(features, spec, use_iv=False)
    assert len(b_summary) == 3 and predictions["year"].min() >= 2018

    sessions, summary, tests = lt.part_c(meta, books, spec)
    assert set(sessions["strategy"]) == {"user_schedule", "twap", "calendar", "adaptive"}
    assert tests["primary"].sum() == 3
    nq = tests.loc[tests["day"].eq("event") & tests["instrument"].eq("NQ.v.0")
                   & tests["comparison"].eq("adaptive minus twap")].iloc[0]
    assert nq["mean_difference_bp"] < 0                 # skipping the wide-spread window is cheaper

    lt.part_d(features, books, spec, None)
    lt.part_e(features, predictions, books, None)
