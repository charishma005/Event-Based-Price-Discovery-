"""Q1 with the pre-declared short-horizon quote-revision share.

Definitions, filters, contrasts and the multiplicity family are fixed in
``config/q1_short_horizon_prereg.yaml``; this script only implements them. It
reads ``data/processed/tick_features/events.parquet`` and writes tables under
``tables/`` and figures under ``figures/q1_short_horizon/``.

Primary outcome
    S = QR / (QR + TR) over the 100 ms window that starts at the arrival anchor,
    where QR and TR are the quote- and trade-attributed midpoint changes.
Key secondary outcome
    The same share over the first-passage window that ends when the midpoint
    has covered half of its 300-second move.
"""
from __future__ import annotations

import argparse
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import binomtest, mannwhitneyu, spearmanr, wilcoxon
from statsmodels.stats.multitest import multipletests

from src.utils.config import PROJECT_ROOT

warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="All-NaN slice encountered")

FEATURES = PROJECT_ROOT / "data" / "processed" / "tick_features"
TABLES = PROJECT_ROOT / "tables"
FIGURES = PROJECT_ROOT / "figures" / "q1_short_horizon"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
CLASS_ORDER = ("scalar_numeric", "multi_dimensional_numeric", "narrative_text", "extemporaneous_speech")
CLASS_LABEL = {
    "scalar_numeric": "Scalar numeric (CPI, PPI)",
    "multi_dimensional_numeric": "Multi-dimensional numeric (jobs, retail)",
    "narrative_text": "Narrative text (FOMC statement)",
    "extemporaneous_speech": "Speech (press conference)",
}
SAMPLES = ("development", "oos_backward", "oos_forward", "oos_all")
PRIMARY, SECONDARY = "share_burst100", "share_fp50"
ARRIVAL_HORIZONS = ("0ms", "50ms", "100ms", "250ms", "500ms", "1s")
FIXED_HORIZONS = ("50ms", "100ms", "250ms", "500ms", "1s", "2s", "5s")
CLEAN_CONTROL = ("clean", "no_scheduled_official_release_at_clock", "bls_and_claims_screen_only")
MIN_REFERENCE_MOVE_BP = 1.0
H1_THRESHOLD, H2_THRESHOLD = 0.70, 0.40


def _share(frame: pd.DataFrame, prefix: str) -> pd.Series:
    quote, trade = frame[f"{prefix}_quote_bp"], frame[f"{prefix}_trade_bp"]
    attributed = quote + trade
    return (quote / attributed).where(attributed.abs() > 1e-9)


def _directional(frame: pd.DataFrame, prefix: str) -> pd.Series:
    quote, trade = frame[f"{prefix}_quote_bp"], frame[f"{prefix}_trade_bp"]
    gross = quote.abs() + trade.abs()
    return (np.sign(quote + trade) * quote / gross).where(gross > 1e-9)


