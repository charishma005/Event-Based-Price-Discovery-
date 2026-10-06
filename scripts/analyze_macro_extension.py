"""The numeric-release arm extended to 2015-2026 (professor's step 5).

The earlier macro sample covered January 2024 to August 2025 (77 release
mornings). The registry now holds every CPI, PPI and Employment Situation
release from January 2015 to September 2026 on the official BLS schedule (plus
the 2024-2025 retail sales releases): 437 release mornings. This script
summarises that arm by release type and period from the tick windows:

A. Response   arrival latency after 8:30:00, absolute move after 1 s, 5 s, 60 s
              and 300 s, time to half and to 90% of the 300-second move.
B. Mechanism  the proposal's first-quote share (H1 as written), how often a
              trade comes first, and the pre-declared quote-revision share at
              arrival next to its pseudo-clock placebo (detail: Q1 tables).
C. Liquidity  final-minute depth, spread and their composite against the
              release's own baseline.
D. Location   which contract moves first (Q3): order of the arrival times of
              ZN and ES, and of NQ and ES, by release type, with FOMC
              statements for comparison.
E. Controls   the depth and spread of C against matched control mornings: the
              same 8:30 a.m. window on a day of the same month without a
              release (112 months have at least one). Depth ratio is the mean
              touch depth in [-60, 0) s over the mean in [-240, -60) s, elapsed
              time weighted; spread change is the final minute minus that
              baseline, in ticks. Paired by month (releases minus the mean of
              the month's control mornings): two-sided Wilcoxon signed-rank,
              sign counts and a bootstrap interval, Holm across the three
              contracts. Shown with all control mornings and without those
              that have a volume spike at 8:30
              (scripts.screen_macro_controls_by_volume).
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon
from statsmodels.stats.multitest import multipletests

from scripts.analyze_q1_short_horizon import PRIMARY, load_events
from scripts.screen_macro_controls_by_volume import OUTPUT as VOLUME_SCREEN, flagged
from src.utils.config import PROJECT_ROOT

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="All-NaN slice")
TABLES = PROJECT_ROOT / "tables"
PROCESSED = PROJECT_ROOT / "data" / "processed"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
PERIODS = ((2015, 2019), (2020, 2023), (2024, 2026), (2015, 2026))
TYPES = ("cpi", "ppi", "employment_situation", "retail_sales")
MIN_ARRIVAL_BP = 1.0
# Control-morning test (E).
SAMPLES = ("development", "oos_backward", "oos_forward", "all")
CLEAN_CONTROL = ("clean", "no_scheduled_official_release_at_clock", "bls_and_claims_screen_only")
DEPTH_MEASURES = {"depth_ratio": "pre60_depth_ratio", "spread_change_ticks": "pre60_spread_change_ticks",
                  "depth_ratio_last_10s": "pre10_depth_ratio", "legacy_message_depth_ratio": "legacy_message_depth_ratio"}
MIN_VALID_TIME = 0.99               # share of the baseline and of the final minute with a valid book
RNG_SEED = 20261005
ALL_CONTROLS = "macro releases vs matched 8:30 a.m. control days (by month)"
QUIET_CONTROLS = "macro releases vs control days without an 8:30 a.m. volume spike"


def _prepare() -> pd.DataFrame:
    events = load_events()
    events = events.loc[events["eligible"]].copy()
    events["type"] = np.where(events["family"].eq("fomc"), "fomc_" + events["subevent"].astype(str),
                              events["event_types"].astype(str).str.split("|").str[0])
    events["pseudo_share"] = np.nan
    pseudo = events.loc[events["role"].eq("pseudo")].set_index(["matched_event", "instrument"])[PRIMARY]
    key = pd.MultiIndex.from_frame(events[["event_id", "instrument"]])
    events["pseudo_share"] = pseudo.reindex(key).to_numpy()
    for horizon in ("1s", "5s", "60s", "300s"):
        events[f"abs_move_{horizon}_bp"] = events[f"w{horizon}_total_bp"].abs().where(events[f"w{horizon}_covered"].astype(bool))
    events["depth_ratio"] = events["pre60_depth"] / events["baseline_depth"]
    events["spread_ratio"] = events["pre60_spread_ticks"] / events["baseline_spread_ticks"]
    events["composite_ratio"] = events["depth_ratio"] / events["spread_ratio"]
    events["trade_first"] = events["trade_before_first_quote"].astype(float)
    return events


def summary(events: pd.DataFrame) -> pd.DataFrame:
    macro = events.loc[events["family"].eq("macro") & events["role"].eq("event")]
    rows = []
    for first, last in PERIODS:
        span = macro.loc[macro["year"].between(first, last)]
        for kind in (*TYPES, "all numeric releases"):
            part = span if kind.startswith("all") else span.loc[span["type"].eq(kind)]
            for instrument, group in part.groupby("instrument"):
                if group["event_id"].nunique() < 5:
                    continue
                arrived = group.loc[group["burst_bp"].abs().ge(MIN_ARRIVAL_BP)]
                rows.append({
                    "period": f"{first}-{last}", "release": kind, "instrument": instrument, "releases": group["event_id"].nunique(),
                    "arrival_seconds_after_0830_median": arrived["arr_burst_seconds"].median(),
                    "abs_move_1s_bp_median": group["abs_move_1s_bp"].median(),
                    "abs_move_5s_bp_median": group["abs_move_5s_bp"].median(),
                    "abs_move_60s_bp_median": group["abs_move_60s_bp"].median(),
                    "abs_move_300s_bp_median": group["abs_move_300s_bp"].median(),
                    "seconds_to_half_of_300s_move_median": group["fp300s_50_seconds"].median(),
                    "seconds_to_90pct_of_300s_move_median": group["fp300s_90_seconds"].median(),
                    "first_quote_share_of_300s_move_median": group["legacy_first_quote_fraction"].median(),
                    "share_of_releases_first_quote_above_70pct": float((group["legacy_first_quote_fraction"] > 0.70).mean()),
                    "trade_before_first_quote_share": group["trade_first"].mean(),
                    "quote_revision_share_at_arrival_median": group[PRIMARY].median(),
                    "same_share_at_pseudo_clock_median": group["pseudo_share"].median(),
                    "final_minute_depth_ratio_geometric_mean": float(np.exp(np.log(group["depth_ratio"].where(group["depth_ratio"] > 0)).mean())),
                    "final_minute_spread_ratio_geometric_mean": float(np.exp(np.log(group["spread_ratio"].where(group["spread_ratio"] > 0)).mean())),
                    "final_minute_composite_ratio_geometric_mean": float(np.exp(np.log(group["composite_ratio"].where(group["composite_ratio"] > 0)).mean())),
                })
    return pd.DataFrame(rows)


def leadership(events: pd.DataFrame) -> pd.DataFrame:
    """Order of arrival across contracts, for arrivals of at least one basis point in both."""
    rows = []
    real = events.loc[events["role"].eq("event") & events["burst_bp"].abs().ge(MIN_ARRIVAL_BP)]
    wide = real.pivot_table(index=["event_id", "type", "year"], columns="instrument", values="arr_burst_seconds").reset_index()
    for kind in ("cpi", "ppi", "employment_situation", "fomc_statement"):
        for first, last in ((2015, 2019), (2020, 2026), (2015, 2026)):
            part = wide.loc[wide["type"].eq(kind) & wide["year"].between(first, last)]
            for other in ("ZN.v.0", "NQ.v.0"):
                both = part[["ES.v.0", other]].dropna()
                if len(both) < 10:
                    continue
                lag_ms = 1e3 * (both[other] - both["ES.v.0"])           # positive: ES first
                close = lag_ms.abs() <= 500                              # same arrival, not a later second move
                lag_ms = lag_ms.loc[close]
                es_first, other_first = int((lag_ms > 1).sum()), int((lag_ms < -1).sum())
                row = {"release": kind, "period": f"{first}-{last}", "pair": f"ES and {other.split('.')[0]}",
                       "events_with_arrival_in_both": len(both), "arrivals_within_half_a_second": int(close.sum()),
                       "es_first_by_more_than_1ms": es_first, "other_first_by_more_than_1ms": other_first,
                       "within_1ms": int(len(lag_ms) - es_first - other_first),
                       "median_lag_ms_other_minus_es": float(lag_ms.median()) if len(lag_ms) else np.nan,
                       "sign_test_p": np.nan, "wilcoxon_p": np.nan}
                if es_first + other_first >= 8:
                    row["sign_test_p"] = binomtest(es_first, es_first + other_first, 0.5).pvalue
                    row["wilcoxon_p"] = wilcoxon(lag_ms).pvalue if np.any(lag_ms != 0) else np.nan
                rows.append(row)
    return pd.DataFrame(rows)


def load_liquidity() -> pd.DataFrame:
    """Releases and control mornings whose baseline and final minute are fully covered."""
    events = pd.read_parquet(PROCESSED / "tick_features" / "events.parquet")
    events = events.loc[events["family"].isin(["macro", "macro_control"])].copy()
    events["dataset_condition"] = events["dataset_condition"].replace("", "available")
    flag = events["quality_flag"].fillna("").astype(str)
    control = events["family"].eq("macro_control")
    eligible = (
        events["dataset_condition"].eq("available") & flag.ne("closed_session")
        & events["baseline_covered"].astype(bool) & events["pre60_covered"].astype(bool)
        & events["baseline_coverage"].ge(MIN_VALID_TIME) & events["pre60_coverage"].ge(MIN_VALID_TIME)
        & (~control | flag.str.startswith(CLEAN_CONTROL))
    )
    return events.loc[eligible]


def paired_table(event: pd.DataFrame, control: pd.DataFrame, key: str, measures: dict[str, str]) -> pd.DataFrame:
    """Event minus mean matched control, by instrument and for the cross-instrument average."""
    rng = np.random.default_rng(RNG_SEED)
    rows = []
    for label, column in measures.items():
        e = event.groupby([key, "instrument"])[column].mean()
        c = control.groupby([key, "instrument"])[column].mean()
        pair = pd.concat([e, c], axis=1, keys=["event", "control"]).dropna().reset_index()
        cluster = pair.groupby(key)[["event", "control"]].mean().reset_index().assign(instrument="cluster_average")
        for instrument, part in pd.concat([pair, cluster]).groupby("instrument"):
            difference = (part["event"] - part["control"]).to_numpy(float)
            row = {"measure": label, "instrument": instrument, "clusters": len(difference),
                   "event_mean": part["event"].mean(), "control_mean": part["control"].mean(),
                   "event_median": part["event"].median(), "control_median": part["control"].median(),
                   "mean_difference": np.nan, "ci_low": np.nan, "ci_high": np.nan,
                   "clusters_event_lower": int((difference < 0).sum()), "sign_p_two_sided": np.nan,
                   "wilcoxon_p_two_sided": np.nan}
            if len(difference) >= 6 and np.any(difference != 0):
                boot = rng.choice(difference, (10000, len(difference)), replace=True).mean(axis=1)
                nonzero = difference[difference != 0]
                row.update(mean_difference=difference.mean(), ci_low=np.quantile(boot, 0.025),
                           ci_high=np.quantile(boot, 0.975),
                           sign_p_two_sided=binomtest(int((nonzero < 0).sum()), len(nonzero), 0.5).pvalue,
                           wilcoxon_p_two_sided=wilcoxon(difference, alternative="two-sided").pvalue)
            rows.append(row)
    table = pd.DataFrame(rows)
    table["holm_p"] = np.nan
    for label in measures:
        family = table["measure"].eq(label) & table["instrument"].isin(INSTRUMENTS) & table["wilcoxon_p_two_sided"].notna()
        if family.any():
            table.loc[family, "holm_p"] = multipletests(table.loc[family, "wilcoxon_p_two_sided"], method="holm")[1]
    return table


def control_mornings() -> pd.DataFrame:
    """Final-minute depth and spread at 8:30 a.m. releases against the month's control mornings."""
    liquidity = load_liquidity()
    release = liquidity.loc[liquidity["family"].eq("macro")]
    control = liquidity.loc[liquidity["family"].eq("macro_control")]
    # The rule-based control mornings are screened for BLS releases and Thursday claims only. A
    # control morning whose 8:30 minute trades at three times the volume of the ten minutes before
    # it most likely had another scheduled release (Census, BEA); the test is repeated without those.
    noisy: set[str] = set()
    if VOLUME_SCREEN.exists():
        screen = pd.read_csv(VOLUME_SCREEN)
        noisy = set(screen.loc[flagged(screen), "event_id"])
    tables = []
    for sample in SAMPLES:
        events = release if sample == "all" else release.loc[release["sample"].eq(sample)]
        mornings = control if sample == "all" else control.loc[control["sample"].eq(sample)]
        variants = [(ALL_CONTROLS, mornings)]
        if noisy:
            variants.append((QUIET_CONTROLS, mornings.loc[~mornings["event_id"].isin(noisy)]))
        for label, subset in variants:
            if subset.empty:
                continue
            table = paired_table(events, subset, "cluster", DEPTH_MEASURES)
            table.insert(0, "comparison", label)
            table.insert(0, "sample", sample)
            tables.append(table)
    return pd.concat(tables, ignore_index=True)


