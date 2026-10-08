"""Audit of strategies P2 (large move + stressed book -> follow) and P3 (large move + recovered book -> fade).

Why so few trades, is the backtest implemented correctly, and is there any predictive value?
Read-only with respect to the original test: it reads data/processed/fomc_strategy/features.parquet,
output/fomc_strategy_frozen_params.json and tables/fomc_strategy_trades.csv / _results.csv, and the
one-second book (scripts.extract_fomc_book_seconds.load("fomc")). It never writes the original
tables, parameters or registry, and does not change the locked strategy code.

Parts
 1 Trade-filter waterfall per strategy, instrument and sample (tables/audit_p2_p3_waterfall.csv).
 2 Correctness checks (tables/audit_p2_p3_checks.csv): frozen parameters re-estimated from
   development rows only; features rebuilt from book rows <= +5:00 match the stored features;
   features unchanged when every book row after +5:00 is corrupted; entry second > decision second;
   trade directions; recomputed trades match tables/fomc_strategy_trades.csv.
 3 Threshold grid (EXPLORATORY; tables/audit_p2_p3_threshold_grid.csv). Move and liquidity
   thresholds = development quantiles in {none, 0.50, 0.67, 0.75, 0.90}. Configuration chosen on
   development only by a rule fixed here: highest development t-statistic of the pooled
   (ES+NQ+ZN, per-event) executable mean among configurations with >= 20 development trades.
   The chosen configuration, the original (0.75, 0.75) and the price-only and no-filter anchors are
   then evaluated on 2023-2026 once. That holdout was already seen for the original configuration,
   so these holdout numbers are labelled exploratory, not a clean test.
 4 Conditional forward returns (tables/audit_p2_p3_forward.csv). Continuation =
   sign(ret 0->5 min) x return from +5:00 to +5:00 + h, h = 5, 10, 15, 30 minutes (mid, from the
   book), for event groups: all events, small moves, large moves, large + stressed (P2 set),
   large + not stressed, large + recovered (P3 set), large + not recovered. Plus the absolute
   forward move (magnitude), and the difference P2 set - large-not-stressed and P3 set -
   large-not-recovered with event-bootstrap CIs. The +30 horizon ends at +35:00, after the
   press-conference start (+30:00) on meetings that have one.
 5 Economic usefulness (tables/audit_p2_p3_economics.csv): gross mid return, executable bid/ask,
   fees (assumed USD 2.50 per contract per side, all-in), +1 tick slippage per side; influence of
   extreme events (drop largest one / two, 10% winsorized mean, share of PnL from top two events,
   PnL by year); directional vs magnitude correlations.
Figures in figures/audit_p2_p3/: waterfall, signal-space scatter with thresholds, forward
continuation by horizon, threshold-grid heatmaps, per-event PnL contributions.

Run: python -m scripts.audit_p2_p3
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.build_fomc_strategy_features import meetings as meeting_table
from scripts.extract_fomc_book_seconds import load as load_book
from src.strategies import fomc_signals as sig
from src.strategies.backtest import registry
from src.strategies.execution import MULTIPLIER, trade_returns
from src.strategies.fomc_features import (
    DECISION, FEATURE_COLUMNS, LATENCY, build_event_features, prepare,
)
from src.strategies.inference import event_bootstrap_mean, t_test
from src.utils.config import PROJECT_ROOT

DATA = PROJECT_ROOT / "data" / "processed" / "fomc_strategy"
PARAMS = PROJECT_ROOT / "output" / "fomc_strategy_frozen_params.json"
TABLES = PROJECT_ROOT / "tables"
FIG = PROJECT_ROOT / "figures" / "audit_p2_p3"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
COLORS = {"ES": "#2a78d6", "NQ": "#eb6834", "ZN": "#1baf7a", "pooled": "#444444"}
HORIZONS = {"5m": 600, "10m": 900, "15m": 1200, "30m": 2100}   # exit second; entry decision at +300
PRIMARY_EXIT = 1200                                            # the registered P2/P3 exit (+20:00)
FEE_USD_PER_SIDE = 2.50
QUANTILES = (None, 0.50, 0.67, 0.75, 0.90)
MIN_DEV_TRADES = 20
SAMPLES = ("development", "holdout", "full_sample")
STRATS = {"P2": ("stress", 1), "P3": ("recovery_score", -1)}   # liquidity score, direction vs first move


# ---------------------------------------------------------------- data

def book_points(book: pd.DataFrame) -> pd.DataFrame:
    """Mid, bid and ask at the seconds the audit needs, per event and instrument."""
    data = prepare(book)
    seconds = sorted({DECISION, DECISION + LATENCY, *HORIZONS.values()})
    pts = data.loc[data["second"].isin(seconds), ["id", "instrument", "second", "mid", "bid", "ask"]]
    wide = pts.pivot_table(index=["id", "instrument"], columns="second", values=["mid", "bid", "ask"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    return wide.reset_index().rename(columns={"id": "event_id"})


def assemble():
    features = pd.read_parquet(DATA / "features.parquet")
    params = json.loads(PARAMS.read_text())
    scored = sig.apply_params(features, params)
    book = load_book("fomc")
    scored = scored.merge(book_points(book), on=["event_id", "instrument"], how="left")
    for name, s in HORIZONS.items():
        scored[f"fwd_{name}"] = 1e4 * np.log(scored[f"mid_{s}"] / scored[f"mid_{DECISION}"])
        scored[f"cont_{name}"] = np.sign(scored["ret_0_5m"]) * scored[f"fwd_{name}"]
    return features, params, scored, book


# ---------------------------------------------------------------- 1 waterfall

def waterfall(scored: pd.DataFrame, params: dict) -> pd.DataFrame:
    n_meetings = len(meeting_table())
    rows = []
    for strat, (score, _) in STRATS.items():
        q_name = "stress_q75" if strat == "P2" else "recovery_score_q75"
        for inst in INSTRUMENTS:
            p = params["instruments"][inst]
            for sample in SAMPLES:
                f = scored.loc[scored["instrument"].eq(inst)]
                f = f if sample == "full_sample" else f.loc[f["sample"].eq(sample)]
                valid_move = f["ret_0_5m"].notna() & f["ret_0_5m"].ne(0)
                valid_liq = f[score].notna()
                large = valid_move & (f["abs_ret_0_5m"] >= p["move_q75"])
                liq = valid_liq & (f[score] >= p[q_name])
                both = large & liq
                execq = f[["bid_entry5", "ask_entry5", "bid_exit20m", "ask_exit20m"]].notna().all(axis=1)
                traded = both & execq
                events_in_sample = (f["event_id"].nunique() if sample != "full_sample" else n_meetings)
                rows.append({
                    "strategy": strat, "instrument": NAMES[inst], "sample": sample,
                    "meetings_in_config": n_meetings if sample == "full_sample" else np.nan,
                    "rows_with_book": len(f), "missing_or_zero_first_move": int((~valid_move).sum()),
                    "missing_liquidity_score": int((~valid_liq).sum()),
                    "pass_large_move": int(large.sum()), "pass_liquidity_condition": int(liq.sum()),
                    "pass_both": int(both.sum()), "dropped_no_execution_quote": int((both & ~execq).sum()),
                    "trades": int(traded.sum()),
                    "expected_if_independent": round(valid_move.sum() * 0.25 * 0.25, 1),
                    "spearman_absmove_vs_score": f.loc[valid_move & valid_liq, ["abs_ret_0_5m", score]]
                    .corr(method="spearman").iloc[0, 1],
                    "events_in_sample": events_in_sample,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2 checks

def checks(features: pd.DataFrame, params: dict, scored: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    out = []

    def add(name, ok, detail=""):
        out.append({"check": name, "passed": bool(ok), "detail": detail})

    dev = features.loc[features["sample"].eq("development")]
    re = sig.estimate_params(dev)
    diffs = [abs(re["instruments"][i][k] - v) for i, p in params["instruments"].items() for k, v in p.items()
             if isinstance(v, (int, float)) and np.isfinite(v)]
    diffs += [abs(re["cross"][k] - v) for k, v in params["cross"].items() if isinstance(v, (int, float)) and np.isfinite(v)]
    add("frozen parameters = re-estimate on development rows only", max(diffs) < 1e-9, f"max abs diff {max(diffs):.2e}")
    add("development rows all dated before 2023-01-01", (dev["event_date"] < "2023-01-01").all())
    same = json.dumps(sig.estimate_params(dev.copy()), sort_keys=True) == json.dumps(re, sort_keys=True)
    add("thresholds reproducible from development rows alone", same)

    meetings = meeting_table()
    rebuilt = build_event_features(book, meetings).set_index(["event_id", "instrument"]).sort_index()
    stored = features.set_index(["event_id", "instrument"]).sort_index()
    common = stored.index.intersection(rebuilt.index)
    a, b = stored.loc[common, FEATURE_COLUMNS], rebuilt.loc[common, FEATURE_COLUMNS]
    diff = float(np.nanmax(np.abs(a.to_numpy(float) - b.to_numpy(float))))
    add("stored features = features rebuilt from the book", diff < 1e-6, f"max abs diff {diff:.2e}")

    corrupted = book.copy()
    after = corrupted["second"] > DECISION
    corrupted.loc[after, ["bid_size", "ask_size"]] *= 37
    corrupted.loc[after, ["bid", "ask"]] *= 1.01
    c = build_event_features(corrupted, meetings).set_index(["event_id", "instrument"]).sort_index()
    diff2 = float(np.nanmax(np.abs(c.loc[common, FEATURE_COLUMNS].to_numpy(float) - b.to_numpy(float))))
    add("features unchanged when all book data after +5:00 is corrupted", diff2 < 1e-9, f"max abs diff {diff2:.2e}")
    add("entry second (+5:01) after decision second (+5:00)", DECISION + LATENCY > DECISION,
        f"decision {DECISION}s, entry {DECISION + LATENCY}s, exit {PRIMARY_EXIT}s")

    original = pd.read_csv(TABLES / "fomc_strategy_trades.csv")
    by_id = {s.strategy_id: s for s in registry()}
    for strat, (_, sign) in STRATS.items():
        legs = by_id[strat].rule(scored, params, entry="entry5", exit_="exit20m")
        orig = original.loc[original["strategy_id"].eq(strat)]
        same = set(zip(legs["event_id"], legs["instrument"])) == set(zip(orig["event_id"], orig["instrument"]))
        add(f"{strat}: recomputed trades = original trades", same, f"{len(legs)} recomputed vs {len(orig)} original")
        expected = sign * np.sign(scored.set_index(["event_id", "instrument"]).loc[
            list(zip(legs["event_id"], legs["instrument"])), "ret_0_5m"]).to_numpy()
        add(f"{strat}: trade direction = {'+' if sign > 0 else '-'}sign(first move)",
            np.array_equal(legs["direction"].to_numpy(), expected))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- shared trade evaluation

def _fees_bp(inst: pd.Series, price: pd.Series) -> pd.Series:
    return FEE_USD_PER_SIDE / (price * inst.map(MULTIPLIER)) * 1e4


def evaluate(rows: pd.DataFrame, direction: pd.Series, exit_second: int = PRIMARY_EXIT) -> pd.DataFrame:
    e = DECISION + LATENCY
    r = trade_returns(direction.to_numpy(), rows[f"bid_{e}"], rows[f"ask_{e}"], rows[f"mid_{e}"],
                      rows[f"bid_{exit_second}"], rows[f"ask_{exit_second}"], rows[f"mid_{exit_second}"],
                      rows["instrument"].to_numpy())
    r.index = rows.index
    out = rows[["event_id", "instrument", "sample", "event_date"]].copy()
    out["direction"] = direction
    out["signal_mid_bp"] = direction * 1e4 * np.log(rows[f"mid_{exit_second}"] / rows[f"mid_{DECISION}"])
    out["gross_bp"], out["executable_bp"], out["slip_bp"] = r["gross_bp"], r["executable_bp"], r["net_slip_bp"]
    out["fee_bp"] = 2 * _fees_bp(rows["instrument"], rows[f"mid_{e}"])
    out["net_fee_bp"] = out["executable_bp"] - out["fee_bp"]
    out["net_fee_slip_bp"] = out["slip_bp"] - out["fee_bp"]
    return out


def stats(values: pd.Series, events: pd.Series) -> dict:
    v = pd.Series(np.asarray(values, float)).groupby(np.asarray(events)).mean().dropna()
    if v.empty:
        return {"N": 0}
    t, p = t_test(v)
    lo, hi = event_bootstrap_mean(v)
    sd = v.std(ddof=1) if len(v) > 1 else np.nan
    return {"N": len(v), "mean": v.mean(), "median": v.median(), "win_rate": (v > 0).mean(),
            "sharpe_per_trade": v.mean() / sd if sd and sd > 0 else np.nan, "t_stat": t, "p_value": p,
            "CI_low": lo, "CI_high": hi}


# ---------------------------------------------------------------- 3 threshold grid

def dev_quantile(scored, col, q):
    if q is None:
        return pd.Series(-np.inf, index=scored.index)
    dev = scored.loc[scored["sample"].eq("development")]
    return scored["instrument"].map(dev.groupby("instrument")[col].quantile(q))


def _qlabel(q) -> str:
    return "none" if q is None else f"{q:.2f}"


def _grid_rows(scored, strat, qm, ql, samples):
    score, sign = STRATS[strat]
    keep = (scored["abs_ret_0_5m"] >= dev_quantile(scored, "abs_ret_0_5m", qm)) & \
           (scored[score] >= dev_quantile(scored, score, ql)) & scored["ret_0_5m"].ne(0) & \
           scored[["ret_0_5m", score]].notna().all(axis=1)
    legs = evaluate(scored.loc[keep], sign * np.sign(scored.loc[keep, "ret_0_5m"]))
    rows = []
    for inst in (*INSTRUMENTS, "pooled"):
        t = legs if inst == "pooled" else legs.loc[legs["instrument"].eq(inst)]
        for sample in samples:
            s = t.loc[t["sample"].eq(sample)]
            rows.append({"strategy": strat, "move_q": _qlabel(qm), "liquidity_q": _qlabel(ql),
                         "config": f"{_qlabel(qm)}/{_qlabel(ql)}", "instrument": NAMES.get(inst, inst),
                         "sample": sample, **stats(s["executable_bp"], s["event_id"]),
                         "mean_gross_bp": s["gross_bp"].mean(), "N_legs": len(s)})
    return rows


def grid(scored: pd.DataFrame) -> pd.DataFrame:
    """Development results for every configuration; holdout only for the configurations named in advance
    (selected on development by the fixed rule, the original, and two anchors). Holdout is exploratory."""
    rows = [r for strat in STRATS for qm in QUANTILES for ql in QUANTILES
            for r in _grid_rows(scored, strat, qm, ql, ("development",))]
    g = pd.DataFrame(rows)
    g["role"] = "exploratory (development only)"
    named = {"0.75/0.75": "original (baseline)", "0.75/none": "anchor: price only", "none/none": "anchor: every event"}
    holdout = []
    for strat in STRATS:
        dev = g.loc[g["strategy"].eq(strat) & g["instrument"].eq("pooled") & g["N"].ge(MIN_DEV_TRADES)]
        dev = dev.dropna(subset=["t_stat"])
        chosen = dict(named)
        if len(dev):
            best = dev.sort_values("t_stat", ascending=False).iloc[0]["config"]
            chosen[best] = ("selected on development; " + chosen[best]) if best in chosen else "selected on development"
        for config, role in chosen.items():
            g.loc[g["strategy"].eq(strat) & g["config"].eq(config), "role"] = role
            qm, ql = (None if x == "none" else float(x) for x in config.split("/"))
            holdout += [{**r, "role": role + " | holdout previously viewed: EXPLORATORY"}
                        for r in _grid_rows(scored, strat, qm, ql, ("holdout",))]
    return pd.concat([g, pd.DataFrame(holdout)], ignore_index=True)


# ---------------------------------------------------------------- 4 forward returns

def groups(scored: pd.DataFrame, params: dict) -> dict[str, pd.Series]:
    q = lambda key: scored["instrument"].map(lambda i: params["instruments"][i][key])   # noqa: E731
    large = scored["abs_ret_0_5m"] >= q("move_q75")
    stressed = scored["stress"] >= q("stress_q75")
    recovered = scored["recovery_score"] >= q("recovery_score_q75")
    valid = scored["ret_0_5m"].notna() & scored["ret_0_5m"].ne(0)
    return {"all events": valid, "small move": valid & ~large, "large move": valid & large,
            "large + stressed (P2 set)": valid & large & stressed,
            "large + not stressed": valid & large & ~stressed & scored["stress"].notna(),
            "large + recovered (P3 set)": valid & large & recovered,
            "large + not recovered": valid & large & ~recovered & scored["recovery_score"].notna()}


def forward(scored: pd.DataFrame, params: dict) -> pd.DataFrame:
    g = groups(scored, params)
    rows = []
    for sample in SAMPLES:
        s_mask = scored["sample"].eq(sample) if sample != "full_sample" else pd.Series(True, index=scored.index)
        for inst in (*INSTRUMENTS, "pooled"):
            i_mask = scored["instrument"].eq(inst) if inst != "pooled" else pd.Series(True, index=scored.index)
            for name, mask in g.items():
                f = scored.loc[mask & s_mask & i_mask]
                for h in HORIZONS:
                    c = stats(f[f"cont_{h}"], f["event_id"])
                    m = f[f"fwd_{h}"].abs().groupby(f["event_id"]).mean()
                    rows.append({"sample": sample, "instrument": NAMES.get(inst, inst), "group": name,
                                 "horizon": h, "N_events": c.get("N", 0), "mean_continuation_bp": c.get("mean"),
                                 "median_continuation_bp": c.get("median"), "share_continuing": c.get("win_rate"),
                                 "CI_low": c.get("CI_low"), "CI_high": c.get("CI_high"), "p_value": c.get("p_value"),
                                 "mean_abs_forward_bp": m.mean()})
            for a, b, label in (("large + stressed (P2 set)", "large + not stressed", "P2 set - large not stressed"),
                                ("large + recovered (P3 set)", "large + not recovered", "P3 set - large not recovered")):
                for h in HORIZONS:
                    x = scored.loc[g[a] & s_mask & i_mask].groupby("event_id")[f"cont_{h}"].mean().dropna()
                    y = scored.loc[g[b] & s_mask & i_mask].groupby("event_id")[f"cont_{h}"].mean().dropna()
                    lo, hi = _diff_ci(x, y)
                    rows.append({"sample": sample, "instrument": NAMES.get(inst, inst), "group": label, "horizon": h,
                                 "N_events": f"{len(x)} vs {len(y)}", "mean_continuation_bp": x.mean() - y.mean(),
                                 "CI_low": lo, "CI_high": hi})
    return pd.DataFrame(rows)


def _diff_ci(x, y, draws=5000, seed=20261008):
    if len(x) < 3 or len(y) < 3:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    d = rng.choice(x.to_numpy(), (draws, len(x))).mean(1) - rng.choice(y.to_numpy(), (draws, len(y))).mean(1)
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


# ---------------------------------------------------------------- 5 economics

def economics(scored: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = groups(scored, params)
    rows, legs_all = [], []
    for strat, (score, sign) in STRATS.items():
        mask = g["large + stressed (P2 set)"] if strat == "P2" else g["large + recovered (P3 set)"]
        legs = evaluate(scored.loc[mask], sign * np.sign(scored.loc[mask, "ret_0_5m"])).assign(strategy=strat)
        legs_all.append(legs)
        for inst in (*INSTRUMENTS, "pooled"):
            t = legs if inst == "pooled" else legs.loc[legs["instrument"].eq(inst)]
            for sample in SAMPLES:
                s = t if sample == "full_sample" else t.loc[t["sample"].eq(sample)]
                row = {"strategy": strat, "instrument": NAMES.get(inst, inst), "sample": sample}
                for col in ("signal_mid_bp", "gross_bp", "executable_bp", "net_fee_bp", "net_fee_slip_bp"):
                    st = stats(s[col], s["event_id"])
                    row[f"{col}_mean"] = st.get("mean")
                    row[f"{col}_CI"] = f"[{st.get('CI_low', np.nan):.1f}, {st.get('CI_high', np.nan):.1f}]"
                per = s.groupby("event_id")["executable_bp"].mean().dropna()
                row["N_events"] = len(per)
                row["cost_bp_round_trip"] = (s["gross_bp"] - s["executable_bp"]).mean()
                row["fee_bp_round_trip"] = s["fee_bp"].mean()
                if len(per):
                    order = per.abs().sort_values(ascending=False).index
                    row["mean_drop_largest"] = per.drop(order[:1]).mean() if len(per) > 1 else np.nan
                    row["mean_drop_top2"] = per.drop(order[:2]).mean() if len(per) > 2 else np.nan
                    lo, hi = per.quantile([0.1, 0.9])
                    row["winsorized_mean_10pct"] = per.clip(lo, hi).mean()
                    row["share_of_pnl_top2"] = per.loc[order[:2]].sum() / per.sum() if per.sum() else np.nan
                    row["pnl_by_year"] = "; ".join(f"{y}: {v:+.0f} ({n})" for y, (v, n) in
                                                   per.groupby(per.index.str[5:9]).agg(["sum", "count"]).iterrows())
                rows.append(row)
    # directional vs magnitude: does the liquidity score relate to the sign or only the size of what follows?
    for inst in INSTRUMENTS:
        f = scored.loc[scored["instrument"].eq(inst) & scored["ret_0_5m"].ne(0)]
        for score in ("stress", "recovery_score"):
            for h in HORIZONS:
                d = f[[score, f"cont_{h}", f"fwd_{h}"]].dropna()
                rows.append({"strategy": "direction_vs_magnitude", "instrument": NAMES[inst], "sample": "full_sample",
                             "score": score, "horizon": h, "N_events": len(d),
                             "spearman_score_vs_continuation": d[score].corr(d[f"cont_{h}"], method="spearman"),
                             "spearman_score_vs_abs_forward": d[score].corr(d[f"fwd_{h}"].abs(), method="spearman")})
    return pd.DataFrame(rows), pd.concat(legs_all, ignore_index=True)


# ---------------------------------------------------------------- figures

def figures(wf, scored, params, fw, gr, legs):
    FIG.mkdir(parents=True, exist_ok=True)
    steps = [("rows_with_book", "events with book"), ("pass_large_move", "large first move"),
             ("pass_liquidity_condition", "liquidity condition"), ("pass_both", "both"), ("trades", "trades")]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8), sharey=True)
    for ax, strat in zip(axes, STRATS):
        d = wf.loc[wf["strategy"].eq(strat) & wf["sample"].ne("full_sample")]
        for k, inst in enumerate(("ES", "NQ", "ZN")):
            for j, sample in enumerate(("development", "holdout")):
                r = d.loc[d["instrument"].eq(inst) & d["sample"].eq(sample)].iloc[0]
                x = np.arange(len(steps)) + (k * 2 + j - 2.5) * 0.13
                ax.bar(x, [r[c] for c, _ in steps], width=0.12, color=COLORS[inst], alpha=1 if j == 0 else 0.45,
                       label=f"{inst} {sample}")
        ax.set_xticks(range(len(steps)), [s for _, s in steps], fontsize=9)
        ax.set_title(f"{strat}: where events drop out (solid = 2015-2022, light = 2023-2026)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("events")
    axes[1].legend(frameon=False, fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(FIG / "fig1_waterfall.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for row, (strat, (score, _)) in enumerate(STRATS.items()):
        qkey = "stress_q75" if strat == "P2" else "recovery_score_q75"
        for ax, inst in zip(axes[row], INSTRUMENTS):
            f = scored.loc[scored["instrument"].eq(inst)]
            for sample, marker in (("development", "o"), ("holdout", "^")):
                s = f.loc[f["sample"].eq(sample)]
                col = np.where(s["cont_15m"] > 0, "#c0392b", "#1f5fa8")
                ax.scatter(s["abs_ret_0_5m"], s[score], c=col, marker=marker, s=24, alpha=0.75)
            p = params["instruments"][inst]
            ax.axvline(p["move_q75"], color="black", ls="--", lw=0.9)
            ax.axhline(p[qkey], color="black", ls="--", lw=0.9)
            ax.set_xscale("symlog", linthresh=5)
            ax.set_title(f"{strat} {NAMES[inst]}: trades = top-right box", fontsize=10)
            ax.set_xlabel("|return 0 -> +5 min| (bp)")
            ax.set_ylabel("stress score" if strat == "P2" else "recovery score")
            ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Signal space at +5:00. Red = move continued +5 -> +20 min, blue = reversed (after the fact). "
                 "Circles 2015-2022, triangles 2023-2026; dashed = frozen development thresholds")
    fig.tight_layout()
    fig.savefig(FIG / "fig2_signal_space.png", dpi=160)
    plt.close(fig)

    hz = list(HORIZONS)
    fig, axes = plt.subplots(1, 4, figsize=(19, 4.6), sharey=True)
    show = ["all events", "large + not stressed", "large + stressed (P2 set)", "large + recovered (P3 set)"]
    styles = dict(zip(show, ("#9a9a9a", "#e0a030", "#c0392b", "#1f5fa8")))
    for ax, inst in zip(axes, ("ES", "NQ", "ZN", "pooled")):
        for name in show:
            d = fw.loc[fw["sample"].eq("full_sample") & fw["instrument"].eq(inst) & fw["group"].eq(name)]
            d = d.set_index("horizon").reindex(hz)
            x = np.arange(len(hz)) + (show.index(name) - 1.5) * 0.08
            ax.errorbar(x, d["mean_continuation_bp"], yerr=[d["mean_continuation_bp"] - d["CI_low"],
                        d["CI_high"] - d["mean_continuation_bp"]], marker="o", capsize=3, color=styles[name],
                        label=f"{name}")
        ax.axhline(0, color="black", lw=0.6)
        ax.set_xticks(range(len(hz)), [f"+5 to +{5 + int(h[:-1])} min" for h in hz], fontsize=8)
        ax.set_title(inst)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("continuation of the first move (bp), 95% CI")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Momentum or reversal after +5:00? Mean continuation by group and horizon (all years; > 0 = continues)")
    fig.tight_layout()
    fig.savefig(FIG / "fig3_forward_continuation.png", dpi=160)
    plt.close(fig)

    labels = ["none" if q is None else f"{q:.2f}" for q in QUANTILES]
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    for row, strat in enumerate(STRATS):
        d = gr.loc[gr["strategy"].eq(strat) & gr["instrument"].eq("pooled") & gr["sample"].eq("development")]
        for ax, (val, title, cmap) in zip(axes[row], (("N", "development trades (events)", "Greys"),
                                                       ("mean", "development mean executable bp", "RdBu"))):
            m = np.full((len(QUANTILES), len(QUANTILES)), np.nan)
            for i, qm in enumerate(QUANTILES):
                for j, ql in enumerate(QUANTILES):
                    r = d.loc[d["config"].eq(f"{_qlabel(qm)}/{_qlabel(ql)}")]
                    m[i, j] = r[val].iloc[0] if len(r) else np.nan
            lim = np.nanmax(np.abs(m)) if val == "mean" else None
            im = ax.imshow(m, cmap=cmap, vmin=-lim if lim else None, vmax=lim)
            for i in range(len(QUANTILES)):
                for j in range(len(QUANTILES)):
                    if np.isfinite(m[i, j]):
                        ax.text(j, i, f"{m[i, j]:.0f}" if val == "N" else f"{m[i, j]:+.1f}", ha="center", va="center",
                                fontsize=8)
            ax.set_xticks(range(len(labels)), labels)
            ax.set_yticks(range(len(labels)), labels)
            ax.set_xlabel("liquidity threshold (development quantile)")
            ax.set_ylabel("move threshold (development quantile)")
            ax.set_title(f"{strat}: {title} (EXPLORATORY)", fontsize=10)
            fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_threshold_grid.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(15, 4.6))
    for ax, strat in zip(axes, STRATS):
        d = legs.loc[legs["strategy"].eq(strat)].sort_values("executable_bp")
        ax.bar(range(len(d)), d["executable_bp"], color=[COLORS[NAMES[i]] for i in d["instrument"]],
               edgecolor=np.where(d["sample"].eq("holdout"), "black", "none"))
        ax.set_xticks(range(len(d)), [f"{e[5:13]} {NAMES[i]}" for e, i in zip(d["event_id"], d["instrument"])],
                      rotation=90, fontsize=6)
        ax.axhline(0, color="black", lw=0.6)
        ax.set_ylabel("executable return (bp)")
        ax.set_title(f"{strat}: every trade, sorted (black edge = 2023-2026)")
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "fig5_trade_contributions.png", dpi=160)
    plt.close(fig)


def main() -> None:
    features, params, scored, book = assemble()
    TABLES.mkdir(exist_ok=True)
    wf = waterfall(scored, params)
    wf.to_csv(TABLES / "audit_p2_p3_waterfall.csv", index=False)
    ck = checks(features, params, scored, book)
    ck.to_csv(TABLES / "audit_p2_p3_checks.csv", index=False)
    gr = grid(scored)
    gr.to_csv(TABLES / "audit_p2_p3_threshold_grid.csv", index=False)
    fw = forward(scored, params)
    fw.to_csv(TABLES / "audit_p2_p3_forward.csv", index=False)
    ec, legs = economics(scored, params)
    ec.to_csv(TABLES / "audit_p2_p3_economics.csv", index=False)
    figures(wf, scored, params, fw, gr, legs)
    pd.set_option("display.width", 220)
    print("Checks:\n" + ck.to_string(index=False))
    print("\nWaterfall:\n" + wf.loc[wf["sample"].ne("full_sample"), ["strategy", "instrument", "sample", "rows_with_book",
          "pass_large_move", "pass_liquidity_condition", "pass_both", "trades", "expected_if_independent"]]
          .to_string(index=False))
    sel = gr.loc[~gr["role"].str.startswith("exploratory") & gr["instrument"].eq("pooled"),
                 ["strategy", "config", "role", "sample", "N", "mean", "median", "win_rate", "CI_low", "CI_high"]]
    print("\nThreshold grid, selected / baseline / anchors (pooled, executable bp):\n" + sel.round(2).to_string(index=False))
    print("\nWrote tables/audit_p2_p3_*.csv and figures/audit_p2_p3/")


if __name__ == "__main__":
    main()
