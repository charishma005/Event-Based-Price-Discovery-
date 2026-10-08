"""ES/NQ lead-lag and pairs trading on the one-second FOMC session panel.

Input: data/processed/fomc_sessions/panel.parquet (scripts/extract_session_panels.py), one-second best
bid/ask from -30 to +120 minutes around 2:00 p.m. on FOMC days and matched control days; session
dates and press-conference clocks from data/events/fomc_session_windows.csv.

Specified before any result was seen. Development = sessions before 2023-01-01, holdout = 2023 on.

Phases (seconds from the 2:00 p.m. clock; P = press-conference start, 1800 when there is none):
  pre        -1800 .. -1    calibration only (beta and spread volatility); no trading
  st_0_5     0 .. 299       first five minutes after the statement
  st_5_30    300 .. P-1
  pc         P .. P+3599    press conference (same clock on days without one)
  after      P+3600 .. 7200
Groups: fomc_pc (statement with press conference), fomc_no_pc (2015-2018 statement only), control.

A. Lead-lag
  A1 Cross-correlation of 1-second log midpoint returns, corr(ES_t, NQ_{t+L}) for L = -10..+10
     (L > 0: ES leads), per session and phase, averaged over sessions with an event-bootstrap CI.
  A2 Predictive regressions, non-overlapping k-second blocks (k = 1, 5, 30):
     NQ_{t+1..t+k} on ES_{t-k+1..t} and NQ_{t-k+1..t}; and the mirror for ES. Event-clustered errors.
     Fitted on development, out-of-sample R2 on the holdout (benchmark: zero return).
B. Pairs trading (mean reversion of the beta-hedged spread)
  beta = OLS slope of 10-second NQ returns on 10-second ES returns over the session's pre window.
  For a signal window W, sigma_W = std of W-second residual moves (NQ - beta ES) over
  the pre window (overlapping moves). z_t = (NQ move - beta x ES move over the last W seconds) / sigma_W.
  If flat and |z_t| >= 2 (fixed in advance, not tuned): short the outperformer, buy the other
  (NQ notional 1, ES notional beta), entry at the book at t+1, exit at the book at t+1+H; then flat.
  Configurations (W, H): (60 s, 300 s) primary; (30 s, 60 s) and (300 s, 900 s) robustness.
  Return per unit of gross notional, in bp: (NQ leg + beta x ES leg) / (1 + beta).
C. Lead-lag trade
  If |ES 5-second return| >= development 99th percentile (all development sessions, phases after 0)
  and NQ has lagged (NQ 5-second return - beta x ES 5-second return has the opposite sign of the ES
  move), trade NQ in the direction of the ES move at t+1; exit at t+1+5 s or t+1+30 s.
  One position at a time per session.
Costs: executable bid/ask on every leg (long buys the ask, sells the bid); fees ignored.
Verdict per rule x group x phase: SUPPORTED = executable mean > 0 in development and holdout, at least
3 holdout sessions with trades, full-sample event-bootstrap 95% CI above 0; WEAK EVIDENCE = positive
in both, rest not met; NOT SUPPORTED otherwise. Sessions are the unit (trades averaged per session).
Disclosure: earlier tests (reports/trading_strategies.md, sections 1 and 6) looked at ES/NQ at the
event level; the one-second session tests here are new.

Run: python -m scripts.analyze_es_nq_pairs
Writes tables/es_nq_xcorr.csv, tables/es_nq_lead_lag_regressions.csv, tables/es_nq_strategies.csv,
tables/es_nq_trades.csv and figures/es_nq/*.png
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.strategies.inference import event_bootstrap_mean, ols_clustered, t_test
from src.utils.config import PROJECT_ROOT

PANEL = PROJECT_ROOT / "data" / "processed" / "fomc_sessions" / "panel.parquet"
WINDOWS_CSV = PROJECT_ROOT / "data" / "events" / "fomc_session_windows.csv"
TABLES = PROJECT_ROOT / "tables"
FIG = PROJECT_ROOT / "figures" / "es_nq"
HOLDOUT_START = pd.Timestamp("2023-01-01")
ES, NQ = "ES.v.0", "NQ.v.0"
START, END, DEFAULT_PC = -1800, 7200, 1800
LAGS = range(-10, 11)
BLOCKS = (1, 5, 30)
PAIRS_CONFIGS = {"pairs-W60-H300": (60, 300), "pairs-W30-H60": (30, 60), "pairs-W300-H900": (300, 900)}
LEADLAG_HOLDS = {"leadlag-H5": 5, "leadlag-H30": 30}
Z_ENTRY = 2.0
SAMPLES = ("development", "holdout", "full_sample")
PHASES = ("st_0_5", "st_5_30", "pc", "after")
COLORS = {"fomc_pc": "#2a78d6", "fomc_no_pc": "#9a9a9a", "control": "#e0a030"}


def sessions() -> pd.DataFrame:
    w = pd.read_csv(WINDOWS_CSV)
    t0 = pd.to_datetime(w["event_time_utc"], utc=True)
    pc = pd.to_datetime(w["press_conference_time_utc"], utc=True)
    w["pc_offset"] = ((pc - t0).dt.total_seconds()).fillna(DEFAULT_PC).astype(int)
    w["group"] = np.select([w["family"].eq("fomc") & pc.notna(), w["family"].eq("fomc")],
                           ["fomc_pc", "fomc_no_pc"], "control")
    w["event_date"] = pd.to_datetime(w["event_date"])
    w["sample"] = np.where(w["event_date"] < HOLDOUT_START, "development", "holdout")
    w = w.loc[w["dataset_condition"].ne("degraded")]
    return w.set_index("event_id")[["group", "pc_offset", "event_date", "sample"]]


def load(meta: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per session: seconds START..END with ES/NQ log mid, bid and ask (last valid quote carried forward)."""
    cols = ["event_id", "instrument", "seconds", "valid", "logmid", "bid", "ask"]
    p = pd.read_parquet(PANEL, columns=cols)
    p = p.loc[p["instrument"].astype(str).isin([ES, NQ])]
    p["event_id"], p["instrument"] = p["event_id"].astype(str), p["instrument"].astype(str)
    p = p.loc[p["event_id"].isin(meta.index) & p["seconds"].between(START, END)]
    for c in ("logmid", "bid", "ask"):
        p[c] = p[c].where(p["valid"].astype(bool))
    out = {}
    grid = np.arange(START, END + 1)
    for event, g in p.groupby("event_id"):
        w = g.pivot_table(index="seconds", columns="instrument", values=["logmid", "bid", "ask"], aggfunc="first")
        if not {ES, NQ} <= set(w.columns.get_level_values(1)):
            continue
        w = w.reindex(grid).ffill()
        w.columns = [f"{a}_{b[:2].lower()}" for a, b in w.columns]
        out[event] = w
    return out


