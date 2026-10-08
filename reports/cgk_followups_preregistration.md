# Pre-declaration: two CGK (2018) follow-ups

Written 2026-10-07 before `scripts/analyze_cgk_followups.py` was run. Internal pre-declaration.
Both are descriptive tests, not strategies; the thresholds are fixed so the verdict is mechanical.

## Test A: the pre-release second

CGK find a 0.6 bp move in the surprise direction in the half second before the release in SPY
(2008-2014) and do not explain it. Question: on our macro mornings, does the mid move in the
direction of the news before the clock?

- Data: `fine.parquet` (20 ms grid), the mid from -1.00 s to -0.02 s before the clock (the -0.02 s
  point is the last grid state strictly before the release second), macro releases 2015-2026 and
  their matched control mornings; the Bloomberg headline surprise as in the latency backtest.
- Primary measure: signed pre-release return in bp, ZN, direction = -sign(surprise), all releases
  with a nonzero surprise. Mean and plain t-statistic over 2015-2026, and by year.
- Secondary: the same for ES and NQ with the direction learned per release type on an expanding
  window (as in the latency backtest); the same windows signed by the realized five-minute
  direction (sign of `w300s_total_bp`, which starts at the clock so it does not overlap the
  pre-release second) for all three contracts; and that realized-direction version on the control
  mornings, which calibrates any microstructure artifact. Splits: before and after March 2020,
  when the BLS removed computers from the lockup; -0.50 to -0.02 s as a shorter window.
- Threshold for "there is a pre-release move": primary mean > 0 with t >= 2, and the control-morning
  realized-direction version smaller than the live realized-direction version by at least the
  primary mean. Otherwise the answer is no.

## Test B: post-burst drift and the state of the book

CGK's Table 7 finds the rent is smaller when makers are fast before the release. Our hollow-book
question is the mirror image: is the drift after the burst larger when the book was thin?

- Data: the arrival-anchored trades of the latency backtest (`tables/strategy_latency_trades.parquet`,
  surprise direction, 100 ms after the burst, exit at 300 s, net of one spread), joined to
  `events.parquet` for `pre1_depth_ratio` (touch depth in the last second over the baseline) and to
  `seconds.parquet` for the pre-event quote-to-trade ratio (book updates per trade from -60 s to -1 s
  before the clock).
- Primary measure: mean net drift in the lowest tercile of `pre1_depth_ratio` minus the highest,
  terciles formed within contract over all releases 2015-2026, pooled across the three contracts by
  averaging per release morning, with a two-sample t-statistic on the morning-level series.
- Secondary: the same split on the quote-to-trade ratio (CGK's direction: low ratio, more drift);
  per contract; by period (2015-2019, 2020-2023, 2024-2026); gross as well as net.
- Threshold: primary difference > 0 with t >= 2, and the quote-to-trade split with the same sign.
  Otherwise the drift does not depend on the book state as measured, and the hollow-book question
  is closed on this evidence.
