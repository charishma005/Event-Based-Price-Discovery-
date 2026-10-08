# The latency-conditioned macro-surprise trade: results

Written 2026-10-07 after running `scripts/backtest_latency_strategy.py` once. The rules were
fixed in `reports/strategy_latency_preregistration.md` before the run. Every number below comes
from `tables/strategy_latency_*.csv` or `tables/strategy_latency_trades.parquet`.

## Verdict in two sentences

The pre-declared test (ZN, enter one second after the 8:30 clock, exit at five minutes, direction
from the Bloomberg headline surprise) passes its own threshold with a mean net return of 10.0 bp
per trade and t = 8.0 over 2015-2023, but it is not a tradable edge: the market's own move starts
on median 1.3 s after the clock, so "one second of latency" measured from the clock is zero
latency measured from the information. Measured from the arrival instead, about 5 bp per trade
net of one spread survives in ES and NQ over 2015 to August 2025, almost all of it from CPI
releases in 2020-2023, and nothing survives in the forward sample from September 2025.

## 1. The pre-declared primary, as declared

| Item | Value |
| --- | --- |
| Trades (ZN, 2015-2023, nonzero surprise) | 281 |
| Mean net return per trade | 10.0 bp |
| t-statistic | 8.0 |
| Hit rate | 67% |
| Development sample (2024 to Aug 2025, 74 trades) | 19.3 bp |
| Net at L = 500 ms / 2 s | 10.2 bp / 1.8 bp |
| Years with a positive mean, 2015-2023 | 9 of 9 |
| Placebo on matched control days (81 trades) | -1.5 bp, t = -3.5 (net); -0.3 bp, t = -0.7 (gross) |

Threshold met, latency and year gates met, placebo gate failed as written. Two parts of the
pre-declaration were mis-specified and I record them here rather than editing the frozen file.
First, the pseudo clock two minutes before the release cannot serve as a placebo for a 300 s exit
because its window contains the release; the matched control days (same clock, no release) replace
it. Second, the placebo gate was written on the net return, which is reliably negative by the size
of the spread on days with nothing to trade, so it fails for a mechanical reason. On the gross return
the control days are flat in every instrument (|t| < 1.2). The pre-declared verdict is therefore
"not supported as declared", and the reason is my specification, not the data.

## 2. Why the clock-anchored number is not an edge

The move after the clock is almost entirely between one and two seconds. The median share of the
five-minute ZN move that is done at 1 s is zero in every year 2015-2026; at 2 s it is between 0.37 and
0.75 (except 2020). The start of the largest 100 ms burst in the first ten seconds
(`arr_burst_seconds`) has median 1.3 s, interquartile range 1.05 to 3.05 s, and the medians by year
are 1.0 to 1.5 s for ES and ZN in every year except 2015 and 2020. On the raw ticks for the
2 February 2024 payrolls, ES trades at 6 ms after 13:30:00 UTC but the ZN sweep through eight price
levels comes at 1070 ms. I read the ~1 s gap as the time the data take to reach the market after the
exchange clock reads 8:30:00; whether the cause is the release mechanism or a clock offset is still
open (pinned timing item in TODO.md). Either way, a trader who learns the surprise at the same
moment as everyone else is at L = 0 on the arrival anchor, not at L = 1 s on the clock.

## 3. The arrival-anchored trade (post-hoc, labelled as such)

Entry at the mid L after the burst start, exit at 300 s, one full spread of cost. Mean net bp per
trade, surprise direction (`tables/strategy_latency_arrival.csv`):