def phase_of(seconds: np.ndarray, p: int) -> np.ndarray:
    return np.select([seconds < 0, seconds < 300, seconds < p, seconds < p + 3600], ["pre", "st_0_5", "st_5_30", "pc"],
                     "after")


def calibrate(w: pd.DataFrame) -> dict:
    """Beta and residual volatilities from the pre window only (seconds -1800..-1)."""
    pre = w.loc[START:-1]
    es, nq = pre["logmid_es"].to_numpy(), pre["logmid_nq"].to_numpy()
    r_es, r_nq = 1e4 * np.diff(es[::10]), 1e4 * np.diff(nq[::10])
    ok = np.isfinite(r_es) & np.isfinite(r_nq)
    beta = float(np.polyfit(r_es[ok], r_nq[ok], 1)[0]) if ok.sum() > 30 and np.std(r_es[ok]) > 0 else np.nan
    sig = {}
    for W in {W for W, _ in PAIRS_CONFIGS.values()} | {5}:
        e, n = 1e4 * (es[W:] - es[:-W]), 1e4 * (nq[W:] - nq[:-W])   # overlapping W-second moves
        resid = n - beta * e
        resid = resid[np.isfinite(resid)]
        sig[W] = float(np.std(resid, ddof=1)) if len(resid) > 5 else np.nan
    return {"beta": beta, "sigma": sig}


# ---------------------------------------------------------------- A

