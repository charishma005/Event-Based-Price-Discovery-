"""Slide chart: does a thinning book before the news predict how big the move is, and which way it goes?

Data: data/processed/tick_features/events.parquet (tick-level measures per event and instrument).
Events: 8:30 a.m. macro releases (CPI, PPI, employment, retail sales) and, separately, FOMC statements.

Book thinning in the minute before the release (-60 s to 0, against the -240 to -60 s baseline):
  thinning = z(spread change in ticks) - z(depth ratio), z-scored within instrument, event type and period.
Events are ranked into five equal groups within each period (2015-2022, 2023-2026), so each bar has the
same number of events. This is descriptive (ranks use each period's own distribution), not a forecast
test; the out-of-sample regression is in reports/trading_strategies.md, section 5.

Top row: median absolute return from 0 to +5 minutes (size). Bottom row: share of events whose 0 to +5
minute return was positive (direction; 50% = no information).

Run: python -m scripts.plot_pre_release_thinning
Writes figures/pre_release_thinning/{macro,fomc}_thinning_quintiles.png and
tables/pre_release_thinning_quintiles.csv
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT

EVENTS = PROJECT_ROOT / "data" / "processed" / "tick_features" / "events.parquet"
FIG = PROJECT_ROOT / "figures" / "pre_release_thinning"
TABLE = PROJECT_ROOT / "tables" / "pre_release_thinning_quintiles.csv"
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
PERIOD_COLORS = {"2015-2022": "#2a5ea8", "2023-2026": "#e0a030"}
TITLES = {"macro": "8:30 a.m. macro releases (CPI, PPI, jobs, retail sales)", "fomc": "FOMC statements"}


def load() -> pd.DataFrame:
    e = pd.read_parquet(EVENTS)
    e = e.loc[e["family"].isin(["fomc", "macro"]) & e["dataset_condition"].ne("degraded") & e["pre_state_valid"]
              & e["instrument"].isin(NAMES)]
    e = e.loc[e["family"].eq("macro") | e["subevent"].eq("statement")].copy()
    e["kind"] = np.where(e["family"].eq("macro"), "macro", "fomc")
    e["period"] = np.where(pd.to_datetime(e["event_date"]) < "2023-01-01", "2015-2022", "2023-2026")
    return e


def quintiles(e: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (kind, inst, period), g in e.groupby(["kind", "instrument", "period"]):
        g = g.dropna(subset=["pre60_spread_change_ticks", "pre60_depth_ratio", "w300s_total_bp"])
        z = lambda c: (g[c] - g[c].mean()) / g[c].std()                          # noqa: E731
        thin = z("pre60_spread_change_ticks") - z("pre60_depth_ratio")
        q = pd.qcut(thin.rank(method="first"), 5, labels=False) + 1
        for k, h in g.groupby(q):
            r = h["w300s_total_bp"]
            rows.append({"kind": kind, "instrument": NAMES[inst], "period": period, "quintile": int(k),
                         "N": len(h), "median_abs_move_bp": r.abs().median(),
                         "q25_abs_move_bp": r.abs().quantile(0.25), "q75_abs_move_bp": r.abs().quantile(0.75),
                         "share_up": (r > 0).mean()})
    return pd.DataFrame(rows)


def plot(q: pd.DataFrame, kind: str) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.6), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for col, inst in enumerate(("ES", "NQ", "ZN")):
        for k, (period, color) in enumerate(PERIOD_COLORS.items()):
            d = q.loc[q["kind"].eq(kind) & q["instrument"].eq(inst) & q["period"].eq(period)].sort_values("quintile")
            x = d["quintile"] + (k - 0.5) * 0.38
            ax = axes[0, col]
            ax.bar(x, d["median_abs_move_bp"], width=0.36, color=color, label=f"{period} (n = {d['N'].sum()})")
            ax.errorbar(x, d["median_abs_move_bp"], yerr=[d["median_abs_move_bp"] - d["q25_abs_move_bp"],
                        d["q75_abs_move_bp"] - d["median_abs_move_bp"]], fmt="none", ecolor="#555555",
                        capsize=2, lw=0.7)
            axes[1, col].plot(d["quintile"], d["share_up"] * 100, marker="o", color=color)
        axes[0, col].set_title(inst)
        axes[0, col].spines[["top", "right"]].set_visible(False)
        axes[1, col].axhline(50, color="black", lw=0.7, ls=":")
        axes[1, col].set_ylim(0, 100)
        axes[1, col].set_xticks(range(1, 6), ["Q1\nleast\nthinned", "Q2", "Q3", "Q4", "Q5\nmost\nthinned"])
        axes[1, col].spines[["top", "right"]].set_visible(False)
    axes[0, 0].set_ylabel("median |move| 0 to +5 min (bp)\nbars: 25-75% range")
    axes[1, 0].set_ylabel("% of events\nmoving up")
    axes[0, 0].legend(frameon=False, fontsize=9)
    fig.suptitle(f"{TITLES[kind]}: book thinning in the minute before the release vs size (top) and "
                 f"direction (bottom) of the move\n(events ranked into fifths within each period)")
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{kind}_thinning_quintiles.png", dpi=160)
    plt.close(fig)


def main() -> None:
    q = quintiles(load())
    TABLE.parent.mkdir(exist_ok=True)
    q.to_csv(TABLE, index=False)
    for kind in TITLES:
        plot(q, kind)
    print(q.pivot_table(index=["kind", "instrument", "period"], columns="quintile", values="median_abs_move_bp")
          .round(1).to_string())
    print(f"Wrote {TABLE.relative_to(PROJECT_ROOT)} and figures in {FIG.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
