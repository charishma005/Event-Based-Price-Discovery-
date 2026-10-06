"""Depth before unscheduled arrivals, each against several control days (professor's step 8).

H4 says displayed liquidity is withdrawn before scheduled arrivals and not
before unscheduled ones. The earlier evidence on the second half was five
hand-picked corporate announcements with one control each. Here the arrivals
come from scripts.build_unscheduled_jump_sample: large one-minute moves in ES
or ZN at times of day when nothing is scheduled, 2015-2026, each with up to
four control days (same weekday, one and two weeks either side, at the
arrival's UTC time). The six unscheduled Federal Reserve announcements in trading hours are
reported separately.

Clock. An arrival is dated by the one-minute bar in which the price jumped, so
the news landed somewhere in that minute. Everything "before" is measured up
to five seconds before the bar opens and is therefore before the news by
construction:
    final minute    [-65, -5) s from the bar open
    own baseline    [-245, -65) s            (the H4 definition used for scheduled events)
    early baseline  [-1800, -600) s
A second version dates the arrival inside the bar (first second at which the
midpoint has moved a tenth of the minute's move, at least 2 bp) and is shown as
a check.

Measures (one-second BBO samples, as for the FOMC afternoons)
    level ratio   depth on the arrival day over the mean of its control days in the same seconds
    own ratio     final minute over own baseline, arrival day against control days
    spread        quoted spread in ticks, arrival day minus control days
Tests are across arrivals: Wilcoxon signed-rank on the log level ratio, sign
counts and a bootstrap interval; Holm across the three instruments.

Selection. An arrival is identified by a jump, and thin books make jumps more
likely. A low depth level on arrival days is therefore expected even without
anticipation; what anticipation would add is a decline into the arrival. The
level ratio is reported for the early window as well, and the test of interest
is whether depth falls between the early window and the final minute.

The matching numbers for scheduled FOMC statements are recomputed here with
the same windows so the two can be compared directly.

Strict subset. The scan removes the minutes at and after scheduled releases,
but an arrival shortly *before* a release clock has a pre-arrival window that
overlaps the run-up to that release, where depth is withdrawn for a different
reason. The primary sample is left as it was fixed; a stricter subset is
reported next to it: arrivals from 10:34 a.m. on (after the last regular data
clock), no FOMC statement day, and no BLS or Federal Reserve release within 45
minutes before or after the window clock, for arrival and control days alike.

Control clocks. A control window sits at the arrival's UTC time one or two
weeks away. When a daylight-saving change falls in between, that is one hour
off in New York time (19 of the 373 control windows). The primary sample is
left as it was fixed; a second check keeps only the controls at the arrival's
New York clock.
"""
from __future__ import annotations

import argparse
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, wilcoxon
from statsmodels.stats.multitest import multipletests

from src.utils.config import PROJECT_ROOT

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message="Mean of empty slice")
PROCESSED = PROJECT_ROOT / "data" / "processed"
TABLES = PROJECT_ROOT / "tables"
FIGURES = PROJECT_ROOT / "figures" / "unscheduled"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
TICK = {"ES.v.0": 0.25, "NQ.v.0": 0.25, "ZN.v.0": 1 / 64}
GUARD = 5
WINDOWS = {"early": (-1800, -600), "baseline": (-240 - GUARD, -60 - GUARD), "final": (-60 - GUARD, -GUARD),
           "arrival_minute": (0, 60), "after_1_to_5_min": (60, 300), "after_5_to_15_min": (300, 900)}
MIN_CONTROLS = 2
STRICT_FIRST_MINUTE = 10 * 60 + 34      # after the 10:00 a.m. data clock and its half hour
STRICT_RELEASE_GAP = 45                 # minutes to the nearest BLS or Federal Reserve release, either side
RNG_SEED = 20261005


