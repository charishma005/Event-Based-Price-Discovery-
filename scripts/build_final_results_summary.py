from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from src.utils.config import PROJECT_ROOT


def _fomc_quote_fraction_tests() -> pd.DataFrame:
    data = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "fomc_sample" / "mechanism_estimates_loo.parquet"
    )
    sample = data.loc[
        data["horizon_seconds"].eq(60)
        & data["quote_definition"].eq("first_valid_quote")
        & data["eligible_primary_q1"]
        & data["total_adjustment_bp"].abs().gt(0.1)
    ].copy()
    sample["absolute_quote_fraction"] = (
        sample["quote_revision_bp"].abs() / sample["total_adjustment_bp"].abs()
    )
    rows = []
    for subevent, group in sample.groupby("subevent"):
        centered = group["absolute_quote_fraction"].to_numpy(float) - 0.40
        rows.append(
            {
                "subevent": subevent,
                "observations": len(group),
                "median_absolute_quote_fraction": group["absolute_quote_fraction"].median(),
                "count_below_40pct": int(group["absolute_quote_fraction"].lt(0.40).sum()),
                "one_sided_wilcoxon_below_40pct_p": float(
                    wilcoxon(centered, alternative="less", method="auto").pvalue
                ),
            }
        )
    return pd.DataFrame(rows)