| Instrument | Sample | n at 100 ms | 0 ms | 100 ms | 1 s | t at 100 ms |
| --- | --- | --- | --- | --- | --- | --- |
| ES | 2015-2023 | 245 | 7.4 | 5.3 | 5.0 | 2.2 |
| ES | 2024-Aug 2025 | 62 | 11.7 | 5.6 | 6.9 | 1.7 |
| ES | Sep 2025-2026 | 27 | 5.4 | 0.0 | -1.0 | 0.0 |
| NQ | 2015-2023 | 245 | 8.2 | 5.4 | 5.1 | 1.9 |
| NQ | 2024-Aug 2025 | 62 | 13.3 | 4.8 | 5.0 | 1.1 |
| NQ | Sep 2025-2026 | 27 | 4.2 | -1.2 | -3.0 | -0.3 |
| ZN | 2015-2023 | 281 | 6.0 | 1.2 | 1.1 | 1.3 |
| ZN | 2024-Aug 2025 | 74 | 17.8 | 4.7 | 2.2 | 1.8 |
| ZN | Sep 2025-2026 | 27 | 7.5 | -0.3 | -0.7 | -0.1 |
| all three | control days | 102-111 | -1.3 | -1.2 | -1.2 | about -2 to -4 (cost only) |

The 0 ms column is the mid after the burst's first update, which nobody gets; from 100 ms on the
curve is flat, so the edge is not a race, it is a slow drift over the remaining five minutes.
Equal-weighting the three contracts per release day gives a mean of 3.6 bp per day (t = 2.2,
32 days a year, annualised Sharpe about 0.7) in 2015-2023, 5.0 bp (t = 2.0, Sharpe about 1.6) in
2024-Aug 2025, and -0.5 bp (t = -0.2) over the 27 release days since September 2025.

The momentum direction (sign of the move up to entry, no survey needed) gives 5 to 6 bp in NQ
over 2015-2023 (t about 2.5), 2 to 3 bp in ES, nothing in ZN, and is negative in the forward sample
everywhere. On FOMC statements the momentum rule earns nothing significant (|t| < 1.7 in every
cell). The control-day momentum placebo is flat, so selecting the largest burst does not by itself
create a continuation bias.

## 4. Where the edge actually is

`tables/strategy_latency_arrival_robustness.csv`, surprise direction, 100 ms after the arrival:

| Cut | ES | NQ | ZN |
| --- | --- | --- | --- |
| 2015-2023 without 2022 | 0.8 bp (t 0.6) | -0.6 (t -0.4) | 0.1 (t 0.1) |
| 2022 alone (32 releases) | 35.3 (t 2.3) | 45.0 (t 2.6) | 9.5 (t 2.4) |
| CPI only, 2015-2023 (72-84) | 21.1 (t 3.1) | 28.4 (t 3.8) | 3.8 (t 2.4) |
| CPI only, 2024-Aug 2025 (17) | 15.1 (t 1.9) | 16.1 (t 1.7) | 1.7 (t 0.3) |
| CPI only, Sep 2025-2026 (8) | 0.8 (t 0.1) | 4.4 (t 0.5) | -2.7 (t -0.8) |
| Payrolls, PPI, retail, 2015-2023 | -1.2 (t -0.7) | -4.2 (t -1.9) | 0.1 (t 0.1) |

The honest description is "CPI releases during the 2020-2023 inflation regime kept drifting in the
direction of the surprise for five minutes after the first second, and equities carried the drift".
Outside CPI the five-minute move is complete within a second of the arrival, net of costs. The learned
equity direction is stable and sensible: on CPI the equity trade is always against the surprise
(higher inflation, sell), on payrolls always with it, on PPI it flips during 2020-2023. Larger
surprises pay more in ZN (3.7 bp against 0.6 bp, split at the median absolute surprise within type)
but not in ES or NQ.

## 5. What this says for the research

The result is the trading-side reading of H1 and H2: the first second after the clock carries
nothing, the burst carries most of the move, and after the burst the market is close to efficient at
the five-minute horizon except for CPI in a regime where inflation was the only number that
mattered. That regime dependence is the point worth a paragraph in the paper, not the Sharpe ratio.

## Limitations

- Fills are at the mid; real entry would cross the spread (charged) and might move the price
  (not charged). With 2 to 25 contracts at the touch before releases, size would be small.
- The arrival anchor is identified ex post (largest burst in ten seconds), but the control-day
  placebo shows the selection itself does not generate the return, and the curve is flat after 100 ms.
- The forward sample has 27 release days; its flat result is informative but not decisive.
- 2024-2025 data for ES/NQ/ZN on this machine cover event windows only, so nothing here is a
  continuous backtest; all horizons stop at 300 s because that is where `events.parquet` stops.
