"""Multi-horizon H6: does the direction of an FOMC statement surprise matter?

Uses the same statement returns as analyze_fomc_h5_horizons.py
(R_h in bp from the last pre-statement midpoint, h = 1s ... 30m).

A hawkish surprise (USMPD > 0) should lower ES, NQ and ZN prices (ZN falls as
yields rise). The aligned return A_h = -sign(surprise) * R_h is positive when
prices move the way the news implies. Meetings in the bottom quartile of
|surprise| are dropped: their sign is close to arbitrary.

H6a  Direction check: share of meetings with A_h > 0 (binomial test vs 50%).
H6b  Size asymmetry: log(1+|R_h|) = a + b*|surprise| + c*hawkish; c > 0 means
     hawkish news moves prices more at the same surprise size.
H6c  Speed asymmetry: |R_h|/|R_30m| = a + b*|surprise| + c*hawkish; c < 0 means
     a smaller share of the 30-minute move is done early after hawkish news
     (slower absorption, the proposal's H6). Needs the 30-minute horizon.

Regressions use HC1 standard errors; every table has Holm and BH columns.
Also writes the median signed return path by hawkish/dovish group for figures.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import binomtest

from scripts.analyze_fomc_h5_horizons import (
    ENDPOINT,
    EQUITY,
    HORIZONS,
    INSTRUMENTS,
    LABELS,
    MEASURES,
    MIN_OBS,
    response_fractions,
)
from scripts.analyze_fomc_surprises import _adjust, _meetings, _write
from src.events.surprises import build_surprise_panel
from src.utils.config import PROJECT_ROOT

SMALL_SURPRISE_QUANTILE = 0.25


def signed_returns(horizons: pd.DataFrame) -> pd.DataFrame:
    """Meeting x instrument x horizon signed R_h for covered statement horizons, plus an ES+NQ average."""
    data = horizons.loc[
        horizons["subevent"].eq("statement")
        & horizons["dataset_condition"].eq("available")
        & horizons["full_horizon_covered"].astype(bool)
        & horizons["horizon_seconds"].isin(HORIZONS)
        & horizons["instrument"].isin(INSTRUMENTS)
    ].dropna(subset=["log_return_bp"])
    data = data[["meeting", "instrument", "horizon_seconds", "log_return_bp"]]
    equity = (
        data.loc[data["instrument"].isin(EQUITY)]
        .groupby(["meeting", "horizon_seconds"])["log_return_bp"]
        .agg(["mean", "count"])
        .reset_index()
    )
    equity = equity.loc[equity["count"].eq(len(EQUITY))].drop(columns="count")
    equity = equity.rename(columns={"mean": "log_return_bp"}).assign(instrument="equity_average")
    data = pd.concat([data, equity], ignore_index=True)
    return data.assign(abs_return_bp=data["log_return_bp"].abs())


def clear_surprises(surprises: pd.DataFrame, measure: str) -> pd.DataFrame:
    """Meetings with a nonzero surprise above the bottom quartile of |surprise|, with a hawkish flag."""
    sample = surprises[["meeting", measure]].dropna()
    magnitude = sample[measure].abs()
    sample = sample.loc[magnitude.gt(magnitude.quantile(SMALL_SURPRISE_QUANTILE)) & magnitude.gt(0)]
    return sample.assign(abs_surprise=sample[measure].abs(), hawkish=sample[measure].gt(0).astype(float))


def _hawkish_coefficient(sample: pd.DataFrame, outcome: str) -> tuple[float, float]:
    design = sm.add_constant(sample[["abs_surprise", "hawkish"]])
    fit = sm.OLS(sample[outcome], design).fit(cov_type="HC1")
    return float(fit.params["hawkish"]), float(fit.pvalues["hawkish"])


def _enough(sample: pd.DataFrame) -> bool:
    hawkish = int(sample["hawkish"].sum())
    return len(sample) >= MIN_OBS and hawkish >= 3 and len(sample) - hawkish >= 3


def direction_rows(returns: pd.DataFrame, surprises: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for measure in MEASURES:
        data = returns.merge(clear_surprises(surprises, measure), on="meeting")
        data = data.assign(aligned_bp=-np.sign(data[measure]) * data["log_return_bp"])
        for (instrument, horizon), group in data.groupby(["instrument", "horizon_seconds"]):
            moved = group.loc[group["aligned_bp"].ne(0)]
            expected = int(moved["aligned_bp"].gt(0).sum())
            rows.append(
                {
                    "instrument": instrument,
                    "horizon": LABELS[int(horizon)],
                    "horizon_seconds": int(horizon),
                    "measure": measure,
                    "observations": len(moved),
                    "expected_direction_count": expected,
                    "expected_direction_share": expected / len(moved) if len(moved) else np.nan,
                    "median_aligned_return_bp": float(group["aligned_bp"].median()),
                    "binomial_p_two_sided": float(binomtest(expected, len(moved)).pvalue) if len(moved) else np.nan,
                }
            )
    table = pd.DataFrame(rows).sort_values(["instrument", "measure", "horizon_seconds"], ignore_index=True)
    return _adjust(table, "binomial_p_two_sided")


def asymmetry_rows(frame: pd.DataFrame, outcome: str, surprises: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for measure in MEASURES:
        data = frame.merge(clear_surprises(surprises, measure), on="meeting")
        for (instrument, horizon), group in data.groupby(["instrument", "horizon_seconds"]):
            sample = group.dropna(subset=[outcome])
            hawkish = sample["hawkish"].eq(1)
            row = {
                "instrument": instrument,
                "horizon": LABELS[int(horizon)],
                "horizon_seconds": int(horizon),
                "measure": measure,
                "observations": len(sample),
                "hawkish_count": int(hawkish.sum()),
                "dovish_count": int((~hawkish).sum()),
                "hawkish_median": float(sample.loc[hawkish, outcome].median()),
                "dovish_median": float(sample.loc[~hawkish, outcome].median()),
                "hawkish_coef_given_magnitude": np.nan,
                "hawkish_coef_p_two_sided": np.nan,
            }
            if _enough(sample):
                row["hawkish_coef_given_magnitude"], row["hawkish_coef_p_two_sided"] = _hawkish_coefficient(sample, outcome)
            rows.append(row)
    table = pd.DataFrame(rows).sort_values(["instrument", "measure", "horizon_seconds"], ignore_index=True)
    return _adjust(table, "hawkish_coef_p_two_sided")


def direction_profile(returns: pd.DataFrame, surprises: pd.DataFrame, measure: str = "STMT") -> pd.DataFrame:
    data = returns.merge(clear_surprises(surprises, measure), on="meeting")
    data = data.assign(direction=np.where(data["hawkish"].eq(1), "hawkish", "dovish"))
    profile = (
        data.groupby(["instrument", "direction", "horizon_seconds"])["log_return_bp"]
        .agg(observations="count", median_return_bp="median", mean_return_bp="mean")
        .reset_index()
    )
    profile.insert(2, "horizon", profile["horizon_seconds"].map(LABELS))
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-horizon H6 on FOMC statements")
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml", help="File under config/")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    parser.add_argument("--suffix", help="Appended to table names (default: config name after fomc_sample)")
    args = parser.parse_args()
    stem = args.config.removesuffix(".yaml")
    root = PROJECT_ROOT / "data" / "processed" / (args.root or stem)
    suffix = args.suffix if args.suffix is not None else stem.removeprefix("fomc_sample")

    panel = build_surprise_panel(_meetings(args.config))
    surprises = panel.loc[panel["dataset_condition"].eq("available"), ["meeting", *MEASURES]]
    returns = signed_returns(pd.read_csv(root / "response_horizons.csv"))
    present = sorted(returns["horizon_seconds"].unique())
    print("Horizons present: " + ", ".join(LABELS[int(h)] for h in present))
    kept = clear_surprises(surprises, "STMT")
    print(f"STMT sample after dropping the smallest 25% of surprises: {len(kept)} meetings "
          f"({int(kept['hawkish'].sum())} hawkish, {int((1 - kept['hawkish']).sum())} dovish)")

    h6a = direction_rows(returns, surprises)
    _write(h6a, f"fomc_h6a_direction{suffix}")
    sized = returns.assign(log_abs_return=np.log1p(returns["abs_return_bp"]))
    h6b = asymmetry_rows(sized, "log_abs_return", surprises)
    _write(h6b, f"fomc_h6b_size_asymmetry{suffix}")
    _write(direction_profile(returns, surprises), f"fomc_h6_direction_profile{suffix}")
    has_endpoint = ENDPOINT in present
    if has_endpoint:
        fractions = response_fractions(returns.drop(columns="log_return_bp"))
        h6c = asymmetry_rows(fractions.loc[fractions["horizon_seconds"].lt(ENDPOINT)], "fraction", surprises)
        _write(h6c, f"fomc_h6c_speed_asymmetry{suffix}")
    else:
        print("No 30-minute horizon: rerun process_fomc_sample.py to add 10/20/30 minutes; H6c skipped.")

    stmt = h6a["measure"].eq("STMT")
    print("\nH6a share of meetings moving in the expected direction (STMT):")
    print(h6a.loc[stmt, ["instrument", "horizon", "observations", "expected_direction_share", "binomial_p_two_sided", "holm_p"]]
          .round(4).to_string(index=False))
    cols = ["instrument", "horizon", "observations", "hawkish_count", "hawkish_coef_given_magnitude", "hawkish_coef_p_two_sided", "holm_p"]
    print("\nH6b hawkish effect on log(1+|R_h|), given |surprise| (STMT):")
    print(h6b.loc[h6b["measure"].eq("STMT"), cols].round(4).to_string(index=False))
    if has_endpoint:
        print("\nH6c hawkish effect on share of the 30-minute move, given |surprise| (STMT):")
        print(h6c.loc[h6c["measure"].eq("STMT"), cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
