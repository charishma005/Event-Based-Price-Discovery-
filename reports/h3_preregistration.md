# Pre-declared test of H3: forecast dispersion and the quote-revision share

Written before any survey figure was related to S. The machine-readable
version, with the freeze time and hashes, is `config/h3_prereg.yaml`. This is an
internal pre-declaration, like the step 1 measure, not an external
preregistration.

## Hypothesis

Across scheduled macro releases, the quote-revision share S at the arrival is
lower when economists disagreed more before the release, holding the size of the
surprise fixed. This is the proposal's H3 ("the order-flow share rises in ex-ante
forecast dispersion") restated on the measure the project now uses, where a
lower S means more of the move came through trades.

The decision rests on one number: the coefficient on dispersion in the primary
regression.

| Outcome | Reading |
|---|---|
| Coefficient below zero, p below 0.05, negative point estimate in both fixed-effect variants | Supported |
| 95% interval excludes -0.05 | Rejected: no effect large enough to matter |
| Neither | Inconclusive: underpowered, not evidence either way |

Why -0.05 is the smallest effect worth claiming: CPI and PPI arrivals sit about
0.18 below the no-news level of 0.5 (median S 0.32 in 2015-2023). A dispersion
effect smaller than a quarter of that gap would not change how the mechanism is
described.

## Data

| Input | File | Supplies |
|---|---|---|
| Outcome and controls | `data/processed/tick_features/events.parquet` | S, the pseudo-clock S, arrival move, pre-event spread, eligibility |
| Event list | `data/events/event_registry.csv` | Release date, type, sample, concurrent-release flag, vendor condition |
| Survey | `data/raw/bloomberg/bbg_eco.xlsx` (local, git-ignored) | Survey median, average, high, low, forecaster count, first-release actual |

The join key is the release date. Coverage checked on 6 October 2026: 138 of 140
CPI, 139 of 140 PPI, 139 of 140 jobs-report and 20 of 20 retail-sales mornings
have survey and actual. The misses are the three January 2015 releases (before
the pull window) and CPI on 18 December 2025 (no Bloomberg rows for the October
and November 2025 prints).

## Measures

**Outcome.** S exactly as pre-declared for step 1 (`share_burst100`): the
quote-attributed share of the midpoint move in the 100 ms from the arrival
anchor. Winsorized to [-1, 2], as in the step 1 regression. One row per release
morning and contract (ES, NQ, ZN).

**Headline series per release.** CPI: headline and core MoM, averaged. PPI:
final demand MoM. Jobs report: nonfarm payrolls. Retail sales: advance MoM.

**Dispersion.** Bloomberg returned no standard deviation, so dispersion is the
survey range, high minus low, standardized within series over 2015-2026 so one
unit is one standard deviation of disagreement for that series. For CPI the
headline and core z-dispersions are averaged; the two ranges correlate at 0.52,
so entering them separately would leave each coefficient imprecise while their
combination is not. The log of the number of forecasters enters as a control,
because a range widens mechanically with more forecasters (for normal draws the
expected range grows about linearly in log n over 20 to 100 forecasters).

**Surprise.** Actual as first released minus survey median, divided by 1.4826
times the median absolute surprise of that series. A plain standard deviation
would be set by the 2020 payroll prints (871 thousand against a typical surprise
of tens of thousands). The regression uses the absolute value, winsorized at 5,
averaged across the release's headline series.

**Placebo.** The same share two minutes before the release. Dispersion should
not predict it.

**What the survey data looks like.** Forecasts are not normal: CPI forecasts are
rounded to 0.1, so ranges take values like 0.2, 0.3, 0.4; payroll, unemployment
and retail surprises have heavy tails driven by 2020, and their ranges correlate
at 0.65 to 0.76 with the gap between survey average and median, the signature of
a single stray forecast. The robust surprise scale and the outlier robustness run
below are there for that reason. The forecast standard deviation from ECOS, to be
pulled after the freeze, will be used as a calibration check and an extra
robustness run, not as a replacement for the primary.