def cross_correlations(data: dict, meta: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for event, w in data.items():
        m = meta.loc[event]
        r_es = 1e4 * np.diff(w["logmid_es"].to_numpy())
        r_nq = 1e4 * np.diff(w["logmid_nq"].to_numpy())
        sec = w.index.to_numpy()[1:]
        ph = phase_of(sec, int(m["pc_offset"]))
        for phase in ("pre", *PHASES):
            mask = ph == phase
            a, b = r_es[mask], r_nq[mask]
            for L in LAGS:
                if L >= 0:
                    x, y = a[: len(a) - L], b[L:]
                else:
                    x, y = a[-L:], b[: len(b) + L]
                ok = np.isfinite(x) & np.isfinite(y)
                c = np.corrcoef(x[ok], y[ok])[0, 1] if ok.sum() > 20 and x[ok].std() > 0 and y[ok].std() > 0 else np.nan
                rows.append({"event_id": event, "group": m["group"], "sample": m["sample"], "phase": phase, "lag": L,
                             "corr": c})
    per = pd.DataFrame(rows)
    out = []
    for sample in SAMPLES:
        s = per if sample == "full_sample" else per.loc[per["sample"].eq(sample)]
        for (group, phase, lag), g in s.groupby(["group", "phase", "lag"]):
            lo, hi = event_bootstrap_mean(g["corr"], draws=2000)
            out.append({"sample": sample, "group": group, "phase": phase, "lag": lag, "mean_corr": g["corr"].mean(),
                        "CI_low": lo, "CI_high": hi, "N_sessions": g["corr"].notna().sum()})
    return pd.DataFrame(out)


def lead_lag_regressions(data: dict, meta: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for event, w in data.items():
        m = meta.loc[event]
        for k in BLOCKS:
            es = w["logmid_es"].to_numpy()[::k]
            nq = w["logmid_nq"].to_numpy()[::k]
            sec = w.index.to_numpy()[::k]
            r_es, r_nq = 1e4 * np.diff(es), 1e4 * np.diff(nq)
            f = pd.DataFrame({"event_id": event, "k": k, "second": sec[1:-1], "es_lag": r_es[:-1], "nq_lag": r_nq[:-1],
                              "es_next": r_es[1:], "nq_next": r_nq[1:]})
            f["phase"] = phase_of(f["second"].to_numpy(), int(m["pc_offset"]))
            f["group"], f["sample"] = m["group"], m["sample"]
            frames.append(f.loc[f["phase"].ne("pre")])
    d = pd.concat(frames, ignore_index=True)
    rows = []
    for (k, group), g in d.groupby(["k", "group"]):
        for phase in ("all_after_0", *PHASES):
            gp = g if phase == "all_after_0" else g.loc[g["phase"].eq(phase)]
            for target, xs in (("nq_next", ["es_lag", "nq_lag"]), ("es_next", ["nq_lag", "es_lag"])):
                dev, hold = gp.loc[gp["sample"].eq("development")], gp.loc[gp["sample"].eq("holdout")]
                fit_dev = ols_clustered(dev, target, xs)
                oos = _oos(fit_dev, hold, target, xs)
                for sample, sub in (("development", dev), ("holdout", hold), ("full_sample", gp)):
                    fit = fit_dev if sample == "development" else ols_clustered(sub, target, xs)
                    rows.append(fit.assign(k=k, group=group, phase=phase, target=target, sample=sample,
                                           r2_oos_holdout=oos))
    return pd.concat(rows, ignore_index=True)


def _oos(fit: pd.DataFrame, hold: pd.DataFrame, y: str, xs: list[str]) -> float:
    if "coef" not in fit or hold.empty:
        return np.nan
    c = fit.set_index("term")["coef"]
    h = hold[[y, *xs]].replace([np.inf, -np.inf], np.nan).dropna()
    if h.empty:
        return np.nan
    pred = c.get("const", 0.0) + sum(c.get(x, 0.0) * h[x] for x in xs)
    sst = (h[y] ** 2).sum()
    return float(1 - ((h[y] - pred) ** 2).sum() / sst) if sst > 0 else np.nan


# ---------------------------------------------------------------- B and C

def _bp(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1e4 * np.log(b / a)


def pairs_trades(data: dict, meta: pd.DataFrame, calib: dict) -> pd.DataFrame:
    rows = []
    for event, w in data.items():
        m, c = meta.loc[event], calib[event]
        beta = c["beta"]
        if not np.isfinite(beta) or beta <= 0:
            continue
        sec = w.index.to_numpy()
        es, nq = w["logmid_es"].to_numpy(), w["logmid_nq"].to_numpy()
        eb, ea, nb, na = (w[x].to_numpy() for x in ("bid_es", "ask_es", "bid_nq", "ask_nq"))
        i0 = int(np.searchsorted(sec, 0))
        for rule, (W, H) in PAIRS_CONFIGS.items():
            sigma = c["sigma"].get(W)
            if not sigma or not np.isfinite(sigma) or sigma <= 0:
                continue
            z = np.full(len(sec), np.nan)
            z[W:] = (1e4 * (nq[W:] - nq[:-W]) - beta * 1e4 * (es[W:] - es[:-W])) / sigma
            t = max(i0, W)
            while t + 1 + H < len(sec):
                if np.isfinite(z[t]) and abs(z[t]) >= Z_ENTRY:
                    e, x = t + 1, t + 1 + H
                    side = -np.sign(z[t])                      # z > 0: NQ outperformed -> short NQ, long ES
                    nq_leg = _bp(na[e], nb[x]) if side > 0 else _bp(na[x], nb[e])
                    es_leg = _bp(ea[e], eb[x]) if side < 0 else _bp(ea[x], eb[e])
                    mid_nq = side * 1e4 * (nq[x] - nq[e])
                    mid_es = -side * 1e4 * (es[x] - es[e])
                    rows.append({"event_id": event, "rule": rule, "entry_second": int(sec[e]),
                                 "phase": phase_of(np.array([sec[t]]), int(m["pc_offset"]))[0],
                                 "z": z[t], "beta": beta,
                                 "gross_bp": (mid_nq + beta * mid_es) / (1 + beta),
                                 "executable_bp": (nq_leg + beta * es_leg) / (1 + beta)})
                    t = x
                else:
                    t += 1
    return pd.DataFrame(rows)


def leadlag_trades(data: dict, meta: pd.DataFrame, calib: dict) -> pd.DataFrame:
    dev_moves = []
    for event, w in data.items():
        if meta.loc[event, "sample"] != "development":
            continue
        es = w.loc[0:, "logmid_es"].to_numpy()
        dev_moves.append(np.abs(1e4 * (es[5:] - es[:-5])))
    q99 = float(np.nanpercentile(np.concatenate(dev_moves), 99))
    rows = []
    for event, w in data.items():
        m, beta = meta.loc[event], calib[event]["beta"]
        if not np.isfinite(beta):
            continue
        sec = w.index.to_numpy()
        es, nq = w["logmid_es"].to_numpy(), w["logmid_nq"].to_numpy()
        nb, na = w["bid_nq"].to_numpy(), w["ask_nq"].to_numpy()
        i0 = max(int(np.searchsorted(sec, 0)), 5)
        r_es = np.full(len(sec), np.nan)
        r_nq = np.full(len(sec), np.nan)
        r_es[5:], r_nq[5:] = 1e4 * (es[5:] - es[:-5]), 1e4 * (nq[5:] - nq[:-5])
        for rule, H in LEADLAG_HOLDS.items():
            t = i0
            while t + 1 + H < len(sec):
                lagged = np.sign(r_nq[t] - beta * r_es[t]) == -np.sign(r_es[t])
                if np.isfinite(r_es[t]) and abs(r_es[t]) >= q99 and lagged:
                    e, x, side = t + 1, t + 1 + H, np.sign(r_es[t])
                    rows.append({"event_id": event, "rule": rule, "entry_second": int(sec[e]),
                                 "phase": phase_of(np.array([sec[t]]), int(m["pc_offset"]))[0],
                                 "trigger_bp": r_es[t], "q99_bp": q99,
                                 "gross_bp": side * 1e4 * (nq[x] - nq[e]),
                                 "executable_bp": _bp(na[e], nb[x]) if side > 0 else _bp(na[x], nb[e])})
                    t = x
                else:
                    t += 1
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    t = trades.join(meta[["group", "sample"]], on="event_id")
    rows = []
    for rule in t["rule"].unique():
        for group in ("fomc_pc", "fomc_no_pc", "control"):
            for phase in ("all_after_0", *PHASES):
                g = t.loc[t["rule"].eq(rule) & t["group"].eq(group)]
                if phase != "all_after_0":
                    g = g.loc[g["phase"].eq(phase)]
                block = []
                for sample in SAMPLES:
                    s = g if sample == "full_sample" else g.loc[g["sample"].eq(sample)]
                    per = s.groupby("event_id")[["gross_bp", "executable_bp"]].mean()
                    net = per["executable_bp"].dropna()
                    tt, p = t_test(net)
                    lo, hi = event_bootstrap_mean(net)
                    block.append({"rule": rule, "group": group, "phase": phase, "sample": sample,
                                  "N_sessions": len(net), "N_trades": len(s), "avg_gross_bp": per["gross_bp"].mean(),
                                  "avg_executable_bp": net.mean(), "hit_rate": (net > 0).mean() if len(net) else np.nan,
                                  "t_stat": tt, "p_value": p, "CI_low": lo, "CI_high": hi})
                b = pd.DataFrame(block).set_index("sample")
                dev_ok, hold_ok = b.loc["development", "avg_executable_bp"] > 0, b.loc["holdout", "avg_executable_bp"] > 0
                if dev_ok and hold_ok and b.loc["holdout", "N_sessions"] >= 3 and b.loc["full_sample", "CI_low"] > 0:
                    label = "SUPPORTED"
                elif dev_ok and hold_ok:
                    label = "WEAK EVIDENCE"
                else:
                    label = "NOT SUPPORTED"
                rows += [{**x, "classification": label} for x in block]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- figures

def figures(xc: pd.DataFrame, results: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    phases = ("pre", *PHASES)
    titles = {"pre": "-30 to 0 min", "st_0_5": "statement 0-5 min", "st_5_30": "+5 to +30 min",
              "pc": "press conference (+30 to +90)", "after": "+90 to +120 min"}
    fig, axes = plt.subplots(1, len(phases), figsize=(18, 4), sharey=True)
    for ax, phase in zip(axes, phases):
        for group in ("control", "fomc_no_pc", "fomc_pc"):
            d = xc.loc[xc["sample"].eq("full_sample") & xc["group"].eq(group) & xc["phase"].eq(phase)].sort_values("lag")
            d = d.loc[d["lag"].ne(0)]
            ax.plot(d["lag"], d["mean_corr"], marker="o", ms=3, lw=1.4, color=COLORS[group], label=group)
            ax.fill_between(d["lag"], d["CI_low"], d["CI_high"], color=COLORS[group], alpha=0.15, lw=0)
        ax.axhline(0, color="#888888", lw=0.6)
        ax.axvline(0, color="#888888", lw=0.6)
        ax.set_title(titles[phase], fontsize=10)
        ax.set_xlabel("lag L (s); L > 0 = ES leads NQ")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("corr(ES return t, NQ return t+L)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("ES-NQ lead-lag at one second (lag 0 omitted; 95% session-bootstrap bands)")
    fig.tight_layout()
    fig.savefig(FIG / "es_nq_cross_correlation.png", dpi=160)
    plt.close(fig)

    r = results.loc[results["phase"].eq("all_after_0") & results["sample"].ne("full_sample")]
    rules = list(dict.fromkeys(r["rule"]))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    width = 0.13
    for i, rule in enumerate(rules):
        for j, group in enumerate(("fomc_pc", "fomc_no_pc", "control")):
            for k, sample in enumerate(("development", "holdout")):
                row = r.loc[r["rule"].eq(rule) & r["group"].eq(group) & r["sample"].eq(sample)]
                if row.empty or pd.isna(row["avg_executable_bp"].iloc[0]):
                    continue
                x = i + (j * 2 + k - 2.5) * width
                ax.bar(x, row["avg_executable_bp"].iloc[0], width=width * 0.92, color=COLORS[group],
                       alpha=1.0 if sample == "development" else 0.5)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(range(len(rules)), rules, fontsize=9)
    ax.set_ylabel("mean executable return per session (bp)")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=COLORS[g]) for g in COLORS], labels=list(COLORS),
              frameon=False, fontsize=8)
    ax.set_title("ES/NQ pairs and lead-lag rules after costs (solid = development, light = holdout)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "es_nq_strategy_returns.png", dpi=160)
    plt.close(fig)


def main() -> None:
    meta = sessions()
    data = load(meta)
    meta = meta.loc[meta.index.isin(data)]
    print("Sessions:\n" + meta.groupby(["group", "sample"]).size().unstack().to_string())
    calib = {e: calibrate(w) for e, w in data.items()}
    TABLES.mkdir(exist_ok=True)
    xc = cross_correlations(data, meta)
    xc.to_csv(TABLES / "es_nq_xcorr.csv", index=False)
    lead_lag_regressions(data, meta).to_csv(TABLES / "es_nq_lead_lag_regressions.csv", index=False)
    trades = pd.concat([pairs_trades(data, meta, calib), leadlag_trades(data, meta, calib)], ignore_index=True)
    trades.join(meta[["group", "sample"]], on="event_id").to_csv(TABLES / "es_nq_trades.csv", index=False)
    results = summarize(trades, meta)
    results.to_csv(TABLES / "es_nq_strategies.csv", index=False)
    figures(xc, results)
    asym = xc.loc[xc["sample"].eq("full_sample") & xc["lag"].ne(0)].assign(
        side=lambda d: np.where(d["lag"] > 0, "ES_leads", "NQ_leads")).groupby(["group", "phase", "side"])[
        "mean_corr"].sum().unstack()
    print("\nSum of cross-correlations at lags 1..10 (ES leads) vs -1..-10 (NQ leads):\n" + asym.round(3).to_string())
    show = results.loc[results["phase"].eq("all_after_0") & results["group"].eq("fomc_pc")]
    print("\nRules on press-conference FOMC days, all phases after 0 (executable bp per session):\n"
          + show.pivot_table(index="rule", columns="sample", values="avg_executable_bp").round(2).to_string())
    print("\nWrote tables/es_nq_*.csv and figures/es_nq/")


if __name__ == "__main__":
    main()
