"""Burst-trigger trend trade on ES/NQ/ZN, own-asset and ES-ZN cross, from the 20 ms panel.

Rules: reports/strategy_trigger_preregistration.md. Results: reports/strategy_trigger_results.md.

Trigger: first 20 ms grid point where |mid move over 100 ms| >= k ticks and volume over the same
100 ms >= v contracts; k, v = 99th percentiles over the previous 20 windows of the same contract
and family (event windows: pre-clock second only; control and pseudo windows: all 11 s).
Entry at the traded contract's mid one grid point later; exit at the mid 300 s (60 s, 30 s) after
the trigger from the 1 s panel; cost = half spread at entry + half spread at exit.

Run: python -m scripts.backtest_trigger_strategy
Feature panels are read from $T3_FEATURES_DIR (default ../data/processed/tick_features).
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES = Path(os.environ.get("T3_FEATURES_DIR", ROOT.parent / "data/processed/tick_features"))
EVENTS = ROOT / "data/processed/tick_features/events.parquet"
TABLES, FIGURES = ROOT / "tables", ROOT / "figures"

TICK = {"ES.v.0": 0.25, "NQ.v.0": 0.25, "ZN.v.0": 1 / 64}
STEP, LAG = 0.02, 5                    # grid step in seconds; 100 ms = 5 steps
HISTORY, PCT, K_FLOOR = 20, 0.99, 1.0
EXITS = [300, 60, 30]
LEGS = [("ZN.v.0", "ES.v.0", -1), ("ES.v.0", "ZN.v.0", -1),
        ("ES.v.0", "ES.v.0", 1), ("NQ.v.0", "NQ.v.0", 1), ("ZN.v.0", "ZN.v.0", 1)]
SAMPLES = ["oos_backward", "development", "oos_forward"]
COLORS = {"oos_backward": "#0072B2", "development": "#E69F00", "oos_forward": "#009E73", "control": "#999999"}
LABELS = {"oos_backward": "2015-2023", "development": "2024-Aug 2025", "oos_forward": "Sep 2025-2026", "control": "control windows"}


def load_windows() -> pd.DataFrame:
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev.family.str.startswith("macro") | ev.subevent.eq("statement") | ev.family.eq("fomc_control")]
    ev["group"] = np.where(ev.family.str.startswith("macro"), "macro", "fomc")
    ev["kind"] = np.where(ev.family.str.endswith("pseudo"), "pseudo", np.where(ev.is_control, "control", "event"))
    ev["year"] = ev.event_time_utc.dt.year
    return ev[["event_id", "instrument", "window_key", "family", "group", "kind", "sample", "year", "event_date",
               "event_time_utc", "first_change_ms", "fp300s_25_seconds", "etype" if "etype" in ev else "event_types"]]


def fine_moves(fine: pd.DataFrame) -> pd.DataFrame:
    """Per grid point: 100 ms mid move in ticks, 100 ms volume, validity, mid and half spread."""
    fine = fine.sort_values(["event_id", "instrument", "seconds"]).copy()
    fine["mid"] = (fine.bid + fine.ask) / 2
    fine["half_spread_bp"] = (fine.ask - fine.bid) / 2 / fine.mid * 1e4
    fine["cum_vol"] = fine.cum_buy_volume + fine.cum_sell_volume + fine.cum_unknown_volume
    g = fine.groupby(["event_id", "instrument"], sort=False)
    fine["move_ticks"] = (fine.mid - g.mid.shift(LAG)) / fine.instrument.map(TICK)
    fine["vol_100ms"] = fine.cum_vol - g.cum_vol.shift(LAG)
    fine["valid"] = fine.state_valid & g.state_valid.shift(LAG).fillna(False).astype(bool)
    fine["mid_next"] = g.mid.shift(-1)
    fine["half_spread_next_bp"] = g.half_spread_bp.shift(-1)
    fine["valid_next"] = g.state_valid.shift(-1).fillna(False).astype(bool)
    return fine


def calibrate(fine: pd.DataFrame, win: pd.DataFrame) -> pd.DataFrame:
    """k and v per traded window from the previous HISTORY windows of the same contract and family."""
    pool_rows = fine.merge(win[["event_id", "instrument", "kind", "group", "event_time_utc"]], on=["event_id", "instrument"])
    pool_rows = pool_rows[pool_rows.valid & ((pool_rows.kind != "event") | (pool_rows.seconds < 0))]
    out = []
    for (inst, grp), w in win.groupby(["instrument", "group"]):
        order = w.sort_values("event_time_utc").drop_duplicates("event_id")
        ids = order.event_id.tolist()
        rows = pool_rows[(pool_rows.instrument == inst) & (pool_rows.group == grp)]
        by_id = {k: (v.move_ticks.abs().to_numpy(), v.vol_100ms.to_numpy()) for k, v in rows.groupby("event_id")}
        for i, eid in enumerate(ids):
            if i < HISTORY:
                continue
            prev = [by_id[p] for p in ids[i - HISTORY:i] if p in by_id]
            if len(prev) < HISTORY:
                continue
            mv = np.concatenate([p[0] for p in prev]); vol = np.concatenate([p[1] for p in prev])
            out.append({"event_id": eid, "instrument": inst, "k_ticks": max(K_FLOOR, np.nanquantile(mv, PCT)),
                        "v_contracts": np.nanquantile(vol, PCT)})
    return pd.DataFrame(out)


def triggers(fine: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """First grid point per window and contract where the calibrated rule fires."""
    f = fine.merge(cal, on=["event_id", "instrument"])
    fire = f[f.valid & f.valid_next & (f.move_ticks.abs() >= f.k_ticks) & (f.vol_100ms >= f.v_contracts)]
    first = fire.sort_values("seconds").groupby(["event_id", "instrument"], as_index=False).first()
    return first[["event_id", "instrument", "seconds", "move_ticks", "vol_100ms", "k_ticks", "v_contracts"]].rename(
        columns={"seconds": "trigger_s", "instrument": "signal_instrument"})


def build_trades(trig: pd.DataFrame, fine: pd.DataFrame, secs: pd.DataFrame, win: pd.DataFrame) -> pd.DataFrame:
    """Entry one grid point after the trigger in the traded contract; exits from the 1 s panel."""
    entry_cols = fine[["event_id", "instrument", "seconds", "mid_next", "half_spread_next_bp", "valid_next"]].rename(
        columns={"instrument": "trade_instrument", "seconds": "trigger_s"})
    secs = secs.copy()
    secs["mid"] = (secs.bid + secs.ask) / 2
    secs["half_spread_bp"] = (secs.ask - secs.bid) / 2 / secs.mid * 1e4
    sec_idx = {k: g.sort_values("seconds") for k, g in secs.groupby(["window_key", "instrument"])}
    meta = win.drop_duplicates(["event_id", "instrument"])[["event_id", "instrument", "window_key", "kind", "group", "sample",
                                                            "year", "event_date", "family", "anchor_offset_s"]]
    rows = []
    for sig, trd, sign in LEGS:
        t = trig[trig.signal_instrument == sig].copy()
        t["trade_instrument"] = trd
        t = t.merge(entry_cols, on=["event_id", "trade_instrument", "trigger_s"], how="inner")
        t = t[t.valid_next]
        t = t.merge(meta.rename(columns={"instrument": "trade_instrument"}), on=["event_id", "trade_instrument"])
        t["direction"] = sign * np.sign(t.move_ticks)
        t["entry_s"] = t.trigger_s + STEP
        for h in EXITS:
            mids, hs = [], []
            for _, r in t.iterrows():
                g = sec_idx.get((r.window_key, trd))
                target = r.entry_s + h + r.anchor_offset_s      # panel seconds are relative to its own anchor
                if g is None:
                    mids.append(np.nan); hs.append(np.nan); continue
                ok = g[(g.seconds <= target) & g.state_valid]
                if ok.empty or ok.seconds.iloc[-1] < target - 1.5:
                    mids.append(np.nan); hs.append(np.nan)
                else:
                    mids.append(ok.mid.iloc[-1]); hs.append(ok.half_spread_bp.iloc[-1])
            t[f"exit_mid_{h}"] = mids
            t[f"gross_bp_{h}"] = t.direction * np.log(t[f"exit_mid_{h}"] / t.mid_next) * 1e4
            t[f"cost_bp_{h}"] = t.half_spread_next_bp + np.array(hs)
            t[f"net_bp_{h}"] = t[f"gross_bp_{h}"] - t[f"cost_bp_{h}"]
        t["leg"] = f"{sig[:2]}->{trd[:2]}"
        rows.append(t)
    out = pd.concat(rows, ignore_index=True)
    return out.drop(columns=["valid_next"]).rename(columns={"mid_next": "entry_mid", "half_spread_next_bp": "entry_half_spread_bp"})


def summarize(t: pd.DataFrame, by: list[str], h: int = 300) -> pd.DataFrame:
    def stats(g: pd.DataFrame) -> pd.Series:
        x = g[f"net_bp_{h}"].dropna(); n = len(x)
        sd = x.std(ddof=1) if n > 1 else np.nan
        return pd.Series({"n": n, "mean_gross_bp": g[f"gross_bp_{h}"].mean(), "mean_cost_bp": g[f"cost_bp_{h}"].mean(),
                          "mean_net_bp": x.mean(), "se_net_bp": sd / np.sqrt(n) if n else np.nan,
                          "t_net": x.mean() / (sd / np.sqrt(n)) if n > 1 and sd else np.nan,
                          "t_gross": g[f"gross_bp_{h}"].mean() / (g[f"gross_bp_{h}"].std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan,
                          "hit_rate": (x > 0).mean(), "median_trigger_s": g.trigger_s.median()})
    return t.groupby(by, observed=True).apply(stats, include_groups=False).reset_index()


def verdict(tr: pd.DataFrame) -> pd.DataFrame:
    p = tr[(tr.leg == "ZN->ES") & (tr.group == "macro")]
    live = p[(p.kind == "event") & (p["sample"] == "oos_backward")]
    dev = p[(p.kind == "event") & (p["sample"] == "development")]
    ctrl = p[p.kind == "control"]
    by_year = summarize(live, ["year"]); by_year.to_csv(TABLES / "strategy_trigger_primary_by_year.csv", index=False)
    s, d, c = summarize(live, ["leg"]).iloc[0], summarize(dev, ["leg"]).iloc[0], summarize(ctrl, ["leg"]).iloc[0]
    ex22 = summarize(live[live.year != 2022], ["leg"]).iloc[0]
    h60 = summarize(live, ["leg"], h=60).iloc[0]
    v = {"primary": "ZN trigger -> ES, macro, 2015-2023, 300 s", "n": s.n, "mean_net_bp": s.mean_net_bp, "t_net": s.t_net,
         "hit_rate": s.hit_rate, "dev_n": d.n, "dev_mean_net_bp": d.mean_net_bp, "control_n": c.n,
         "control_mean_gross_bp": c.mean_gross_bp, "control_t_gross": c.t_gross,
         "years_positive": int((by_year.mean_net_bp > 0).sum()), "years": len(by_year),
         "mean_net_ex2022": ex22.mean_net_bp, "mean_net_60s": h60.mean_net_bp}
    v["threshold_met"] = bool(s.mean_net_bp > 0 and s.t_net >= 2 and d.mean_net_bp > 0 and not (c.t_gross >= 2))
    v["gate_years"] = bool(v["years_positive"] >= 6)
    v["gate_ex2022"] = bool(ex22.mean_net_bp > 0)
    v["gate_60s"] = bool(h60.mean_net_bp > 0)
    v["supported"] = v["threshold_met"] and v["gate_years"] and v["gate_ex2022"] and v["gate_60s"]
    return pd.DataFrame([v])


def plot(tr: pd.DataFrame, path: Path) -> None:
    m = tr[tr.group == "macro"]
    legs = [l for _, _, _ in [(0, 0, 0)] for l in ["ZN->ES", "ES->ZN", "ES->ES", "NQ->NQ", "ZN->ZN"]]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, h in zip(axes, EXITS):
        for j, grp in enumerate(SAMPLES + ["control"]):
            sub = m[(m.kind == "control")] if grp == "control" else m[(m.kind == "event") & (m["sample"] == grp)]
            s = summarize(sub, ["leg"], h=h).set_index("leg").reindex(legs)
            x = np.arange(len(legs)) + (j - 1.5) * 0.19
            ax.bar(x, s.mean_net_bp, width=0.18, yerr=s.se_net_bp, color=COLORS[grp], label=LABELS[grp],
                   error_kw={"lw": 0.8, "capsize": 2})
        ax.axhline(0, color="#bbbbbb", lw=0.8)
        ax.set_xticks(np.arange(len(legs))); ax.set_xticklabels(legs)
        ax.set_title(f"exit {h} s after the trigger", fontsize=10, loc="left")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color="#eeeeee", lw=0.6)
    axes[0].set_ylabel("mean net return per triggered trade, bp")
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Burst-trigger trend trade on macro mornings: signal contract -> traded contract, net of the quoted spread",
                 fontsize=10.5, x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def lead_lag(win: pd.DataFrame) -> pd.DataFrame:
    e = win[(win.kind == "event") & (win.group == "macro")]
    wide = e.pivot_table(index=["event_id", "year"], columns="instrument", values=["first_change_ms", "fp300s_25_seconds"])
    out = pd.DataFrame({"year": wide.index.get_level_values("year").to_numpy(),
                        "first_change_es_minus_zn_ms": wide[("first_change_ms", "ES.v.0")] - wide[("first_change_ms", "ZN.v.0")],
                        "fp25_es_minus_zn_ms": 1000 * (wide[("fp300s_25_seconds", "ES.v.0")] - wide[("fp300s_25_seconds", "ZN.v.0")])}).reset_index(drop=True)
    g = out.groupby("year").agg(n=("first_change_es_minus_zn_ms", "size"),
                                first_change_median_ms=("first_change_es_minus_zn_ms", "median"),
                                zn_first_share=("first_change_es_minus_zn_ms", lambda s: (s > 0).mean()),
                                fp25_median_ms=("fp25_es_minus_zn_ms", "median"),
                                zn_fp25_first_share=("fp25_es_minus_zn_ms", lambda s: (s > 0).mean()))
    return g.reset_index()


def main() -> None:
    win = load_windows()
    fine = fine_moves(pd.read_parquet(FEATURES / "fine.parquet"))
    secs = pd.read_parquet(FEATURES / "seconds.parquet",
                           columns=["window_key", "instrument", "anchor_time_utc", "seconds", "state_valid", "bid", "ask", "logmid"])
    # the 1 s panel is anchored per window (sometimes the pseudo clock); re-express its clock as seconds after each event
    anchor = secs.drop_duplicates(["window_key", "instrument"])[["window_key", "instrument", "anchor_time_utc"]]
    win = win.merge(anchor, on=["window_key", "instrument"], how="left")
    win["anchor_offset_s"] = (win.event_time_utc - win.anchor_time_utc).dt.total_seconds()
    # alignment check: the 1 s panel at 0 s must equal the 20 ms panel at 0 s for live windows
    chk = fine[(fine.seconds == 0) & fine.event_id.isin(win[win.kind == "event"].event_id)].merge(
        win[["event_id", "instrument", "window_key"]], on=["event_id", "instrument"]).merge(
        secs[["window_key", "instrument", "seconds", "logmid"]].rename(columns={"seconds": "sec_s"}), on=["window_key", "instrument"], suffixes=("", "_sec"))
    chk = chk.merge(win.drop_duplicates(["event_id", "instrument"])[["event_id", "instrument", "anchor_offset_s"]], on=["event_id", "instrument"])
    chk = chk[chk.sec_s == chk.anchor_offset_s]
    diff = (chk.logmid - chk.logmid_sec).abs()
    print(f"alignment: {len(chk)} windows, |logmid diff| at 0 s: max {diff.max():.2e}, share > 1e-6: {(diff > 1e-6).mean():.3f}")
    if (diff > 1e-6).any():
        print(chk.loc[diff > 1e-6, ["event_id", "instrument", "logmid", "logmid_sec"]].head(8).to_string())

    cal = calibrate(fine, win)
    cal.merge(win.drop_duplicates(["event_id", "instrument"])[["event_id", "instrument", "year", "kind"]]).to_csv(
        TABLES / "strategy_trigger_thresholds.csv", index=False)
    trig = triggers(fine, cal)
    tr = build_trades(trig, fine, secs, win)
    tr = tr[tr.kind != "pseudo"]
    tr.to_parquet(TABLES / "strategy_trigger_trades.parquet", index=False)

    traded = cal.merge(win.drop_duplicates(["event_id", "instrument"])[["event_id", "instrument", "kind", "group", "sample"]])
    fired = traded.merge(trig.rename(columns={"signal_instrument": "instrument"})[["event_id", "instrument", "trigger_s"]], how="left")
    rate = fired[fired.kind != "pseudo"].groupby(["group", "kind", "instrument"]).agg(
        windows=("event_id", "size"), fired=("trigger_s", lambda s: s.notna().sum()),
        median_trigger_s=("trigger_s", "median")).reset_index()
    rate["fire_rate"] = rate.fired / rate.windows
    rate.to_csv(TABLES / "strategy_trigger_fire_rate.csv", index=False)

    for h in EXITS:
        summarize(tr, ["group", "leg", "kind", "sample"], h=h).assign(exit_s=h).to_csv(
            TABLES / f"strategy_trigger_summary_{h}s.csv", index=False)
    summarize(tr[(tr.group == "macro") & (tr.kind == "event")], ["leg", "year"]).to_csv(
        TABLES / "strategy_trigger_by_year.csv", index=False)
    v = verdict(tr); v.to_csv(TABLES / "strategy_trigger_verdict.csv", index=False)
    ll = lead_lag(win); ll.to_csv(TABLES / "strategy_trigger_lead_lag.csv", index=False)
    plot(tr, FIGURES / "paper" / "strategy_trigger_net.png")

    pd.set_option("display.width", 230)
    print("\nPre-declared primary:"); print(v.T.to_string())
    print("\nFire rates:"); print(rate.round(3).to_string())
    print("\nThresholds (median k ticks, v contracts) by instrument and kind:")
    print(traded.merge(cal).groupby(["group", "instrument"])[["k_ticks", "v_contracts"]].median().round(2).to_string())
    for h in EXITS:
        s = summarize(tr[tr.group == "macro"], ["leg", "kind", "sample"], h=h)
        s["grp"] = np.where(s.kind == "control", "control", s["sample"])
        print(f"\nMacro, exit {h} s: mean net bp (t) by leg and sample")
        piv = s.pivot_table(index="leg", columns="grp", values=["mean_net_bp", "t_net", "n"]).round(2)
        print(piv.to_string())
    print("\nFOMC statements, exit 300 s:")
    print(summarize(tr[tr.group == "fomc"], ["leg", "kind"]).round(2).to_string())
    print("\nES-ZN lead-lag (positive = ZN first):"); print(ll.round(2).to_string())


if __name__ == "__main__":
    main()
