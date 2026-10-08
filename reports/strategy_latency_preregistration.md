# Pre-declaration: the latency-conditioned macro-surprise trade

Written 2026-10-07 on branch `strategy-latency` from `main` at `9764365`, before
`scripts/backtest_latency_strategy.py` was run. Internal pre-declaration, not an
external preregistration. Nothing below was tuned on any sample.

## Idea in one sentence

Step 1 found that the first post-release quote carries none of the five-minute
move and that ES reacts 1.1 to 2.0 seconds after the 8:30 clock in 2015-2019.
If that is right, a trader who learns the headline surprise with latency L and
trades its sign should still capture part of the move for L of about one second,
and the edge should decay with L. The strategy is the trading-side reading of H1.

## Hypothesis

After a scheduled macro release (employment situation, CPI, PPI, retail sales),
selling ZN on a positive headline surprise and buying it on a negative one,
entering L = 1 s after the release clock and exiting at the 300 s mark, earns a
positive mean return net of crossing the spread, because price discovery is not
complete one second after the clock.

## Data

- `data/processed/tick_features/events.parquet`, rows with `family == "macro"`
  and the matching `macro_pseudo` rows (pseudo clock two minutes before the release).
- `data/processed/bloomberg_surveys.parquet` for the surprise: `actual_release`
  minus `survey_median` of the headline series, joined on release date.
  Headline series: employment `NFP TCH Index`; CPI `CPI CHNG Index`, falling back to
  `CPUPXCHG Index` when the headline surprise is exactly zero; PPI `FDIDFDMO Index`;
  retail sales `RSTAMOM Index`. Mixed bundles use the first listed type.
- Releases with a zero (or missing) surprise are not traded.
- USMPD surprises are not used as a signal: `STMT` is computed from the futures
  move in the same window, so it is not known at the time of the trade.

## Trade mechanics (fixed)

- Direction for ZN: d = -sign(surprise) for every release type (stronger activity
  or higher inflation lowers Treasury prices).
- Entry at the mid at the fixed clock t0 + L, exit at the mid at t0 + 300 s.
  Gross return in bp = d * (`w300s_total_bp` - `wL_total_bp`).
- Cost: one full spread per round trip in bp, half at entry using the time-weighted
  spread over 0-5 s (`post5_spread_ticks`, or `post60_spread_ticks` when L > 5 s),
  half at exit using the spread over 60-300 s (`post60_300_spread_ticks`), times the
  tick size (ES 0.25, NQ 0.25, ZN 1/64) over the pre-event price.
- Latency grid for the decay curve: 50 ms, 100 ms, 250 ms, 500 ms, 1 s, 2 s, 5 s,
  10 s, 30 s, 60 s.

## Primary metric

Mean net return per trade in bp for ZN at L = 1 s over the `oos_backward` sample
(releases from 2015 to 2023), with a plain t-statistic (one trade per release day,
so no clustering is needed for a single instrument).

## Success threshold

Mean net return > 0 with t >= 2 on the primary metric, and a positive mean net return
on the `development` sample (2024 to August 2025) as well. The baseline is not
trading (zero).

## Robustness gate (all must hold for the result to be called supported)

1. Mean net return positive at L = 500 ms and at L = 2 s on `oos_backward`.
2. Positive mean net return in at least six of the nine years 2015 to 2023.
3. Placebo: the same rule applied at the pseudo clock two minutes before the release
   (same surprise sign, same horizons) has |t| < 2.

## Kill criterion

Mean net return at L = 1 s on `oos_backward` is <= 0, or the pseudo-clock placebo is
as large as the live estimate. Then the idea goes to the rejected list and is not
retried with a different horizon, cost or instrument on the same sample.

## Secondary (reported, cannot rescue the primary)

- ES and NQ with the direction learned on an expanding window: the sign of the
  correlation between the surprise and the 300 s return over all earlier releases
  of the same type, requiring at least twelve earlier releases. No trade before that.
- Momentum variant needing no survey: d = sign of the move over the first L, applied
  to macro releases and to FOMC statements (every instrument). Exit at 300 s.
- The whole latency decay curve per instrument, by period (2015-2019, 2020-2023,
  2024-2026).
