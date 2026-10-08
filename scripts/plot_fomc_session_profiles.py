"""Full-session depth and spread profiles around FOMC statements, from the one-second session panel.

Extends figures/paper/figure_fomc_depth_profile_minute.png (scripts/plot_fomc_depth_profile.py),
which covers -5 to +40 minutes with controls only to +10, to the whole session panel: -30 to +120
minutes for FOMC days and matched control days alike.

Input: data/processed/fomc_sessions/panel.parquet (scripts/extract_session_panels.py; one-second
best bid/ask and sizes on the vendor's bbo-1s sampling) and data/events/fomc_session_windows.csv.

Method
- Touch depth = best-bid size + best-ask size; spread in ticks. Invalid seconds are dropped and the
  last valid quote is carried forward, so each second holds the book in force at that second.
- Each minute gets the median of its 60 seconds (minute m covers [m, m+1) minutes from 2:00 p.m.).
- Depth: each session and instrument is divided by its own mean over the baseline minutes. The default
  baseline is minutes -30 to -16, well before the pre-statement withdrawal; the H4-style baseline
  (minutes -5 to -2) is drawn as a second version for comparison with the old figure.
- Spread is shown in absolute ticks: the mean over each minute's seconds, then the mean across
  sessions (spreads are whole ticks, so medians are almost always exactly one tick).
- Depth lines show the cross-session median per minute and the 25-75% band, by group:
    fomc_pc     statements followed by a press conference
    fomc_no_pc  statement-only meetings (2015-2018)
    control     matched control days at the same clock

Run: python -m scripts.plot_fomc_session_profiles
Writes figures/fomc_session_profiles/*.png and tables/fomc_session_profiles.csv
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.microstructure.tick_arrays import tick_size
from src.utils.config import PROJECT_ROOT

PANEL = PROJECT_ROOT / "data" / "processed" / "fomc_sessions" / "panel.parquet"
WINDOWS_CSV = PROJECT_ROOT / "data" / "events" / "fomc_session_windows.csv"
FIG = PROJECT_ROOT / "figures" / "fomc_session_profiles"
TABLE = PROJECT_ROOT / "tables" / "fomc_session_profiles.csv"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
BASELINES = {"quiet": (-30, -16), "h4": (-5, -2)}
GROUPS = {"fomc_pc": ("FOMC with press conference", "#2a5ea8"),
          "fomc_no_pc": ("FOMC, no press conference (2015-2018)", "#b04a2e"),
          "control": ("matched normal days", "#808080")}


def sessions() -> pd.DataFrame:
    w = pd.read_csv(WINDOWS_CSV)
    pc = pd.to_datetime(w["press_conference_time_utc"], utc=True)
    w["group"] = np.select([w["family"].eq("fomc") & pc.notna(), w["family"].eq("fomc")],
                           ["fomc_pc", "fomc_no_pc"], "control")
    w = w.loc[w["dataset_condition"].ne("degraded")]
    return w.set_index("event_id")[["group"]]


def minute_medians(meta: pd.DataFrame) -> pd.DataFrame:
    """Session x instrument x minute: median depth and spread (ticks) over the minute's seconds."""
    cols = ["event_id", "instrument", "seconds", "valid", "bid", "ask", "bid_size", "ask_size"]
    p = pd.read_parquet(PANEL, columns=cols)
    p["event_id"], p["instrument"] = p["event_id"].astype(str), p["instrument"].astype(str)
    p = p.loc[p["event_id"].isin(meta.index) & p["instrument"].isin(INSTRUMENTS)]
    ok = p["valid"].astype(bool)
    p["depth"] = (p["bid_size"].astype(float) + p["ask_size"].astype(float)).where(ok)
    p["spread_ticks"] = ((p["ask"] - p["bid"]) / p["instrument"].map(tick_size)).where(ok)
    p = p.sort_values(["event_id", "instrument", "seconds"])
    p[["depth", "spread_ticks"]] = p.groupby(["event_id", "instrument"])[["depth", "spread_ticks"]].ffill()
    p["minute"] = np.floor(p["seconds"] / 60).astype(int)
    p = p.loc[p["minute"].between(-30, 119)]          # minute 120 would hold a single second
    g = p.groupby(["event_id", "instrument", "minute"])
    m = g["depth"].median().to_frame().join(g["spread_ticks"].mean()).reset_index()
    return m.join(meta, on="event_id")


def normalized(m: pd.DataFrame, baseline: tuple[int, int]) -> pd.DataFrame:
    base = (m.loc[m["minute"].between(*baseline)].groupby(["event_id", "instrument"])[["depth", "spread_ticks"]]
            .mean().rename(columns=lambda c: f"base_{c}"))
    out = m.join(base, on=["event_id", "instrument"])
    out["depth_ratio"] = out["depth"] / out["base_depth"].where(out["base_depth"] > 0)
    out["spread_ratio"] = out["spread_ticks"] / out["base_spread_ticks"].where(out["base_spread_ticks"] > 0)
    return out