def _speed_tests() -> pd.DataFrame:
    speed = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "fomc_sample" / "speed_metrics.parquet"
    )
    rows = []
    for metric in (
        "first_crossing_50_seconds",
        "first_crossing_90_seconds",
        "stable_within_10pct_seconds",
    ):
        for instrument in sorted(speed["instrument"].unique()):
            wide = (
                speed.loc[speed["instrument"].eq(instrument)]
                .pivot(index="meeting", columns="subevent", values=metric)[
                    ["statement", "press_conference"]
                ]
                .dropna()
            )
            difference = (wide["statement"] - wide["press_conference"]).to_numpy(float)
            nonzero = difference[~np.isclose(difference, 0)]
            rows.append(
                {
                    "metric": metric,
                    "instrument": instrument,
                    "paired_meetings": len(difference),
                    "statement_median_seconds": wide["statement"].median(),
                    "press_median_seconds": wide["press_conference"].median(),
                    "statement_faster_count": int((nonzero < 0).sum()),
                    "one_sided_sign_p_statement_faster": float(
                        binomtest(
                            (nonzero < 0).sum(), len(nonzero), 0.5, alternative="greater"
                        ).pvalue
                    ),
                    "one_sided_wilcoxon_p_statement_faster": float(
                        wilcoxon(nonzero, alternative="less", method="auto").pvalue
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    tables = PROJECT_ROOT / "tables"
    reports = PROJECT_ROOT / "reports"
    tables.mkdir(parents=True, exist_ok=True)
    quote = _fomc_quote_fraction_tests()
    speed = _speed_tests()
    quote.to_csv(tables / "fomc_h2_quote_fraction.csv", index=False)
    quote.to_latex(
        tables / "fomc_h2_quote_fraction.tex", index=False, float_format="%.6f"
    )
    speed.to_csv(tables / "fomc_speed_inference.csv", index=False)
    speed.to_latex(
        tables / "fomc_speed_inference.tex", index=False, float_format="%.6f"
    )

    hypothesis = pd.DataFrame(
        [
            ["H1", "Rejected", "Scalar first-quote share is not above 70%", "ES/NQ/ZN opposite-direction p < 4.8e-7"],
            ["H2", "Supported in sample", "Narrative first-quote share is below 40%", "12-meeting: statement p=4.2e-6, press p=3.5e-7; 93-meeting (2015-2026): statement p=2.40e-32, press p=1.80e-34"],
            ["H3", "Not identified", "Needs vintage forecast dispersion", "Unavailable from current providers"],
            ["H4", "Partly supported", "Withdrawal occurs before scheduled events", "FOMC (12-meeting) p=0.00024; 93-meeting (2015-2026) statement p=4.07e-17, press p=2.72e-8; macro p=1.9e-6; unscheduled also p=0.031"],
            ["H5", "Not supported", "FOMC statement horizons shorten, not lengthen, with |surprise|", "12-meeting STMT meeting-average rho=-0.79, p=0.002; 93-meeting (2015-2026) STMT rho=-0.284, p=0.0061; press mixed in both"],
            ["H6", "Not supported", "12-meeting ES/NQ press asymmetry does not replicate at 93 meetings", "12-meeting: ES p=0.003, NQ p=0.012; 93-meeting (2015-2026): ES p=0.75, NQ p=0.52, ZN p=0.32; only ZN stable-within-10% cell significant (p=0.0104)"],
        ],
        columns=["hypothesis", "status", "finding", "evidence"],
    )
    questions = pd.DataFrame(
        [
            ["Q1", "Completed", "Exchange-time quote/flow/residual decomposition with explicit eligibility flags"],
            ["Q2", "Completed descriptively", "Crossing, stable-band, and overshoot metrics; paired speed tests"],
            ["Q3", "Completed descriptively", "100 ms timing and first-material-move tests; no structural information share"],
            ["Q4", "Completed with caveat", "Touch and selected MBP-10 depth plus scheduled and corporate placebos"],
            ["Q5", "Partly answered", "FOMC only, via USMPD policy surprises; macro needs vintage consensus"],
        ],
        columns=["question", "status", "evidence"],
    )
    hypothesis.to_csv(tables / "hypothesis_status.csv", index=False)
    hypothesis.to_latex(tables / "hypothesis_status.tex", index=False)
    questions.to_csv(tables / "proposal_question_status.csv", index=False)
    questions.to_latex(tables / "proposal_question_status.tex", index=False)

    report = """# Submission readiness

## Bottom line

The project is ready to submit as a serious empirical research draft, provided it is described as a twenty-month message-level study rather than the proposal's full five-to-ten-year implementation. Q1 is implemented directly; Q2-Q4 have credible descriptive or matched-control evidence; H3 remains unidentified because Databento and Alpha Vantage do not contain vintage consensus distributions; H5 and H6 are tested for FOMC meetings with USMPD policy surprises (H5 not supported, H6 not supported). A 93-meeting (2015-2026) FOMC extension confirms H2 and H4 at scale and shows the original 12-meeting H6 asymmetry does not replicate.

## Strong findings

- H1 is rejected under the proposal's literal first-quote definition. The quote fraction is near zero, not above 70%.
- H2 is supported in the current FOMC sample and strengthens under the 93-meeting (2015-2026) extension (statement p=2.40e-32, press p=1.80e-34).
- Scheduled depth withdrawal is highly significant in independent FOMC and macro samples, and holds at 93 meetings (statement p=4.07e-17, press p=2.72e-8).
- Written statements reach 50% of their five-minute move faster than press openings by paired Wilcoxon tests in ES, NQ, and ZN.

## Important qualifications

- The stable-within-10% speed measure is not significant; early crossings include overshoot and reversal.
- Five selected nominally unscheduled events also show lower pre-event depth than controls. Withdrawal is robust, but scheduled-event specificity is not established.
- The flow component is predictive rather than structural and leaves a material residual.
- Q3 is a cross-asset timing result, not a Hasbrouck information share.

## Remaining work for a full proposal execution

1. License vintage consensus and dispersion data for H3 and for macro-release versions of H5, H6, and Q5.
2. Extend the sample toward five to ten years if the professor expects the originally proposed horizon.
3. Expand corporate news using a random or pre-declared sampling rule with multiple controls per event.
4. Add more MBP-10 windows if deeper-book population claims are required.

These are extensions and identification inputs, not missing basic pipeline work.
"""
    (reports / "submission_readiness.md").write_text(report, encoding="utf-8")
    print(f"Wrote final status tables, {len(speed)} speed tests, and {reports / 'submission_readiness.md'}")


if __name__ == "__main__":
    main()
