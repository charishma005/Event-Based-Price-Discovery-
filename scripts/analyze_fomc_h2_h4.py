"""H2 and H4 on a processed FOMC sample.

H2: narrative communication relies on order flow; the absolute first-quote share
of the 60-second move is below 40%. Same filters as
``build_final_results_summary.py``.

H4: displayed touch depth falls in the final 60 seconds before a scheduled
arrival. This is the within-event test from ``analyze_macro_sample_full.py``
(final-minute depth / prior four-minute mean, Wilcoxon against 1). The paper's
matched-control FOMC comparison needs placebo windows, which exist only for
2024-2025.

Inputs, from process_fomc_sample.py and analyze_fomc_sample.py:
- data/processed/<root>/mechanism_estimates_loo.parquet
- data/processed/<root>/timing_liquidity.parquet
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from src.utils.config import PROJECT_ROOT


def _h2_quote_fraction(mechanisms: pd.DataFrame) -> pd.DataFrame:
    sample = mechanisms.loc[
        mechanisms["horizon_seconds"].eq(60)
        & mechanisms["quote_definition"].eq("first_valid_quote")
        & mechanisms["eligible_primary_q1"]
        & mechanisms["total_adjustment_bp"].abs().gt(0.1)
    ].copy()
    sample["absolute_quote_fraction"] = (
        sample["quote_revision_bp"].abs() / sample["total_adjustment_bp"].abs()
    )
    rows = []
    for (subevent, instrument), group in pd.concat(
        [sample, sample.assign(instrument="pooled")]
    ).groupby(["subevent", "instrument"]):
        centered = group["absolute_quote_fraction"].to_numpy(float) - 0.40
        rows.append(
            {
                "subevent": subevent,
                "instrument": instrument,
                "observations": len(group),
                "meetings": group["meeting"].nunique(),
                "median_absolute_quote_fraction": group["absolute_quote_fraction"].median(),
                "count_below_40pct": int(group["absolute_quote_fraction"].lt(0.40).sum()),
                "one_sided_wilcoxon_below_40pct_p": float(
                    wilcoxon(centered, alternative="less", method="auto").pvalue
                ),
            }
        )
    return pd.DataFrame(rows)


def _h4_depth(timing: pd.DataFrame) -> pd.DataFrame:
    available = timing.loc[timing["dataset_condition"].eq("available")]
    cluster = (
        available.groupby(["meeting", "subevent"], as_index=False)["pre60_to_baseline_depth_ratio"]
        .mean()
        .assign(instrument="meeting_cluster_average")
    )
    rows = []
    for (subevent, instrument), group in pd.concat([available, cluster]).groupby(
        ["subevent", "instrument"]
    ):
        ratios = group["pre60_to_baseline_depth_ratio"].dropna().to_numpy(float)
        p_value = sign_p = np.nan
        if len(ratios) >= 3 and not np.allclose(ratios - 1, 0):
            p_value = float(wilcoxon(ratios - 1, alternative="less").pvalue)
            nonzero = ratios[~np.isclose(ratios, 1)]
            sign_p = float(binomtest((nonzero < 1).sum(), len(nonzero), 0.5, alternative="greater").pvalue)
        rows.append(
            {
                "subevent": subevent,
                "instrument": instrument,
                "events": len(ratios),
                "mean_depth_ratio": np.mean(ratios),
                "median_depth_ratio": np.median(ratios),
                "fraction_below_one": np.mean(ratios < 1),
                "one_sided_sign_p": sign_p,
                "one_sided_wilcoxon_vs_one_p": p_value,
            }
        )
    return pd.DataFrame(rows)


def _write(frame: pd.DataFrame, name: str) -> None:
    tables = PROJECT_ROOT / "tables"
    frame.to_csv(tables / f"{name}.csv", index=False)
    frame.to_latex(tables / f"{name}.tex", index=False, float_format="%.6f")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test H2/H4 on a processed FOMC sample")
    parser.add_argument("--config", default="fomc_sample.yaml", help="File under config/")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    parser.add_argument("--suffix", help="Appended to table names (default: config name after fomc_sample)")
    args = parser.parse_args()
    stem = args.config.removesuffix(".yaml")
    root = PROJECT_ROOT / "data" / "processed" / (args.root or stem)
    suffix = args.suffix if args.suffix is not None else stem.removeprefix("fomc_sample")

    (PROJECT_ROOT / "tables").mkdir(parents=True, exist_ok=True)
    h2 = _h2_quote_fraction(pd.read_parquet(root / "mechanism_estimates_loo.parquet"))
    h4 = _h4_depth(pd.read_parquet(root / "timing_liquidity.parquet"))
    _write(h2, f"fomc_h2_quote_fraction{suffix}")
    _write(h4, f"fomc_h4_depth_withdrawal{suffix}")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print("H2 (60s first-quote share below 40%):")
        print(h2.to_string(index=False))
        print("\nH4 (final-minute / prior four-minute touch depth below 1):")
        print(h4.to_string(index=False))


if __name__ == "__main__":
    main()