def load_events() -> pd.DataFrame:
    """Apply the pre-declared eligibility filters and build the outcome columns."""
    events = pd.read_parquet(FEATURES / "events.parquet")
    events["dataset_condition"] = events["dataset_condition"].replace("", "available")
    events["role"] = np.select(
        [events["family"].str.endswith("_pseudo"), events["family"].str.endswith("_control")],
        ["pseudo", "control"], default="event",
    )
    flag = events["quality_flag"].fillna("").astype(str)
    clean_control = flag.str.startswith(CLEAN_CONTROL)
    events["eligible"] = (
        events["dataset_condition"].eq("available")
        & flag.ne("closed_session")
        & events["pre_state_valid"].astype(bool)
        & events["pre_seconds_available"].ge(60)
        & events["post_seconds_available"].ge(10.2)
        & (events["role"].ne("control") | clean_control)
    )
    events[PRIMARY] = _share(events, "arr_burst_100ms")
    events["dqc_burst100"] = _directional(events, "arr_burst_100ms")
    events["share_burst100_alt"] = _share(events, "alt_arr_burst_100ms")
    reference_ok = events["w300s_total_bp"].abs().ge(MIN_REFERENCE_MOVE_BP) & events["post_seconds_available"].ge(300)
    events[SECONDARY] = _share(events, "fp300s_50").where(reference_ok & events["role"].ne("pseudo"))
    events["dqc_fp50"] = _directional(events, "fp300s_50").where(reference_ok & events["role"].ne("pseudo"))
    for label in ARRIVAL_HORIZONS:
        events[f"share_arr_{label}"] = _share(events, f"arr_burst_{label}")
    for label in FIXED_HORIZONS:
        events[f"share_fixed_{label}"] = _share(events, f"w{label}")
    move = events["w300s_total_bp"].abs()
    events["legacy_first_quote_fraction"] = (events["first_quote_revision_bp"].abs() / move).where(move > 0.1)
    events["legacy_last_pretrade_fraction"] = (events["last_pretrade_revision_bp"].abs() / move).where(move > 0.1)
    # Each pseudo row inherits the representation class of the arrival it precedes.
    classes = events.loc[events["role"].eq("event")].drop_duplicates("event_id").set_index("event_id")["representation_class"]
    events["event_class"] = np.where(
        events["role"].eq("pseudo"), events["matched_event"].map(classes), events["representation_class"]
    )
    events["base_event"] = np.where(events["role"].eq("pseudo"), events["matched_event"], events["event_id"])
    events["year"] = pd.to_datetime(events["event_time_utc"], utc=True).dt.year
    return events


def in_sample(frame: pd.DataFrame, sample: str) -> pd.DataFrame:
    if sample == "oos_all":
        return frame.loc[frame["sample"].isin(["oos_backward", "oos_forward"])]
    return frame.loc[frame["sample"].eq(sample)]


