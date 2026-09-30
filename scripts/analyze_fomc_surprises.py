"""H5/H6: relate FOMC price-discovery speed to high-frequency policy surprises.

H5: the discovery horizon increases with the absolute surprise.
H6: conditional on magnitude, hawkish surprises (bad news for equities) are
incorporated more slowly than dovish ones.

Inputs:
- data/external/usmpd/mps.csv (committed; published USMPD surprises)
- data/external/usmpd/USMPD.xlsx (optional; adds MP1, GSS target/path and
  real-time factors that use no future events)
- data/processed/fomc_sample/speed_metrics.parquet (from analyze_fomc_sample.py)

With only 10-12 meetings these tests are suggestive, not confirmatory.

Every H5/H6 table carries Holm and Benjamini-Hochberg adjusted p-values across
all cells of that table. Two robustness variants address known artifacts:
``equity_average`` averages ES and NQ only, because the USMPD surprise is built
from rate-futures moves in the same window as the ZN outcome; and the
``_large_moves`` tables drop observations whose five-minute move is near zero or
in the bottom quartile of its subevent/instrument cell, because a crossing time
defined as a fraction of a tiny terminal move is mostly noise.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import mannwhitneyu, spearmanr
from statsmodels.stats.multitest import multipletests

from src.events.surprises import build_surprise_panel, load_mps
from src.utils.config import PROJECT_ROOT, load_yaml


METRICS = ("first_crossing_50_seconds", "first_crossing_90_seconds", "stable_within_10pct_seconds")
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
MEASURES = {
    "statement": ("STMT", "STMT_real_time", "MP1", "target", "path"),
    "press_conference": ("PC", "PC_real_time"),
}
MIN_OBS = 6
EQUITY = ("ES.v.0", "NQ.v.0")
SMALL_MOVE_QUANTILE = 0.25


def _meetings(config_name: str = "fomc_sample.yaml") -> pd.DataFrame:
    config = load_yaml(PROJECT_ROOT / "config" / config_name)
    return pd.DataFrame(
        [
            {
                "meeting": item["label"],
                "meeting_date": item["meeting_date"],
                "dataset_condition": item.get("dataset_condition", "available"),
            }
            for item in config["meetings"]
        ]
    )


def _check_recomputation(panel: pd.DataFrame) -> None:
    if "STMT_recomputed" not in panel:
        return
    gap = (panel["STMT_recomputed"] - panel["STMT"]).abs().max()
    print(f"STMT recomputed from USMPD.xlsx vs published mps.csv: max abs gap {gap:.2e}")
    if not gap < 1e-6:
        raise ValueError("Recomputed STMT does not match mps.csv; check USMPD/y1 vintages")


def _large_moves(speed: pd.DataFrame) -> pd.DataFrame:
    """Drop near-zero moves and the bottom quartile of |5-minute move| per cell."""
    magnitude = speed["terminal_300s_bp"].abs()
    cutoff = magnitude.groupby([speed["subevent"], speed["instrument"]]).transform(
        lambda values: values.quantile(SMALL_MOVE_QUANTILE)
    )
    return speed.loc[~speed["near_zero_terminal"].astype(bool) & magnitude.gt(cutoff)]


def _speed_panel(surprises: pd.DataFrame, speed: pd.DataFrame) -> pd.DataFrame:
    speed = speed.loc[speed["instrument"].isin(INSTRUMENTS)]
    long = speed.melt(
        id_vars=["meeting", "subevent", "instrument"],
        value_vars=list(METRICS),
        var_name="metric",
        value_name="seconds",
    ).dropna(subset=["seconds"])
    long["log_seconds"] = np.log1p(long["seconds"])
    # Cross-instrument summaries: mean log horizon per meeting, as in the depth
    # tables, over all three contracts and over the two equity contracts only.
    averages = []
    for label, members in (("meeting_average", INSTRUMENTS), ("equity_average", EQUITY)):
        average = (
            long.loc[long["instrument"].isin(members)]
            .groupby(["meeting", "subevent", "metric"], as_index=False)["log_seconds"]
            .mean()
            .assign(instrument=label)
        )
        average["seconds"] = np.expm1(average["log_seconds"])
        averages.append(average)
    return pd.concat([long, *averages], ignore_index=True).merge(surprises, on="meeting")


def _adjust(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Holm and Benjamini-Hochberg adjustment across every cell of one table."""
    frame = frame.copy()
    frame["holm_p"] = np.nan
    frame["bh_q"] = np.nan
    tested = frame[column].notna()
    if tested.any():
        values = frame.loc[tested, column].to_numpy()
        frame.loc[tested, "holm_p"] = multipletests(values, method="holm")[1]
        frame.loc[tested, "bh_q"] = multipletests(values, method="fdr_bh")[1]
    return frame