def load_panel(folder: str, event_family: str, control_family: str, clean_prefix: tuple[str, ...] = ("",)) -> pd.DataFrame:
    panel = pd.read_parquet(PROCESSED / folder / "panel.parquet",
                            columns=["event_id", "instrument", "seconds", "valid", "logmid", "bid", "ask", "bid_size", "ask_size"])
    sessions = pd.read_parquet(PROCESSED / folder / "sessions.parquet")
    sessions["dataset_condition"] = sessions["dataset_condition"].replace("", "available")
    flag = sessions["quality_flag"].fillna("").astype(str)
    keep = sessions["dataset_condition"].eq("available") & (
        sessions["family"].eq(event_family) | (sessions["family"].eq(control_family) & flag.str.startswith(clean_prefix)))
    sessions = sessions.loc[keep, ["event_id", "family", "cluster"]]
    panel = panel.loc[panel["seconds"].between(-1800, 959) & panel["valid"]].copy()
    panel["event_id"], panel["instrument"] = panel["event_id"].astype(str), panel["instrument"].astype(str)
    panel = panel.merge(sessions, on="event_id")
    panel["role"] = np.where(panel["family"].eq(event_family), "event", "control")
    panel["depth"] = panel["bid_size"] + panel["ask_size"]
    panel["spread_ticks"] = (panel["ask"] - panel["bid"]) / panel["instrument"].map(TICK).astype(float)
    return panel


def strict_windows() -> set[str]:
    """Windows (arrival or control) that are clear of every scheduled release in the calendars on hand."""
    events = PROJECT_ROOT / "data" / "events"
    windows = pd.read_csv(events / "unscheduled_windows.csv", parse_dates=["event_time_utc"])
    local = windows["event_time_utc"].dt.tz_convert("America/New_York")
    minute = local.dt.hour * 60 + local.dt.minute
    fed = pd.read_csv(events / "fed_release_calendar_2015_2026.csv")
    bls = pd.read_csv(events / "bls_release_calendar_2015_2026.csv")
    fomc_days = set(fed.loc[fed["release"].eq("fomc_statement"), "release_date"])
    releases = pd.concat([fed.loc[fed["release"].ne("fomc_statement"), ["release_date", "release_time_et"]],
                          bls[["release_date", "release_time_et"]]], ignore_index=True)
    clock = releases["release_time_et"].str.split(":", expand=True).astype(int)
    releases["release_minute"] = clock[0] * 60 + clock[1]
    by_day = releases.groupby("release_date")["release_minute"].apply(list).to_dict()
    near = [any(abs(m - other) <= STRICT_RELEASE_GAP for other in by_day.get(day, [])) for day, m in zip(windows["event_date"], minute)]
    keep = minute.ge(STRICT_FIRST_MINUTE) & ~windows["event_date"].isin(fomc_days) & ~np.array(near)
    return set(windows.loc[keep, "event_id"])


def same_clock_windows() -> set[str]:
    """Arrivals, and the control windows at the same New York clock time as their arrival."""
    windows = pd.read_csv(PROJECT_ROOT / "data" / "events" / "unscheduled_windows.csv", parse_dates=["event_time_utc"])
    local = windows["event_time_utc"].dt.tz_convert("America/New_York")
    minute = local.dt.hour * 60 + local.dt.minute
    arrival_minute = dict(zip(windows.loc[~windows["is_control"], "event_id"], minute[~windows["is_control"]]))
    same = minute.eq(windows["matched_event"].map(arrival_minute))
    return set(windows.loc[same, "event_id"])


def refine_arrival(panel: pd.DataFrame, detected: dict[str, str]) -> dict[str, int]:
    """Second inside the jump minute at which the move starts, per arrival (cluster)."""
    out = {}
    events = panel.loc[panel["role"].eq("event") & panel["seconds"].between(-GUARD, 65)]
    for cluster, part in events.groupby("cluster"):
        instrument = "ZN.v.0" if detected.get(cluster, "ES") == "ZN" else "ES.v.0"
        path = part.loc[part["instrument"].eq(instrument)].set_index("seconds")["logmid"].sort_index()
        if len(path) < 30:
            out[cluster] = 0
            continue
        move = 1e4 * (path - path.iloc[0])
        total = move.iloc[-1]
        reached = move.index[(np.sign(total) * move) >= max(0.1 * abs(total), 2.0)]
        out[cluster] = int(reached[0]) - 1 if len(reached) else 0
    return out