def _write(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(TABLES / f"{name}.csv", index=False)
    frame.to_latex(TABLES / f"{name}.tex", index=False, float_format="%.4f")


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    events = _prepare()
    table = summary(events)
    leaders = leadership(events)
    controls = control_mornings()
    _write(table, "macro_extension_summary_2015_2026")
    _write(leaders, "q3_first_mover_2015_2026")
    _write(controls, "macro_depth_vs_control_mornings_2015_2026")
    with pd.option_context("display.width", 280, "display.max_columns", 40, "display.float_format", lambda v: f"{v:.3f}"):
        all_period = table.loc[table["period"].eq("2015-2026")]
        print(all_period.drop(columns=["period"]).to_string(index=False))
        print("\nBy period, all numeric releases:")
        print(table.loc[table["release"].eq("all numeric releases")].drop(columns=["release"]).to_string(index=False))
        print("\nWhich contract moves first:")
        print(leaders.to_string(index=False))
        print("\nFinal minute before 8:30 a.m. releases against control mornings (paired by month):")
        view = controls.loc[controls["measure"].isin(["depth_ratio", "spread_change_ticks"])
                            & controls["sample"].isin(["all", "oos_backward"])]
        print(view[["sample", "comparison", "measure", "instrument", "clusters", "event_mean", "control_mean",
                    "mean_difference", "ci_low", "ci_high", "clusters_event_lower", "wilcoxon_p_two_sided",
                    "holm_p"]].to_string(index=False))


if __name__ == "__main__":
    main()
