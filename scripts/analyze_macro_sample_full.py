from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import mannwhitneyu, wilcoxon

from src.microstructure.mechanism import fit_order_flow_impact, mechanism_components
from src.utils.config import PROJECT_ROOT


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
HORIZONS = (60.0, 300.0)


def _impacts(intervals: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    bundles = sorted(intervals.loc[intervals["dataset_condition"].eq("available"), "bundle_id"].unique())
    for bundle in bundles:
        for instrument in INSTRUMENTS:
            sample = intervals.loc[
                intervals["dataset_condition"].eq("available")
                & intervals["bundle_id"].ne(bundle)
                & intervals["instrument"].eq(instrument)
                & intervals["event_seconds"].ge(-240)
                & intervals["event_seconds"].lt(-60)
            ]
            diagnostics, _ = fit_order_flow_impact(sample)
            rows.append(
                {
                    "focal_bundle": bundle,
                    "instrument": instrument,
                    **diagnostics,
                    "training_bundle_count": sample["bundle_id"].nunique(),
                }
            )
    return pd.DataFrame(rows)


def _mechanisms(
    timing: pd.DataFrame, horizons: pd.DataFrame, impacts: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for timing_row in timing.itertuples(index=False):
        impact = impacts.loc[
            impacts["focal_bundle"].eq(timing_row.bundle_id)
            & impacts["instrument"].eq(timing_row.instrument)
        ].iloc[0]
        event_horizons = horizons.loc[
            horizons["bundle_id"].eq(timing_row.bundle_id)
            & horizons["instrument"].eq(timing_row.instrument)
            & horizons["horizon_seconds"].isin(HORIZONS)
        ]
        for horizon in event_horizons.itertuples(index=False):
            total = float(horizon.log_return_bp) / 10_000
            for definition, quote_bp in (
                ("first_valid_quote", timing_row.first_quote_revision_bp),
                ("last_pretrade_quote", timing_row.last_pretrade_quote_revision_bp),
            ):
                if pd.isna(quote_bp):
                    continue
                quote = float(quote_bp) / 10_000
                components = mechanism_components(
                    quote_revision=quote,
                    cumulative_signed_flow=float(horizon.signed_volume),
                    impact_coefficient=float(impact.impact_coefficient),
                    total_adjustment=total,
                )
                near_zero_total = abs(total * 10_000) < 0.10
                direct_share = np.nan if near_zero_total else quote / total
                rows.append(
                    {
                        "bundle_id": timing_row.bundle_id,
                        "event_types": timing_row.event_types,
                        "representation_class": timing_row.representation_class,
                        "concurrent_release": timing_row.concurrent_release,
                        "instrument": timing_row.instrument,
                        "horizon_seconds": float(horizon.horizon_seconds),
                        "quote_definition": definition,
                        "eligible_primary_q1": bool(timing_row.eligible_primary_q1),
                        "total_adjustment_bp": total * 10_000,
                        "quote_revision_bp": quote * 10_000,
                        "order_flow_component_bp": float(components["order_flow_component"]) * 10_000,
                        "residual_component_bp": float(components["residual_component"]) * 10_000,
                        "mechanism_share": components["mechanism_share"],
                        "quote_fraction_of_total": direct_share,
                        "absolute_quote_fraction": abs(direct_share) if np.isfinite(direct_share) else np.nan,
                        "same_direction_quote": bool(
                            not near_zero_total and quote != 0 and np.sign(quote) == np.sign(total)
                        ),
                        "near_zero_total": near_zero_total,
                        "known_side_fraction": horizon.known_side_fraction,
                        "impact_coefficient": impact.impact_coefficient,
                        "impact_r_squared": impact.r_squared,
                        "impact_training_nobs": impact.nobs,
                        "quality_flags": "|".join(components["quality_flags"]),
                    }
                )
    return pd.DataFrame(rows)


def _h1_summary(mechanisms: pd.DataFrame) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["horizon_seconds"].eq(300)
        & ~mechanisms["near_zero_total"]
    ].copy()
    rows: list[dict[str, object]] = []
    for keys, group in sample.groupby(["representation_class", "instrument"]):
        fractions = group["absolute_quote_fraction"].dropna().to_numpy(float)
        p_value = np.nan
        below_p_value = np.nan
        if len(fractions) >= 3 and not np.allclose(fractions - 0.7, 0):
            p_value = float(
                wilcoxon(fractions - 0.7, alternative="greater", method="auto").pvalue
            )
            below_p_value = float(
                wilcoxon(fractions - 0.7, alternative="less", method="auto").pvalue
            )
        rows.append(
            {
                "representation_class": keys[0],
                "instrument": keys[1],
                "observations": len(group),
                "zero_first_quote_count": int(np.isclose(group["quote_revision_bp"], 0).sum()),
                "median_abs_total_bp": group["total_adjustment_bp"].abs().median(),
                "median_absolute_quote_fraction": np.median(fractions) if len(fractions) else np.nan,
                "fraction_above_70pct": float((fractions > 0.7).mean()) if len(fractions) else np.nan,
                "one_sided_wilcoxon_vs_70pct_p": p_value,
                "one_sided_wilcoxon_below_70pct_p": below_p_value,
                "median_abs_residual_bp": group["residual_component_bp"].abs().median(),
            }
        )
    return pd.DataFrame(rows)


def _regression(mechanisms: pd.DataFrame) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["horizon_seconds"].eq(300)
        & mechanisms["mechanism_share"].notna()
    ].copy()
    sample["concurrent_indicator"] = sample["concurrent_release"].fillna("").ne("").astype(int)
    model = smf.ols(
        "mechanism_share ~ C(representation_class) + C(instrument) + concurrent_indicator",
        data=sample,
    ).fit(cov_type="HC1")
    confidence = model.conf_int()
    return pd.DataFrame(
        {
            "term": model.params.index,
            "coefficient": model.params.values,
            "std_error_hc1": model.bse.values,
            "p_value": model.pvalues.values,
            "ci_95_low": confidence[0].values,
            "ci_95_high": confidence[1].values,
            "nobs": int(model.nobs),
            "r_squared": model.rsquared,
        }
    )


