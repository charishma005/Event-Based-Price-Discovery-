"""Additional p-value statistics for the multi-horizon H5 and H6 (FOMC statements).

Uses the returns from analyze_fomc_h5_horizons / analyze_fomc_h6_horizons and the
USMPD STMT surprise. Surprises are in percentage points of the one-year yield;
slopes are reported per 1 basis point of surprise.

H5 (|surprise| vs |R_h|), all statement meetings:
- OLS slope of |R_h| on |S| (HC1), with and without a SEP-meeting control
- permutation p-value for Spearman rho (meeting labels shuffled)
- Kruskal-Wallis across small/medium/large surprise terciles
- Mann-Whitney, large vs small tercile (one-sided: large moves more)

H6 (direction), smallest 25% of |surprise| dropped as in analyze_fomc_h6_horizons:
- R_h = a + b_hawk * S+ + b_dove * S- (HC1), Wald test b_hawk = b_dove
- Mann-Whitney on |R_h|, hawkish vs dovish (two-sided)
- Fisher exact test on the expected-direction share, hawkish vs dovish

Every p-value column gets a Holm-adjusted companion across its table.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import fisher_exact, kruskal, mannwhitneyu, permutation_test, spearmanr
from statsmodels.stats.multitest import multipletests

from scripts.analyze_fomc_h5_horizons import LABELS, MIN_OBS, surprise_terciles
from scripts.analyze_fomc_h6_horizons import clear_surprises, signed_returns
from scripts.analyze_fomc_surprises import _meetings, _write
from src.events.surprises import build_surprise_panel
from src.utils.config import PROJECT_ROOT

MEASURE = "STMT"
BP = 100.0  # USMPD surprises are in percentage points
PERMUTATIONS = 9999


def _holm(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in [c for c in frame.columns if c.endswith("_p")]:
        tested = frame[column].notna()
        frame[f"{column}_holm"] = np.nan
        if tested.any():
            frame.loc[tested, f"{column}_holm"] = multipletests(frame.loc[tested, column], method="holm")[1]
    return frame


def _ols(y: pd.Series, x: pd.DataFrame):
    return sm.OLS(y, sm.add_constant(x)).fit(cov_type="HC1")


def _permutation_spearman_p(x: np.ndarray, y: np.ndarray, seed: int) -> float:
    result = permutation_test(
        (x, y),
        lambda a, b: spearmanr(a, b).statistic,
        permutation_type="pairings",
        n_resamples=PERMUTATIONS,
        alternative="two-sided",
        random_state=seed,
    )
    return float(result.pvalue)


def h5_extra(returns: pd.DataFrame, surprises: pd.DataFrame, sep: pd.Series) -> pd.DataFrame:
    terciles = surprise_terciles(surprises).rename("group").reset_index()
    data = returns.merge(surprises[["meeting", MEASURE]].dropna(), on="meeting").merge(terciles, on="meeting")
    data = data.assign(abs_surprise_bp=data[MEASURE].abs() * BP, sep=data["meeting"].map(sep).astype(float))
    rows = []
    for number, ((instrument, horizon), group) in enumerate(data.groupby(["instrument", "horizon_seconds"])):
        if len(group) < MIN_OBS:
            continue
        plain = _ols(group["abs_return_bp"], group[["abs_surprise_bp"]])
        controlled = _ols(group["abs_return_bp"], group[["abs_surprise_bp", "sep"]])
        by_group = [group.loc[group["group"].eq(g), "abs_return_bp"] for g in ("small", "medium", "large")]
        low, high = plain.conf_int().loc["abs_surprise_bp"]
        rows.append(
            {
                "instrument": instrument,
                "horizon": LABELS[int(horizon)],
                "horizon_seconds": int(horizon),
                "observations": len(group),
                "slope_bp_per_bp_surprise": float(plain.params["abs_surprise_bp"]),
                "slope_ci_low": float(low),
                "slope_ci_high": float(high),
                "slope_p": float(plain.pvalues["abs_surprise_bp"]),
                "slope_with_sep_control": float(controlled.params["abs_surprise_bp"]),
                "slope_with_sep_control_p": float(controlled.pvalues["abs_surprise_bp"]),
                "spearman_rho": float(spearmanr(group["abs_surprise_bp"], group["abs_return_bp"]).statistic),
                "spearman_permutation_p": _permutation_spearman_p(
                    group["abs_surprise_bp"].to_numpy(), group["abs_return_bp"].to_numpy(), seed=number
                ),
                "median_small_bp": float(by_group[0].median()),
                "median_medium_bp": float(by_group[1].median()),
                "median_large_bp": float(by_group[2].median()),
                "kruskal_wallis_p": float(kruskal(*by_group).pvalue),
                "large_vs_small_mannwhitney_p": float(
                    mannwhitneyu(by_group[2], by_group[0], alternative="greater").pvalue
                ),
            }
        )
    return _holm(pd.DataFrame(rows).sort_values(["instrument", "horizon_seconds"], ignore_index=True))


def h6_extra(returns: pd.DataFrame, surprises: pd.DataFrame) -> pd.DataFrame:
    kept = clear_surprises(surprises, MEASURE)
    data = returns.merge(kept, on="meeting")
    surprise_bp = data[MEASURE] * BP
    data = data.assign(
        hawkish_part=surprise_bp.clip(lower=0),
        dovish_part=surprise_bp.clip(upper=0),
        expected=(-np.sign(data[MEASURE]) * data["log_return_bp"]).gt(0),
    )
    rows = []
    for (instrument, horizon), group in data.groupby(["instrument", "horizon_seconds"]):
        hawkish = group["hawkish"].eq(1)
        if len(group) < MIN_OBS or hawkish.sum() < 3 or (~hawkish).sum() < 3:
            continue
        fit = _ols(group["log_return_bp"], group[["hawkish_part", "dovish_part"]])
        equal = fit.t_test("hawkish_part - dovish_part = 0")
        interval = fit.conf_int()
        table = [
            [int(group.loc[hawkish, "expected"].sum()), int((~group.loc[hawkish, "expected"]).sum())],
            [int(group.loc[~hawkish, "expected"].sum()), int((~group.loc[~hawkish, "expected"]).sum())],
        ]
        rows.append(
            {
                "instrument": instrument,
                "horizon": LABELS[int(horizon)],
                "horizon_seconds": int(horizon),
                "observations": len(group),
                "hawkish_count": int(hawkish.sum()),
                "dovish_count": int((~hawkish).sum()),
                "slope_hawkish_bp_per_bp": float(fit.params["hawkish_part"]),
                "slope_dovish_bp_per_bp": float(fit.params["dovish_part"]),
                "slope_hawkish_ci_low": float(interval.loc["hawkish_part", 0]),
                "slope_hawkish_ci_high": float(interval.loc["hawkish_part", 1]),
                "slope_dovish_ci_low": float(interval.loc["dovish_part", 0]),
                "slope_dovish_ci_high": float(interval.loc["dovish_part", 1]),
                "equal_slopes_wald_p": float(np.asarray(equal.pvalue).item()),
                "median_abs_hawkish_bp": float(group.loc[hawkish, "abs_return_bp"].median()),
                "median_abs_dovish_bp": float(group.loc[~hawkish, "abs_return_bp"].median()),
                "abs_move_mannwhitney_p": float(
                    mannwhitneyu(group.loc[hawkish, "abs_return_bp"], group.loc[~hawkish, "abs_return_bp"]).pvalue
                ),
                "expected_share_hawkish": table[0][0] / sum(table[0]),
                "expected_share_dovish": table[1][0] / sum(table[1]),
                "expected_share_fisher_p": float(fisher_exact(table).pvalue),
            }
        )
    return _holm(pd.DataFrame(rows).sort_values(["instrument", "horizon_seconds"], ignore_index=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extra H5/H6 statistics on FOMC statements")
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml", help="File under config/")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    parser.add_argument("--suffix", help="Appended to table names (default: config name after fomc_sample)")
    args = parser.parse_args()
    stem = args.config.removesuffix(".yaml")
    root = PROJECT_ROOT / "data" / "processed" / (args.root or stem)
    suffix = args.suffix if args.suffix is not None else stem.removeprefix("fomc_sample")

    panel = build_surprise_panel(_meetings(args.config))
    surprises = panel.loc[panel["dataset_condition"].eq("available"), ["meeting", MEASURE]]
    horizons = pd.read_csv(root / "response_horizons.csv")
    sep = horizons.drop_duplicates("meeting").set_index("meeting")["sep_release"]
    returns = signed_returns(horizons)

    h5 = h5_extra(returns, surprises, sep)
    h6 = h6_extra(returns, surprises)
    _write(h5, f"fomc_h5_extra_tests{suffix}")
    _write(h6, f"fomc_h6_extra_tests{suffix}")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print("H5 extra tests (STMT):")
        print(h5[["instrument", "horizon", "slope_bp_per_bp_surprise", "slope_p", "slope_with_sep_control_p",
                  "spearman_permutation_p", "kruskal_wallis_p", "large_vs_small_mannwhitney_p",
                  "large_vs_small_mannwhitney_p_holm"]].round(4).to_string(index=False))
        print("\nH6 extra tests (STMT, smallest 25% of surprises dropped):")
        print(h6[["instrument", "horizon", "slope_hawkish_bp_per_bp", "slope_dovish_bp_per_bp", "equal_slopes_wald_p",
                  "equal_slopes_wald_p_holm", "abs_move_mannwhitney_p", "expected_share_hawkish",
                  "expected_share_dovish", "expected_share_fisher_p"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