## Sample

All CPI, PPI, jobs-report and retail-sales mornings from January 2015 to
September 2026, the step 1 development and out-of-sample periods together. There
is no held-out period: S was frozen in step 1 and the survey data has not been
related to it. Rows must pass the step 1 eligibility flag and have S defined.
Dropped: the three same-clock bundles, the four mornings without survey data, and
vendor-degraded days. Mornings with a concurrent release (another release flagged at the clock,
such as jobless claims, import prices or trade; Real Earnings accompanies every
CPI and does not count) stay in the primary and are dropped in a robustness run. Expected size: about 430 mornings, roughly
1,100 to 1,250 morning-contract rows.

## Primary test

OLS on morning-contract rows, standard errors clustered by release day:

S = beta D + gamma |u| + delta log n + release-type effects + contract effects + period effects

with D the z-dispersion, |u| the absolute scaled surprise, n the forecaster
count, and periods 2015-17, 2018-19, 2020-21, 2022-23, 2024-26.

- Decisive quantity: beta with its 95% interval, read against the table above.
- Support also needs a negative point estimate with no period effects and with
  year effects in place of period effects.
- One primary coefficient, no multiplicity adjustment. Everything below is
  Holm-adjusted within its family and cannot rescue a failed primary.
- Placebo: the same regression with the pseudo-clock S as outcome.

Period effects rather than year effects: disagreement moves slowly within a
series, so most of its variation is across regimes (2020, the 2021-23 inflation).
Year effects would discard nearly all of it and leave month-to-month noise in a
range quantized to 0.1 for CPI. Period effects keep regime variation while
absorbing the slow drift in S seen in step 1. Both alternatives are reported.

## Secondary family (Holm-adjusted, reported, not decisive)

1. Beta by release type, four slopes from one interacted regression.
2. Composite dispersion: the mean of z-dispersion over every surveyed series in
   the release (CPI headline and core; PPI final demand and ex food and energy;
   payrolls, unemployment rate and hourly earnings; retail headline and ex autos).
3. CPI headline-only and CPI core-only dispersion, two separate runs.
4. Within-day outcome: S at the announcement minus S at the pseudo clock.
5. Speed outcome: seconds to half of the five-minute move (`fp300s_50_seconds`),
   prediction positive.

## Robustness runs (the primary beta under a changed sample or definition)

No period effects; year effects; log range in place of z-dispersion; range
divided by d2(n), the expected range of n standard normal draws, without the
log n control; drop March to July 2020; drop releases whose range looks driven
by one stray forecaster (survey average minus median above a tenth of the
range); drop mornings with a concurrent release; one contract at a time; no
winsorization of S; drop arrival moves under 2 bp.

## What was looked at before the freeze

- The workbook's coverage, field completeness and forecaster counts, and its
  match to the registry (6 October).
- The distribution of the high-low range for CPI, PPI and payrolls and its
  correlation with the absolute surprise; the headline-core CPI range
  correlation (6 October).
- The shape of the surprise distribution for six series and the gap between
  survey average and median (7 October).
- S by event class, pseudo clock and control day, and the step 1 regression of
  S on class, spread and move size.

Nothing relating dispersion or the surprise to S had been computed. The survey
data had not been merged onto `events.parquet`.

## Freeze

`scripts/freeze_h3_preregistration.py` marks the YAML frozen and records the
SHA-256 of the survey workbook, `events.parquet`, the registry,
`scripts/build_bloomberg_surveys.py` and `scripts/analyze_h3_dispersion.py`,
with the time. The analysis script refuses to run unless the YAML is frozen and
every hash still matches. Anything changed afterwards is dated in the YAML's
`post_freeze_log`. The workbook stays local; the parser, the analysis script,
this document and the result tables are tracked.
