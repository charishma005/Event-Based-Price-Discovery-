# Pre-declaration: the burst-trigger trend trade, own-asset and ES-ZN cross

Written 2026-10-07 on branch `strategy-latency`, before `scripts/backtest_trigger_strategy.py`
was run. Internal pre-declaration. Choices below were agreed with Giancarlo in conversation and
nothing was tuned on any sample. Supersedes the latency version for the trading question; that
one stays as the diagnostic that motivated this (its ex-post burst anchor is replaced by a
real-time trigger).

## Idea in one sentence

A trend follower at ultra-high frequency enters whenever the mid has just moved unusually far on
unusually large volume, in the direction of the move, without knowing the calendar or the
surprise; the cross version reads the trigger in ZN and trades ES with the sign flipped.

## Data

- `fine.parquet` (20 ms grid, -1 s to +10 s around each clock; bid, ask, sizes, cumulative
  volume) for the trigger and the calibration; `seconds.parquet` (1 s grid) for the exits;
  both from the team archive now at `../data/processed/tick_features/`.
- `events.parquet` (repo) for the window list, sample labels and the lead-lag columns.
- Windows: macro mornings (employment, CPI, PPI, retail sales), their matched control mornings,
  and the pseudo windows two minutes before each release (calibration only). FOMC statements and
  their controls run separately as a secondary and are never pooled with macro.

## Trigger (fixed)

- At each 20 ms grid point t, move = mid(t) - mid(t - 100 ms) in ticks, volume = contracts traded
  in the same 100 ms. Both ends must be valid book states.
- Fire at the first t with |move| >= k and volume >= v. One trade per window, no re-entry.
  The trigger may fire anywhere in the grid (from -0.9 s on); the rule does not know the clock.
- Direction = sign of the move for the own-asset legs; minus the sign of the ZN move for the
  ZN-triggers-ES leg; minus the sign of the ES move for the ES-triggers-ZN leg.
- Entry at the mid of the traded contract one grid point later (t + 20 ms).

## Calibration without lookahead (fixed)

For each window and contract, k and v are the 99th percentiles of |move| and volume over the pool
of the previous 20 windows of the same contract and family (macro or FOMC), ordered by clock time:
event windows contribute only their pre-clock second, control and pseudo windows contribute all
eleven seconds. k has a floor of one tick. Windows with fewer than 20 predecessors are not traded.

## Exit and cost (fixed)

- Primary exit at the mid 300 s after the trigger (last 1 s state at or before). Secondary exits
  at 60 s and 30 s, reported, never used to rescue the primary.
- Cost: half the quoted spread at entry (from the 20 ms panel) plus half the quoted spread at
  exit (from the 1 s panel), in bp of the mid.

## Primary metric

Mean net return per triggered trade, ZN trigger trading ES, macro mornings, `oos_backward`
(2015-2023), with a plain t-statistic (one trade per morning).

## Success threshold

Mean net > 0 with t >= 2 on the primary; the same leg positive on `development` (2024 to Aug
2025); and on control mornings the gross return of triggered trades not significantly positive
(t < 2).

## Robustness gate (all must hold)

1. Positive mean net in at least six of the nine years 2015-2023.
2. Positive mean net on 2015-2023 without 2022.
3. Positive mean net at the 60 s exit.

## Kill criterion

Primary mean net <= 0 on 2015-2023, or the gate fails because 2022 alone carries the result.
Then the cross leg is dead; the own-asset NQ leg is judged on its own numbers as a secondary.

## Secondaries (reported, cannot rescue the primary)

- NQ, ES and ZN own-asset legs; ES trigger trading ZN.
- FOMC statements, all legs, separately.
- False-trigger rate: share of control mornings on which the rule fires, against the share of
  release mornings, and the time of the trigger.
- ES-ZN lead-lag, descriptive: per release morning, the first mid change and the first passage of
  25% of the five-minute move, ES minus ZN in milliseconds, by year (from `events.parquet`).