def _h5_rows(data: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for (subevent, metric, instrument), group in data.groupby(["subevent", "metric", "instrument"]):
        for measure in MEASURES[subevent]:
            if measure not in group:
                continue
            sample = group.dropna(subset=[measure])
            row: dict[str, object] = {
                "subevent": subevent,
                "metric": metric,
                "instrument": instrument,
                "measure": measure,
                "observations": len(sample),
                "spearman_rho_abs_surprise": np.nan,
                "one_sided_p_positive": np.nan,
                "two_sided_p": np.nan,
            }
            if len(sample) >= MIN_OBS and sample[measure].abs().nunique() > 1:
                result = spearmanr(sample[measure].abs(), sample["seconds"], alternative="greater")
                row["spearman_rho_abs_surprise"] = float(result.statistic)
                row["one_sided_p_positive"] = float(result.pvalue)
                row["two_sided_p"] = float(
                    spearmanr(sample[measure].abs(), sample["seconds"]).pvalue
                )
            rows.append(row)
    return rows


def _h6_rows(data: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for (subevent, metric, instrument), group in data.groupby(["subevent", "metric", "instrument"]):
        for measure in MEASURES[subevent]:
            if measure not in group:
                continue
            sample = group.loc[group[measure].notna() & group[measure].ne(0)]
            hawkish = sample[measure].gt(0)
            row: dict[str, object] = {
                "subevent": subevent,
                "metric": metric,
                "instrument": instrument,
                "measure": measure,
                "observations": len(sample),
                "hawkish_count": int(hawkish.sum()),
                "dovish_count": int((~hawkish).sum()),
                "hawkish_median_seconds": sample.loc[hawkish, "seconds"].median(),
                "dovish_median_seconds": sample.loc[~hawkish, "seconds"].median(),
                "mannwhitney_p_two_sided": np.nan,
                "hawkish_log_coef_given_magnitude": np.nan,
                "hawkish_coef_p_two_sided": np.nan,
            }
            if len(sample) >= MIN_OBS and hawkish.sum() >= 2 and (~hawkish).sum() >= 2:
                row["mannwhitney_p_two_sided"] = float(
                    mannwhitneyu(
                        sample.loc[hawkish, "seconds"],
                        sample.loc[~hawkish, "seconds"],
                        alternative="two-sided",
                    ).pvalue
                )
                design = sm.add_constant(
                    pd.DataFrame(
                        {
                            "abs_surprise": sample[measure].abs(),
                            "hawkish": hawkish.astype(float),
                        }
                    )
                )
                fit = sm.OLS(sample["log_seconds"], design).fit(cov_type="HC1")
                row["hawkish_log_coef_given_magnitude"] = float(fit.params["hawkish"])
                row["hawkish_coef_p_two_sided"] = float(fit.pvalues["hawkish"])
            rows.append(row)
    return rows


def _write(frame: pd.DataFrame, name: str) -> None:
    tables = PROJECT_ROOT / "tables"
    frame.to_csv(tables / f"{name}.csv", index=False)
    frame.to_latex(tables / f"{name}.tex", index=False, float_format="%.4f")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test H5/H6 against USMPD policy surprises")
    parser.add_argument("--config", default="fomc_sample.yaml", help="File under config/")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    parser.add_argument("--suffix", help="Appended to table names (default: config name after fomc_sample)")
    args = parser.parse_args()
    stem = args.config.removesuffix(".yaml")
    root = args.root or stem
    suffix = args.suffix if args.suffix is not None else stem.removeprefix("fomc_sample")

    (PROJECT_ROOT / "tables").mkdir(parents=True, exist_ok=True)
    panel = build_surprise_panel(_meetings(args.config))
    _check_recomputation(panel)
    missing = panel.loc[panel["STMT"].isna(), "meeting"].tolist()
    if missing:
        print(f"Meetings without a USMPD statement surprise: {missing}")
    _write(panel.drop(columns=["STMT_recomputed"], errors="ignore"), f"fomc_surprise_panel{suffix}")
    if "MP1" not in panel:
        print("USMPD.xlsx not found: MP1, GSS target/path and real-time factors skipped")
    mps = load_mps()
    print(
        "Sample SD across all USMPD events (for scale): "
        f"STMT={mps['STMT'].std():.4f}, PC={mps['PC'].std():.4f}"
    )

    speed_path = PROJECT_ROOT / "data" / "processed" / root / "speed_metrics.parquet"
    if not speed_path.exists():
        print(f"{speed_path} not found; run scripts/analyze_fomc_sample.py first")
        return

    surprises = panel.loc[panel["dataset_condition"].eq("available")].drop(
        columns=["meeting_date", "dataset_condition", "STMT_recomputed"], errors="ignore"
    )
    speed = pd.read_parquet(speed_path)
    large = _large_moves(speed)
    print(f"Large-move robustness keeps {len(large)} of {len(speed)} speed rows")
    tables = {}
    for variant, frame in (("", speed), ("_large_moves", large)):
        data = _speed_panel(surprises, frame)
        h5 = _adjust(pd.DataFrame(_h5_rows(data)), "two_sided_p")
        h6 = _adjust(pd.DataFrame(_h6_rows(data)), "mannwhitney_p_two_sided")
        _write(h5, f"fomc_h5_surprise_speed{variant}{suffix}")
        _write(h6, f"fomc_h6_surprise_asymmetry{variant}{suffix}")
        tables[variant] = (h5, h6)
    h5, h6 = tables[""]
    for name, table, column in (("H5", h5, "two_sided_p"), ("H6", h6, "mannwhitney_p_two_sided")):
        tested = table[column].notna()
        print(
            f"{name}: {int(tested.sum())} tests, {int(table.loc[tested, column].lt(0.05).sum())} raw p<0.05, "
            f"{int(table['holm_p'].lt(0.05).sum())} Holm p<0.05, {int(table['bh_q'].lt(0.05).sum())} BH q<0.05"
        )

    headline = h5.loc[
        h5["metric"].eq("first_crossing_50_seconds") & h5["instrument"].eq("meeting_average")
    ]
    print("\nH5 headline (50% crossing, meeting-average log horizon):")
    print(headline.to_string(index=False))
    headline = h6.loc[
        h6["metric"].eq("first_crossing_50_seconds") & h6["instrument"].eq("meeting_average")
    ]
    print("\nH6 headline (50% crossing, meeting-average log horizon):")
    print(headline.to_string(index=False))


if __name__ == "__main__":
    main()
