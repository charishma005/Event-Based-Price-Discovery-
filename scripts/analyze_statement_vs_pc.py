"""FOMC statement vs press conference: are their price moves related, and is there a strategy?

Input: data/processed/fomc_sessions/panel.parquet (scripts/extract_session_panels.py): one-second
best bid/ask from -30 to +120 minutes around 2:00 p.m. for every FOMC statement and matched control
day, ES/NQ/ZN. Session dates and press-conference clocks come from data/events/fomc_session_windows.csv.

Windows (seconds from the statement clock; P = press-conference start, normally +1800):
  st_0_5      0 -> 300            first 5 minutes after the statement
  st_0_30     0 -> P              statement to press-conference start
  st_5_30     300 -> P            drift before the press conference
  pc_0_15     P -> P + 900        first 15 minutes of the press conference
  pc_0_60     P -> P + 3600       the press conference (about one hour)
  post        P + 3600 -> 7200    after the press conference, to +120 minutes
Returns are 10,000 x log midpoint changes (bp), from the last valid quote at or before each second.

Groups, all on the same clock:
  fomc_pc       statements followed by a press conference (2019 on, plus quarterly 2015-2018)
  fomc_no_pc    statements without a press conference (2015-2018): 2:30 p.m. has no scheduled news
  control       matched control days at 2:00 p.m. (no FOMC)

Part 1, correlations: Pearson and Spearman correlations, and OLS slopes with robust errors (one
observation per session), of each later window on each earlier one, per instrument, group and sample.

Part 2, strategies (specified before any result was seen; development = before 2023-01-01,
holdout = 2023 on; thresholds from development fomc_pc sessions only). Decisions use quotes at or
before the decision second; entry fills at the book one second later (long buys the ask, short
sells the bid); exit at the book at the exit second. Fees ignored.
  SP1-fade      at P, fade sign(st_0_30); exit P + 3600  (robustness exits P + 900, +7200)
  SP1-follow    at P, follow sign(st_0_30); exit P + 3600
  SP2-fade-large   SP1-fade only when |st_0_30| >= development 75th percentile (per instrument)
  SP2-follow-large SP1-follow, same filter
  SP3-pc-momentum  at P + 900, follow sign(pc_0_15); exit P + 3600
Every rule is also run on fomc_no_pc and control sessions at the same clock as a placebo.
The classification rule is the one used for the FOMC strategies: SUPPORTED = executable mean > 0 in
development and holdout, at least 3 holdout trades, full-sample event-bootstrap 95% CI above 0;
WEAK EVIDENCE = positive in both but not all of the rest; NOT SUPPORTED otherwise.

Disclosure: the 0 -> 5 minute press-conference return was already compared with the statement move
in reports/trading_strategies.md (section 4, no relation). The longer windows here are new.

Run: python -m scripts.analyze_statement_vs_pc
Writes tables/statement_pc_correlations.csv, tables/statement_pc_strategies.csv,
tables/statement_pc_trades.csv, figures/statement_pc/*.png
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.strategies.inference import event_bootstrap_mean, ols_clustered, t_test
from src.utils.config import PROJECT_ROOT

PANEL = PROJECT_ROOT / "data" / "processed" / "fomc_sessions" / "panel.parquet"
WINDOWS_CSV = PROJECT_ROOT / "data" / "events" / "fomc_session_windows.csv"
TABLES = PROJECT_ROOT / "tables"
FIG = PROJECT_ROOT / "figures" / "statement_pc"
HOLDOUT_START = pd.Timestamp("2023-01-01")
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
COLORS = {"ES": "#2a78d6", "NQ": "#eb6834", "ZN": "#1baf7a"}
GROUP_COLORS = {"fomc_pc": None, "fomc_no_pc": "#9a9a9a", "control": "#cfcfcf"}
DEFAULT_PC = 1800
LATENCY = 1
SAMPLES = ("development", "holdout", "full_sample")
PAIRS = [("pc_0_15", "st_0_30"), ("pc_0_60", "st_0_30"), ("pc_0_60", "st_0_5"), ("st_5_30", "st_0_5"),
         ("post", "pc_0_60"), ("post", "st_0_30"), ("pc_0_60", "pc_0_15")]


def sessions() -> pd.DataFrame:
    w = pd.read_csv(WINDOWS_CSV)
    w["event_time_utc"] = pd.to_datetime(w["event_time_utc"], utc=True)
    w["pc_time"] = pd.to_datetime(w["press_conference_time_utc"], utc=True)
    w["pc_offset"] = ((w["pc_time"] - w["event_time_utc"]).dt.total_seconds()).fillna(DEFAULT_PC).astype(int)
    w["group"] = np.select([w["family"].eq("fomc") & w["pc_time"].notna(), w["family"].eq("fomc")],
                           ["fomc_pc", "fomc_no_pc"], "control")
    w["event_date"] = pd.to_datetime(w["event_date"])
    w["sample"] = np.where(w["event_date"] < HOLDOUT_START, "development", "holdout")
    return w.set_index("event_id")[["group", "pc_offset", "event_date", "sample", "dataset_condition"]]


def needed_seconds(offsets) -> list[int]:
    out = {0, 300, 7200}
    for p in set(offsets):
        out |= {p, p + LATENCY, p + 900, p + 900 + LATENCY, p + 3600}
    return sorted(out)


def quotes(meta: pd.DataFrame) -> pd.DataFrame:
    """Last valid bid/ask/mid at or before each needed second, per session and instrument (wide)."""
    columns = ["event_id", "instrument", "seconds", "valid", "logmid", "bid", "ask"]
    panel = pd.read_parquet(PANEL, columns=columns)
    panel = panel.loc[panel["seconds"].between(-60, 7200) & panel["instrument"].astype(str).isin(INSTRUMENTS)]
    panel["event_id"] = panel["event_id"].astype(str)
    panel["instrument"] = panel["instrument"].astype(str)
    panel = panel.loc[panel["event_id"].isin(meta.index)]
    for c in ("logmid", "bid", "ask"):
        panel[c] = panel[c].where(panel["valid"].astype(bool))
    panel = panel.sort_values(["event_id", "instrument", "seconds"])
    panel[["logmid", "bid", "ask"]] = panel.groupby(["event_id", "instrument"], observed=True)[
        ["logmid", "bid", "ask"]].ffill()
    keep = panel["seconds"].isin(needed_seconds(meta["pc_offset"]))
    return panel.loc[keep, ["event_id", "instrument", "seconds", "logmid", "bid", "ask"]]


def window_returns(q: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (event, inst), g in q.groupby(["event_id", "instrument"]):
        g = g.set_index("seconds")
        p = int(meta.loc[event, "pc_offset"])

        def mid(s):
            return g["logmid"].get(s, np.nan)

        def side(s, c):
            return g[c].get(s, np.nan)

        rows.append({
            "event_id": event, "instrument": inst,
            "st_0_5": 1e4 * (mid(300) - mid(0)), "st_0_30": 1e4 * (mid(p) - mid(0)),
            "st_5_30": 1e4 * (mid(p) - mid(300)), "pc_0_15": 1e4 * (mid(p + 900) - mid(p)),
            "pc_0_60": 1e4 * (mid(p + 3600) - mid(p)), "post": 1e4 * (mid(7200) - mid(p + 3600)),
            **{f"{c}_{name}": side(s, c) for name, s in (("entry_p", p + LATENCY), ("entry_p15", p + 900 + LATENCY),
                                                         ("exit_15", p + 900), ("exit_60", p + 3600), ("exit_120", 7200))
               for c in ("bid", "ask")},
            **{f"mid_{name}": np.exp(mid(s)) for name, s in (("entry_p", p + LATENCY), ("entry_p15", p + 900 + LATENCY),
                                                              ("exit_15", p + 900), ("exit_60", p + 3600), ("exit_120", 7200))},
        })
    out = pd.DataFrame(rows)
    return out.join(meta, on="event_id")


def _subset(d, sample):
    return d if sample == "full_sample" else d.loc[d["sample"].eq(sample)]


def correlations(r: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group in ("fomc_pc", "fomc_no_pc", "control"):
        for sample in SAMPLES:
            g = _subset(r.loc[r["group"].eq(group)], sample)
            for inst in INSTRUMENTS:
                f = g.loc[g["instrument"].eq(inst)]
                for y, x in PAIRS:
                    d = f[[y, x, "event_id"]].replace([np.inf, -np.inf], np.nan).dropna()
                    if len(d) < 8:
                        continue
                    fit = ols_clustered(d, y, [x]).set_index("term")
                    rows.append({"group": group, "sample": sample, "instrument": NAMES[inst], "y": y, "x": x,
                                 "N": len(d), "pearson": d[y].corr(d[x]), "spearman": stats.spearmanr(d[y], d[x])[0],
                                 "slope": fit.loc[x, "coef"], "slope_se": fit.loc[x, "se"],
                                 "slope_p": fit.loc[x, "p_value"], "r2": fit.loc[x, "r2"]})
    return pd.DataFrame(rows)


def _trade_returns(d: pd.DataFrame, direction: pd.Series, entry: str, exit_: str) -> pd.DataFrame:
    long_ = direction > 0
    executable = np.where(long_, np.log(d[f"bid_{exit_}"] / d[f"ask_{entry}"]),
                          np.log(d[f"bid_{entry}"] / d[f"ask_{exit_}"])) * 1e4
    gross = direction * np.log(d[f"mid_{exit_}"] / d[f"mid_{entry}"]) * 1e4
    return d[["event_id", "instrument", "group", "sample"]].assign(direction=direction, gross_bp=gross,
                                                                   executable_bp=executable)


def strategies(r: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dev = r.loc[r["group"].eq("fomc_pc") & r["sample"].eq("development")]
    q75 = dev.assign(a=dev["st_0_30"].abs()).groupby("instrument")["a"].quantile(0.75)
    large = r["st_0_30"].abs() >= r["instrument"].map(q75)
    s30, s15 = np.sign(r["st_0_30"]), np.sign(r["pc_0_15"])
    rules = {
        "SP1-fade": (-s30, None, "entry_p", "exit_60"), "SP1-fade-exit15": (-s30, None, "entry_p", "exit_15"),
        "SP1-fade-exit120": (-s30, None, "entry_p", "exit_120"), "SP1-follow": (s30, None, "entry_p", "exit_60"),
        "SP2-fade-large": (-s30, large, "entry_p", "exit_60"), "SP2-follow-large": (s30, large, "entry_p", "exit_60"),
        "SP3-pc-momentum": (s15, None, "entry_p15", "exit_60"),
    }
    trades, rows = [], []
    dates = r.drop_duplicates("event_id").set_index("event_id")["event_date"]
    for rule, (direction, mask, entry, exit_) in rules.items():
        keep = direction.ne(0) & direction.notna() & (mask if mask is not None else True)
        t = _trade_returns(r.loc[keep], direction.loc[keep], entry, exit_).assign(rule=rule)
        trades.append(t)
        for group in ("fomc_pc", "fomc_no_pc", "control"):
            for inst in (*INSTRUMENTS, "portfolio"):
                block = []
                for sample in SAMPLES:
                    s = _subset(t.loc[t["group"].eq(group)], sample)
                    if inst != "portfolio":
                        s = s.loc[s["instrument"].eq(inst)]
                    per = s.groupby("event_id")[["gross_bp", "executable_bp"]].mean().dropna()
                    net = per["executable_bp"]
                    tt, p = t_test(net)
                    lo, hi = event_bootstrap_mean(net)
                    order = net.index.map(dates).argsort()
                    cum = net.iloc[order].cumsum()
                    block.append({"rule": rule, "group": group, "instrument": NAMES.get(inst, inst), "sample": sample,
                                  "N_trades": len(net), "avg_gross_bp": per["gross_bp"].mean(),
                                  "avg_executable_bp": net.mean(), "median_executable_bp": net.median(),
                                  "hit_rate": (net > 0).mean() if len(net) else np.nan, "t_stat": tt, "p_value": p,
                                  "CI_low": lo, "CI_high": hi,
                                  "max_drawdown": float((cum - cum.cummax()).min()) if len(cum) else np.nan})
                b = pd.DataFrame(block).set_index("sample")
                dev_ok = b.loc["development", "avg_executable_bp"] > 0
                hold_ok = b.loc["holdout", "avg_executable_bp"] > 0
                if dev_ok and hold_ok and b.loc["holdout", "N_trades"] >= 3 and b.loc["full_sample", "CI_low"] > 0:
                    label = "SUPPORTED"
                elif dev_ok and hold_ok:
                    label = "WEAK EVIDENCE"
                else:
                    label = "NOT SUPPORTED"
                rows += [{**x, "classification": label} for x in block]
    return pd.DataFrame(rows), pd.concat(trades, ignore_index=True)


def figures(r: pd.DataFrame, corr: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for ax, inst in zip(axes, INSTRUMENTS):
        name = NAMES[inst]
        for group, color in (("control", GROUP_COLORS["control"]), ("fomc_no_pc", GROUP_COLORS["fomc_no_pc"]),
                             ("fomc_pc", COLORS[name])):
            d = r.loc[r["instrument"].eq(inst) & r["group"].eq(group)]
            ax.scatter(d["st_0_30"], d["pc_0_60"], s=16 if group == "fomc_pc" else 10, color=color, alpha=0.85,
                       label={"fomc_pc": "FOMC with press conference", "fomc_no_pc": "FOMC, no press conference",
                              "control": "control day"}[group], zorder=3 if group == "fomc_pc" else 2)
        c = corr.loc[corr["group"].eq("fomc_pc") & corr["sample"].eq("full_sample") & corr["instrument"].eq(name)
                     & corr["y"].eq("pc_0_60") & corr["x"].eq("st_0_30")]
        if len(c):
            c = c.iloc[0]
            ax.set_title(f"{name}: slope {c['slope']:+.2f} (p = {c['slope_p']:.2f}), corr {c['pearson']:+.2f}, N = {c['N']}",
                         fontsize=10)
        ax.axhline(0, color="#888888", lw=0.6)
        ax.axvline(0, color="#888888", lw=0.6)
        ax.set_xlabel("statement -> press-conference start (bp)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("press conference, first 60 min (bp)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Is the press-conference move related to the statement move? (same clock on control days)")
    fig.tight_layout()
    fig.savefig(FIG / "statement_vs_pc_scatter.png", dpi=160)
    plt.close(fig)

    labels = [f"{y} ~ {x}" for y, x in PAIRS]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        for k, (group, color) in enumerate((("fomc_pc", COLORS[inst]), ("fomc_no_pc", "#9a9a9a"), ("control", "#cfcfcf"))):
            d = corr.loc[corr["group"].eq(group) & corr["sample"].eq("full_sample") & corr["instrument"].eq(inst)]
            d = d.assign(label=d["y"] + " ~ " + d["x"]).set_index("label").reindex(labels)
            y = np.arange(len(labels)) + (k - 1) * 0.25
            ax.barh(y, d["pearson"], height=0.23, color=color, label=group)
        ax.axvline(0, color="black", lw=0.6)
        ax.set_yticks(range(len(labels)), labels, fontsize=8)
        ax.set_title(inst)
        ax.set_xlabel("Pearson correlation (full sample)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Correlation of later windows with earlier windows: FOMC with press conference vs placebos")
    fig.tight_layout()
    fig.savefig(FIG / "window_correlations.png", dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    meta = sessions()
    meta = meta.loc[meta["dataset_condition"].ne("degraded")]
    r = window_returns(quotes(meta), meta)
    print("Sessions with returns:\n" + r.drop_duplicates("event_id").groupby(["group", "sample"]).size().unstack().to_string())
    TABLES.mkdir(exist_ok=True)
    corr = correlations(r)
    corr.to_csv(TABLES / "statement_pc_correlations.csv", index=False)
    results, trades = strategies(r)
    results.to_csv(TABLES / "statement_pc_strategies.csv", index=False)
    trades.to_csv(TABLES / "statement_pc_trades.csv", index=False)
    figures(r, corr)
    main_corr = corr.loc[corr["sample"].eq("full_sample") & corr["group"].eq("fomc_pc")]
    print("\nFOMC with press conference, full sample:\n"
          + main_corr[["instrument", "y", "x", "N", "pearson", "slope", "slope_p"]].round(3).to_string(index=False))
    show = results.loc[results["group"].eq("fomc_pc") & results["instrument"].ne("portfolio")]
    print("\nStrategies on FOMC press-conference days (executable bp):\n"
          + show.pivot_table(index=["rule", "instrument"], columns="sample",
                             values="avg_executable_bp").round(1).to_string())
    print("\nWrote tables/statement_pc_*.csv and figures/statement_pc/")


if __name__ == "__main__":
    main()
