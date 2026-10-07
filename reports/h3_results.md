# H3 result: forecast dispersion and the quote-revision share

Pre-declared in `reports/h3_preregistration.md` and `config/h3_prereg.yaml`
(frozen 2026-10-07 07:01 UTC, commit `8bcf099`), run once afterwards with
`python -m scripts.analyze_h3_dispersion`. Tables: `tables/h3_primary.csv`,
`h3_secondary.csv`, `h3_robustness.csv`, `h3_sample.csv`. Figure:
`figures/h3/h3_s_vs_dispersion.png`.

## Verdict: rejected under the pre-declared rule

H3 predicted that the quote-revision share S falls when economists disagree
more before a release. It does not. Across 425 release mornings (134 CPI, 135
PPI, 139 jobs reports, 17 retail sales) and 1,255 morning-contract rows, one
standard deviation more disagreement goes with a change in S of +0.033
(standard error 0.022, p = 0.13, 95% interval -0.009 to +0.075). The interval
excludes the smallest effect the pre-declaration said would matter, -0.05, so
the rule reads "rejected: no effect of at least 0.05 per standard deviation of
dispersion". The point estimate has the opposite sign to the hypothesis.

| Run | beta | se | p | 95% interval |
|---|---|---|---|---|
| Primary (release, contract and period effects) | +0.033 | 0.022 | 0.13 | -0.009, +0.075 |
| Placebo: same regression on the pseudo-clock S | +0.006 | 0.018 | 0.75 | -0.030, +0.042 |
| No period effects | +0.032 | 0.021 | 0.14 | -0.010, +0.074 |
| Year effects | +0.024 | 0.022 | 0.27 | -0.019, +0.066 |

The placebo is flat, as it should be. The surprise control behaves as in step
1: larger scaled surprises go with lower S (not shown in the table; the
coefficient is in the fitted model, not pre-declared as a result).

## Secondary family (Holm-adjusted; nothing survives)

| Test | beta | p | Holm p |
|---|---|---|---|
| CPI | +0.053 | 0.16 | 1.00 |
| PPI | +0.054 | 0.15 | 1.00 |
| Jobs report | -0.009 | 0.78 | 1.00 |
| Retail sales (17 mornings) | +0.334 | 0.36 | 1.00 |
| Composite dispersion, all surveyed series | +0.035 | 0.11 | 0.88 |
| CPI headline-only dispersion | +0.025 | 0.21 | 1.00 |
| CPI core-only dispersion | +0.035 | 0.09 | 0.84 |
| Within-day outcome, S minus pseudo-clock S | +0.035 | 0.36 | 1.00 |
| Speed: seconds to half of the 5-minute move | -2.8 s | 0.17 | 1.00 |

The speed outcome also has the wrong sign for the proposal's Q2 reading (more
disagreement, faster, not slower), and is not significant.

## Robustness (the primary beta under a changed sample or definition)

Every run keeps a positive point estimate; none is negative. Log range in
place of the z-score gives +0.007 (p = 0.83); range divided by d2(n) gives
+0.031; dropping March to July 2020 gives +0.053 (p = 0.07); dropping
outlier-driven ranges +0.033; dropping concurrent-release mornings +0.037; no
winsorization +0.039; arrival moves of at least 2 bp +0.025. By contract: ES
+0.024 (p = 0.58), ZN +0.007 (p = 0.74), NQ +0.068 (p = 0.004, unadjusted). NQ
is again the contract with room for S to move, as in step 1.

## Reading

Disagreement among forecasters does not make a release more trade-driven. If
anything the high-dispersion CPI and PPI releases are slightly more
quote-driven, and the one contract where that is significant on its own, NQ,
is the one whose spread leaves S free to vary. The proposal's mechanism, that
people who disagree beforehand must trade to learn what the number means, is
not visible at the arrival.

## Limitations seen after the run

- **Payroll dispersion has almost no variation outside 2020.** The z-score
  divides by the full-sample standard deviation of the range, and the 2020
  ranges (thousands, against a normal 100 to 200) set that scale. In every
  other period the payroll z-dispersion has a standard deviation of about 0.02
  (`tables/h3_sample.csv`), so the jobs-report slope is identified almost
  entirely by 2020. The log-range run, which does not have this problem, gives
  +0.007. **Post-freeze addition (logged in the YAML):** standardizing the range
  by its series median and MAD instead of mean and standard deviation, capped at
  plus or minus 5, gives the payroll measure a standard deviation of 0.6 to 0.8
  in every period. The primary coefficient on that measure is +0.015 (se 0.011,
  p = 0.19, interval -0.007 to +0.036), still positive and further from -0.05.
- **CPI ranges are quantized to 0.1**, so the dispersion variable takes a
  handful of values. The forecast standard deviation from ECOS, being pulled
  separately, will be used as a calibration check and a further robustness run
  and will be logged in the YAML's `post_freeze_log`.
- **No held-out sample.** The whole 2015-2026 period was used in one pass, as
  pre-declared, so this is a single test rather than a replication.