def summary(n: pd.DataFrame, baseline_name: str) -> pd.DataFrame:
    rows = []
    for (group, inst, minute), g in n.groupby(["group", "instrument", "minute"]):
        v = g["depth_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
        if len(v) >= 5:
            rows.append({"baseline": baseline_name, "group": group, "instrument": NAMES[inst], "minute": minute,
                         "measure": "depth_ratio", "median": v.median(), "q25": v.quantile(0.25),
                         "q75": v.quantile(0.75), "mean": v.mean(), "N_sessions": len(v)})
        w = g["spread_ticks"].dropna()
        if len(w) >= 5:
            rows.append({"baseline": baseline_name, "group": group, "instrument": NAMES[inst], "minute": minute,
                         "measure": "spread_ticks", "median": w.median(), "q25": w.quantile(0.25),
                         "q75": w.quantile(0.75), "mean": w.mean(), "N_sessions": len(w)})
    return pd.DataFrame(rows)


DEPTH_YMAX = 1.6
SETTLEMENTS = ((60, "3:00 p.m. ZN settlement"), (119.5, "4:00 p.m. equity close"))


def plot(s: pd.DataFrame, measure: str, baseline_name: str) -> None:
    """Depth: median ratio to the baseline with 25-75% band. Spread: mean quoted spread in ticks
    (spreads are whole ticks, so the median is almost always exactly one tick and hides widening)."""
    lo, hi = BASELINES[baseline_name]
    depth = measure == "depth_ratio"
    stat = "median" if depth else "mean"
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.4), sharey=depth)
    handles = {}
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        for group in ("control", "fomc_no_pc", "fomc_pc"):
            d = s.loc[s["measure"].eq(measure) & s["group"].eq(group) & s["instrument"].eq(inst)].sort_values("minute")
            if d.empty:
                continue
            name, color = GROUPS[group]
            x = d["minute"] + 0.5
            (line,) = ax.plot(x, d[stat], color=color, lw=1.8 if group == "fomc_pc" else 1.3)
            handles[group] = (line, f"{name}, n = {int(d['N_sessions'].max())}")
            if depth and group != "fomc_no_pc":
                ax.fill_between(x, d["q25"], d["q75"], color=color, alpha=0.15, lw=0)
            if depth:
                over = d.loc[d[stat] > DEPTH_YMAX]
                for minute, value in zip(over["minute"], over[stat]):
                    ax.annotate(f"{value:.1f}", (minute + 0.5, DEPTH_YMAX), xytext=(0, -10),
                                textcoords="offset points", ha="center", fontsize=7, color=color)
        if depth:
            ax.axvspan(lo, hi + 1, color="#f0e6c8", alpha=0.6, lw=0)
            ax.set_ylim(0, DEPTH_YMAX)
            ax.axhline(1, color="black", lw=0.5, ls=":")
        for t, text, ls in ((0, "statement", "--"), (30, "press conf.", "-."), (90, "about end of PC", ":")):
            ax.axvline(t, color="black", ls=ls, lw=0.9)
            ax.text(t + 1, 0.02, text, transform=ax.get_xaxis_transform(), fontsize=8)
        for t, text in SETTLEMENTS:
            ax.axvline(t, color="#9a9a9a", lw=0.7, ls=(0, (1, 2)))
            ax.text(t - 1, 0.97, text, transform=ax.get_xaxis_transform(), fontsize=7, color="#666666",
                    rotation=90, ha="right", va="top")
        ax.set_title(inst)
        ax.set_xlim(-30, 120)
        ax.set_xlabel("Minutes from 2:00 p.m. (FOMC statement)")
        ax.spines[["top", "right"]].set_visible(False)
    if depth:
        axes[0].set_ylabel(f"Median touch depth\n(relative to minutes {lo} to {hi + 1}, shaded)")
        title = (f"Touch depth from -30 to +120 minutes, minute by minute (median and 25-75% band; "
                 f"values above {DEPTH_YMAX} printed at the top)")
    else:
        axes[0].set_ylabel("Mean quoted spread (ticks)")
        title = "Quoted spread from -30 to +120 minutes, minute by minute (mean across sessions)"
    order = [g for g in ("fomc_pc", "fomc_no_pc", "control") if g in handles]
    fig.legend([handles[g][0] for g in order], [handles[g][1] for g in order], loc="lower center", ncol=3,
               frameon=False, fontsize=9)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    FIG.mkdir(parents=True, exist_ok=True)
    name = f"depth_profile_baseline_{baseline_name}.png" if depth else "spread_profile.png"
    fig.savefig(FIG / name, dpi=160)
    plt.close(fig)


def main() -> None:
    meta = sessions()
    m = minute_medians(meta)
    print("Sessions with data:\n" + m.drop_duplicates("event_id")["group"].value_counts().to_string())
    out = []
    for name, baseline in BASELINES.items():
        s = summary(normalized(m, baseline), name)
        out.append(s)
        plot(s, "depth_ratio", name)
    plot(out[0], "spread_ticks", "quiet")            # spread is in absolute ticks: baseline-free
    table = pd.concat(out, ignore_index=True)
    TABLE.parent.mkdir(exist_ok=True)
    table.to_csv(TABLE, index=False)
    key = table.loc[table["baseline"].eq("quiet") & table["measure"].eq("depth_ratio")
                    & table["minute"].isin([-10, -5, -1, 0, 1, 5, 10, 25, 30, 45, 60, 90, 119])]
    print("\nMedian depth ratio (quiet baseline, minutes -30 to -16):\n"
          + key.pivot_table(index=["group", "instrument"], columns="minute", values="median").round(2).to_string())
    print(f"\nWrote {TABLE.relative_to(PROJECT_ROOT)} and figures in {FIG.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