def window_means(panel: pd.DataFrame, shift: dict[str, int] | None = None) -> pd.DataFrame:
    """Mean depth and spread per session, instrument and window; optional per-arrival clock shift."""
    seconds = panel["seconds"] - panel["cluster"].map(shift).fillna(0) if shift else panel["seconds"]
    frames = []
    for name, (first, last) in WINDOWS.items():
        part = panel.loc[(seconds >= first) & (seconds < last)]
        grouped = part.groupby(["cluster", "role", "event_id", "instrument"])[["depth", "spread_ticks"]]
        means = grouped.mean().where(grouped.count() >= 0.8 * (last - first))
        frames.append(means.add_suffix(f"_{name}"))
    wide = pd.concat(frames, axis=1).reset_index()
    wide["own_ratio"] = wide["depth_final"] / wide["depth_baseline"]
    wide["early_ratio"] = wide["depth_final"] / wide["depth_early"]
    wide["own_spread_change"] = wide["spread_ticks_final"] - wide["spread_ticks_baseline"]
    return wide


def compare(wide: pd.DataFrame, label: str, min_controls: int = MIN_CONTROLS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Arrival day against the mean of its control days, per instrument."""
    rng = np.random.default_rng(RNG_SEED)
    value_columns = [c for c in wide.columns if c.startswith(("depth_", "spread_ticks_")) or c in ("own_ratio", "early_ratio", "own_spread_change")]
    event = wide.loc[wide["role"].eq("event")].set_index(["cluster", "instrument"])[value_columns]
    control_rows = wide.loc[wide["role"].eq("control")]
    counts = control_rows.groupby(["cluster", "instrument"])["event_id"].nunique()
    control = control_rows.groupby(["cluster", "instrument"])[value_columns].mean()
    control = control.loc[counts.reindex(control.index).ge(min_controls).to_numpy()]
    both = event.join(control, lsuffix="_event", rsuffix="_control", how="inner").reset_index()
    for name in WINDOWS:
        both[f"level_ratio_{name}"] = both[f"depth_{name}_event"] / both[f"depth_{name}_control"]
        both[f"spread_gap_{name}"] = both[f"spread_ticks_{name}_event"] - both[f"spread_ticks_{name}_control"]
    both["decline_into_arrival"] = both["level_ratio_final"] / both["level_ratio_early"]
    both["own_ratio_gap"] = both["own_ratio_event"] - both["own_ratio_control"]
    rows = []
    for instrument, part in both.groupby("instrument"):
        for measure, kind in [(f"level_ratio_{name}", "ratio") for name in WINDOWS] + [("decline_into_arrival", "ratio"),
                                                                                         ("own_ratio_gap", "difference"),
                                                                                         ("spread_gap_final", "difference"),
                                                                                         ("spread_gap_arrival_minute", "difference")]:
            values = part[measure].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
            if len(values) < 5:
                continue
            centred = np.log(values[values > 0]) if kind == "ratio" else values
            boot = rng.choice(centred, (4000, len(centred)), replace=True).mean(axis=1)
            estimate, low, high = centred.mean(), np.quantile(boot, 0.025), np.quantile(boot, 0.975)
            if kind == "ratio":
                estimate, low, high = np.exp(estimate), np.exp(low), np.exp(high)
            rows.append({"sample": label, "instrument": instrument, "measure": measure, "arrivals": len(centred),
                         "estimate": estimate, "ci_low": low, "ci_high": high,
                         "median": float(np.median(values)),
                         "arrivals_below_control": int((centred < 0).sum()),
                         "wilcoxon_p": wilcoxon(centred).pvalue if np.any(centred != 0) else np.nan})
    table = pd.DataFrame(rows)
    table["holm_p"] = np.nan
    for measure in table["measure"].unique():
        family = table["measure"].eq(measure) & table["wilcoxon_p"].notna()
        table.loc[family, "holm_p"] = multipletests(table.loc[family, "wilcoxon_p"], method="holm")[1]
    return table, both.assign(sample=label)


def minute_path(panel: pd.DataFrame, label: str) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED)
    data = panel.assign(minute=np.floor(panel["seconds"] / 60).astype(int))
    per = data.groupby(["cluster", "role", "event_id", "instrument", "minute"])[["depth", "spread_ticks"]].mean().reset_index()
    event = per.loc[per["role"].eq("event")].set_index(["cluster", "instrument", "minute"])[["depth", "spread_ticks"]]
    control = per.loc[per["role"].eq("control")].groupby(["cluster", "instrument", "minute"])[["depth", "spread_ticks"]].mean()
    both = event.join(control, lsuffix="_event", rsuffix="_control", how="inner").reset_index()
    rows = []
    for (instrument, minute), part in both.groupby(["instrument", "minute"]):
        log_ratio = np.log(part["depth_event"] / part["depth_control"]).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
        boot = rng.choice(log_ratio, (1000, len(log_ratio)), replace=True).mean(axis=1)
        rows.append({"sample": label, "instrument": instrument, "minute": minute, "arrivals": len(log_ratio),
                     "level_ratio": np.exp(log_ratio.mean()), "ci_low": np.exp(np.quantile(boot, 0.025)),
                     "ci_high": np.exp(np.quantile(boot, 0.975)),
                     "spread_event_ticks": part["spread_ticks_event"].mean(), "spread_control_ticks": part["spread_ticks_control"].mean()})
    return pd.DataFrame(rows)


def figure(paths: pd.DataFrame) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    styles = {"unscheduled arrivals (price jumps)": "#c9772b", "scheduled FOMC statements": "#1565a3"}
    for ax, instrument in zip(axes, INSTRUMENTS):
        for label, color in styles.items():
            part = paths.loc[paths["instrument"].eq(instrument) & paths["sample"].eq(label) & paths["minute"].between(-30, 14)]
            ax.fill_between(part["minute"] + 0.5, part["ci_low"], part["ci_high"], color=color, alpha=0.18, lw=0)
            ax.plot(part["minute"] + 0.5, part["level_ratio"], color=color, lw=1.3, label=f"{label} ({int(part['arrivals'].max())})")
        ax.axvline(0, color="#555555", lw=0.8)
        ax.axhline(1, color="#888888", lw=0.7)
        ax.set_title(instrument.split(".")[0], fontsize=9)
        ax.set_xlabel("minutes from the arrival")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("depth: event day / control days")
    axes[0].legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(FIGURES / "depth_before_scheduled_and_unscheduled_arrivals.png", dpi=180)
    plt.close(fig)


def _write(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(TABLES / f"{name}.csv", index=False)
    frame.to_latex(TABLES / f"{name}.tex", index=False, float_format="%.4f")


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    TABLES.mkdir(parents=True, exist_ok=True)
    detail = pd.read_csv(PROJECT_ROOT / "data" / "events" / "unscheduled_jump_events.csv")
    detected = dict(zip(detail["event_id"], detail["detected_in"].str.split().str[0]))

    jumps = load_panel("unscheduled", "unscheduled_jump", "unscheduled_jump_control")
    fed = load_panel("unscheduled", "unscheduled_fed", "unscheduled_fed_control")
    fomc = load_panel("fomc_sessions", "fomc", "fomc_control", clean_prefix=("clean",))

    tables, pairs, paths = [], [], []
    # FOMC meetings have one or two control afternoons by design; unscheduled arrivals have two to four.
    for label, panel, least in (("unscheduled arrivals (price jumps)", jumps, MIN_CONTROLS), ("scheduled FOMC statements", fomc, 1)):
        table, both = compare(window_means(panel), label, least)
        tables.append(table)
        pairs.append(both)
        paths.append(minute_path(panel, label))
    shift = refine_arrival(jumps, detected)
    refined, _ = compare(window_means(jumps, shift), "unscheduled arrivals, arrival dated inside the minute")
    tables.append(refined)
    strict = strict_windows()
    strict_panel = jumps.loc[jumps["event_id"].isin(strict) & jumps["cluster"].isin(strict)]
    strict_table, strict_pairs = compare(window_means(strict_panel), "unscheduled arrivals, strict subset")
    tables.append(strict_table)
    same_clock = jumps.loc[jumps["event_id"].isin(same_clock_windows())]
    tables.append(compare(window_means(same_clock), "unscheduled arrivals, controls at the same New York clock only")[0])
    for name, keep in (("unscheduled arrivals detected in ES", lambda c: detected.get(c, "") != "ZN"),
                       ("unscheduled arrivals detected in ZN only", lambda c: detected.get(c, "") == "ZN"),
                       ("unscheduled arrivals, 2015-2020", lambda c: int(c[5:9]) <= 2020),
                       ("unscheduled arrivals, 2021-2026", lambda c: int(c[5:9]) >= 2021)):
        subset = jumps.loc[jumps["cluster"].map(keep)]
        tables.append(compare(window_means(subset), name)[0])
    summary = pd.concat(tables, ignore_index=True)

    fed_wide = window_means(fed)
    fed_table, fed_pairs = compare(fed_wide, "unscheduled Federal Reserve announcements")
    per_event = pd.concat([*pairs, fed_pairs], ignore_index=True)
    columns = ["sample", "cluster", "instrument", "level_ratio_early", "level_ratio_final", "decline_into_arrival",
               "own_ratio_event", "own_ratio_control", "spread_gap_final", "level_ratio_arrival_minute", "level_ratio_after_1_to_5_min"]
    per_event = per_event[columns]

    # Scheduled against unscheduled, arrival by arrival.
    contrast = []
    scheduled, unscheduled = pairs[1], pairs[0]
    for instrument in INSTRUMENTS:
        for measure in ("level_ratio_final", "decline_into_arrival", "own_ratio_gap"):
            a = scheduled.loc[scheduled["instrument"].eq(instrument), measure].dropna()
            b = unscheduled.loc[unscheduled["instrument"].eq(instrument), measure].dropna()
            contrast.append({"instrument": instrument, "measure": measure, "scheduled_median": a.median(), "unscheduled_median": b.median(),
                             "scheduled_n": len(a), "unscheduled_n": len(b), "mann_whitney_p": mannwhitneyu(a, b).pvalue})
    contrast = pd.DataFrame(contrast)
    contrast["holm_p"] = multipletests(contrast["mann_whitney_p"], method="holm")[1]

    path_table = pd.concat(paths, ignore_index=True)
    _write(summary, "unscheduled_arrivals_depth_summary")
    _write(fed_table, "unscheduled_fed_announcements_depth_summary")
    _write(contrast, "unscheduled_vs_scheduled_contrast")
    _write(path_table, "unscheduled_arrivals_depth_by_minute")
    per_event.to_csv(TABLES / "unscheduled_arrivals_per_event.csv", index=False)
    figure(path_table)

    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 400, "display.float_format", lambda v: f"{v:.3f}"):
        headline = summary.loc[summary["measure"].isin(["level_ratio_early", "level_ratio_final", "decline_into_arrival", "own_ratio_gap",
                                                        "spread_gap_final", "level_ratio_arrival_minute", "level_ratio_after_1_to_5_min",
                                                        "level_ratio_after_5_to_15_min"])]
        print(headline.loc[headline["sample"].isin(["unscheduled arrivals (price jumps)", "scheduled FOMC statements",
                                                    "unscheduled arrivals, arrival dated inside the minute"])].to_string(index=False))
        print("\nSubsets (level in the final minute and decline from the early window):")
        print(summary.loc[summary["sample"].str.contains("detected|20|strict") & summary["measure"].isin(
            ["level_ratio_early", "level_ratio_final", "decline_into_arrival", "own_ratio_gap", "level_ratio_after_1_to_5_min"])].to_string(index=False))
        dropped = sorted(set(jumps.loc[jumps["role"].eq("event"), "cluster"]) - set(strict_pairs["cluster"]))
        print(f"\nStrict subset: {strict_pairs['cluster'].nunique()} arrivals; left out: {len(dropped)}")
        print(", ".join(dropped))
        print("\nScheduled against unscheduled:")
        print(contrast.to_string(index=False))
        print("\nUnscheduled Federal Reserve announcements, ES:")
        print(fed_pairs.loc[fed_pairs["instrument"].eq("ES.v.0"), columns].to_string(index=False))
        print(fed_table.loc[fed_table["measure"].isin(["level_ratio_final", "decline_into_arrival"])].to_string(index=False))
        worst = pairs[0].loc[pairs[0]["instrument"].eq("ES.v.0")].nsmallest(12, "decline_into_arrival")
        print("\nUnscheduled arrivals with the largest fall in ES depth before the jump:")
        print(worst[["cluster", "level_ratio_early", "level_ratio_final", "decline_into_arrival", "own_ratio_event", "own_ratio_control"]].to_string(index=False))
        print(f"\nMedian arrival offset inside the minute: {np.median(list(shift.values())):.0f} s")


if __name__ == "__main__":
    main()
