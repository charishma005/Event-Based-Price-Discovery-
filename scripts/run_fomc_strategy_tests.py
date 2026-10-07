"""Steps 5-16: integrity checks, registry, split, regressions, frozen parameters, backtests, holdout.

Order (as specified):
  5  data-integrity and no-look-ahead checks
  6  write and freeze output/strategy_registry.csv
  7  print the chronological development / holdout split
  8  continuous regressions (fitted on development; holdout and full shown alongside)
  9-10 estimate every threshold / z-score / beta on development only; freeze to
       output/fomc_strategy_frozen_params.json
  11 development backtests
  12 holdout, guarded by output/fomc_strategy_holdout.lock: the lock stores a hash of
     the registry, the frozen parameters and the strategy code. A rerun with the
     same hash reproduces the same numbers; any change to rules or parameters after
     the holdout has been seen is refused.
  13-14 executable costs, one-tick slippage and exit robustness (in the results)
  15 second-level microstructure regressions (development fit, holdout out-of-sample)
  16 tables in tables/

USMPD surprises and rate actions are not read by this script.

Run: python -m scripts.run_fomc_strategy_tests
"""

from __future__ import annotations

import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from src.strategies import fomc_signals as sig
from src.strategies.backtest import ES, NQ, ZN, evaluate, registry, registry_frame, summarize
from src.strategies.fomc_features import FEATURE_COLUMNS, INSTRUMENTS, TARGET_COLUMNS
from src.strategies.inference import ols_clustered
from src.utils.config import PROJECT_ROOT

DATA = PROJECT_ROOT / "data" / "processed" / "fomc_strategy"
OUTPUT = PROJECT_ROOT / "output"
TABLES = PROJECT_ROOT / "tables"
REGISTRY = OUTPUT / "strategy_registry.csv"
PARAMS = OUTPUT / "fomc_strategy_frozen_params.json"
LOCK = OUTPUT / "fomc_strategy_holdout.lock"
CODE = ("src/strategies/fomc_features.py", "src/strategies/fomc_signals.py", "src/strategies/execution.py",
        "src/strategies/backtest.py", "scripts/run_fomc_strategy_tests.py")
SAMPLES = ("development", "holdout", "full_sample")


# ---------------------------------------------------------------- step 5

def integrity_checks(features: pd.DataFrame) -> None:
    assert not set(FEATURE_COLUMNS) & set(TARGET_COLUMNS), "a target is listed as a feature"
    forbidden = [c for c in features.columns if any(k in c for k in ("STMT", "surprise", "policy_change", "action"))]
    assert not forbidden, f"ex-post columns present in the feature dataset: {forbidden}"
    dup = features.duplicated(["event_id", "instrument"]).sum()
    assert dup == 0, f"{dup} duplicate event x instrument rows"
    assert (features["sample"].eq("holdout") == (features["event_date"] >= pd.Timestamp("2023-01-01"))).all()
    for column in ("mid_entry5", "mid_exit20m"):
        bad = (features[column] <= 0).sum()
        assert bad == 0, f"{bad} non-positive {column}"
    print("Step 5: integrity checks passed "
          f"({len(features)} rows, {features['event_id'].nunique()} events, no target or ex-post column in features)")


# ---------------------------------------------------------------- step 8

