"""Steps 17-18: figures and reports/fomc_trading_strategy_results.md.

Reads only outputs of build_fomc_strategy_features and run_fomc_strategy_tests. The
USMPD surprise appears in one clearly separated ex-post section at the end and is
never used by any strategy.

Classification rule (fixed before any results were seen):
  SUPPORTED      executable mean > 0 in development AND holdout, holdout has >= 3 trades,
                 AND the full-sample event-bootstrap 95% CI of the executable mean is above 0
  WEAK EVIDENCE  executable mean > 0 in both development and holdout, but the CI includes 0
                 (or fewer than 3 holdout trades)
  NOT SUPPORTED  anything else
(Fees are ignored for now, so executable = net.)

Run: python -m scripts.make_fomc_strategy_report
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.strategies import fomc_signals as sig
from src.strategies.backtest import registry
from src.strategies.inference import event_bootstrap_mean
from src.utils.config import PROJECT_ROOT

DATA = PROJECT_ROOT / "data" / "processed" / "fomc_strategy"
TABLES = PROJECT_ROOT / "tables"
OUTPUT = PROJECT_ROOT / "output"
FIG = PROJECT_ROOT / "figures" / "fomc_strategy"
REPORT = PROJECT_ROOT / "reports" / "fomc_trading_strategy_results.md"
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
COLORS = {"ES": "#2a78d6", "NQ": "#eb6834", "ZN": "#1baf7a", "portfolio": "#555555"}


def load():
    features = pd.read_parquet(DATA / "features.parquet")
    params = json.loads((OUTPUT / "fomc_strategy_frozen_params.json").read_text())
    scored = sig.apply_params(features, params)
    scored["inst"] = scored["instrument"].map(NAMES)
    t = {name: pd.read_csv(TABLES / f"fomc_{name}.csv") for name in
         ("strategy_results", "strategy_regressions", "strategy_thresholds", "strategy_cost_robustness",
          "strategy_trades")}
    micro_path = TABLES / "fomc_microstructure_predictability.csv"
    t["micro"] = pd.read_csv(micro_path) if micro_path.exists() else pd.DataFrame()
    paths = pd.read_parquet(DATA / "minute_paths.parquet")
    return scored, params, t, paths


def classify(results: pd.DataFrame, strategy: str, instrument: str) -> str:
    r = results.loc[results["strategy"].eq(strategy) & results["instrument"].eq(instrument)].set_index("sample")
    if not {"development", "holdout", "full_sample"} <= set(r.index):
        return "NOT SUPPORTED"
    dev, hold, full = (r.loc[k] for k in ("development", "holdout", "full_sample"))
    dev_ok = dev.get("avg_executable_return", np.nan) > 0
    hold_ok = hold.get("avg_executable_return", np.nan) > 0
    enough = hold.get("N_trades", 0) >= 3
    if dev_ok and hold_ok and enough and full.get("CI_low", np.nan) > 0:
        return "SUPPORTED"
    if dev_ok and hold_ok:
        return "WEAK EVIDENCE"
    return "NOT SUPPORTED"


# ---------------------------------------------------------------- figures

def _save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=160)
    plt.close(fig)


def _scatter(ax, f, x, y, inst):
    for sample, marker in (("development", "o"), ("holdout", "^")):
        d = f.loc[f["sample"].eq(sample)]
        ax.scatter(d[x], d[y], s=22, marker=marker, alpha=0.7, color=COLORS[inst], label=sample,
                   facecolors="none" if sample == "holdout" else COLORS[inst])
    d = f[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) > 5:
        b, a = np.polyfit(d[x], d[y], 1)
        xs = np.linspace(d[x].min(), d[x].max(), 50)
        ax.plot(xs, a + b * xs, color="black", lw=1)
    ax.axhline(0, color="grey", lw=0.6)


def figures(s, params, t, paths):
    for inst in ("ES", "NQ", "ZN"):                                                   # 1-3
        fig, ax = plt.subplots(figsize=(6, 4.5))
        _scatter(ax, s.loc[s["inst"].eq(inst)], "stress", "continuation_5_20", inst)
        ax.set_xlabel("liquidity_stress_5m (development z-scores)")
        ax.set_ylabel("continuation +5 -> +20 min (bp)")
        ax.set_title(f"{inst}: continuation vs liquidity stress at +5 min")
        ax.legend(frameon=False, fontsize=8)
        _save(fig, f"fig01_continuation_vs_stress_{inst}.png")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))                                   # 4
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        _scatter(ax, s.loc[s["inst"].eq(inst)], "depth_ratio_5m", "continuation_5_20", inst)
        ax.set_title(inst)
        ax.set_xlabel("depth_ratio_5m")
    axes[0].set_ylabel("continuation +5 -> +20 min (bp)")
    _save(fig, "fig04_continuation_vs_depth_ratio.png")

    s = s.copy()
    stressed = s["stress"] >= s["instrument"].map(lambda i: params["instruments"][i]["stress_q75"])
    recovered = s["recovery_score"] >= s["instrument"].map(lambda i: params["instruments"][i]["recovery_score_q75"])
    s["state"] = np.select([stressed, recovered], ["stressed", "recovered"], "other")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))                                   # 5
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        f = s.loc[s["inst"].eq(inst)]
        for state, color in (("stressed", "#c0392b"), ("recovered", "#1f5fa8"), ("other", "#aaaaaa")):
            d = f.loc[f["state"].eq(state)]
            ax.scatter(d["ret_0_5m"], d["ret_5_20m"], s=20, color=color, label=state, alpha=0.8)
        ax.axhline(0, color="grey", lw=0.6)
        ax.axvline(0, color="grey", lw=0.6)
        ax.set_title(inst)
        ax.set_xlabel("ret 0 -> +5 min (bp)")
    axes[0].set_ylabel("ret +5 -> +20 min (bp)")
    axes[0].legend(frameon=False, fontsize=8)
    _save(fig, "fig05_initial_vs_future_by_liquidity_state.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))                                            # 6
    groups = [("large + stressed", s["large_move"] & s["state"].eq("stressed")),
              ("large + recovered", s["large_move"] & s["state"].eq("recovered")),
              ("other", ~(s["large_move"] & s["state"].isin(["stressed", "recovered"])))]
    for k, inst in enumerate(("ES", "NQ", "ZN")):
        for j, (label, mask) in enumerate(groups):
            d = s.loc[mask & s["inst"].eq(inst), "continuation_5_20"].dropna()
            lo, hi = event_bootstrap_mean(d)
            x = k * 4 + j
            ax.bar(x, d.mean() if len(d) else 0, color=["#c0392b", "#1f5fa8", "#aaaaaa"][j], width=0.8)
            if np.isfinite(lo):
                ax.vlines(x, lo, hi, color="black")
            ax.text(x, 0, f"n={len(d)}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks([1, 5, 9], ["ES", "NQ", "ZN"])
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("mean continuation +5 -> +20 (bp), 95% bootstrap CI")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in ("#c0392b", "#1f5fa8", "#aaaaaa")],
              labels=[g[0] for g in groups], frameon=False, fontsize=8)
    ax.set_title("Continuation by liquidity state (full sample; states from frozen development thresholds)")
    _save(fig, "fig06_continuation_by_state.png")

    r = t["strategy_results"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)                      # 7
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        for j, strat in enumerate(("P1", "P2", "P3")):
            for k, sample in enumerate(("development", "holdout")):
                row = r.loc[r["strategy"].eq(strat) & r["instrument"].eq(inst) & r["sample"].eq(sample)]
                v = row["avg_net_return"].iloc[0] if len(row) and "avg_net_return" in row else np.nan
                n = int(row["N_trades"].iloc[0]) if len(row) else 0
                x = j * 3 + k
                ax.bar(x, 0 if pd.isna(v) else v, color=["#7f8c8d", "#c0392b", "#1f5fa8"][j],
                       alpha=1 if sample == "development" else 0.5)
                ax.text(x, 0, f"n={n}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks([0.5, 3.5, 6.5], ["P1 price only", "P2 +stress", "P3 recovery fade"])
        ax.axhline(0, color="black", lw=0.6)
        ax.set_title(f"{inst} (solid = development, light = holdout)")
    axes[0].set_ylabel("mean executable return per trade (bp)")
    _save(fig, "fig07_price_only_vs_price_liquidity.png")

    main_rows = r.loc[r["instrument"].isin(["ES", "NQ", "ZN", "portfolio"])]            # 8
    wide = main_rows.pivot_table(index=["strategy", "instrument"], columns="sample", values="avg_net_return")
    fig, ax = plt.subplots(figsize=(7, 6))
    for (strat, inst), row in wide.iterrows():
        ax.scatter(row.get("development"), row.get("holdout"), color=COLORS.get(inst, "#555"), s=25)
        ax.annotate(f"{strat}-{inst}", (row.get("development"), row.get("holdout")), fontsize=6)
    lim = np.nanmax(np.abs(wide[["development", "holdout"]].to_numpy())) if wide.size else 1
    ax.plot([-lim, lim], [-lim, lim], color="grey", lw=0.6, ls=":")
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlabel("development mean executable return (bp)")
    ax.set_ylabel("holdout mean executable return (bp)")
    ax.set_title("Every registered strategy: development vs holdout")
    _save(fig, "fig08_development_vs_holdout.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))                                            # 9
    for j, strat in enumerate(("P1", "P2", "P3")):
        for k, inst in enumerate(("ES", "NQ", "ZN")):
            row = r.loc[r["strategy"].eq(strat) & r["instrument"].eq(inst) & r["sample"].eq("full_sample")]
            if not len(row) or pd.isna(row.get("avg_net_return", pd.Series([np.nan])).iloc[0]):
                continue
            x = j * 4 + k
            ax.bar(x, row["avg_net_return"].iloc[0], color=COLORS[inst])
            ax.vlines(x, row["CI_low"].iloc[0], row["CI_high"].iloc[0], color="black")
    ax.set_xticks([1, 5, 9], ["P1 price only", "P2 + stress", "P3 recovery fade"])
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("mean executable return (bp), full sample, 95% CI")
    ax.set_title("ES (blue) vs NQ (orange) vs ZN (green)")
    _save(fig, "fig09_instrument_comparison.png")

    trades = t["strategy_trades"].copy()                                                # 10
    dates = s.drop_duplicates("event_id").set_index("event_id")["event_date"]
    trades["event_date"] = trades["event_id"].map(dates)
    strategies = list(dict.fromkeys(trades["strategy_id"]))
    cols = 4
    fig, axes = plt.subplots(int(np.ceil(len(strategies) / cols)), cols, figsize=(16, 2.6 * np.ceil(len(strategies) / cols)),
                             squeeze=False)
    for ax, strat in zip(axes.flat, strategies):
        d = trades.loc[trades["strategy_id"].eq(strat)]
        w = d["weight"] / d.groupby("event_id")["weight"].transform("sum")
        per = (d["net_bp"] * w).groupby(d["event_date"]).sum().sort_index().cumsum()
        ax.plot(per.index, per.values, color="#333333", lw=1.2)
        ax.axvspan(pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31"), color="#f3d9a4", alpha=0.4)
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_title(strat, fontsize=9)
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[len(strategies):]:
        ax.axis("off")
    fig.suptitle("Cumulative executable PnL per event (bp); shaded = holdout. Every registered strategy.")
    _save(fig, "fig10_cumulative_pnl_all_strategies.png")

    p = paths.merge(s[["event_id", "instrument", "continuation_5_20", "large_move"]],
                    left_on=["id", "instrument"], right_on=["event_id", "instrument"])  # 11
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    for ax, inst in zip(axes, ("ES.v.0", "NQ.v.0", "ZN.v.0")):
        f = p.loc[p["instrument"].eq(inst)]
        for label, mask, color in (("continued", f["continuation_5_20"] > 0, "#c0392b"),
                                   ("reversed", f["continuation_5_20"] < 0, "#1f5fa8")):
            m = f.loc[mask].groupby("minute")["depth_ratio"].median()
            ax.plot(m.index + 0.5, m.values, color=color, label=f"{label} (n={f.loc[mask, 'id'].nunique()})")
        ax.axvline(0, color="black", ls="--", lw=0.8)
        ax.axvline(5, color="black", ls=":", lw=0.8)
        ax.axhline(1, color="grey", lw=0.5)
        ax.set_title(NAMES[inst])
        ax.set_xlabel("minutes from statement (dotted = +5 decision)")
    axes[0].set_ylabel("median depth ratio (H4 baseline)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Liquidity paths of events that continued vs reversed after +5 min (outcome labels are ex-post)")
    _save(fig, "fig11_recovery_paths_continuation_vs_reversal.png")

    zn = p.loc[p["instrument"].eq("ZN.v.0")]                                             # 12
    zs = s.loc[s["inst"].eq("ZN")].set_index("event_id")
    q = params["instruments"]["ZN.v.0"]
    cls = np.select([zs["depth_ratio_10m"] >= q.get("depth_ratio_10m_q75", np.inf),
                     zs["depth_ratio_10m"] <= q.get("depth_ratio_10m_q25", -np.inf)], ["replenished", "thin"], "middle")
    zn = zn.assign(cls=zn["id"].map(pd.Series(cls, index=zs.index)))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for label, color in (("replenished", "#1f5fa8"), ("middle", "#aaaaaa"), ("thin", "#c0392b")):
        m = zn.loc[zn["cls"].eq(label)].groupby("minute")["depth_ratio"].median()
        axes[0].plot(m.index + 0.5, m.values, color=color, label=f"{label} at +10m (n={zn.loc[zn['cls'].eq(label), 'id'].nunique()})")
        c = zs.loc[pd.Series(cls, index=zs.index).eq(label), "continuation_10_20"].dropna()
        lo, hi = event_bootstrap_mean(c)
        x = ["replenished", "middle", "thin"].index(label)
        axes[1].bar(x, c.mean() if len(c) else 0, color=color)
        if np.isfinite(lo):
            axes[1].vlines(x, lo, hi, color="black")
    axes[0].axvline(10, color="black", ls=":", lw=0.8)
    axes[0].axhline(1, color="grey", lw=0.5)
    axes[0].set_xlabel("minutes from statement (dotted = +10 decision)")
    axes[0].set_ylabel("ZN median depth ratio")
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].set_xticks([0, 1, 2], ["replenished", "middle", "thin"])
    axes[1].axhline(0, color="black", lw=0.6)
    axes[1].set_ylabel("mean continuation +10 -> +20 (bp), 95% CI")
    fig.suptitle("ZN depth replenishment / overshoot (classes from frozen development quartiles)")
    _save(fig, "fig12_zn_replenishment.png")

    micro = t["micro"]                                                                  # 13
    if not micro.empty and "term" in micro:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        for inst, g in micro.loc[micro["model"].eq("changes") & micro["lookback_s"].eq(5)].groupby("instrument"):
            r2 = g.drop_duplicates("horizon_s").sort_values("horizon_s")
            axes[0].plot(r2["horizon_s"], r2["r2_oos_holdout"], marker="o", color=COLORS[NAMES[inst]], label=NAMES[inst])
            imb = g.loc[g["term"].eq("d_imbalance_5s")].sort_values("horizon_s")
            axes[1].errorbar(imb["horizon_s"], imb["coef"], yerr=1.96 * imb["se"], marker="o", capsize=3,
                             color=COLORS[NAMES[inst]], label=NAMES[inst])
        axes[0].axhline(0, color="black", lw=0.6)
        axes[0].set_xlabel("prediction horizon (s)")
        axes[0].set_ylabel("holdout out-of-sample R2 (development coefficients)")
        axes[1].axhline(0, color="black", lw=0.6)
        axes[1].set_xlabel("prediction horizon (s)")
        axes[1].set_ylabel("coefficient on 5s change in imbalance (bp), 95% CI")
        axes[0].legend(frameon=False)
        fig.suptitle("Second-level book predictability by horizon (event-clustered; 'changes' model, 5s lookback)")
        _save(fig, "fig13_microstructure_by_horizon.png")


# ---------------------------------------------------------------- report

def _labels(strategy) -> list[str]:
    """Result rows of a strategy: each instrument, plus the portfolio when it trades several."""
    return [i[:2] for i in strategy.instruments] + (["portfolio"] if len(strategy.instruments) > 1 else [])


def _fmt(x, digits=2):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{digits}f}"


def _coef(reg, sample, instrument, model, term):
    row = reg.loc[reg["sample"].eq(sample) & reg["instrument"].eq(instrument) & reg["model"].eq(model)
                  & reg["term"].eq(term)]
    return row.iloc[0] if len(row) else None


def _coef_text(reg, instrument, model, term):
    parts = []
    for sample in ("development", "holdout"):
        row = _coef(reg, sample, instrument, model, term)
        if row is None or pd.isna(row.get("coef")):
            parts.append(f"{sample}: n/a")
        else:
            parts.append(f"{sample}: {row['coef']:+.3f} (SE {row['se']:.3f}, p = {row['p_value']:.3f}, "
                         f"95% CI [{row['ci_low']:+.3f}, {row['ci_high']:+.3f}], N = {int(row['N'])})")
    return "; ".join(parts)


def _result(r, strat, inst, sample):
    row = r.loc[r["strategy"].eq(strat) & r["instrument"].eq(inst) & r["sample"].eq(sample)]
    return row.iloc[0] if len(row) else None


def _result_text(r, strat, inst, sample):
    row = _result(r, strat, inst, sample)
    if row is None or int(row.get("N_trades", 0) or 0) == 0:
        return "no trades"
    return (f"{int(row['N_trades'])} trades, mean {row['avg_executable_return']:+.1f} bp "
            f"(mid {row['avg_gross_return']:+.1f}, +1 tick/side {row['avg_net_slip_return']:+.1f}), "
            f"hit {row['hit_rate']:.0%}, 95% CI [{_fmt(row['CI_low'], 1)}, {_fmt(row['CI_high'], 1)}]")


def report(s, params, t):
    r, reg, micro = t["strategy_results"], t["strategy_regressions"], t["micro"]
    reg_by_id = {x.strategy_id: x for x in registry()}
    lines = ["# FOMC trading-hypothesis tests: does liquidity tell us whether the first move continues?", ""]
    dev = s.loc[s["sample"].eq("development")]
    hold = s.loc[s["sample"].eq("holdout")]
    lock = json.loads((OUTPUT / "fomc_strategy_holdout.lock").read_text()) if (OUTPUT / "fomc_strategy_holdout.lock").exists() else {}
    lines += [
        f"*Generated by `scripts/make_fomc_strategy_report.py`. Development {dev['event_date'].min():%Y-%m-%d} to "
        f"{dev['event_date'].max():%Y-%m-%d} ({dev['event_id'].nunique()} FOMC statements); holdout "
        f"{hold['event_date'].min():%Y-%m-%d} to {hold['event_date'].max():%Y-%m-%d} ({hold['event_id'].nunique()}). "
        f"Holdout lock overrides: {len(lock.get('overrides', []))}.*", "",
        "Decision at +5:00 using data timestamped at or before +5:00; entry at the book in force at +5:01; exit at "
        "+20:00 (primary). Long buys the ask and sells the bid; short the reverse. Fees are ignored for now, so "
        "executable = net. No USMPD surprise or rate decision is used by any strategy. Every threshold, z-score, "
        "beta and cross-market relationship was estimated on development events only and frozen before the holdout "
        "was run. The descriptive H4/H5/H6 work in this project had already looked at group medians across all "
        "meetings (including 2023-2026); no strategy had been run on any period before this test.", "",
        "## Master table", "",
        "| Strategy | Role | Instrument | Development | Holdout | Full sample | Classification |",
        "|---|---|---|---|---|---|---|"]
    for strat in [x.strategy_id for x in registry()]:
        meta = reg_by_id[strat]
        for inst in _labels(meta):
            lines.append(f"| {strat}: {meta.name} | {meta.role} | {inst} | {_result_text(r, strat, inst, 'development')} | "
                         f"{_result_text(r, strat, inst, 'holdout')} | {_result_text(r, strat, inst, 'full_sample')} | "
                         f"{classify(r, strat, inst)} |")
    lines += ["", "Classification rule, fixed before any result was seen: SUPPORTED = mean executable return > 0 in "
              "development and in the holdout, at least 3 holdout trades, and the full-sample event-bootstrap 95% CI "
              "above 0; WEAK EVIDENCE = positive in both but the CI includes 0; NOT SUPPORTED = anything else.", ""]

    lines += ["## Answers to the research questions", ""]
    q = []
    for inst in ("ES.v.0", "NQ.v.0", "ZN.v.0"):
        n = NAMES[inst]
        q.append((1, f"**{n}** ret_5_20m on ret_0_5m: " + _coef_text(reg, inst, "first_move_predicts_next", "ret_0_5m")))
        q.append((2, f"**{n}** continuation on depth_ratio_5m (controlling for |ret_0_5m|): "
                     + _coef_text(reg, inst, "with_price_depth_ratio_5m", "depth_ratio_5m")))
        q.append((3, f"**{n}** continuation on spread_ratio_5m (controlling for |ret_0_5m|): "
                     + _coef_text(reg, inst, "with_price_spread_ratio_5m", "spread_ratio_5m")))
        q.append((4, f"**{n}** depth_recovery_1_5: " + _coef_text(reg, inst, "with_price_depth_recovery_1_5", "depth_recovery_1_5")
                  + ". spread_recovery_1_5: " + _coef_text(reg, inst, "with_price_spread_recovery_1_5", "spread_recovery_1_5")))
        q.append((5, f"**{n}** Model C stress coefficient: " + _coef_text(reg, inst, "C_price_plus_liquidity", "stress")
                  + ". Model D interaction |ret| x stress: " + _coef_text(reg, inst, "D_interaction", "abs_x_stress")))
        q.append((6, f"**{n}** P2 (large + stressed -> follow): development {_result_text(r, 'P2', n, 'development')}; "
                     f"holdout {_result_text(r, 'P2', n, 'holdout')}. Price-only P1: development "
                     f"{_result_text(r, 'P1', n, 'development')}; holdout {_result_text(r, 'P1', n, 'holdout')}."))
        q.append((7, f"**{n}** P3 (large + recovered -> fade): development {_result_text(r, 'P3', n, 'development')}; "
                     f"holdout {_result_text(r, 'P3', n, 'holdout')}."))
    q.append((8, "Strongest instrument: compare the P1-P3 rows and the Model C/D coefficients above across ES, NQ "
                 "and ZN (figure 9). Classification per instrument is in the master table."))
    q.append((9, "NQ depth-only vs spread-only (Model C): depth " + _coef_text(reg, "NQ.v.0", "C_depth_only", "stress_depth_only")
              + "; spread " + _coef_text(reg, "NQ.v.0", "C_spread_only", "stress_spread_only")
              + f". Strategies: S2-NQd holdout {_result_text(r, 'S2-NQd', 'NQ', 'holdout')}; S2-NQs holdout "
              f"{_result_text(r, 'S2-NQs', 'NQ', 'holdout')}."))
    q.append((10, f"ES/NQ confirmation: S5B portfolio holdout {_result_text(r, 'S5B', 'portfolio', 'holdout')}; S5C "
                  f"holdout {_result_text(r, 'S5C', 'portfolio', 'holdout')}; versus P1 ES holdout "
                  f"{_result_text(r, 'P1', 'ES', 'holdout')} and NQ {_result_text(r, 'P1', 'NQ', 'holdout')}."))
    q.append((11, "ZN replenishment (decision +10, exit +20): depth_ratio_10m " + _coef_text(reg, "ZN.v.0", "S9_zn_replenishment", "depth_ratio_10m")
              + f". S9-fade holdout {_result_text(r, 'S9-fade', 'ZN', 'holdout')}; S9-follow holdout "
              f"{_result_text(r, 'S9-follow', 'ZN', 'holdout')}."))
    costs = t["strategy_cost_robustness"]
    full = costs.loc[costs["sample"].eq("full_sample") & costs["N_trades"].fillna(0).gt(0)]
    q.append((12, f"{int(full['survives_executable'].sum())} of {len(full)} strategy x instrument rows have a positive "
                  "full-sample mean after executable bid/ask costs (tables/fomc_strategy_cost_robustness.csv)."))
    q.append((13, f"{int(full['survives_one_tick_slippage'].sum())} of {len(full)} remain positive with one extra tick "
                  "per side."))
    classes = [(x.strategy_id, inst, classify(r, x.strategy_id, inst)) for x in registry() for inst in _labels(x)]
    supported = [f"{a} {b}" for a, b, c in classes if c == "SUPPORTED"]
    weak = [f"{a} {b}" for a, b, c in classes if c == "WEAK EVIDENCE"]
    q.append((14, f"Holdout survivors (SUPPORTED): {', '.join(supported) or 'none'}. WEAK EVIDENCE: "
                  f"{', '.join(weak) or 'none'}."))
    if not micro.empty and "term" in micro:
        m = micro.loc[micro["model"].eq("changes") & micro["lookback_s"].eq(5)].drop_duplicates(["instrument", "horizon_s"])
        r2 = "; ".join(f"{NAMES[i]} {int(h)}s: dev R2 {d:.4f}, holdout OOS R2 {o:+.4f}"
                       for i, h, d, o in zip(m["instrument"], m["horizon_s"], m["r2"], m["r2_oos_holdout"]))
        q.append((15, "Second-level 'changes' model (5s lookback), development fit and holdout out-of-sample R2: " + r2 + "."))
        q.append((16, "Predictability is classified as microstructure (not a trading strategy) if it is present at 5 s "
                      "but the holdout out-of-sample R2 is <= 0 by 30-60 s; see figure 13."))
    q.append((17, "Strongest hypothesis for further research: the first entry of the SUPPORTED list above if any; "
                  "otherwise the specification with the most consistent development/holdout sign in the regressions. "
                  "This line is filled in by hand after reviewing the numbers (see Interpretation)."))
    current = None
    for number, text in sorted(q, key=lambda item: item[0]):     # stable: ES, NQ, ZN within each question
        if number != current:
            lines += ["", f"**Q{number}.**"]
            current = number
        lines.append(f"- {text}")

    lines += ["", "## Strategy details", ""]
    for x in registry():
        insts = _labels(x)
        lines += [f"### {x.strategy_id}: {x.name} ({x.role})", "",
                  f"- Hypothesis: {x.hypothesis}", f"- Economic logic: {x.logic}",
                  f"- Features available at entry: {x.features} (all timestamped <= {'+10:00' if x.entry == 'entry10' else '+5:00'})",
                  f"- Entry rule: {x.threshold_definition}; {x.direction_rule}; fill at {x.entry_time}",
                  f"- Exit rule: {x.exit_time}"]
        for inst in insts:
            lines.append(f"- {inst}: development {_result_text(r, x.strategy_id, inst, 'development')}; holdout "
                         f"{_result_text(r, x.strategy_id, inst, 'holdout')}; classification {classify(r, x.strategy_id, inst)}")
        lines += ["- Failure modes: few events per year (about 8); thresholds from development quartiles leave few "
                  "trades; regime change across 2015-2026 (zero lower bound, 2022-23 hikes, faster markets).", ""]

    lines += ["## Ex-post interpretation only (USMPD, not used in any strategy)", ""]
    try:
        from src.events.meeting_groups import meeting_groups

        g = meeting_groups().set_index("meeting")
        e = s.assign(surprise=s["event_id"].map(g["surprise"]))
        table = e.groupby(["inst", "surprise"])["continuation_5_20"].agg(["count", "mean", "median"]).reset_index()
        lines += ["Mean continuation +5 -> +20 (bp) by USMPD surprise third, after the fact:", "",
                  "| Instrument | Surprise third | N | Mean | Median |", "|---|---|---|---|---|"]
        lines += [f"| {a} | {b} | {int(n)} | {_fmt(m, 1)} | {_fmt(md, 1)} |" for a, b, n, m, md in table.itertuples(index=False)]
    except Exception as exc:  # the ex-post section must never block the report
        lines.append(f"(ex-post section skipped: {exc})")
    lines += ["", "## Figures", ""] + [f"- `figures/fomc_strategy/{p.name}`" for p in sorted(FIG.glob("*.png"))]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    s, params, t, paths = load()
    figures(s, params, t, paths)
    report(s, params, t)
    print(f"Wrote {len(list(FIG.glob('*.png')))} figures to {FIG.relative_to(PROJECT_ROOT)} and {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
