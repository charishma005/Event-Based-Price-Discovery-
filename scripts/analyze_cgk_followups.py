"""Two CGK (2018) follow-ups: the pre-release second and post-burst drift by book state.

Rules: reports/cgk_followups_preregistration.md. Results: reports/cgk_followups_results.md.
Run: python -m scripts.analyze_cgk_followups   (panels from $T3_FEATURES_DIR, default ../data/processed/tick_features)
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest_latency_strategy import directions, load_panel

ROOT = Path(__file__).resolve().parents[1]
FEATURES = Path(os.environ.get("T3_FEATURES_DIR", ROOT.parent / "data/processed/tick_features"))
TABLES = ROOT / "tables"
LOCKUP_CHANGE = pd.Timestamp("2020-03-01", tz="UTC")


def tstats(x: pd.Series) -> dict:
    x = x.dropna(); n = len(x)
    return {"n": n, "mean_bp": x.mean(), "t": x.mean() / x.std(ddof=1) * np.sqrt(n) if n > 1 else np.nan,
            "share_positive": (x > 0).mean()}


def test_a() -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = directions(load_panel())
    ev = ev[ev.family.isin(["macro", "macro_control"])].copy()
    fine = pd.read_parquet(FEATURES / "fine.parquet", columns=["event_id", "instrument", "seconds", "state_valid", "bid", "ask"])
    fine = fine[fine.seconds <= 0].copy()
    fine["mid"] = (fine.bid + fine.ask) / 2
    pts = {}
    for s in (-1.0, -0.5, -0.02):
        p = fine[(np.isclose(fine.seconds, s)) & fine.state_valid].set_index(["event_id", "instrument"]).mid
        pts[s] = p
    ev = ev.set_index(["event_id", "instrument"])
    ev["r_1s_bp"] = np.log(pts[-0.02] / pts[-1.0]).reindex(ev.index) * 1e4
    ev["r_500ms_bp"] = np.log(pts[-0.02] / pts[-0.5]).reindex(ev.index) * 1e4
    ev = ev.reset_index()
    ev["d_realized"] = np.sign(ev.w300s_total_bp).replace(0, np.nan)
    ev["post_lockup"] = ev.event_time_utc >= LOCKUP_CHANGE
    rows = []
    for name, d in (("surprise", ev.d_surprise), ("realized", ev.d_realized)):
        for w in ("r_1s_bp", "r_500ms_bp"):
            signed = d * ev[w]
            for (inst, ctrl, post), g in signed.groupby([ev.instrument, ev.is_control, ev.post_lockup]):
                rows.append({"direction": name, "window": w, "instrument": inst, "control": ctrl, "post_lockup": post, **tstats(g)})
            for (inst, ctrl), g in signed.groupby([ev.instrument, ev.is_control]):
                rows.append({"direction": name, "window": w, "instrument": inst, "control": ctrl, "post_lockup": "all", **tstats(g)})
    out = pd.DataFrame(rows)
    live = ev[(~ev.is_control) & ev.d_surprise.notna()]
    by_year = (live.assign(signed=live.d_surprise * live.r_1s_bp).groupby(["instrument", "year"]).signed
               .apply(lambda g: pd.Series(tstats(g))).unstack().reset_index())
    return out, by_year


def test_b() -> tuple[pd.DataFrame, pd.DataFrame]:
    t = pd.read_parquet(TABLES / "strategy_latency_trades.parquet")
    t = t[(t.family == "macro") & (~t.control) & (t.anchor == "arrival") & (t.latency == "100ms") & (t.variant == "surprise")]
    ev = pd.read_parquet(ROOT / "data/processed/tick_features/events.parquet")[
        ["event_id", "instrument", "window_key", "pre1_depth_ratio", "pre60_depth_ratio", "pre60_book_updates"]]
    secs = pd.read_parquet(FEATURES / "seconds.parquet",
                           columns=["window_key", "instrument", "anchor_time_utc", "seconds", "cum_trades", "cum_book_updates"])
    # event windows of the 1 s panel are anchored at the pseudo clock, 120 s before the release
    pre = secs[secs.seconds.isin([59.0, 119.0])].pivot_table(index=["window_key", "instrument"], columns="seconds",
                                                           values=["cum_trades", "cum_book_updates"])
    qt = pd.DataFrame({"pre_trades": pre[("cum_trades", 119.0)] - pre[("cum_trades", 59.0)],
                       "pre_updates": pre[("cum_book_updates", 119.0)] - pre[("cum_book_updates", 59.0)]}).reset_index()
    qt["qt_ratio"] = qt.pre_updates / qt.pre_trades.replace(0, np.nan)
    t = t.merge(ev, on=["event_id", "instrument"]).merge(qt, on=["window_key", "instrument"], how="left")
    for col in ("pre1_depth_ratio", "qt_ratio"):
        t[f"{col}_tercile"] = t.groupby("instrument")[col].transform(
            lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"]))
    rows = []
    for col in ("pre1_depth_ratio", "qt_ratio"):
        ter = f"{col}_tercile"
        for scope, sub in [("pooled", t)] + [(p, t[t.period == p]) for p in sorted(t.period.unique())] + \
                          [(i, t[t.instrument == i]) for i in sorted(t.instrument.unique())]:
            if scope == "pooled" or scope in t.period.unique():
                day = sub.groupby(["event_date", ter], observed=True)[["net_bp", "gross_bp"]].mean().reset_index()
            else:
                day = sub[["event_date", ter, "net_bp", "gross_bp"]]
            lo, hi = day[day[ter] == "low"], day[day[ter] == "high"]
            for m in ("net_bp", "gross_bp"):
                diff = lo[m].mean() - hi[m].mean()
                se = np.sqrt(lo[m].var(ddof=1) / len(lo) + hi[m].var(ddof=1) / len(hi))
                rows.append({"split": col, "scope": scope, "measure": m, "n_low": len(lo), "n_high": len(hi),
                             "low_mean_bp": lo[m].mean(), "mid_mean_bp": day.loc[day[ter] == "mid", m].mean(),
                             "high_mean_bp": hi[m].mean(), "low_minus_high_bp": diff, "t": diff / se})
    return pd.DataFrame(rows), t


def main() -> None:
    pd.set_option("display.width", 230)
    a, a_year = test_a()
    a.to_csv(TABLES / "cgk_prerelease_second.csv", index=False)
    a_year.to_csv(TABLES / "cgk_prerelease_second_by_year.csv", index=False)
    print("Test A: signed pre-release return, bp (mean / t), all years")
    show = a[a.post_lockup == "all"].pivot_table(index=["direction", "window", "instrument"], columns="control",
                                                  values=["n", "mean_bp", "t"]).round(2)
    print(show.to_string())
    print("\nby lockup regime, surprise direction, -1 s window, live:")
    print(a[(a.direction == "surprise") & (a.window == "r_1s_bp") & (~a.control.astype(bool)) & (a.post_lockup != "all")]
          .pivot_table(index="instrument", columns="post_lockup", values=["n", "mean_bp", "t"]).round(2).to_string())
    print("\nZN by year:"); print(a_year[a_year.instrument == "ZN.v.0"].round(2).to_string())
    b, trades = test_b()
    b.to_csv(TABLES / "cgk_drift_by_book_state.csv", index=False)
    print("\nTest B: post-burst drift (100 ms after the arrival, exit 300 s), low minus high tercile")
    print(b.round(2).to_string())


if __name__ == "__main__":
    main()