def regressions(s: pd.DataFrame, samples: tuple[str, ...] = SAMPLES) -> pd.DataFrame:
    s = s.copy()
    s["abs_x_stress"] = s["abs_ret_0_5m"] * s["stress"]
    s["ret_x_stress"] = s["ret_0_5m"] * s["stress"]
    for score in ("stress_depth_only", "stress_spread_only"):
        s[f"abs_x_{score}"] = s["abs_ret_0_5m"] * s[score]
    s["abs_x_depth_slope"] = s["abs_ret_0_5m"] * s["depth_recovery_slope_1_5"]
    s["abs_x_spread_slope"] = s["abs_ret_0_5m"] * s["spread_recovery_slope_1_5"]
    specs = [("A_price_only", "continuation_5_20", ["abs_ret_0_5m"]),
             ("B_liquidity_only", "continuation_5_20", ["stress"]),
             ("C_price_plus_liquidity", "continuation_5_20", ["abs_ret_0_5m", "stress"]),
             ("D_interaction", "continuation_5_20", ["abs_ret_0_5m", "stress", "abs_x_stress"]),
             ("signed_interaction", "ret_5_20m", ["ret_0_5m", "stress", "ret_x_stress"]),
             ("first_move_predicts_next", "ret_5_20m", ["ret_0_5m"]),
             ("C_depth_only", "continuation_5_20", ["abs_ret_0_5m", "stress_depth_only"]),
             ("D_depth_only", "continuation_5_20", ["abs_ret_0_5m", "stress_depth_only", "abs_x_stress_depth_only"]),
             ("C_spread_only", "continuation_5_20", ["abs_ret_0_5m", "stress_spread_only"]),
             ("D_spread_only", "continuation_5_20", ["abs_ret_0_5m", "stress_spread_only", "abs_x_stress_spread_only"]),
             ("S4_recovery_speed", "continuation_5_20",
              ["abs_ret_0_5m", "depth_recovery_slope_1_5", "spread_recovery_slope_1_5",
               "abs_x_depth_slope", "abs_x_spread_slope"])]
    for var in ("depth_ratio_5m", "spread_ratio_5m", "depth_recovery_1_5", "spread_recovery_1_5",
                "depth_recovery_slope_1_5", "spread_recovery_slope_1_5"):
        specs.append((f"univariate_{var}", "continuation_5_20", [var]))
        specs.append((f"with_price_{var}", "continuation_5_20", ["abs_ret_0_5m", var]))
    for horizon in ("5_10", "5_30"):
        for name, _, xs in specs[:4]:
            specs.append((f"{name}_robust_{horizon}", f"continuation_{horizon}", xs))
    rows = []
    for sample in samples:
        sub = s if sample == "full_sample" else s.loc[s["sample"].eq(sample)]
        for instrument in INSTRUMENTS:
            f = sub.loc[sub["instrument"].eq(instrument)]
            for name, y, xs in specs:
                rows.append(ols_clustered(f, y, xs).assign(model=name, y=y, instrument=instrument, sample=sample))
        for name, y, xs in specs[:5]:
            rows.append(ols_clustered(sub, y, xs, fixed_effects="instrument")
                        .assign(model=f"{name}_pooled_FE", y=y, instrument="pooled", sample=sample))
        zn = sub.loc[sub["instrument"].eq(ZN)].copy()
        zn["abs_x_depth10"] = zn["abs_ret_0_5m"] * zn["depth_ratio_10m"]
        rows.append(ols_clustered(zn, "continuation_10_20",
                                  ["abs_ret_0_5m", "depth_ratio_10m", "depth_recovery_1_10", "spread_recovery_1_10",
                                   "abs_x_depth10"]).assign(model="S9_zn_replenishment", y="continuation_10_20",
                                                            instrument=ZN, sample=sample))
        rows.append(relative_value_regression(sub).assign(sample=sample))
    out = pd.concat(rows, ignore_index=True)
    first = ["sample", "instrument", "model", "y", "term", "coef", "se", "t_stat", "p_value", "ci_low", "ci_high",
             "r2", "N", "N_events", "dropped_constant"]
    return out[[c for c in first if c in out]]


def relative_value_regression(s: pd.DataFrame) -> pd.DataFrame:
    """Does the +5m NQ-vs-ES residual (development beta) converge by +20m? Interaction with relative recovery."""
    c = PARAMS_CACHE["cross"]
    wide = {k: s.pivot_table(index="event_id", columns="instrument", values=k)
            for k in ("ret_0_5m", "ret_5_20m", "recovery_score")}
    if not {ES, NQ} <= set(wide["ret_0_5m"]):
        return pd.DataFrame()
    frame = pd.DataFrame({
        "resid_5m": wide["ret_0_5m"][NQ] - (c["es_nq_alpha"] + c["es_nq_beta"] * wide["ret_0_5m"][ES]),
        "rv_5_20": wide["ret_5_20m"][NQ] - c["es_nq_beta"] * wide["ret_5_20m"][ES],
        "rel_recovery": wide["recovery_score"][NQ] - wide["recovery_score"][ES],
    }).reset_index()
    frame["resid_x_rel_recovery"] = frame["resid_5m"] * frame["rel_recovery"]
    return ols_clustered(frame, "rv_5_20", ["resid_5m", "rel_recovery", "resid_x_rel_recovery"]).assign(
        model="S7_relative_value_convergence", y="rv_5_20 (NQ - beta x ES, +5 to +20)", instrument="ES|NQ")


# ---------------------------------------------------------------- steps 11-14

