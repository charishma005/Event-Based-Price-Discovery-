"""Follow-up ideas 1, 3, 4 and 5 (specification: reports/trading_strategies.md, appendix A).

Reads data/processed/tick_features/events.parquet and writes tables/followup_*.csv. Thresholds,
z-score moments and prediction coefficients come from development events (before 2023) only.

Run: python -m scripts.run_followup_ideas
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.microstructure.tick_arrays import tick_size
from src.strategies.inference import event_bootstrap_mean, ols_clustered, t_test
from src.utils.config import PROJECT_ROOT

EVENTS = PROJECT_ROOT / "data" / "processed" / "tick_features" / "events.parquet"
TABLES = PROJECT_ROOT / "tables"
HOLDOUT_START = pd.Timestamp("2023-01-01")
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
SAMPLES = ("development", "holdout", "full_sample")


def load() -> pd.DataFrame:
    e = pd.read_parquet(EVENTS)
    e = e.loc[e["family"].isin(["fomc", "macro"]) & e["instrument"].isin(INSTRUMENTS)
              & e["dataset_condition"].ne("degraded") & e["pre_state_valid"]].copy()
    e["event_date"] = pd.to_datetime(e["event_date"])
    e["sample"] = np.where(e["event_date"] < HOLDOUT_START, "development", "holdout")
    e["kind"] = np.where(e["family"].eq("macro"), "macro", "fomc_" + e["subevent"].astype(str))
    e["etype"] = np.where(e["family"].eq("macro"), e["event_types"].str.split("|").str[0], e["kind"])
    e["price"] = np.exp(e["pre_logmid"])
    e["tick_bp"] = e["instrument"].map(tick_size) / e["price"] * 1e4
    return e


def _subset(f: pd.DataFrame, sample: str) -> pd.DataFrame:
    return f if sample == "full_sample" else f.loc[f["sample"].eq(sample)]


def _summary(r: pd.Series, events: pd.Series) -> dict:
    r = pd.Series(r, dtype=float).groupby(np.asarray(events)).mean().dropna()   # one value per event
    if r.empty:
        return {"N_trades": 0}
    t, p = t_test(r)
    lo, hi = event_bootstrap_mean(r)
    return {"N_trades": len(r), "mean_bp": r.mean(), "median_bp": r.median(), "hit_rate": (r > 0).mean(),
            "t_stat": t, "p_value": p, "CI_low": lo, "CI_high": hi}


def _classify(rows: pd.DataFrame) -> str:
    r = rows.set_index("sample")
    if not {"development", "holdout", "full_sample"} <= set(r.index):
        return "NOT SUPPORTED"
    dev, hold, full = (r.loc[k] for k in ("development", "holdout", "full_sample"))
    if dev.get("mean_net_bp", np.nan) > 0 and hold.get("mean_net_bp", np.nan) > 0:
        if hold.get("N_trades", 0) >= 3 and full.get("CI_low", np.nan) > 0:
            return "SUPPORTED"
        return "WEAK EVIDENCE"
    return "NOT SUPPORTED"


# ---------------------------------------------------------------- idea 1

def idea1(e: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, regs = [], []
    for kind in ("macro", "fomc_statement"):
        k = e.loc[e["kind"].eq(kind)].copy()
        k["ret_0_60"], k["ret_0_300"] = k["w60s_total_bp"], k["w300s_total_bp"]
        k["direction"] = np.sign(k["ret_0_60"])
        k["cont_1_5"] = k["direction"] * (k["ret_0_300"] - k["ret_0_60"])
        k["abs_ret"] = k["ret_0_60"].abs()
        k["cost_bp"] = 0.5 * (k["post60_spread_ticks"] + k["late_spread_ticks"]) * k["tick_bp"]
        parts = {"s_depth": 1 - k["post60_depth_ratio"], "s_spread": k["post60_spread_change_ticks"]}
        scored = []
        for inst, g in k.groupby("instrument"):
            dev = g.loc[g["sample"].eq("development")]
            g = g.copy()
            stress = 0.0
            for name, values in parts.items():
                v = values.loc[g.index]
                d = v.loc[dev.index]
                stress = stress + ((v - d.mean()) / d.std() if d.std() > 0 else v * 0)
            g["stress"] = stress
            g["large"] = g["abs_ret"] >= dev["abs_ret"].quantile(0.75)
            g["stressed"] = g["stress"] >= g.loc[dev.index, "stress"].quantile(0.75)
            scored.append(g)
        k = pd.concat(scored)
        k["abs_x_stress"] = k["abs_ret"] * k["stress"]
        rules = {"T1-fade": (k["large"] & k["stressed"], -1), "T1-follow": (k["large"], 1),
                 "T1-follow-calm": (k["large"] & ~k["stressed"], 1)}
        for rule, (mask, sign) in rules.items():
            trades = k.loc[mask].copy()
            trades["gross"] = sign * trades["cont_1_5"]
            trades["net"] = trades["gross"] - trades["cost_bp"]
            for inst in (*INSTRUMENTS, "portfolio"):
                t = trades if inst == "portfolio" else trades.loc[trades["instrument"].eq(inst)]
                block = []
                for sample in SAMPLES:
                    s = _subset(t, sample)
                    net = _summary(s["net"], s["event_id"])
                    gross = _summary(s["gross"], s["event_id"])
                    block.append({"idea": 1, "events": kind, "rule": rule, "instrument": inst[:2] if inst != "portfolio"
                                  else inst, "sample": sample, "N_trades": net.get("N_trades", 0),
                                  "mean_gross_bp": gross.get("mean_bp"), "mean_net_bp": net.get("mean_bp"),
                                  **{key: net.get(key) for key in ("hit_rate", "t_stat", "p_value", "CI_low", "CI_high")}})
                label = _classify(pd.DataFrame(block))
                rows += [{**b, "classification": label} for b in block]
        for sample in SAMPLES:
            s = _subset(k, sample)
            for inst in INSTRUMENTS:
                f = s.loc[s["instrument"].eq(inst)]
                for name, xs in (("price_only", ["abs_ret"]), ("price_stress", ["abs_ret", "stress"]),
                                 ("interaction", ["abs_ret", "stress", "abs_x_stress"])):
                    regs.append(ols_clustered(f, "cont_1_5", xs).assign(idea=1, events=kind, instrument=inst[:2],
                                                                         sample=sample, model=name))
            regs.append(ols_clustered(s, "cont_1_5", ["abs_ret", "stress", "abs_x_stress"], fixed_effects="instrument")
                        .assign(idea=1, events=kind, instrument="pooled_FE", sample=sample, model="interaction"))
    return pd.DataFrame(rows), pd.concat(regs, ignore_index=True)


# ---------------------------------------------------------------- idea 3

def idea3(e: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    st = e.loc[e["kind"].eq("fomc_statement")].set_index(["matched_event", "instrument"])
    pc = e.loc[e["kind"].eq("fomc_press_conference")].set_index(["matched_event", "instrument"])
    both = st.index.intersection(pc.index)
    st, pc = st.loc[both], pc.loc[both]
    d = pd.DataFrame({
        "event_id": both.get_level_values(0), "instrument": both.get_level_values(1),
        "sample": st["sample"].to_numpy(),
        "st_0_5": st["w300s_total_bp"].to_numpy(),
        "st_0_30": 1e4 * (pc["pre_logmid"].to_numpy() - st["pre_logmid"].to_numpy()),
        "pc_0_5": pc["w300s_total_bp"].to_numpy(),
        "pc_pre60_depth_ratio": pc["pre60_depth_ratio"].to_numpy(),
        "cost_bp": (0.5 * (pc["pre1_spread_ticks"] + pc["late_spread_ticks"]) * pc["tick_bp"]).to_numpy(),
    })
    d["st_5_30"] = d["st_0_30"] - d["st_0_5"]
    regs, rows = [], []
    for sample in SAMPLES:
        s = _subset(d, sample)
        for inst in INSTRUMENTS:
            f = s.loc[s["instrument"].eq(inst)]
            for y, x in (("st_5_30", "st_0_5"), ("pc_0_5", "st_0_5"), ("pc_0_5", "st_0_30")):
                regs.append(ols_clustered(f, y, [x]).assign(idea=3, instrument=inst[:2], sample=sample,
                                                            model=f"{y}_on_{x}"))
        regs.append(ols_clustered(s, "pc_0_5", ["st_0_30"], fixed_effects="instrument")
                    .assign(idea=3, instrument="pooled_FE", sample=sample, model="pc_0_5_on_st_0_30"))
    d["gross"] = -np.sign(d["st_0_30"]) * d["pc_0_5"]          # fade the statement move at the PC start
    d["net"] = d["gross"] - d["cost_bp"]
    for inst in (*INSTRUMENTS, "portfolio"):
        t = d if inst == "portfolio" else d.loc[d["instrument"].eq(inst)]
        block = []
        for sample in SAMPLES:
            s = _subset(t, sample)
            net, gross = _summary(s["net"], s["event_id"]), _summary(s["gross"], s["event_id"])
            block.append({"idea": 3, "events": "fomc_press_conference", "rule": "T3-fade-statement-at-PC",
                          "instrument": inst[:2] if inst != "portfolio" else inst, "sample": sample,
                          "N_trades": net.get("N_trades", 0), "mean_gross_bp": gross.get("mean_bp"),
                          "mean_net_bp": net.get("mean_bp"),
                          **{k: net.get(k) for k in ("hit_rate", "t_stat", "p_value", "CI_low", "CI_high")}})
        label = _classify(pd.DataFrame(block))
        rows += [{**b, "classification": label} for b in block]
    return pd.DataFrame(rows), pd.concat(regs, ignore_index=True)


# ---------------------------------------------------------------- ideas 4 and 5

def _oos(dev: pd.DataFrame, hold: pd.DataFrame, y: str, xs: list[str], fe: str | None) -> float:
    """Holdout R2 of the development OLS fit (fixed effects as dummies, benchmark = development mean)."""
    cols = [y, *xs] + ([fe] if fe else [])
    dev, hold = (x[cols].replace([np.inf, -np.inf], np.nan).dropna() for x in (dev, hold))
    if len(dev) < 10 or hold.empty:
        return np.nan

    def design(frame):
        X = frame[xs].astype(float).copy()
        if fe:
            return pd.concat([X, pd.get_dummies(frame[fe], dtype=float)], axis=1)
        return X.assign(const=1.0)

    Xd = design(dev)
    beta = np.linalg.lstsq(Xd.to_numpy(), dev[y].to_numpy(float), rcond=None)[0]
    Xh = design(hold).reindex(columns=Xd.columns, fill_value=0.0)     # unseen cells get no fixed effect
    pred = Xh.to_numpy() @ beta
    sse = ((hold[y] - pred) ** 2).sum()
    sst = ((hold[y] - dev[y].mean()) ** 2).sum()
    return float(1 - sse / sst) if sst > 0 else np.nan


def idea4(e: pd.DataFrame) -> pd.DataFrame:
    k = e.loc[e["kind"].isin(["macro", "fomc_statement"])].copy()
    k["log_abs_300"] = np.log1p(k["w300s_total_bp"].abs())
    k["log_abs_60"] = np.log1p(k["w60s_total_bp"].abs())
    k["cell"] = k["etype"] + "|" + k["instrument"]
    regs = []
    xs = ["pre60_depth_ratio", "pre60_spread_change_ticks"]
    for scope, f in (("all", k), ("macro", k.loc[k["kind"].eq("macro")]), ("fomc_statement", k.loc[k["kind"].eq("fomc_statement")])):
        for y in ("log_abs_300", "log_abs_60"):
            dev, hold = f.loc[f["sample"].eq("development")], f.loc[f["sample"].eq("holdout")]
            oos_full = _oos(dev, hold, y, xs, "cell")
            oos_fe = _oos(dev.assign(_zero=0.0), hold.assign(_zero=0.0), y, ["_zero"], "cell")
            for sample in SAMPLES:
                regs.append(ols_clustered(_subset(f, sample), y, xs, fixed_effects="cell").assign(
                    idea=4, scope=scope, y=y, sample=sample, r2_oos_holdout=oos_full, r2_oos_fe_only=oos_fe))
            for inst in INSTRUMENTS:
                g = f.loc[f["instrument"].eq(inst)]
                regs.append(ols_clustered(g, y, xs, fixed_effects="etype").assign(
                    idea=4, scope=f"{scope}|{inst[:2]}", y=y, sample="full_sample"))
    return pd.concat(regs, ignore_index=True)


def idea5(e: pd.DataFrame) -> pd.DataFrame:
    k = e.loc[e["kind"].isin(["macro", "fomc_statement"])]
    r5 = k.pivot_table(index=["event_id", "kind", "sample"], columns="instrument", values="w5s_total_bp")
    r60 = k.pivot_table(index=["event_id", "kind", "sample"], columns="instrument", values="w60s_total_bp")
    regs = []
    for target in INSTRUMENTS:
        for leader in INSTRUMENTS:
            if leader == target:
                continue
            d = pd.DataFrame({"y": r60[target] - r5[target], "own_5s": r5[target], "lead_5s": r5[leader]}).reset_index()
            for scope, f in (("all", d), ("macro", d.loc[d["kind"].eq("macro")]),
                             ("fomc_statement", d.loc[d["kind"].eq("fomc_statement")])):
                dev, hold = f.loc[f["sample"].eq("development")], f.loc[f["sample"].eq("holdout")]
                oos = _oos(dev, hold, "y", ["own_5s", "lead_5s"], None)
                oos_own = _oos(dev, hold, "y", ["own_5s"], None)
                for sample in SAMPLES:
                    regs.append(ols_clustered(_subset(f, sample), "y", ["own_5s", "lead_5s"]).assign(
                        idea=5, target=target[:2], leader=leader[:2], scope=scope, sample=sample,
                        r2_oos_holdout=oos, r2_oos_own_only=oos_own))
    return pd.concat(regs, ignore_index=True)


def main() -> None:
    e = load()
    TABLES.mkdir(exist_ok=True)
    counts = e.drop_duplicates("event_id").groupby(["kind", "sample"]).size().unstack()
    print("Events by kind and sample:\n" + counts.to_string())
    s1, r1 = idea1(e)
    s3, r3 = idea3(e)
    pd.concat([s1, s3], ignore_index=True).to_csv(TABLES / "followup_strategies.csv", index=False)
    pd.concat([r1, r3], ignore_index=True).to_csv(TABLES / "followup_regressions_ideas_1_3.csv", index=False)
    idea4(e).to_csv(TABLES / "followup_idea4_withdrawal_magnitude.csv", index=False)
    idea5(e).to_csv(TABLES / "followup_idea5_lead_lag.csv", index=False)
    print("Wrote tables/followup_*.csv")


if __name__ == "__main__":
    main()
