"""Why NQ does not appear to withdraw: the tick constraint (professor's step 8, second part).

In the H4 tables ES and ZN lose most of their touch depth before a scheduled
arrival and NQ does not. ES and ZN trade at a one-tick spread almost all the
time, so a market maker who wants to show less can only shrink the size at the
touch. NQ's normal spread is wider than one tick, so the same decision shows up
as a wider quote and the size at the (now wider) touch changes less.

This script puts the two margins together for every FOMC statement, against the
matched control afternoons in the same seconds (one-second BBO samples):
    depth ratio       touch depth, FOMC day over control days, final minute
    spread ratio      quoted spread in ticks, FOMC day over control days
    composite         depth ratio / spread ratio: displayed size per tick of spread
    spread share      log(spread ratio) / (log(spread ratio) - log(depth ratio)):
                      the part of the composite withdrawal that comes through the spread
and relates the split to how tick-constrained the contract normally is (control-day
spread in ticks and the share of seconds at one tick, 1:30-1:50 p.m.). The same
split is shown for the 8:30 a.m. macro releases from the tick windows, where the
comparison is the release's own [-240, -60) s baseline.
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon

from src.utils.config import PROJECT_ROOT

warnings.filterwarnings("ignore", category=FutureWarning)
PROCESSED = PROJECT_ROOT / "data" / "processed"
TABLES = PROJECT_ROOT / "tables"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
TICK = {"ES.v.0": 0.25, "NQ.v.0": 0.25, "ZN.v.0": 1 / 64}
PERIODS = ((2015, 2017), (2018, 2020), (2021, 2023), (2024, 2026))


def fomc_meetings() -> pd.DataFrame:
    panel = pd.read_parquet(PROCESSED / "fomc_sessions" / "panel.parquet",
                            columns=["event_id", "instrument", "seconds", "valid", "bid", "ask", "bid_size", "ask_size"])
    sessions = pd.read_parquet(PROCESSED / "fomc_sessions" / "sessions.parquet")
    sessions["dataset_condition"] = sessions["dataset_condition"].replace("", "available")
    flag = sessions["quality_flag"].fillna("").astype(str)
    sessions = sessions.loc[sessions["dataset_condition"].eq("available") & (sessions["family"].eq("fomc") | flag.str.startswith("clean"))]
    panel = panel.loc[panel["valid"] & panel["seconds"].between(-1800, -1)].copy()
    panel["event_id"], panel["instrument"] = panel["event_id"].astype(str), panel["instrument"].astype(str)
    panel = panel.merge(sessions[["event_id", "family", "cluster", "event_time_utc"]], on="event_id")
    tick = panel["instrument"].map(TICK).astype(float)
    panel["depth"] = panel["bid_size"] + panel["ask_size"]
    panel["spread_ticks"] = (panel["ask"] - panel["bid"]) / tick
    panel["one_tick"] = (panel["spread_ticks"] < 1.5).astype(float)
    panel["relative_tick_bp"] = 1e4 * tick / ((panel["ask"] + panel["bid"]) / 2)
    panel["window"] = np.select([panel["seconds"].between(-1800, -601), panel["seconds"].between(-60, -1)], ["early", "final"], default="")
    panel = panel.loc[panel["window"].ne("")]
    means = panel.groupby(["family", "cluster", "event_id", "instrument", "window"])[
        ["depth", "spread_ticks", "one_tick", "relative_tick_bp"]].mean().reset_index()
    by_family = means.groupby(["family", "cluster", "instrument", "window"])[["depth", "spread_ticks", "one_tick", "relative_tick_bp"]].mean()
    wide = by_family.unstack(["family", "window"]).dropna()
    out = pd.DataFrame({
        "normal_spread_ticks": wide[("spread_ticks", "fomc_control", "early")],
        "normal_one_tick_share": wide[("one_tick", "fomc_control", "early")],
        "relative_tick_bp": wide[("relative_tick_bp", "fomc_control", "early")],
        "normal_depth": wide[("depth", "fomc_control", "early")],
        "depth_ratio": wide[("depth", "fomc", "final")] / wide[("depth", "fomc_control", "final")],
        "spread_ratio": wide[("spread_ticks", "fomc", "final")] / wide[("spread_ticks", "fomc_control", "final")],
    }).reset_index()
    out["composite_ratio"] = out["depth_ratio"] / out["spread_ratio"]
    spread, depth = np.log(out["spread_ratio"]), np.log(out["depth_ratio"])
    out["spread_share_of_withdrawal"] = (spread / (spread - depth)).where((spread - depth) > 0.05)
    out["year"] = out["cluster"].str[5:9].astype(int)
    return out


def macro_releases() -> pd.DataFrame:
    events = pd.read_parquet(PROCESSED / "tick_features" / "events.parquet")
    events["dataset_condition"] = events["dataset_condition"].replace("", "available")
    rows = events.loc[events["family"].eq("macro") & events["dataset_condition"].eq("available")
                      & events["baseline_covered"].astype(bool) & events["pre60_covered"].astype(bool)].copy()
    rows["depth_ratio"] = rows["pre60_depth"] / rows["baseline_depth"]
    rows["spread_ratio"] = rows["pre60_spread_ticks"] / rows["baseline_spread_ticks"]
    rows["composite_ratio"] = rows["depth_ratio"] / rows["spread_ratio"]
    rows["normal_spread_ticks"] = rows["baseline_spread_ticks"]
    rows["normal_one_tick_share"] = rows["baseline_one_tick_share"]
    rows["year"] = pd.to_datetime(rows["event_time_utc"], utc=True).dt.year
    return rows[["event_id", "instrument", "year", "normal_spread_ticks", "normal_one_tick_share", "depth_ratio", "spread_ratio", "composite_ratio"]]


def by_period(data: pd.DataFrame, label: str) -> pd.DataFrame:
    rows = []
    spans = [*PERIODS, (2015, 2026)]
    for first, last in spans:
        part = data.loc[data["year"].between(first, last)]
        for instrument, group in part.groupby("instrument"):
            row = {"sample": label, "period": f"{first}-{last}", "instrument": instrument, "events": len(group)}
            for column in ("normal_spread_ticks", "normal_one_tick_share", "relative_tick_bp"):
                if column in group:
                    row[column] = group[column].mean()
            for column in ("depth_ratio", "spread_ratio", "composite_ratio"):
                row[f"{column}_geometric_mean"] = float(np.exp(np.log(group[column].where(group[column] > 0)).mean()))
            if "spread_share_of_withdrawal" in group:
                row["spread_share_of_withdrawal_median"] = group["spread_share_of_withdrawal"].median()
            rows.append(row)
    return pd.DataFrame(rows)


def tests(fomc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    wide = fomc.pivot_table(index="cluster", columns="instrument", values=["depth_ratio", "composite_ratio"])
    for measure in ("depth_ratio", "composite_ratio"):
        for other in ("ES.v.0", "ZN.v.0"):
            both = wide[measure][["NQ.v.0", other]].dropna()
            gap = np.log(both["NQ.v.0"]) - np.log(both[other])
            rows.append({"test": f"NQ against {other.split('.')[0]}, {measure} in the final minute (paired by meeting)",
                         "meetings": len(both), "nq_geometric_mean": float(np.exp(np.log(both["NQ.v.0"]).mean())),
                         "other_geometric_mean": float(np.exp(np.log(both[other]).mean())),
                         "statistic": float(np.exp(gap.mean())), "p_two_sided": wilcoxon(gap).pvalue})
    for instrument in INSTRUMENTS:
        part = fomc.loc[fomc["instrument"].eq(instrument)]
        for driver in ("normal_spread_ticks", "normal_one_tick_share"):
            for outcome in ("depth_ratio", "spread_share_of_withdrawal"):
                both = part[[driver, outcome]].dropna()
                result = spearmanr(both[driver], both[outcome])
                rows.append({"test": f"{instrument.split('.')[0]}: {driver} against {outcome} across meetings (Spearman)",
                             "meetings": len(both), "statistic": result.statistic, "p_two_sided": result.pvalue})
    return pd.DataFrame(rows)


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    fomc = fomc_meetings()
    macro = macro_releases()
    periods = pd.concat([by_period(fomc, "FOMC statement, final minute against control days"),
                         by_period(macro, "8:30 a.m. macro releases, final minute against own baseline")], ignore_index=True)
    checks = tests(fomc)
    for name, frame in (("h4_tick_constraint_by_period", periods), ("h4_tick_constraint_tests", checks)):
        frame.to_csv(TABLES / f"{name}.csv", index=False)
        frame.to_latex(TABLES / f"{name}.tex", index=False, float_format="%.4f")
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", lambda v: f"{v:.3f}"):
        print(periods.to_string(index=False))
        print()
        print(checks.to_string(index=False))


if __name__ == "__main__":
    main()
