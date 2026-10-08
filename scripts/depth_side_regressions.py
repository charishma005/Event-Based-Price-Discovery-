"""Does depth at +5:00 predict what happens from +5:00 to +20:00? Direction from the side split, size from the level.

Every FOMC meeting (no thresholds). Features from data/processed/fomc_strategy/features.parquet (all
measured at or before +5:00, 30-second trailing means against the -240..-61 s baseline); forward mid
returns from the one-second book via scripts.audit_p2_p3.assemble (read-only; the original test is
untouched).

Direction (signed by the first move, so > 0 means the move continues):
  continuation_h       = sign(ret 0->5) x mid return +5:00 -> +5:00+h, h = 5, 10, 15, 30 min (primary 15)
  aligned_imbalance    = sign(ret 0->5) x book imbalance at +5:00, imbalance = (bid - ask) / (bid + ask).
                         > 0: the side ahead of the move is the thinner one.
  ahead_vs_behind      = ln(depth ratio on the side ahead of the move / depth ratio on the side behind)
                         (up move: ahead = ask, behind = bid). < 0: ahead side thinner than behind.
Size (no sign):
  abs_forward_h        = |mid return +5:00 -> +5:00+h|
  depth_ratio_5m, spread_ratio_5m, abs_ret_0_5m (size of the first move) as predictors.

Models, per instrument and pooled with instrument fixed effects; event-clustered errors:
  D1  continuation ~ aligned_imbalance
  D2  continuation ~ ahead_vs_behind
  D3  continuation ~ abs_ret_0_5m + aligned_imbalance + ahead_vs_behind + depth_ratio_5m
  M1  abs_forward ~ depth_ratio_5m
  M2  abs_forward ~ depth_ratio_5m + spread_ratio_5m
  M3  abs_forward ~ abs_ret_0_5m + depth_ratio_5m + spread_ratio_5m
  M0  abs_forward ~ abs_ret_0_5m                (benchmark: does the book add to the first move's size?)
Fitted on development (2015-2022); the holdout (2023-2026) gets the out-of-sample R2 of that fit
against the development mean of the outcome (so the predictors, not the constant, earn the credit). The holdout was looked at in
earlier tests, so it is a check, not a clean test. Results for every sample are also fitted
separately for reference.

Run: python -m scripts.depth_side_regressions
Writes tables/depth_side_regressions.csv and figures/depth_side/*.png
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.audit_p2_p3 import HORIZONS, assemble
from src.strategies.inference import ols_clustered
from src.utils.config import PROJECT_ROOT

TABLES = PROJECT_ROOT / "tables"
FIG = PROJECT_ROOT / "figures" / "depth_side"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN", "pooled": "pooled"}
COLORS = {"ES": "#2a78d6", "NQ": "#eb6834", "ZN": "#1baf7a", "pooled": "#444444"}
SAMPLES = ("development", "holdout", "full_sample")
PRIMARY = "15m"
LABEL = {h: f"+5 to +{5 + int(h[:-1])}" for h in HORIZONS}
DIRECTION = {"D1": ["aligned_imbalance"], "D2": ["ahead_vs_behind"],
             "D3": ["abs_ret_0_5m", "aligned_imbalance", "ahead_vs_behind", "depth_ratio_5m"]}
SIZE = {"M0": ["abs_ret_0_5m"], "M1": ["depth_ratio_5m"], "M2": ["depth_ratio_5m", "spread_ratio_5m"],
        "M3": ["abs_ret_0_5m", "depth_ratio_5m", "spread_ratio_5m"]}


def build() -> pd.DataFrame:
    _, _, s, _ = assemble()
    s = s.loc[s["ret_0_5m"].notna() & s["ret_0_5m"].ne(0)].copy()
    up = np.sign(s["ret_0_5m"])
    s["aligned_imbalance"] = up * s["book_imbalance_5m"]
    ahead = np.where(up > 0, s["ask_depth_ratio_5m"], s["bid_depth_ratio_5m"])
    behind = np.where(up > 0, s["bid_depth_ratio_5m"], s["ask_depth_ratio_5m"])
    with np.errstate(divide="ignore", invalid="ignore"):
        s["ahead_vs_behind"] = np.log(ahead / behind)
    for h in HORIZONS:
        s[f"abs_forward_{h}"] = s[f"fwd_{h}"].abs()
    return s.replace([np.inf, -np.inf], np.nan)


def _oos(dev: pd.DataFrame, hold: pd.DataFrame, y: str, xs: list[str], pooled: bool) -> float:
    cols = [y, *xs, "instrument"]
    dev, hold = dev[cols].dropna(), hold[cols].dropna()
    if len(dev) < len(xs) + 5 or hold.empty:
        return np.nan

    def design(f):
        X = f[xs].astype(float)
        if pooled:
            X = pd.concat([X, pd.get_dummies(f["instrument"], dtype=float)], axis=1)
        else:
            X = X.assign(const=1.0)
        return X

    Xd = design(dev)
    beta = np.linalg.lstsq(Xd.to_numpy(), dev[y].to_numpy(float), rcond=None)[0]
    pred = design(hold).reindex(columns=Xd.columns, fill_value=0.0).to_numpy() @ beta
    bench = dev[y].mean()          # intercept-only development forecast
    sst = ((hold[y] - bench) ** 2).sum()
    return float(1 - ((hold[y] - pred) ** 2).sum() / sst) if sst > 0 else np.nan


def regressions(s: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for inst in (*INSTRUMENTS, "pooled"):
        f = s if inst == "pooled" else s.loc[s["instrument"].eq(inst)]
        pooled = inst == "pooled"
        for h in HORIZONS:
            specs = [(m, f"cont_{h}", xs, "direction") for m, xs in DIRECTION.items()] + \
                    [(m, f"abs_forward_{h}", xs, "size") for m, xs in SIZE.items()]
            for model, y, xs, kind in specs:
                dev, hold = f.loc[f["sample"].eq("development")], f.loc[f["sample"].eq("holdout")]
                oos = _oos(dev, hold, y, xs, pooled)
                for sample in SAMPLES:
                    sub = f if sample == "full_sample" else f.loc[f["sample"].eq(sample)]
                    fit = ols_clustered(sub, y, xs, fixed_effects="instrument" if pooled else None)
                    rows.append(fit.assign(instrument=NAMES[inst], horizon=h, window=LABEL[h], model=model, kind=kind,
                                           y=y, sample=sample, r2_oos_holdout=oos))
    out = pd.concat(rows, ignore_index=True)
    first = ["kind", "model", "instrument", "window", "horizon", "sample", "term", "coef", "se", "t_stat", "p_value",
             "ci_low", "ci_high", "r2", "r2_oos_holdout", "N", "N_events"]
    return out[[c for c in first if c in out]]


def figures(t: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    hz = list(HORIZONS)
    panels = [("D1", "aligned_imbalance", "aligned imbalance (> 0: side ahead of the move thinner)"),
              ("D2", "ahead_vs_behind", "ln(depth ahead / depth behind) (< 0: ahead thinner)"),
              ("M1", "depth_ratio_5m", "SIZE: |move +5 -> +h| per +1.0 depth ratio")]
    fig, axes = plt.subplots(1, 3, figsize=(18, 4.8))
    for ax, (model, term, title) in zip(axes, panels):
        for k, inst in enumerate(("ES", "NQ", "ZN", "pooled")):
            d = t.loc[t["model"].eq(model) & t["term"].eq(term) & t["instrument"].eq(inst)
                      & t["sample"].eq("full_sample")].set_index("horizon").reindex(hz)
            x = np.arange(len(hz)) + (k - 1.5) * 0.12
            ax.errorbar(x, d["coef"], yerr=[d["coef"] - d["ci_low"], d["ci_high"] - d["coef"]], fmt="o",
                        capsize=3, color=COLORS[inst], label=inst)
        ax.axhline(0, color="black", lw=0.6)
        ax.set_xticks(range(len(hz)), [f"{LABEL[h]} min" for h in hz], fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("coefficient (bp), 95% CI, all years")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Depth at +5:00 vs what happens next: direction (left, middle) and size (right); every FOMC meeting")
    fig.tight_layout()
    fig.savefig(FIG / "depth_side_coefficients.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), sharey=False)
    for ax, (kind, models) in zip(axes, (("direction", list(DIRECTION)), ("size", list(SIZE)))):
        d = t.loc[t["kind"].eq(kind) & t["horizon"].eq(PRIMARY) & t["sample"].eq("development")]
        d = d.drop_duplicates(["model", "instrument"])
        for k, inst in enumerate(("ES", "NQ", "ZN", "pooled")):
            for j, model in enumerate(models):
                r = d.loc[d["model"].eq(model) & d["instrument"].eq(inst)]
                if r.empty:
                    continue
                x = j + (k - 1.5) * 0.18
                ax.bar(x, r["r2"].iloc[0], width=0.17, color=COLORS[inst], alpha=0.45,
                       label=f"{inst} in-sample" if j == 0 else None)
                ax.plot(x, r["r2_oos_holdout"].iloc[0], "k_", ms=12, mew=2,
                        label="out of sample (2023-2026)" if (j == 0 and k == 0) else None)
        ax.axhline(0, color="black", lw=0.6)
        ax.set_xticks(range(len(models)), models)
        ax.set_title(f"{kind}: R2 at +5 to +20 min (bars: 2015-2022 fit; dash: 2023-2026 out of sample)", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "depth_side_r2.png", dpi=160)
    plt.close(fig)


def main() -> None:
    s = build()
    TABLES.mkdir(exist_ok=True)
    t = regressions(s)
    t.to_csv(TABLES / "depth_side_regressions.csv", index=False)
    figures(t)
    pd.set_option("display.width", 220)
    key = t.loc[t["horizon"].eq(PRIMARY) & t["term"].isin(["aligned_imbalance", "ahead_vs_behind", "depth_ratio_5m",
                                                            "spread_ratio_5m"])
                & t["model"].isin(["D1", "D2", "M2"])]
    key = key.assign(v=key.apply(lambda r: f"{r['coef']:+.2f} (p={r['p_value']:.2f})", axis=1))
    print("+5 -> +20 min, coefficient (p):\n" + key.pivot_table(index=["model", "term", "instrument"], columns="sample",
          values="v", aggfunc="first")[list(SAMPLES)].to_string())
    r2 = t.loc[t["horizon"].eq(PRIMARY) & t["sample"].eq("development")].drop_duplicates(["model", "instrument"])
    print("\nR2 at +5 -> +20 (2015-2022 fit) and out of sample on 2023-2026:\n"
          + r2.pivot_table(index="model", columns="instrument", values=["r2", "r2_oos_holdout"]).round(3).to_string())
    print("\nWrote tables/depth_side_regressions.csv and figures/depth_side/")


if __name__ == "__main__":
    main()
