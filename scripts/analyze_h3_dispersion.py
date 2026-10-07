"""H3: is the quote-revision share lower when economists disagreed more beforehand?

Everything here is fixed in ``config/h3_prereg.yaml`` and
``reports/h3_preregistration.md``; this script only implements it. It refuses to
run unless the YAML is frozen and the survey workbook, ``events.parquet``, the
registry, the survey parser and this file still match the recorded hashes.

Run: python -m scripts.analyze_h3_dispersion
"""
from __future__ import annotations

import argparse
import hashlib
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm
from statsmodels.stats.multitest import multipletests

import scripts.analyze_q1_short_horizon as q1
from src.utils.config import PROJECT_ROOT, load_yaml

warnings.filterwarnings("ignore", category=FutureWarning)

PREREGISTRATION = "config/h3_prereg.yaml"
HASHED_FILES = {
    "survey_workbook_sha256": "data/raw/bloomberg/bbg_eco.xlsx",
    "events_sha256": "data/processed/tick_features/events.parquet",
    "event_registry_sha256": "data/events/event_registry.csv",
    "survey_parser_sha256": "scripts/build_bloomberg_surveys.py",
    "analysis_code_sha256": "scripts/analyze_h3_dispersion.py",
}
SURVEYS = PROJECT_ROOT / "data" / "processed" / "bloomberg_surveys.parquet"
TABLES = PROJECT_ROOT / "tables"
FIGURES = PROJECT_ROOT / "figures" / "h3"
RELEASES = ("cpi", "ppi", "employment_situation", "retail_sales")
S = q1.PRIMARY
SURPRISE_SCALE = 1.4826          # median absolute deviation to sigma, for normal data
SURPRISE_CAP = 5.0
OUTLIER_SHARE = 0.1              # |average - median| above this share of the range: one stray forecaster
SMALLEST_EFFECT = -0.05
CONTROLS = "abs_u + log_n + C(release) + C(instrument)"
PRIMARY_RHS = f"D + {CONTROLS} + C(period)"


def sha256(relative: str) -> str:
    return hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()


def check_freeze(allow_change: bool) -> dict:
    spec = load_yaml(PROJECT_ROOT / PREREGISTRATION)
    problems = []
    if spec.get("status") != "frozen":
        problems.append("the pre-declaration is not frozen")
    for key, relative in HASHED_FILES.items():
        if spec.get("freeze", {}).get(key) != sha256(relative):
            problems.append(f"{relative} differs from the frozen hash")
    if problems and not allow_change:
        raise SystemExit("; ".join(problems) + ". Freeze first, or pass --allow-post-freeze-change and log it.")
    for problem in problems:
        print(f"WARNING (post-freeze change): {problem}")
    return spec


def expected_range(n: np.ndarray) -> np.ndarray:
    """E[max - min] of n standard normal draws (d2 in quality-control tables)."""
    x = np.linspace(-8, 8, 16001)
    out = np.empty(len(n))
    for i, count in enumerate(np.asarray(n, dtype=float)):
        density = count * norm.pdf(x) * norm.cdf(x) ** (count - 1)
        out[i] = 2 * np.trapezoid(x * density, x)
    return out


def series_measures(surveys: pd.DataFrame) -> pd.DataFrame:
    """Per ticker and release date: dispersion in several forms and the scaled surprise."""
    rows = surveys.loc[surveys["survey_median"].notna() & surveys["survey_high"].notna()
                       & surveys["actual_release"].notna() & surveys["survey_n"].gt(0)].copy()
    rows["range"] = rows["survey_range"]
    rows["range_d2"] = rows["range"] / expected_range(rows["survey_n"].to_numpy())
    rows["log_range"] = np.log(rows["range"].clip(lower=rows["range"][rows["range"] > 0].min()))
    rows["log_n"] = np.log(rows["survey_n"])
    rows["outlier_range"] = (rows["survey_average"] - rows["survey_median"]).abs() > OUTLIER_SHARE * rows["range"]
    by_ticker = rows.groupby("ticker")
    for column, name in (("range", "D"), ("range_d2", "D_d2")):
        rows[name] = (rows[column] - by_ticker[column].transform("mean")) / by_ticker[column].transform("std")
    rows["D_log"] = rows["log_range"] - by_ticker["log_range"].transform("mean")
    scale = SURPRISE_SCALE * by_ticker["surprise"].transform(lambda s: s.abs().median())
    rows["abs_u"] = (rows["surprise"] / scale).abs().clip(upper=SURPRISE_CAP)
    return rows[["ticker", "release", "release_date", "D", "D_d2", "D_log", "log_n", "abs_u", "outlier_range"]]