def event_level(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """One value per event clock: the mean over the instruments where the outcome is defined."""
    keys = ["event_id", "base_event", "role", "family", "subevent", "event_class", "cluster", "sample"]
    return frame.groupby(keys, dropna=False)[column].mean().reset_index().dropna(subset=[column])


def paired_difference(frame: pd.DataFrame, column: str, left: pd.DataFrame, right: pd.DataFrame,
                      left_key: str, right_key: str) -> pd.Series:
    """Per-pair difference, averaged over the instruments where both sides are defined."""
    a = left[[left_key, "instrument", column]].rename(columns={left_key: "pair", column: "a"})
    b = right[[right_key, "instrument", column]].rename(columns={right_key: "pair", column: "b"})
    merged = a.merge(b, on=["pair", "instrument"]).dropna()
    merged["difference"] = merged["a"] - merged["b"]
    return merged.groupby("pair")["difference"].mean()


def _paired_row(name: str, difference: pd.Series) -> dict[str, object]:
    row = {"contrast": name, "test": "paired Wilcoxon signed-rank", "n_left": len(difference), "n_right": len(difference),
           "estimate": np.nan, "estimate_kind": "median paired difference", "mean_difference": np.nan,
           "share_negative": np.nan, "p_two_sided": np.nan}
    values = difference.to_numpy(float)
    if len(values) >= 6 and np.any(values != 0):
        row.update(estimate=float(np.median(values)), mean_difference=float(values.mean()),
                   share_negative=float((values < 0).mean()),
                   p_two_sided=float(wilcoxon(values, alternative="two-sided").pvalue))
    return row


def _unpaired_row(name: str, left: pd.Series, right: pd.Series) -> dict[str, object]:
    row = {"contrast": name, "test": "Mann-Whitney U", "n_left": len(left), "n_right": len(right),
           "estimate": np.nan, "estimate_kind": "difference in medians", "mean_difference": np.nan,
           "share_negative": np.nan, "p_two_sided": np.nan}
    if len(left) >= 6 and len(right) >= 6:
        row.update(estimate=float(left.median() - right.median()), mean_difference=float(left.mean() - right.mean()),
                   p_two_sided=float(mannwhitneyu(left, right, alternative="two-sided").pvalue))
    return row


def contrasts(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """The pre-declared contrast family for one sample and one outcome."""
    rows = frame.loc[frame["eligible"]]
    real = rows.loc[rows["role"].eq("event")]
    pseudo = rows.loc[rows["role"].eq("pseudo")]
    control = rows.loc[rows["role"].eq("control")]
    level = event_level(rows, column)
    by_class = {name: level.loc[level["role"].eq("event") & level["event_class"].eq(name), column]
                for name in CLASS_ORDER}
    out = []
    primary_family = []
    if column != SECONDARY:        # the first-passage window is not defined at a pseudo clock
        for name in CLASS_ORDER:
            label = f"{name} minus own pseudo clock"
            difference = paired_difference(
                rows, column, real.loc[real["event_class"].eq(name)], pseudo.loc[pseudo["event_class"].eq(name)],
                "event_id", "matched_event",
            )
            out.append(_paired_row(label, difference))
            primary_family.append(label)
    statement = real.loc[real["subevent"].eq("statement")]
    press = real.loc[real["subevent"].eq("press_conference")]
    label = "statement minus press conference (same meeting)"
    out.append(_paired_row(label, paired_difference(rows, column, statement, press, "cluster", "cluster")))
    primary_family.append(label)
    for left, right in (("scalar_numeric", "narrative_text"), ("scalar_numeric", "multi_dimensional_numeric")):
        label = f"{left} vs {right}"
        out.append(_unpaired_row(label, by_class[left], by_class[right]))
        primary_family.append(label)
    # Matched-day controls, where the sample has them.
    control_level = level.loc[level["role"].eq("control")]
    for name, family in (("scalar_numeric", "macro_control"), ("multi_dimensional_numeric", "macro_control"),
                         ("narrative_text", "fomc_control"), ("extemporaneous_speech", "fomc_control")):
        out.append(_unpaired_row(f"{name} vs matched-day {family}", by_class[name],
                                 control_level.loc[control_level["family"].eq(family), column]))
    table = pd.DataFrame(out)
    table["in_primary_family"] = table["contrast"].isin(primary_family)
    table["holm_p"] = np.nan
    tested = table["in_primary_family"] & table["p_two_sided"].notna()
    if tested.any():
        table.loc[tested, "holm_p"] = multipletests(table.loc[tested, "p_two_sided"], method="holm")[1]
    return table


def robustness(frame: pd.DataFrame) -> pd.DataFrame:
    """The primary contrast family on pre-declared subsets."""
    variants = {
        "ES only": frame["instrument"].eq("ES.v.0"),
        "NQ only": frame["instrument"].eq("NQ.v.0"),
        "ZN only": frame["instrument"].eq("ZN.v.0"),
        "no invalid-book gap in the arrival window": frame["arr_burst_100ms_gap_bp"].abs().fillna(0).le(1e-9),
        "nanosecond same-stamped feed only": frame["timestamp_resolution_ns"].eq(1)
        & frame["attribution_tolerance_ns"].eq(0),
        "arrival move of at least 2 bp, events only": frame["role"].ne("event") | frame["burst_bp"].abs().ge(2.0),
    }
    out = []
    for name, keep in variants.items():
        table = contrasts(frame.loc[keep], PRIMARY)
        table.insert(0, "variant", name)
        out.append(table)
    return pd.concat(out, ignore_index=True)


def thresholds(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """The proposal's literal H1 (> 70%) and H2 (< 40%) claims as one-sided sign tests."""
    level = event_level(frame.loc[frame["eligible"] & frame["role"].eq("event")], column)
    rows = []
    for name, threshold, direction in (
        ("scalar_numeric", H1_THRESHOLD, "greater"), ("multi_dimensional_numeric", H1_THRESHOLD, "greater"),
        ("narrative_text", H2_THRESHOLD, "less"), ("extemporaneous_speech", H2_THRESHOLD, "less"),
    ):
        values = level.loc[level["event_class"].eq(name), column]
        row = {"event_class": name, "hypothesis": "H1: share above 0.70" if direction == "greater" else "H2: share below 0.40",
               "events": len(values), "median_share": values.median() if len(values) else np.nan,
               "events_satisfying": np.nan, "one_sided_sign_p": np.nan, "opposite_side_sign_p": np.nan}
        if len(values):
            hits = int((values > threshold).sum()) if direction == "greater" else int((values < threshold).sum())
            row["events_satisfying"] = hits
            row["one_sided_sign_p"] = float(binomtest(hits, len(values), 0.5, alternative="greater").pvalue)
            row["opposite_side_sign_p"] = float(binomtest(hits, len(values), 0.5, alternative="less").pvalue)
        rows.append(row)
    return pd.DataFrame(rows)


def class_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame.loc[frame["eligible"]].copy()
    rows["group"] = np.where(rows["role"].eq("control"), rows["family"], rows["event_class"])
    pooled = event_level(rows, PRIMARY).assign(instrument="event_mean")
    pooled["group"] = np.where(pooled["role"].eq("control"), pooled["family"], pooled["event_class"])
    pooled = pooled.merge(event_level(rows, SECONDARY)[["event_id", SECONDARY]], on="event_id", how="left")
    pooled = pooled.merge(event_level(rows, "dqc_burst100")[["event_id", "dqc_burst100"]], on="event_id", how="left")
    out = []
    for table in (rows, pooled):
        for (role, group, instrument), part in table.groupby(["role", "group", "instrument"]):
            primary = part[PRIMARY].dropna()
            out.append({
                "role": role, "group": group, "instrument": instrument, "rows": len(part),
                "primary_defined": len(primary), "primary_median": primary.median(), "primary_mean": primary.mean(),
                "primary_q25": primary.quantile(0.25), "primary_q75": primary.quantile(0.75),
                "primary_share_above_070": (primary > H1_THRESHOLD).mean(),
                "primary_share_below_040": (primary < H2_THRESHOLD).mean(),
                "directional_mean": part["dqc_burst100"].mean(),
                "secondary_defined": part[SECONDARY].notna().sum(), "secondary_median": part[SECONDARY].median(),
                "legacy_first_quote_fraction_median": part.get("legacy_first_quote_fraction", pd.Series(dtype=float)).median(),
                "legacy_last_pretrade_fraction_median": part.get("legacy_last_pretrade_fraction", pd.Series(dtype=float)).median(),
            })
    return pd.DataFrame(out)


def horizon_sensitivity(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame.loc[frame["eligible"]].copy()
    rows["group"] = np.where(rows["role"].eq("control"), rows["family"], rows["event_class"])
    columns = [f"share_arr_{label}" for label in ARRIVAL_HORIZONS] + [f"share_fixed_{label}" for label in FIXED_HORIZONS]
    out = []
    for column in columns:
        level = event_level(rows, column)
        level["group"] = np.where(level["role"].eq("control"), level["family"], level["event_class"])
        for (role, group), part in level.groupby(["role", "group"]):
            clock, horizon = column.replace("share_", "").split("_", 1)
            out.append({"clock": "arrival anchor" if clock == "arr" else "scheduled second", "horizon": horizon,
                        "role": role, "group": group, "events": len(part), "median_share": part[column].median(),
                        "mean_share": part[column].mean()})
    return pd.DataFrame(out)


def trade_intervention(frame: pd.DataFrame) -> pd.DataFrame:
    """How often a trade intervenes, by representation class (the legacy eligibility selection)."""
    rows = frame.loc[frame["eligible"]].copy()
    rows["group"] = np.where(rows["role"].eq("control"), rows["family"], rows["event_class"])
    out = []
    for (role, group, instrument), part in rows.groupby(["role", "group", "instrument"]):
        change = part["first_change_attr"]
        out.append({
            "role": role, "group": group, "instrument": instrument, "rows": len(part),
            "trade_before_first_quote": part["trade_before_first_quote"].astype(float).mean(),
            "first_quote_is_trade_effect": part["same_event_first_quote_trade"].astype(float).mean(),
            "first_quote_moves_midpoint": (part["first_quote_revision_bp"].abs() > 1e-9).mean(),
            "first_midpoint_change_is_trade": (change == 1).sum() / max(change.notna().sum(), 1),
            "median_first_quote_ms": part["first_quote_ms"].median(),
            "median_first_trade_ms": part["first_trade_ms"].median(),
            "median_trades_first_100ms": part["w100ms_trade_count"].median(),
            "median_trades_first_second": part["w1s_trade_count"].median(),
            "median_trades_in_arrival_100ms": part["arr_burst_100ms_trade_count"].median(),
        })
    return pd.DataFrame(out)


def arrival_latency(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame.loc[frame["eligible"] & frame["role"].eq("event")].copy()
    rows["discrete_arrival"] = rows["burst_bp"].abs().ge(2.0) & (
        rows["burst_bp"].abs() >= 4 * rows["pre_burst_bp"].abs().fillna(0)
    )
    out = []
    for (name, year), part in rows.groupby(["event_class", "year"]):
        seen = part.loc[part["discrete_arrival"]]
        out.append({"event_class": name, "year": year, "rows": len(part),
                    "discrete_arrival_share": part["discrete_arrival"].mean(),
                    "median_arrival_seconds": seen["arr_burst_seconds"].median(),
                    "q25_arrival_seconds": seen["arr_burst_seconds"].quantile(0.25),
                    "q75_arrival_seconds": seen["arr_burst_seconds"].quantile(0.75),
                    "median_abs_burst_bp": part["burst_bp"].abs().median()})
    return pd.DataFrame(out)


def regressions(frame: pd.DataFrame) -> pd.DataFrame:
    """Row-level taxonomy regression (event x instrument), clustered by event day."""
    rows = frame.loc[frame["eligible"] & frame["role"].eq("event") & frame["event_class"].isin(CLASS_ORDER)].copy()
    rows["outcome_share"] = rows[PRIMARY].clip(-1, 2)
    rows["event_class"] = pd.Categorical(rows["event_class"], CLASS_ORDER)
    rows["log_pre_spread"] = np.log(rows["pre_spread_ticks"].clip(lower=1))
    rows["log_burst"] = np.log1p(rows["burst_bp"].abs())
    out = []
    for outcome, label in (("outcome_share", "share, winsorized to [-1, 2]"), ("dqc_burst100", "directional share in [-1, 1]")):
        for spec, formula in (("class + instrument", f"{outcome} ~ C(event_class) + C(instrument)"),
                              ("plus spread and move size", f"{outcome} ~ C(event_class) + C(instrument) + log_pre_spread + log_burst")):
            data = rows.dropna(subset=[outcome, "log_pre_spread", "log_burst"])
            if data["event_class"].nunique() < 2 or len(data) < 30:
                continue
            fit = smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": data["event_date"]})
            for term in fit.params.index:
                out.append({"outcome": label, "specification": spec, "term": term, "coefficient": fit.params[term],
                            "se_clustered": fit.bse[term], "p_two_sided": fit.pvalues[term],
                            "observations": int(fit.nobs), "clusters": data["event_date"].nunique()})
    return pd.DataFrame(out)


def trend(frame: pd.DataFrame, column: str) -> dict[str, object]:
    level = event_level(frame.loc[frame["eligible"] & frame["role"].eq("event")], column)
    level = level.loc[level["event_class"].isin(CLASS_ORDER)]
    rank = level["event_class"].map({name: i for i, name in enumerate(CLASS_ORDER)})
    if level["event_class"].nunique() < 3:
        return {"events": len(level), "spearman_rho": np.nan, "p_two_sided": np.nan}
    result = spearmanr(rank, level[column])
    return {"events": len(level), "spearman_rho": float(result.statistic), "p_two_sided": float(result.pvalue)}


def _write(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(TABLES / f"{name}.csv", index=False)
    frame.to_latex(TABLES / f"{name}.tex", index=False, float_format="%.4f")


def figure_shares(events: pd.DataFrame, samples: list[str]) -> None:
    fig, axes = plt.subplots(1, len(samples), figsize=(max(7.5, 5.2 * len(samples)), 4.9), sharey=True, squeeze=False)
    for ax, sample in zip(axes[0], samples):
        rows = in_sample(events, sample)
        rows = rows.loc[rows["eligible"]]
        level = event_level(rows, PRIMARY)
        groups, labels = [], []
        for name in CLASS_ORDER:
            for role, tag in (("event", ""), ("pseudo", "\n2 min earlier")):
                values = level.loc[level["role"].eq(role) & level["event_class"].eq(name), PRIMARY].clip(-1, 2)
                groups.append(values.to_numpy())
                labels.append(CLASS_LABEL[name].split(" (")[0].replace("Multi-dimensional", "Multi-dim.") + tag)
        positions = np.arange(len(groups))
        colors = ["#1565a3", "#b8c4cf"] * len(CLASS_ORDER)
        for position, values, color in zip(positions, groups, colors):
            if len(values) == 0:
                continue
            box = ax.boxplot(values, positions=[position], widths=0.6, patch_artist=True, showfliers=False)
            box["boxes"][0].set(facecolor=color, alpha=0.75)
            box["medians"][0].set(color="black")
            ax.text(position, 2.08, f"n={len(values)}", ha="center", va="bottom", fontsize=7)
        ax.axhline(H1_THRESHOLD, color="#b54a40", lw=0.9, ls="--")
        ax.axhline(H2_THRESHOLD, color="#b54a40", lw=0.9, ls=":")
        ax.axhline(0, color="#888888", lw=0.6)
        ax.set_xticks(positions, labels, rotation=55, ha="right", fontsize=7)
        ax.set_ylim(-1.05, 2.25)
        ax.set_title(sample.replace("_", " "))
        ax.grid(axis="y", alpha=0.2)
    axes[0][0].set_ylabel("quote-revision share of the arrival move (100 ms)")
    fig.suptitle("Blue: announcement. Grey: same window two minutes earlier.\nDashed 0.70 = H1 threshold, dotted 0.40 = H2 threshold.", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "quote_revision_share_by_class.png", dpi=180)
    plt.close(fig)


def figure_arrival_paths(events: pd.DataFrame, samples: list[str]) -> None:
    """Average midpoint path around the arrival anchor, split into quote and trade components."""
    fine = pd.read_parquet(FEATURES / "fine.parquet",
                           columns=["event_id", "instrument", "seconds", "cum_quote_bp", "cum_trade_bp"])
    grid = np.round(np.arange(-0.2, 1.0001, 0.02), 2)
    fig, axes = plt.subplots(len(samples), len(CLASS_ORDER), figsize=(3.6 * len(CLASS_ORDER), 2.9 * len(samples)),
                             sharex=True, squeeze=False)
    for i, sample in enumerate(samples):
        rows = in_sample(events, sample)
        rows = rows.loc[rows["eligible"] & rows["role"].eq("event") & rows["arr_burst_seconds"].between(0, 8.9)]
        for j, name in enumerate(CLASS_ORDER):
            ax = axes[i][j]
            part = rows.loc[rows["event_class"].eq(name), ["event_id", "instrument", "arr_burst_seconds", "burst_bp"]]
            paths = fine.merge(part, on=["event_id", "instrument"])
            paths["relative"] = np.round(paths["seconds"] - np.round(paths["arr_burst_seconds"] / 0.02) * 0.02, 2)
            paths = paths.loc[paths["relative"].between(-0.2, 1.0)]
            sign = np.sign(paths["burst_bp"]).replace(0, 1)
            for column in ("cum_quote_bp", "cum_trade_bp"):
                paths[column] = paths[column] * sign
            origin = paths.loc[paths["relative"].eq(-0.2)].set_index(["event_id", "instrument"])[["cum_quote_bp", "cum_trade_bp"]]
            paths = paths.join(origin, on=["event_id", "instrument"], rsuffix="_origin").dropna()
            for column in ("cum_quote_bp", "cum_trade_bp"):
                paths[column] = paths[column] - paths[f"{column}_origin"]
            mean = paths.groupby("relative")[["cum_quote_bp", "cum_trade_bp"]].mean().reindex(grid)
            ax.plot(mean.index, mean["cum_trade_bp"], color="#b54a40", label="trade-attributed")
            ax.plot(mean.index, mean["cum_quote_bp"], color="#1565a3", label="quote-attributed")
            ax.plot(mean.index, mean.sum(axis=1), color="black", lw=0.8, ls="--", label="midpoint")
            ax.axvline(0, color="#888888", lw=0.6)
            ax.axhline(0, color="#888888", lw=0.6)
            ax.set_title(f"{CLASS_LABEL[name].split(' (')[0]}\n{sample.replace('_', ' ')}, n={len(part)}", fontsize=8)
            ax.grid(alpha=0.2)
            if i == len(samples) - 1:
                ax.set_xlabel("seconds from arrival anchor")
            if j == 0:
                ax.set_ylabel("mean cumulative move (bp,\nin the direction of the burst)")
    axes[0][0].legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGURES / "arrival_aligned_components.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", nargs="*", default=list(SAMPLES))
    parser.add_argument("--suffix", default="", help="Appended to table names, e.g. _development")
    args = parser.parse_args()
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    events = load_events()
    present = [sample for sample in args.samples if len(in_sample(events, sample))]
    tests, levels, summaries, horizons, interventions, fits, trends, checks = [], [], [], [], [], [], [], []
    for sample in present:
        rows = in_sample(events, sample)
        for column, role in ((PRIMARY, "primary"), (SECONDARY, "secondary"), ("share_burst100_alt", "sensitivity: 100 us tolerance")):
            table = contrasts(rows, column)
            table.insert(0, "outcome", role)
            table.insert(0, "sample", sample)
            tests.append(table)
            trends.append({"sample": sample, "outcome": role, **trend(rows, column)})
            if column != "share_burst100_alt":
                level = thresholds(rows, column)
                level.insert(0, "outcome", role)
                level.insert(0, "sample", sample)
                levels.append(level)
        for builder, bucket in ((class_summary, summaries), (horizon_sensitivity, horizons),
                                (trade_intervention, interventions), (regressions, fits), (robustness, checks)):
            table = builder(rows)
            if len(table):
                table.insert(0, "sample", sample)
                bucket.append(table)
    latency = arrival_latency(events)
    outputs = {
        "q1_short_horizon_contrasts": pd.concat(tests, ignore_index=True),
        "q1_short_horizon_thresholds": pd.concat(levels, ignore_index=True),
        "q1_short_horizon_trend": pd.DataFrame(trends),
        "q1_short_horizon_class_summary": pd.concat(summaries, ignore_index=True),
        "q1_short_horizon_horizons": pd.concat(horizons, ignore_index=True),
        "q1_trade_intervention": pd.concat(interventions, ignore_index=True),
        "q1_short_horizon_regression": pd.concat(fits, ignore_index=True) if fits else pd.DataFrame(),
        "q1_arrival_latency": latency,
        "q1_short_horizon_robustness": pd.concat(checks, ignore_index=True),
    }
    for name, table in outputs.items():
        _write(table, f"{name}{args.suffix}")
    figure_shares(events, present)
    figure_arrival_paths(events, present)

    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", lambda v: f"{v:.4f}"):
        summary = outputs["q1_short_horizon_class_summary"]
        print("Event-level primary share (median) by sample:")
        view = summary.loc[summary["instrument"].eq("event_mean")]
        print(view.pivot_table(index=["role", "group"], columns="sample", values="primary_median").to_string())
        print("\nPre-declared contrasts, primary outcome:")
        contrast_view = outputs["q1_short_horizon_contrasts"]
        print(contrast_view.loc[contrast_view["outcome"].eq("primary"),
                                ["sample", "contrast", "n_left", "n_right", "estimate", "p_two_sided", "holm_p"]].to_string(index=False))
        print("\nH1/H2 literal thresholds, primary outcome:")
        print(outputs["q1_short_horizon_thresholds"].loc[lambda t: t["outcome"].eq("primary")].to_string(index=False))


if __name__ == "__main__":
    main()
