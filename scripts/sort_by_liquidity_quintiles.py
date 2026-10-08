"""Quintile sorts: does liquidity stress (or recovery) at +5:00 line up with what the first move does next?

Uses every FOMC meeting, not just threshold trades. Per instrument, meetings are put into five equal
groups by the liquidity score at +5:00 (stress, as in P2; recovery score, as in P3). The quintile
cut points are the development (2015-2022) 20/40/60/80th percentiles and are applied unchanged to
2023-2026, so no later information sets the groups. Scores come from the frozen development
parameters (output/fomc_strategy_frozen_params.json); nothing here changes the original test.

Outcome: continuation of the first move = sign(ret 0 -> +5:00) x mid return from +5:00 to +5:00 + h,
h = 5, 10, 15, 30 minutes (+5 -> +10, +15, +20, +35; the last ends after the +30 press-conference
start on meetings that have one). Also the absolute forward move (size, regardless of direction).

Per instrument x score x sample x quintile: N, mean, median, share continuing, event-bootstrap 95% CI.
Trend tests per instrument x score x sample x horizon:
  - slope of continuation on quintile number (1..5), OLS with robust errors
  - Spearman correlation between the score and continuation (all meetings, not grouped)
  - Q5 - Q1 difference with a permutation p-value (10,000 shuffles of the score across meetings)
Prediction from the earlier results: for NQ, higher stress -> lower continuation (reversal).

Run: python -m scripts.sort_by_liquidity_quintiles
Writes tables/liquidity_quintiles.csv, tables/liquidity_quintile_trends.csv and
figures/liquidity_quintiles/*.png
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from scripts.audit_p2_p3 import HORIZONS, assemble
from src.strategies.inference import event_bootstrap_mean
from src.utils.config import PROJECT_ROOT

TABLES = PROJECT_ROOT / "tables"
FIG = PROJECT_ROOT / "figures" / "liquidity_quintiles"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
SCORES = {"stress": "liquidity stress at +5:00 (P2 score)", "recovery_score": "liquidity recovery at +5:00 (P3 score)"}
SAMPLES = ("development", "holdout", "full_sample")
PRIMARY = "15m"                      # +5:00 -> +20:00, the registered exit
PERMUTATIONS = 10_000
SEED = 20261008
LABEL = {h: f"+5 to +{5 + int(h[:-1])} min" for h in HORIZONS}


def assign_quintiles(scored: pd.DataFrame) -> pd.DataFrame:
    out = scored.loc[scored["ret_0_5m"].notna() & scored["ret_0_5m"].ne(0)].copy()
    for score in SCORES:
        out[f"q_{score}"] = np.nan
        for inst, g in out.groupby("instrument"):
            dev = g.loc[g["sample"].eq("development"), score].dropna()
            cuts = dev.quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
            q = np.searchsorted(cuts, g[score].to_numpy(), side="right") + 1
            out.loc[g.index, f"q_{score}"] = np.where(g[score].notna(), q, np.nan)
    return out


def _subset(d, sample):
    return d if sample == "full_sample" else d.loc[d["sample"].eq(sample)]


def quintile_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for score in SCORES:
        for inst in INSTRUMENTS:
            for sample in SAMPLES:
                f = _subset(d.loc[d["instrument"].eq(inst)], sample)
                for q in range(1, 6):
                    g = f.loc[f[f"q_{score}"].eq(q)]
                    for h in HORIZONS:
                        v = g[f"cont_{h}"].dropna()
                        lo, hi = event_bootstrap_mean(v, draws=4000)
                        rows.append({"score": score, "instrument": NAMES[inst], "sample": sample, "quintile": q,
                                     "horizon": h, "N": len(v), "mean_continuation_bp": v.mean(),
                                     "median_continuation_bp": v.median(),
                                     "share_continuing": (v > 0).mean() if len(v) else np.nan,
                                     "CI_low": lo, "CI_high": hi, "mean_abs_forward_bp": g[f"fwd_{h}"].abs().mean(),
                                     "mean_abs_first_move_bp": g["abs_ret_0_5m"].mean()})
    return pd.DataFrame(rows)


def trend_table(d: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for score in SCORES:
        for inst in INSTRUMENTS:
            for sample in SAMPLES:
                f = _subset(d.loc[d["instrument"].eq(inst)], sample)
                for h in HORIZONS:
                    x = f[[f"q_{score}", score, f"cont_{h}", f"fwd_{h}"]].dropna()
                    if len(x) < 10:
                        continue
                    q, s, y = x[f"q_{score}"].to_numpy(), x[score].to_numpy(), x[f"cont_{h}"].to_numpy()
                    fit = sm.OLS(y, sm.add_constant(q)).fit(cov_type="HC1")
                    rho, rho_p = st.spearmanr(s, y)
                    rho_abs, rho_abs_p = st.spearmanr(s, np.abs(x[f"fwd_{h}"].to_numpy()))
                    top, bottom = y[q == 5], y[q == 1]
                    diff = top.mean() - bottom.mean() if len(top) and len(bottom) else np.nan
                    perm = np.nan
                    if len(top) and len(bottom):
                        sims = np.empty(PERMUTATIONS)
                        for i in range(PERMUTATIONS):
                            qq = rng.permutation(q)
                            sims[i] = y[qq == 5].mean() - y[qq == 1].mean()
                        perm = float((np.abs(sims) >= abs(diff)).mean())
                    rows.append({"score": score, "instrument": NAMES[inst], "sample": sample, "horizon": h,
                                 "N": len(x), "slope_per_quintile_bp": fit.params[1], "slope_se": fit.bse[1],
                                 "slope_p": fit.pvalues[1], "spearman_score_continuation": rho, "spearman_p": rho_p,
                                 "Q5_minus_Q1_bp": diff, "N_Q1": len(bottom), "N_Q5": len(top),
                                 "permutation_p_Q5_minus_Q1": perm,
                                 "spearman_score_abs_forward": rho_abs, "spearman_abs_p": rho_abs_p})
    return pd.DataFrame(rows)


def figures(qt: pd.DataFrame, tt: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    colors = {"development": "#2a5ea8", "holdout": "#e0a030"}
    for score, title in SCORES.items():
        fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
        for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
            for k, sample in enumerate(("development", "holdout")):
                d = qt.loc[qt["score"].eq(score) & qt["instrument"].eq(inst) & qt["sample"].eq(sample)
                           & qt["horizon"].eq(PRIMARY)].sort_values("quintile")
                x = d["quintile"] + (k - 0.5) * 0.36
                ax.bar(x, d["mean_continuation_bp"], width=0.34, color=colors[sample],
                       label=f"{'2015-2022' if sample == 'development' else '2023-2026'}")
                ax.errorbar(x, d["mean_continuation_bp"], yerr=[d["mean_continuation_bp"] - d["CI_low"],
                            d["CI_high"] - d["mean_continuation_bp"]], fmt="none", ecolor="black", capsize=2, lw=0.8)
                for xi, n in zip(x, d["N"]):
                    ax.text(xi, 0.01, f"n={n}", ha="center", va="bottom", fontsize=7, color="#555555",
                            transform=ax.get_xaxis_transform())
            t = tt.loc[tt["score"].eq(score) & tt["instrument"].eq(inst) & tt["sample"].eq("full_sample")
                       & tt["horizon"].eq(PRIMARY)]
            if len(t):
                t = t.iloc[0]
                ax.set_title(f"{inst}: slope {t['slope_per_quintile_bp']:+.1f} bp/quintile (p = {t['slope_p']:.2f}); "
                             f"Q5-Q1 {t['Q5_minus_Q1_bp']:+.1f} (perm. p = {t['permutation_p_Q5_minus_Q1']:.2f})",
                             fontsize=9)
            ax.axhline(0, color="black", lw=0.6)
            ax.set_xticks(range(1, 6), ["Q1\nlowest", "Q2", "Q3", "Q4", "Q5\nhighest"])
            ax.set_xlabel(f"quintile of {title.split(' (')[0]}")
            ax.spines[["top", "right"]].set_visible(False)
        axes[0].set_ylabel("continuation of the first move,\n+5:00 to +20:00 (bp); > 0 = continues")
        axes[0].legend(frameon=False, fontsize=8)
        fig.suptitle(f"Every FOMC meeting sorted into fifths by {title}; numbers = meetings per bar "
                     f"(trend statistics: all years)")
        fig.tight_layout()
        fig.savefig(FIG / f"{score}_quintiles_primary.png", dpi=160)
        plt.close(fig)

        fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), sharey=True)
        shades = plt.cm.viridis(np.linspace(0.1, 0.85, len(HORIZONS)))
        for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
            for c, h in zip(shades, HORIZONS):
                d = qt.loc[qt["score"].eq(score) & qt["instrument"].eq(inst) & qt["sample"].eq("full_sample")
                           & qt["horizon"].eq(h)].sort_values("quintile")
                ax.plot(d["quintile"], d["mean_continuation_bp"], marker="o", color=c, label=LABEL[h])
            ax.axhline(0, color="black", lw=0.6)
            ax.set_xticks(range(1, 6), ["Q1", "Q2", "Q3", "Q4", "Q5"])
            ax.set_title(inst)
            ax.set_xlabel(f"quintile of {title.split(' (')[0]} (low -> high)")
            ax.spines[["top", "right"]].set_visible(False)
        axes[0].set_ylabel("mean continuation (bp), all years")
        axes[0].legend(frameon=False, fontsize=8, title="window")
        fig.suptitle(f"Same sort, every horizon: {title}")
        fig.tight_layout()
        fig.savefig(FIG / f"{score}_quintiles_by_horizon.png", dpi=160)
        plt.close(fig)


def main() -> None:
    _, _, scored, _ = assemble()
    d = assign_quintiles(scored)
    TABLES.mkdir(exist_ok=True)
    qt = quintile_table(d)
    qt.to_csv(TABLES / "liquidity_quintiles.csv", index=False)
    tt = trend_table(d)
    tt.to_csv(TABLES / "liquidity_quintile_trends.csv", index=False)
    figures(qt, tt)
    pd.set_option("display.width", 220)
    show = qt.loc[qt["horizon"].eq(PRIMARY) & qt["sample"].eq("full_sample")]
    print("Mean continuation +5:00 -> +20:00 by quintile (all years, bp):\n"
          + show.pivot_table(index=["score", "instrument"], columns="quintile", values="mean_continuation_bp")
          .round(1).to_string())
    t = tt.loc[tt["horizon"].eq(PRIMARY), ["score", "instrument", "sample", "N", "slope_per_quintile_bp", "slope_p",
                                          "Q5_minus_Q1_bp", "permutation_p_Q5_minus_Q1", "spearman_score_continuation"]]
    print("\nTrend tests (+5:00 -> +20:00):\n" + t.round(3).to_string(index=False))
    print("\nWrote tables/liquidity_quintile*.csv and figures/liquidity_quintiles/")


if __name__ == "__main__":
    main()