def morning_measures(measures: pd.DataFrame, series_map: dict[str, list[str]], suffix: str = "") -> pd.DataFrame:
    """One row per release morning: the mean over the release's chosen series."""
    parts = []
    for release, tickers in series_map.items():
        part = measures.loc[measures["release"].eq(release) & measures["ticker"].isin(tickers)]
        agg = part.groupby("release_date").agg(
            D=("D", "mean"), D_d2=("D_d2", "mean"), D_log=("D_log", "mean"), log_n=("log_n", "mean"),
            abs_u=("abs_u", "mean"), outlier_range=("outlier_range", "any"), series_count=("ticker", "size"),
        ).reset_index()
        agg["release"] = release
        parts.append(agg)
    out = pd.concat(parts, ignore_index=True)
    return out.rename(columns={c: f"{c}{suffix}" for c in out.columns if c not in ("release_date", "release")})


def build_panel(spec: dict) -> pd.DataFrame:
    events = q1.load_events()
    rows = events.loc[events["eligible"] & events["family"].eq("macro") & events["event_types"].isin(RELEASES)].copy()
    rows["release"] = rows["event_types"]
    rows["event_date"] = pd.to_datetime(rows["event_date"])
    rows["year"] = rows["event_date"].dt.year
    periods = spec["sample"]["periods_for_fixed_effects"]
    rows["period"] = pd.cut(rows["year"], bins=[min(v[0] for v in periods.values()) - 1] + [v[1] for v in periods.values()],
                            labels=list(periods)).astype(str)
    pseudo = events.loc[events["family"].eq("macro_pseudo"), ["matched_event", "instrument", S]]
    rows = rows.merge(pseudo.rename(columns={"matched_event": "event_id", S: "S_pseudo"}), on=["event_id", "instrument"], how="left")
    rows["S_w"] = rows[S].clip(-1, 2)
    rows["S_pseudo_w"] = rows["S_pseudo"].clip(-1, 2)
    rows["S_diff"] = rows["S_w"] - rows["S_pseudo_w"]
    rows["speed"] = rows["fp300s_50_seconds"]
    # Real Earnings is published with every CPI and is not a separate surprise; anything else at the clock counts.
    others = rows["concurrent_release"].fillna("").astype(str).str.split("|").map(lambda names: [n for n in names if n and n != "Real Earnings"])
    rows["concurrent"] = others.map(bool)

    measures = series_measures(pd.read_parquet(SURVEYS))
    headline = morning_measures(measures, spec["series"]["headline"])
    composite = morning_measures(measures, spec["series"]["composite"], "_comp")
    cpi_only = {r: t for r, t in spec["series"]["headline"].items() if r != "cpi"}
    cpi_headline = morning_measures(measures, {**cpi_only, "cpi": ["CPI CHNG Index"]}, "_cpih")
    cpi_core = morning_measures(measures, {**cpi_only, "cpi": ["CPUPXCHG Index"]}, "_cpic")
    for table in (headline, composite, cpi_headline, cpi_core):
        rows = rows.merge(table, left_on=["event_date", "release"], right_on=["release_date", "release"], how="left").drop(columns="release_date")
    rows = rows.loc[rows["D"].notna() & rows["S_w"].notna()].reset_index(drop=True)
    rows["outlier_range"] = rows["outlier_range"].astype(bool)
    return rows