def run_backtests(s: pd.DataFrame, params: dict, samples: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = s.drop_duplicates("event_id").set_index("event_id")["event_date"]
    rows, legs_all = [], []
    for strategy in registry():
        trades = strategy.rule(s, params, entry=strategy.entry, exit_=strategy.exit)
        legs = evaluate(trades, s)
        legs["strategy_id"] = strategy.strategy_id
        legs_all.append(legs)
        for sample in samples:
            in_sample = s if sample == "full_sample" else s.loc[s["sample"].eq(sample)]
            leg_sample = legs if sample == "full_sample" else legs.loc[legs["sample"].eq(sample)]
            groups = [(i[:2], [i]) for i in strategy.instruments]
            if len(strategy.instruments) > 1:
                groups.append(("portfolio", strategy.instruments))
            for label, instruments in groups:
                chosen = leg_sample.loc[leg_sample["instrument"].isin(instruments)]
                n_events = in_sample.loc[in_sample["instrument"].isin(instruments), "event_id"].nunique()
                rows.append({"strategy": strategy.strategy_id, "strategy_name": strategy.name, "role": strategy.role,
                             "instrument": label, "sample": sample, "entry_time": strategy.entry_time,
                             "exit_time": strategy.exit_time, **summarize(chosen, n_events, dates)})
    return pd.DataFrame(rows), pd.concat(legs_all, ignore_index=True)


# ---------------------------------------------------------------- step 15

def microstructure(seconds: pd.DataFrame, dev_events: set[str]) -> pd.DataFrame:
    rows = []
    seconds = seconds.assign(sample=np.where(seconds["event_id"].isin(dev_events), "development", "holdout"))
    for instrument, g in seconds.groupby("instrument"):
        dev, hold = g.loc[g["sample"].eq("development")], g.loc[g["sample"].eq("holdout")]
        for lead in (5, 30, 60):
            y = f"fut_ret_{lead}s"
            for k in (5, 10, 30, 60):
                models = {"levels": ["depth", "bid_depth", "ask_depth", "imbalance", "spread", f"past_ret_{k}s"],
                          "changes": [f"d_depth_{k}s", f"d_bid_depth_{k}s", f"d_ask_depth_{k}s",
                                      f"d_imbalance_{k}s", f"d_spread_{k}s", f"past_ret_{k}s"]}
                for model, xs in models.items():
                    if model == "levels" and k != 5:
                        continue     # levels do not depend on the lookback except through past_ret
                    fit = ols_clustered(dev, y, xs)
                    oos = _oos_r2(fit, hold, y, xs)
                    rows.append(fit.assign(instrument=instrument, horizon_s=lead, lookback_s=k, model=model,
                                           fit_sample="development", r2_oos_holdout=oos))
    return pd.concat(rows, ignore_index=True)


def _oos_r2(fit: pd.DataFrame, hold: pd.DataFrame, y: str, xs: list[str]) -> float:
    if "coef" not in fit or hold.empty:
        return np.nan
    coef = fit.set_index("term")["coef"]
    data = hold[[y, *xs]].replace([np.inf, -np.inf], np.nan).dropna()
    if data.empty:
        return np.nan
    pred = coef["const"] + sum(coef.get(x, 0.0) * data[x] for x in xs)
    sse = ((data[y] - pred) ** 2).sum()
    sst = ((data[y] - 0.0) ** 2).sum()        # benchmark: no predictability (zero expected return)
    return float(1 - sse / sst) if sst > 0 else np.nan


# ---------------------------------------------------------------- holdout guard

def _hash() -> str:
    digest = hashlib.sha256()
    for path in (REGISTRY, PARAMS, *(PROJECT_ROOT / c for c in CODE)):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def holdout_guard(override: bool) -> None:
    current = _hash()
    if LOCK.exists():
        recorded = json.loads(LOCK.read_text())["sha256"]
        if recorded != current and not override:
            raise SystemExit(
                "Holdout already run with a different registry / parameters / strategy code.\n"
                "Changing rules after seeing the holdout is not allowed. Restore the frozen version, or rerun with\n"
                "--override-holdout-lock (the override is recorded in the lock file and the report).")
        if recorded != current:
            history = json.loads(LOCK.read_text()).get("overrides", []) + [recorded]
            LOCK.write_text(json.dumps({"sha256": current, "overrides": history}, indent=2))
            print("WARNING: holdout lock overridden; recorded.")
        else:
            print("Holdout lock matches the frozen specification: reproducing the same holdout run.")
    else:
        LOCK.write_text(json.dumps({"sha256": current, "overrides": []}, indent=2))
        print("Holdout lock written: the specification is now frozen.")


PARAMS_CACHE: dict = {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--development-only", action="store_true", help="Stop after the development backtests")
    parser.add_argument("--override-holdout-lock", action="store_true")
    parser.add_argument("--skip-microstructure", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    TABLES.mkdir(exist_ok=True)

    features = pd.read_parquet(DATA / "features.parquet")
    integrity_checks(features)                                                       # step 5

    registry_frame(registry()).to_csv(REGISTRY, index=False)                         # step 6
    print(f"Step 6: registered {len(registry())} strategy specifications in {REGISTRY.relative_to(PROJECT_ROOT)}")

    dev = features.loc[features["sample"].eq("development")]                         # step 7
    hold = features.loc[features["sample"].eq("holdout")]
    print(f"Step 7: development {dev['event_date'].min():%Y-%m-%d} to {dev['event_date'].max():%Y-%m-%d}, "
          f"{dev['event_id'].nunique()} events | holdout {hold['event_date'].min():%Y-%m-%d} to "
          f"{hold['event_date'].max():%Y-%m-%d}, {hold['event_id'].nunique()} events")

    params = sig.estimate_params(dev)                                                # steps 9-10
    sig.save_params(params, PARAMS)
    PARAMS_CACHE.update(params)
    thresholds = [{"scope": scope, "instrument": inst, "parameter": k, "value": v}
                  for scope, block in (("instrument", params["instruments"]),)
                  for inst, p in block.items() for k, v in p.items()]
    thresholds += [{"scope": "cross", "instrument": "", "parameter": k, "value": v} for k, v in params["cross"].items()]
    pd.DataFrame(thresholds).to_csv(TABLES / "fomc_strategy_thresholds.csv", index=False)
    print(f"Steps 9-10: {len(thresholds)} parameters estimated on development and frozen in "
          f"{PARAMS.relative_to(PROJECT_ROOT)}")

    scored = sig.apply_params(features, params)
    if args.development_only:                                                        # steps 8, 11 (development)
        regressions(scored, ("development",)).to_csv(TABLES / "fomc_strategy_regressions_development_only.csv",
                                                     index=False)
        results, _ = run_backtests(scored, params, ("development",))
        results.to_csv(TABLES / "fomc_strategy_results_development_only.csv", index=False)
        print("Steps 8 and 11: development regressions and backtests written (*_development_only.csv); "
              "holdout not touched")
        return

    holdout_guard(args.override_holdout_lock)                                        # step 12 gate
    reg = regressions(scored)                                                        # step 8
    reg.to_csv(TABLES / "fomc_strategy_regressions.csv", index=False)
    print(f"Step 8: {reg['model'].nunique()} regression specifications x instruments x samples written "
          "(fitted separately on development, holdout and full sample)")
    results, legs = run_backtests(scored, params, SAMPLES)
    print("Step 12: holdout evaluated once with the frozen specification")
    results.to_csv(TABLES / "fomc_strategy_results.csv", index=False)
    legs.to_csv(TABLES / "fomc_strategy_trades.csv", index=False)

    costs = results[["strategy", "instrument", "sample", "N_trades", "avg_gross_return", "avg_executable_return",
                     "avg_net_return", "avg_net_slip_return"]].copy()                 # steps 13-14
    costs["cost_drag_bp"] = costs["avg_gross_return"] - costs["avg_executable_return"]
    costs["survives_executable"] = costs["avg_executable_return"] > 0
    costs["survives_one_tick_slippage"] = costs["avg_net_slip_return"] > 0
    costs.to_csv(TABLES / "fomc_strategy_cost_robustness.csv", index=False)
    primary = results.loc[results["strategy"].isin(["P1", "P2", "P3"]) & results["instrument"].isin(["ES", "NQ", "ZN"])]
    primary.pivot_table(index=["instrument", "sample"], columns="strategy",
                        values=["N_trades", "avg_net_return", "CI_low", "CI_high", "hit_rate"]).to_csv(
        TABLES / "fomc_strategy_instrument_comparison.csv")
    print("Steps 13-14: costs, slippage and exit robustness written")

    if not args.skip_microstructure:                                                 # step 15
        seconds = pd.read_parquet(DATA / "seconds.parquet")
        micro = microstructure(seconds, set(dev["event_id"]))
        micro.to_csv(TABLES / "fomc_microstructure_predictability.csv", index=False)
        print("Step 15: second-level microstructure regressions written")
    print("Step 16: tables written to tables/fomc_strategy_*.csv and tables/fomc_microstructure_predictability.csv")


if __name__ == "__main__":
    main()