def _depth_test(timing: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for instrument, group in timing.loc[
        timing["dataset_condition"].eq("available")
    ].groupby("instrument"):
        ratios = group["pre60_to_baseline_depth_ratio"].dropna().to_numpy(float)
        p_value = np.nan
        if len(ratios) >= 3 and not np.allclose(ratios - 1, 0):
            p_value = float(wilcoxon(ratios - 1, alternative="less").pvalue)
        rows.append(
            {
                "instrument": instrument,
                "events": len(ratios),
                "mean_depth_ratio": np.mean(ratios),
                "median_depth_ratio": np.median(ratios),
                "fraction_below_one": np.mean(ratios < 1),
                "one_sided_wilcoxon_vs_one_p": p_value,
            }
        )
    return pd.DataFrame(rows)


def _representation_test(mechanisms: pd.DataFrame) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["horizon_seconds"].eq(300)
        & mechanisms["absolute_quote_fraction"].notna()
        & mechanisms["representation_class"].isin(
            ["scalar_numeric", "multi_dimensional_numeric"]
        )
    ]
    scalar = sample.loc[
        sample["representation_class"].eq("scalar_numeric"), "absolute_quote_fraction"
    ]
    multi = sample.loc[
        sample["representation_class"].eq("multi_dimensional_numeric"), "absolute_quote_fraction"
    ]
    test = mannwhitneyu(scalar, multi, alternative="greater")
    return pd.DataFrame(
        [
            {
                "scalar_n": len(scalar),
                "multi_dimensional_n": len(multi),
                "scalar_median_absolute_quote_fraction": scalar.median(),
                "multi_median_absolute_quote_fraction": multi.median(),
                "mann_whitney_u": test.statistic,
                "one_sided_p": test.pvalue,
            }
        ]
    )


def _figure(horizons: pd.DataFrame, output) -> None:
    sample = horizons.loc[horizons["horizon_seconds"].eq(60)].copy()
    sample["primary_type"] = sample["event_types"].str.split("|").str[0]
    order = ["employment_situation", "cpi", "ppi", "retail_sales"]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    for ax, instrument in zip(axes, INSTRUMENTS):
        panel = sample.loc[sample["instrument"].eq(instrument)]
        values = [
            panel.loc[panel["primary_type"].eq(event_type), "log_return_bp"].abs()
            for event_type in order
        ]
        ax.boxplot(values, tick_labels=["jobs", "CPI", "PPI", "retail"], patch_artist=True)
        ax.set_title(instrument.replace(".v.0", ""))
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    axes[0].set_ylabel("absolute 60-second midpoint return (bp)")
    fig.suptitle("Macro announcement response by release class and sample period")
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one or more processed macro samples")
    parser.add_argument("--samples", nargs="+", default=["macro_sample"])
    parser.add_argument("--output", default="macro_sample")
    args = parser.parse_args()
    roots = [PROJECT_ROOT / "data" / "processed" / name for name in args.samples]
    timing = pd.concat(
        [pd.read_parquet(root / "timing_liquidity.parquet") for root in roots],
        ignore_index=True,
    )
    horizons = pd.concat(
        [pd.read_parquet(root / "response_horizons.parquet") for root in roots],
        ignore_index=True,
    )
    intervals = pd.concat(
        [pd.read_parquet(root / "one_second_intervals.parquet") for root in roots],
        ignore_index=True,
    )
    root = PROJECT_ROOT / "data" / "processed" / args.output
    root.mkdir(parents=True, exist_ok=True)
    impacts = _impacts(intervals)
    mechanisms = _mechanisms(timing, horizons, impacts)
    products = {
        "impact_coefficients_loo": impacts,
        "mechanism_estimates_loo": mechanisms,
        "h1_summary_300s": _h1_summary(mechanisms),
        "mechanism_regression": _regression(mechanisms),
        "depth_withdrawal_test": _depth_test(timing),
        "representation_comparison": _representation_test(mechanisms),
    }
    for name, product in products.items():
        product.to_parquet(root / f"{name}.parquet", index=False)
        product.to_csv(root / f"{name}.csv", index=False)
    figure_dir = PROJECT_ROOT / "figures" / args.output
    figure_dir.mkdir(parents=True, exist_ok=True)
    _figure(horizons, figure_dir / "macro_response_by_type.png")
    print(
        f"Wrote {len(impacts)} impact fits and {len(mechanisms)} mechanism rows "
        f"from {len(args.samples)} processed sample(s), plus H1/representation/liquidity tests."
    )


if __name__ == "__main__":
    main()
