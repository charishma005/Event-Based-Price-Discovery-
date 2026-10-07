"""The strategy pipeline cannot see the future, the holdout or USMPD."""

import ast
import inspect

import numpy as np
import pandas as pd
import pytest

from scripts import run_fomc_strategy_tests as run
from src.strategies import fomc_signals as sig
from src.strategies.backtest import registry
from src.strategies.fomc_features import (
    DECISION, FEATURE_COLUMNS, TARGET_COLUMNS, ZN_DECISION, build_event_features, decision_features, prepare,
)
from tests.strategy_synthetic import synthetic_book


@pytest.fixture(scope="module")
def book():
    return synthetic_book(n_dev=20, n_hold=8, last=1860)


@pytest.fixture(scope="module")
def features(book):
    return build_event_features(*book)


def test_decision_features_refuse_future_rows(book):
    g = prepare(book[0].loc[book[0]["id"].eq(book[0]["id"].iloc[0]) & book[0]["instrument"].eq("ES.v.0")])
    with pytest.raises(ValueError):
        decision_features(g, DECISION)


def test_corrupting_the_future_leaves_features_unchanged(book):
    raw, meetings = book
    corrupted = raw.copy()
    after = corrupted["second"] > DECISION
    zn_after = corrupted["instrument"].eq("ZN.v.0") & corrupted["second"].gt(ZN_DECISION)
    rng = np.random.default_rng(1)
    for column in ("bid", "ask"):
        corrupted.loc[after, column] *= rng.uniform(0.9, 1.1, after.sum())
    corrupted.loc[after, "ask"] = np.maximum(corrupted.loc[after, "ask"], corrupted.loc[after, "bid"] + 1)
    corrupted.loc[after, ["bid_size", "ask_size"]] *= 50
    a = build_event_features(raw, meetings).set_index(["event_id", "instrument"]).sort_index()
    b = build_event_features(corrupted, meetings).set_index(["event_id", "instrument"]).sort_index()
    pd.testing.assert_frame_equal(a[FEATURE_COLUMNS], b[FEATURE_COLUMNS])
    # ZN +10m features may use (5, 10] minutes but nothing after +10:00
    corrupted_zn = raw.copy()
    corrupted_zn.loc[zn_after, ["bid_size", "ask_size"]] *= 50
    c = build_event_features(corrupted_zn, meetings).set_index(["event_id", "instrument"]).sort_index()
    pd.testing.assert_frame_equal(a[FEATURE_COLUMNS + ["depth_ratio_10m", "spread_ratio_10m"]],
                                  c[FEATURE_COLUMNS + ["depth_ratio_10m", "spread_ratio_10m"]])
    assert not np.allclose(a["ret_5_20m"], b["ret_5_20m"])   # sanity: targets did change


def test_no_target_or_usmpd_column_is_a_feature():
    banned = ("ret_5_", "ret_10_", "continuation", "exit", "STMT", "PC", "surprise", "action")
    assert not [c for c in FEATURE_COLUMNS if any(b in c for b in banned)]
    assert not set(FEATURE_COLUMNS) & set(TARGET_COLUMNS)


def _code_without_docstrings(module) -> str:
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_signal_code_reads_no_target_or_usmpd():
    code = _code_without_docstrings(sig)
    for banned in ("ret_5_", "ret_10_", "continuation", "STMT", "surprise", "usmpd", "meeting_groups",
                   "bid_exit", "ask_exit", "mid_exit"):
        assert banned not in code, banned


def test_estimate_params_rejects_holdout_rows(features):
    with pytest.raises(ValueError):
        sig.estimate_params(features)


def test_params_ignore_holdout_and_future_values(features):
    dev = features.loc[features["sample"].eq("development")]
    base = sig.estimate_params(dev)
    shocked = dev.copy()
    for column in TARGET_COLUMNS + [c for c in dev if c.startswith(("bid_exit", "ask_exit", "mid_exit"))]:
        shocked[column] = shocked[column] * -7 + 3
    assert sig.estimate_params(shocked) == base
    # parameters depend only on development rows, whatever the holdout looks like
    hold = features.loc[features["sample"].eq("holdout")].copy()
    hold["ret_0_5m"] *= 100
    assert sig.estimate_params(pd.concat([dev, hold]).query("sample == 'development'")) == base


def test_trades_do_not_depend_on_targets(features):
    params = sig.estimate_params(features.loc[features["sample"].eq("development")])
    scored = sig.apply_params(features, params)
    shocked = scored.copy()
    for column in TARGET_COLUMNS:
        shocked[column] = np.random.default_rng(2).normal(size=len(shocked))
    for strategy in registry():
        a = strategy.rule(scored, params, entry=strategy.entry, exit_=strategy.exit)
        b = strategy.rule(shocked, params, entry=strategy.entry, exit_=strategy.exit)
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_holdout_trades_use_frozen_development_thresholds(features):
    params = sig.estimate_params(features.loc[features["sample"].eq("development")])
    scored = sig.apply_params(features, params)
    trades = registry()[0].rule(scored, params, entry="entry5", exit_="exit20m")
    hold = scored.loc[scored["sample"].eq("holdout")]
    q = hold["instrument"].map(lambda i: params["instruments"][i]["move_q75"])
    expected = hold.loc[hold["abs_ret_0_5m"] >= q, ["event_id", "instrument"]]
    got = trades.loc[trades["sample"].eq("holdout"), ["event_id", "instrument"]]
    assert set(map(tuple, expected.to_numpy())) == set(map(tuple, got.to_numpy()))


def test_holdout_lock_refuses_changed_specification(tmp_path, monkeypatch):
    code = tmp_path / "rule.py"
    code.write_text("x = 1\n")
    registry_csv, params_json = tmp_path / "registry.csv", tmp_path / "params.json"
    registry_csv.write_text("a\n")
    params_json.write_text("{}")
    monkeypatch.setattr(run, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(run, "CODE", ("rule.py",))
    monkeypatch.setattr(run, "REGISTRY", registry_csv)
    monkeypatch.setattr(run, "PARAMS", params_json)
    monkeypatch.setattr(run, "LOCK", tmp_path / "holdout.lock")
    run.holdout_guard(override=False)            # first run writes the lock
    run.holdout_guard(override=False)            # same specification: allowed
    params_json.write_text('{"move_q75": 1}')    # change a frozen parameter after the holdout
    with pytest.raises(SystemExit):
        run.holdout_guard(override=False)
    run.holdout_guard(override=True)             # explicit override is recorded
    assert len(__import__("json").loads((tmp_path / "holdout.lock").read_text())["overrides"]) == 1