def fit(data: pd.DataFrame, outcome: str, rhs: str, term: str = "D") -> dict[str, float]:
    data = data.dropna(subset=[outcome] + [c for c in ("abs_u", "log_n") if c in rhs])
    result = smf.ols(f"{outcome} ~ {rhs}", data).fit(cov_type="cluster", cov_kwds={"groups": data["event_date"]})
    interval = result.conf_int().loc[term]
    return {"beta": result.params[term], "se": result.bse[term], "p": result.pvalues[term],
            "ci_low": interval[0], "ci_high": interval[1], "rows": int(result.nobs), "mornings": data["event_date"].nunique()}


def verdict(primary: dict, no_period: dict, year: dict) -> str:
    if primary["beta"] < 0 and primary["p"] < 0.05 and no_period["beta"] < 0 and year["beta"] < 0:
        return "supported"
    if primary["ci_low"] > SMALLEST_EFFECT:
        return "rejected: no effect of at least 0.05 per sd of dispersion"
    return "inconclusive"


def primary_table(panel: pd.DataFrame) -> pd.DataFrame:
    runs = {
        "primary": fit(panel, "S_w", PRIMARY_RHS),
        "placebo: pseudo-clock S": fit(panel, "S_pseudo_w", PRIMARY_RHS),
        "variant: no period effects": fit(panel, "S_w", f"D + {CONTROLS}"),
        "variant: year effects": fit(panel, "S_w", f"D + {CONTROLS} + C(year)"),
    }
    table = pd.DataFrame(runs).T.rename_axis("run").reset_index()
    table["verdict"] = ""
    table.loc[0, "verdict"] = verdict(runs["primary"], runs["variant: no period effects"], runs["variant: year effects"])
    return table


def secondary_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    by_release = smf.ols(f"S_w ~ D:C(release) + {CONTROLS} + C(period)", panel.dropna(subset=["abs_u"])).fit(
        cov_type="cluster", cov_kwds={"groups": panel.dropna(subset=["abs_u"])["event_date"]})
    for release in RELEASES:
        term = f"D:C(release)[{release}]"
        ci = by_release.conf_int().loc[term]
        rows.append({"test": f"beta for {release}", "beta": by_release.params[term], "se": by_release.bse[term],
                     "p": by_release.pvalues[term], "ci_low": ci[0], "ci_high": ci[1], "rows": int(by_release.nobs),
                     "mornings": panel.dropna(subset=["abs_u"])["event_date"].nunique()})
    alternatives = [
        ("composite dispersion, all surveyed series", "S_w", PRIMARY_RHS.replace("D +", "D_comp +").replace("abs_u", "abs_u_comp").replace("log_n", "log_n_comp"), "D_comp"),
        ("CPI headline-only dispersion", "S_w", PRIMARY_RHS.replace("D +", "D_cpih +").replace("abs_u", "abs_u_cpih").replace("log_n", "log_n_cpih"), "D_cpih"),
        ("CPI core-only dispersion", "S_w", PRIMARY_RHS.replace("D +", "D_cpic +").replace("abs_u", "abs_u_cpic").replace("log_n", "log_n_cpic"), "D_cpic"),
        ("within-day outcome: S minus pseudo-clock S", "S_diff", PRIMARY_RHS, "D"),
        ("speed outcome: seconds to half of the 5-minute move (prediction: positive)", "speed", PRIMARY_RHS, "D"),
    ]
    for name, outcome, rhs, term in alternatives:
        data = panel.dropna(subset=[outcome, term])
        rows.append({"test": name, **fit(data, outcome, rhs, term)})
    table = pd.DataFrame(rows)
    table["holm_p"] = multipletests(table["p"], method="holm")[1]
    return table


