"""Latency-conditioned event trade on ES/NQ/ZN, built from events.parquet.

Pre-declared rules: reports/strategy_latency_preregistration.md (clock-anchored
primary, ZN at L = 1 s). Results and the post-hoc arrival-anchored version:
reports/strategy_latency_results.md.

Two direction rules
* surprise: sign of the Bloomberg headline surprise (ZN: short on a positive surprise;
  ES/NQ: sign learned on an expanding window of earlier releases of the same type);
* momentum: sign of the market's own move up to the entry time.

Two clocks for the latency L
* clock: entry at the mid at t0 + L, t0 the scheduled release second;
* arrival: entry at the mid at a + L, a the start of the 100 ms window with the largest
  absolute midpoint move in the first 10 s (``arr_burst_seconds``, median 1.3 s).

Exit at the mid at t0 + 300 s in both cases. Cost: one full spread per round trip
(half at entry from the 0-5 s time-weighted spread, half at exit from the 60-300 s
spread). Placebo: the same rules on the matched control days (no release, same clock).

Run: python -m scripts.backtest_latency_strategy
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data/processed/tick_features/events.parquet"
SURVEYS = ROOT / "data/processed/bloomberg_surveys.parquet"
TABLES, FIGURES = ROOT / "tables", ROOT / "figures"

CLOCK_LATENCIES = [("50ms", 0.05), ("100ms", 0.1), ("250ms", 0.25), ("500ms", 0.5), ("1s", 1.0),
                   ("2s", 2.0), ("5s", 5.0), ("10s", 10.0), ("30s", 30.0), ("60s", 60.0)]
ARRIVAL_LATENCIES = [("0ms", 0.0), ("50ms", 0.05), ("100ms", 0.1), ("250ms", 0.25), ("500ms", 0.5), ("1s", 1.0)]
TICK = {"ES": 0.25, "NQ": 0.25, "ZN": 1 / 64}
HEADLINE = {"employment_situation": ["NFP TCH Index"], "cpi": ["CPI CHNG Index", "CPUPXCHG Index"],
            "ppi": ["FDIDFDMO Index"], "retail_sales": ["RSTAMOM Index"]}
MIN_HISTORY = 12          # earlier releases of the same type before ES/NQ take a surprise direction
PRIMARY = ("ZN.v.0", "1s", "oos_backward")
SAMPLES = ["oos_backward", "development", "oos_forward"]
# Okabe-Ito, colorblind-safe, fixed order: one hue per sample.
COLORS = {"oos_backward": "#0072B2", "development": "#E69F00", "oos_forward": "#009E73", "control": "#999999"}
LABELS = {"oos_backward": "2015-2023 (out of sample, backward)", "development": "2024-Aug 2025 (development)",
          "oos_forward": "Sep 2025-2026 (out of sample, forward)", "control": "matched control days"}


def period(year: int) -> str:
    return "2015-2019" if year <= 2019 else "2020-2023" if year <= 2023 else "2024-2026"


def headline_surprise(surveys: pd.DataFrame) -> pd.DataFrame:
    """One surprise per release morning and type: headline series, fallback when it is zero."""
    rows = []
    for (release, date), g in surveys.groupby(["release", "release_date"]):
        if release not in HEADLINE:
            continue
        surprise = np.nan
        for ticker in HEADLINE[release]:
            s = g.loc[g.ticker == ticker, "surprise"]
            if len(s) and np.isfinite(s.iloc[0]):
                surprise = float(s.iloc[0])
                if surprise != 0:
                    break
        rows.append({"etype": release, "event_date": date.strftime("%Y-%m-%d"), "surprise": surprise})
    return pd.DataFrame(rows)


def load_panel() -> pd.DataFrame:
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev.family.isin(["macro", "macro_control", "fomc", "fomc_control"])].copy()
    ev = ev[ev.family.str.startswith("macro") | (ev.subevent == "statement")]
    ev["root"] = ev.instrument.str[:2]
    ev["year"] = ev.event_time_utc.dt.year
    ev["period"] = ev.year.map(period)
    ev["etype"] = ev.event_types.str.split("|").str[0]
    ev["control"] = ev.is_control
    ev["price"] = np.exp(ev.pre_logmid)
    ev["tick_bp"] = ev.root.map(TICK) / ev.price * 1e4
    sur = headline_surprise(pd.read_parquet(SURVEYS))
    ev = ev.merge(sur, on=["etype", "event_date"], how="left")
    ev.loc[ev.family.str.startswith("fomc"), "surprise"] = np.nan   # USMPD is not known at the trade time
    return ev


def expanding_sign(live: pd.DataFrame) -> pd.Series:
    """Sign of corr(surprise, 300 s return) over earlier releases of the same type, per instrument."""
    out = pd.Series(np.nan, index=live.index)
    for _, g in live.groupby(["instrument", "etype"]):
        g = g.sort_values("event_time_utc")
        s, r = g.surprise.to_numpy(), g.w300s_total_bp.to_numpy()
        for i in range(len(g)):
            ok = np.isfinite(s[:i]) & (s[:i] != 0) & np.isfinite(r[:i])
            if ok.sum() >= MIN_HISTORY:
                c = np.corrcoef(s[:i][ok], r[:i][ok])[0, 1]
                out.loc[g.index[i]] = np.sign(c) if np.isfinite(c) and c != 0 else np.nan
    return out


def directions(ev: pd.DataFrame) -> pd.DataFrame:
    """Surprise direction per row; control days borrow the direction of the first release in their cluster."""
    ev = ev.copy()
    ev["d_surprise"] = np.nan
    live = ev[(~ev.control) & (ev.family == "macro")]
    zn = live.index[live.root == "ZN"]
    ev.loc[zn, "d_surprise"] = -np.sign(ev.loc[zn, "surprise"])
    learned = expanding_sign(live[live.root != "ZN"])
    ev.loc[learned.index, "d_surprise"] = learned * np.sign(ev.loc[learned.index, "surprise"])
    ev.loc[ev.d_surprise == 0, "d_surprise"] = np.nan
    first = (ev.loc[(~ev.control) & (ev.family == "macro")].sort_values("event_time_utc")
             .groupby(["cluster", "instrument"]).d_surprise.first().rename("d_cluster"))
    ctrl = ev.index[ev.control & (ev.family == "macro_control")]
    borrowed = ev.loc[ctrl, ["matched_event", "instrument"]].rename(columns={"matched_event": "cluster"}).merge(
        first, on=["cluster", "instrument"], how="left")
    ev.loc[ctrl, "d_surprise"] = borrowed.d_cluster.to_numpy()
    return ev


def trades(ev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    exit_half = 0.5 * ev.post60_300_spread_ticks * ev.tick_bp
    specs = [("clock", label, seconds, ev[f"w{label}_total_bp"], ev[f"w{label}_endpoint_valid"],
              0.5 * (ev.post5_spread_ticks if seconds <= 5 else ev.post60_spread_ticks) * ev.tick_bp,
              pd.Series(seconds, index=ev.index)) for label, seconds in CLOCK_LATENCIES]
    for label, seconds in ARRIVAL_LATENCIES:
        moved = ev.arr_burst_prior_total_bp + ev[f"arr_burst_{label}_total_bp"]
        specs.append(("arrival", label, seconds, moved, moved.notna(), 0.5 * ev.post5_spread_ticks * ev.tick_bp,
                      ev.arr_burst_seconds + seconds))
    for anchor, label, seconds, moved, valid, entry_half, entry_time in specs:
        remaining = ev.w300s_total_bp - moved
        cost = entry_half + exit_half
        for variant, d in (("surprise", ev.d_surprise), ("momentum", np.sign(moved).replace(0, np.nan))):
            ok = d.notna() & remaining.notna() & valid.astype(bool) & cost.notna()
            t = ev.loc[ok, ["event_id", "event_date", "family", "instrument", "root", "year", "period", "sample",
                            "control", "etype", "surprise", "arr_burst_seconds"]].copy()
            t["anchor"], t["variant"], t["latency"], t["latency_s"] = anchor, variant, label, seconds
            t["entry_s_after_clock"] = entry_time[ok]
            t["direction"] = d[ok]
            t["gross_bp"] = (d * remaining)[ok]
            t["cost_bp"] = cost[ok]
            t["net_bp"] = t.gross_bp - t.cost_bp
            rows.append(t)
    return pd.concat(rows, ignore_index=True)


def summarize(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    def stats(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        sd = g.net_bp.std(ddof=1) if n > 1 else np.nan
        return pd.Series({"n": n, "mean_gross_bp": g.gross_bp.mean(), "mean_cost_bp": g.cost_bp.mean(),
                          "mean_net_bp": g.net_bp.mean(), "se_net_bp": sd / np.sqrt(n),
                          "t_net": g.net_bp.mean() / (sd / np.sqrt(n)) if sd else np.nan,
                          "hit_rate": (g.net_bp > 0).mean(), "median_net_bp": g.net_bp.median(),
                          "sharpe_per_trade": g.net_bp.mean() / sd if sd else np.nan,
                          "median_entry_s_after_clock": g.entry_s_after_clock.median()})
    out = t.groupby(by, observed=True).apply(stats, include_groups=False).reset_index()
    if "latency" in by:
        out["latency_s"] = out.latency.map(dict(CLOCK_LATENCIES + ARRIVAL_LATENCIES))
        out = out.sort_values([c for c in by if c != "latency"] + ["latency_s"])
    return out


def prereg_verdict(macro: pd.DataFrame) -> pd.DataFrame:
    """The pre-declared primary test (clock anchor, ZN, L = 1 s) with its gates."""
    inst, lat, sample = PRIMARY
    base = macro[(macro.anchor == "clock") & (macro.variant == "surprise") & (macro.instrument == inst)]
    prim = base[base.latency == lat]
    live, dev = prim[(~prim.control) & (prim["sample"] == sample)], prim[(~prim.control) & (prim["sample"] == "development")]
    plac = prim[prim.control & (prim["sample"] == sample)]
    by_year = summarize(live, ["year"])
    by_year.to_csv(TABLES / "strategy_latency_primary_by_year.csv", index=False)
    gate = {f"mean_net_{lab}": base[(base.latency == lab) & (~base.control) & (base["sample"] == sample)].net_bp.mean()
            for lab in ("500ms", "2s")}
    s_live, s_dev, s_plac = (summarize(x, ["instrument"]).iloc[0] for x in (live, dev, plac))
    v = {"primary": f"{inst} clock L={lat} {sample}", "n": s_live.n, "mean_net_bp": s_live.mean_net_bp, "t_net": s_live.t_net,
         "hit_rate": s_live.hit_rate, "dev_mean_net_bp": s_dev.mean_net_bp, "dev_n": s_dev.n,
         "placebo": "matched control days (replaces the pseudo clock, whose 300 s exit straddles the release)",
         "placebo_n": s_plac.n, "placebo_mean_net_bp": s_plac.mean_net_bp, "placebo_t": s_plac.t_net, **gate,
         "years_positive": int((by_year.mean_net_bp > 0).sum()), "years": len(by_year)}
    v["threshold_met"] = bool(s_live.mean_net_bp > 0 and s_live.t_net >= 2 and s_dev.mean_net_bp > 0)
    v["gate_latencies"] = bool(gate["mean_net_500ms"] > 0 and gate["mean_net_2s"] > 0)
    v["gate_years"] = bool(v["years_positive"] >= 6)
    v["gate_placebo"] = bool(abs(s_plac.t_net) < 2)
    v["supported_as_predeclared"] = v["threshold_met"] and v["gate_latencies"] and v["gate_years"] and v["gate_placebo"]
    return pd.DataFrame([v])


def plot_decay(arr: pd.DataFrame, path: Path) -> None:
    """Mean net bp per trade against latency after the arrival, one panel per instrument and variant."""
    live = arr[~arr.control]
    ctrl = arr[arr.control]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.4), sharex=True, sharey="row")
    x_of = {lab: max(sec, 0.02) for lab, sec in ARRIVAL_LATENCIES}      # 0 ms drawn at 20 ms on the log axis
    for r, variant in enumerate(["surprise", "momentum"]):
        for c, inst in enumerate(["ES.v.0", "NQ.v.0", "ZN.v.0"]):
            ax = axes[r, c]
            ax.axhline(0, color="#bbbbbb", lw=0.8, zorder=0)
            for sample in SAMPLES:
                s = summarize(live[(live.variant == variant) & (live.instrument == inst) & (live["sample"] == sample)], ["latency"])
                x = s.latency.map(x_of)
                ax.errorbar(x, s.mean_net_bp, yerr=s.se_net_bp, color=COLORS[sample], lw=1.6, marker="o", ms=4,
                            capsize=2, label=LABELS[sample])
            s = summarize(ctrl[(ctrl.variant == variant) & (ctrl.instrument == inst)], ["latency"])
            ax.plot(s.latency.map(x_of), s.mean_net_bp, color=COLORS["control"], lw=1.4, ls="--", marker="s", ms=3.5,
                    label=LABELS["control"])
            ax.set_xscale("log")
            ax.set_xticks(list(x_of.values()))
            ax.set_xticklabels(["0", "50", "100", "250", "500", "1000"])
            ax.set_title(f"{inst[:2]}, {variant} direction", fontsize=10, loc="left")
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.grid(axis="y", color="#eeeeee", lw=0.6)
            if r == 1:
                ax.set_xlabel("entry latency after the arrival, ms")
            if c == 0:
                ax.set_ylabel("mean net return per trade, bp")
    axes[0, 0].legend(fontsize=8, frameon=False, loc="upper right")
    fig.suptitle("Macro releases 2015-2026: what is left of the five-minute move after entering L ms after the arrival, "
                 "net of one spread", fontsize=10.5, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    ev = directions(load_panel())
    t = trades(ev)
    t.to_parquet(TABLES / "strategy_latency_trades.parquet", index=False)
    macro, fomc = t[t.family.str.startswith("macro")], t[t.family.str.startswith("fomc")]

    summarize(macro[macro.anchor == "clock"], ["variant", "control", "instrument", "sample", "latency"]).to_csv(
        TABLES / "strategy_latency_clock.csv", index=False)
    arr = macro[macro.anchor == "arrival"]
    summarize(arr, ["variant", "control", "instrument", "sample", "latency"]).to_csv(
        TABLES / "strategy_latency_arrival.csv", index=False)
    summarize(arr, ["variant", "control", "instrument", "period", "latency"]).to_csv(
        TABLES / "strategy_latency_arrival_by_period.csv", index=False)
    summarize(arr[(arr.variant == "surprise") & (~arr.control)], ["instrument", "etype", "latency"]).to_csv(
        TABLES / "strategy_latency_arrival_by_release.csv", index=False)
    summarize(fomc[fomc.anchor == "arrival"], ["variant", "control", "instrument", "period", "latency"]).to_csv(
        TABLES / "strategy_latency_fomc_momentum.csv", index=False)
    verdict = prereg_verdict(macro)
    verdict.to_csv(TABLES / "strategy_latency_verdict.csv", index=False)
    plot_decay(arr, FIGURES / "paper" / "strategy_latency_decay.png")

    pd.set_option("display.width", 220)
    print("Pre-declared primary (clock anchor):")
    print(verdict.T.to_string())
    for variant in ("surprise", "momentum"):
        print(f"\nArrival anchor, {variant} direction, mean net bp (rows: instrument x sample; 'control' = placebo):")
        a = arr[arr.variant == variant].copy()
        a["grp"] = np.where(a.control, "control", a["sample"])
        s = summarize(a, ["instrument", "grp", "latency"])
        print(s.pivot_table(index=["instrument", "grp"], columns="latency", values="mean_net_bp")
              .reindex(columns=[l for l, _ in ARRIVAL_LATENCIES]).round(2).to_string())
        print(s.pivot_table(index=["instrument", "grp"], columns="latency", values="t_net")
              .reindex(columns=[l for l, _ in ARRIVAL_LATENCIES]).round(2).to_string())
    print("\nFOMC statements, momentum, arrival anchor:")
    f = summarize(fomc[(fomc.anchor == "arrival") & (fomc.variant == "momentum")], ["instrument", "control", "latency"])
    print(f.pivot_table(index=["instrument", "control"], columns="latency", values=["mean_net_bp", "t_net"])
          .round(2).to_string())


if __name__ == "__main__":
    main()
