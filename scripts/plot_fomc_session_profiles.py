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
- Each session and instrument is divided by its own mean over the baseline minutes. The default
  baseline is minutes -30 to -16, well before the pre-statement withdrawal; the H4-style baseline
  (minutes -5 to -2) is drawn as a second version for comparison with the old figure.
- Lines show the cross-session median per minute and the 25-75% band, by group:
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
    m = p.groupby(["event_id", "instrument", "minute"])[["depth", "spread_ticks"]].median().reset_index()
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
        for measure in ("depth_ratio", "spread_ratio"):
            v = g[measure].replace([np.inf, -np.inf], np.nan).dropna()
            if len(v) < 5:
                continue
            rows.append({"baseline": baseline_name, "group": group, "instrument": NAMES[inst], "minute": minute,
                         "measure": measure, "median": v.median(), "q25": v.quantile(0.25), "q75": v.quantile(0.75),
                         "N_sessions": len(v)})
    return pd.DataFrame(rows)


def plot(s: pd.DataFrame, measure: str, baseline_name: str) -> None:
    lo, hi = BASELINES[baseline_name]
    label = {"depth_ratio": "touch depth", "spread_ratio": "quoted spread (ticks)"}[measure]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=measure == "depth_ratio")
    for ax, inst in zip(axes, ("ES", "NQ", "ZN")):
        for group in ("control", "fomc_no_pc", "fomc_pc"):
            d = s.loc[s["measure"].eq(measure) & s["group"].eq(group) & s["instrument"].eq(inst)].sort_values("minute")
            if d.empty:
                continue
            name, color = GROUPS[group]
            x = d["minute"] + 0.5
            ax.plot(x, d["median"], color=color, lw=1.8 if group == "fomc_pc" else 1.3,
                    label=f"{name} (n={int(d['N_sessions'].max())})")
            if group != "fomc_no_pc":
                ax.fill_between(x, d["q25"], d["q75"], color=color, alpha=0.15, lw=0)
        ax.axvspan(lo, hi + 1, color="#f0e6c8", alpha=0.5, lw=0)
        for t, text, ls in ((0, "statement", "--"), (30, "press conf.", "-."), (90, "about end of PC", ":")):
            ax.axvline(t, color="black", ls=ls, lw=0.9)
            ax.text(t + 1, 0.02, text, transform=ax.get_xaxis_transform(), fontsize=8)
        ax.axhline(1, color="black", lw=0.5, ls=":")
        ax.set_title(inst)
        ax.set_xlim(-30, 120)
        ax.set_xlabel("Minutes from 2:00 p.m. (FOMC statement)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel(f"Median {label}\n(relative to minutes {lo} to {hi + 1}, shaded)")
    axes[0].legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle(f"{label.capitalize()} from -30 to +120 minutes, minute by minute (median and 25-75% band)")
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{measure.replace('_ratio', '')}_profile_baseline_{baseline_name}.png", dpi=160)
    plt.close(fig)


def main() -> None:
    meta = sessions()
    m = minute_medians(meta)
    print("Sessions with data:\n" + m.drop_duplicates("event_id")["group"].value_counts().to_string())
    out = []
    for name, baseline in BASELINES.items():
        s = summary(normalized(m, baseline), name)
        out.append(s)
        for measure in ("depth_ratio", "spread_ratio"):
            plot(s, measure, name)
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