def robustness_table(panel: pd.DataFrame) -> pd.DataFrame:
    no_log_n = PRIMARY_RHS.replace("D +", "D_d2 +").replace(" + log_n", "")
    variants = [
        ("log range in place of z-dispersion", panel, "S_w", PRIMARY_RHS.replace("D +", "D_log +"), "D_log"),
        ("range / d2(n), no log n control", panel, "S_w", no_log_n, "D_d2"),
        ("drop March to July 2020", panel.loc[~panel["event_date"].between("2020-03-01", "2020-07-31")], "S_w", PRIMARY_RHS, "D"),
        ("drop outlier-driven ranges", panel.loc[~panel["outlier_range"]], "S_w", PRIMARY_RHS, "D"),
        ("drop mornings with a concurrent release", panel.loc[~panel["concurrent"]], "S_w", PRIMARY_RHS, "D"),
        ("no winsorization of S", panel, S, PRIMARY_RHS, "D"),
        ("arrival move of at least 2 bp", panel.loc[panel["burst_bp"].abs().ge(2.0)], "S_w", PRIMARY_RHS, "D"),
    ]
    for instrument in q1.INSTRUMENTS:
        variants.append((f"{instrument.split('.')[0]} only", panel.loc[panel["instrument"].eq(instrument)], "S_w",
                         PRIMARY_RHS.replace(" + C(instrument)", ""), "D"))
    return pd.DataFrame([{"variant": name, **fit(data, outcome, rhs, term)} for name, data, outcome, rhs, term in variants])


def sample_table(panel: pd.DataFrame) -> pd.DataFrame:
    mornings = panel.drop_duplicates("event_id")
    return mornings.groupby(["release", "period"]).agg(
        mornings=("event_id", "size"), rows=("event_id", lambda s: int(panel["event_id"].isin(s).sum())),
        mean_D=("D", "mean"), sd_D=("D", "std"), mean_abs_u=("abs_u", "mean"), outlier_ranges=("outlier_range", "sum"),
    ).reset_index()


def figure(panel: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, len(RELEASES), figsize=(3.4 * len(RELEASES), 3.2), sharey=True)
    for ax, release in zip(axes, RELEASES):
        part = panel.loc[panel["release"].eq(release)].copy()
        part["bin"] = pd.qcut(part["D"], 5, labels=False, duplicates="drop")
        grouped = part.groupby("bin").agg(D=("D", "mean"), S=("S_w", "mean"), se=("S_w", lambda s: s.std() / np.sqrt(len(s))))
        ax.errorbar(grouped["D"], grouped["S"], yerr=1.96 * grouped["se"], fmt="o", color="#4a3aa7", ecolor="#b8b4d8", capsize=3)
        ax.axhline(0.5, color="#52514e", lw=0.8)
        ax.set_title(release.replace("_", " "), fontsize=9, loc="left")
        ax.set_xlabel("z-dispersion (quintile means)")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("mean S (winsorized), 95% band")
    fig.suptitle("Quote-revision share against pre-release forecast dispersion", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "h3_s_vs_dispersion.png", dpi=160)
    plt.close(fig)


def write(table: pd.DataFrame, name: str) -> None:
    table.to_csv(TABLES / f"{name}.csv", index=False)
    table.to_latex(TABLES / f"{name}.tex", index=False, float_format="%.4f")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allow-post-freeze-change", action="store_true",
                        help="Run although an input or script changed after the freeze; log the change in the YAML")
    args = parser.parse_args()
    spec = check_freeze(args.allow_post_freeze_change)
    panel = build_panel(spec)
    outputs = {
        "h3_sample": sample_table(panel), "h3_primary": primary_table(panel),
        "h3_secondary": secondary_table(panel), "h3_robustness": robustness_table(panel),
    }
    for name, table in outputs.items():
        write(table, name)
    figure(panel)
    with pd.option_context("display.width", 220, "display.max_columns", 20, "display.float_format", lambda v: f"{v:.4f}"):
        print(f"Panel: {panel['event_id'].nunique()} mornings, {len(panel)} morning-contract rows\n")
        for name in ("h3_primary", "h3_secondary", "h3_robustness"):
            print(name)
            print(outputs[name].to_string(index=False), "\n")


if __name__ == "__main__":
    main()
