# The burst-trigger trend trade: results

Written 2026-10-07 after one run of `scripts/backtest_trigger_strategy.py` on the 20 ms and 1 s
panels from the team archive (`../data/processed/tick_features/`). Rules were fixed in
`reports/strategy_trigger_preregistration.md` before the run. Numbers come from
`tables/strategy_trigger_*.csv` and `tables/strategy_trigger_trades.parquet`.

One correction was needed between the first and the second run and is recorded here: the 1 s panel
is anchored at the pseudo clock for release windows (120 s before the release, 1,920 s for FOMC
press windows) while the 20 ms panel is anchored at the release. The first run read the exits at
the wrong second; the script now re-expresses every exit in seconds after the event and checks that
the two panels agree exactly at the clock (they do, in all 1,584 live windows). No rule changed.

## Verdict in two sentences

The pre-declared primary, trading ES against the direction of a ZN burst on macro mornings and
exiting 300 s later, is rejected: -6.3 bp per trade net, t = -3.7, over 294 trades in 2015-2023,
positive in two of nine years, negative in 2024-25 and since September 2025. Own-asset trend
following after the same trigger earns nothing net of the spread in any contract, at any of the
three exits, in any sample, and the control windows confirm the trigger itself carries no
information.

## 1. The trigger

- Calibrated k and v are small: the 99th percentile of the pre-event 100 ms move is one tick for
  ES and ZN in every year and 1 to 8.5 ticks for NQ; the volume thresholds run from 20 to 40
  contracts for ES, 3 to 14 for NQ and 26 to 200 for ZN.
- It fires on 89% (ES), 92% (NQ) and 98% (ZN) of release mornings, at a median of 1.1 s after the
  clock (1.3 to 1.4 s in 2015-2019, 0.4 to 1.1 s since 2023), and on about half of the control
  mornings, where triggered trades earn a gross return of zero (t between -0.9 and +1.0).
- Sanity check, 2 February 2024 payrolls: ZN fires at 1.06 s on a 15-tick move with 3,374
  contracts in 100 ms; ES and NQ fire in the same grid step.

## 2. Pre-declared primary and gates (`tables/strategy_trigger_verdict.csv`)

| Item | Value |
| --- | --- |
| ZN trigger, trade ES against it, 2015-2023, 300 s | n = 294, -6.3 bp, t = -3.7, hit rate 38% |
| Same, 2024 to Aug 2025 | n = 76, -0.7 bp |
| Same, Sep 2025-2026 | n = 33, -4.0 bp |
| Control mornings, gross | n = 52, -0.1 bp, t = -0.1 |
| Years positive 2015-2023 | 2 of 9 |
| Without 2022 | -3.1 bp |
| 60 s exit | -6.1 bp |

Kill criterion met. The loss is concentrated in CPI (-11.9 bp, t = -3.1 over 96 trades in
2015-2023) and in 2022 (-35.7 bp), and it is a sign error rather than noise. The rule traded ES
opposite to the ZN price move (bond price down, buy stocks), which is the growth-news regime where
stock and bond prices move against each other. On release mornings that regime ended around 2018:
the correlation between the five-minute ES and ZN price moves is -0.28 in 2015-2017, +0.14 in
2018-2019, +0.77 in 2020-2023 and +0.50 in 2024-2026, and on CPI mornings it is +0.39 even in
2015-2017 and +0.90 in 2020-2023 (hot inflation: yields up and equities down together). A sign
learned per release type and period, as in the first backtest, would flip it; that is a post-hoc
change and is not claimed here.

## 3. Own-asset legs (`tables/strategy_trigger_summary_300s.csv`, `_60s`, `_30s`)

Mean net bp per triggered trade, macro mornings:

| Leg | Exit | 2015-2023 | 2024-Aug 2025 | Sep 2025-2026 | controls |
| --- | --- | --- | --- | --- | --- |
| ES | 300 s | 3.1 (t 1.6) | -5.7 | 1.0 | 0.6 |
| NQ | 300 s | 3.6 (t 1.1) | -5.4 | 3.0 | 4.5 |
| ZN | 300 s | -0.4 | -4.4 | -1.8 | -0.7 |
| ES | 60 s | 1.6 | -5.2 | 0.0 | -0.8 |
| NQ | 60 s | 1.8 | -5.9 | 2.5 | 2.7 |
| ZN | 60 s | -1.1 | -3.5 | -0.6 | -1.7 |

The 2015-2023 ES and NQ numbers lean on 2022 again (19.0 and 8.5 bp that year); without it they
are 1.2 bp (t 0.7) and 2.9 bp (t 1.5). The ES trigger trading ZN is flat to negative everywhere.
FOMC statements, run separately: no leg has |t| above 1.3 except ES trading ZN against the ES move,
which loses 7.3 bp (t = -3.7) for the same sign reason as above.

## 4. ES-ZN lead-lag (`tables/strategy_trigger_lead_lag.csv`)

Per release morning, the first mid change ES minus ZN in ms (positive means ZN moved first):
median +520 ms in 2015 and +490 ms in 2017, zero in 2016, 2018 and 2019, then -7 to -242 ms in every
year from 2020 on, with ZN first on only 28% to 42% of mornings. On the first passage of a quarter
of the five-minute move the medians since 2023 are within 1 ms of zero. There is no ZN lead to
trade at a 20 ms grid, and since 2020 ES tends to move first.

## 5. What this says

Trend following at this horizon has no edge after costs on these mornings. The burst itself is
the price discovery; what follows it is noise plus a slow drift that only CPI in 2020-2023 showed,
and the cross-asset sign is regime-dependent in a way a fixed rule cannot carry. For the paper this
is a cleaner statement of H1 than the first backtest: a real-time rule that detects the arrival with
no calendar fires within about a second of the clock on nearly every release, and the detected move
is essentially complete.

## Limitations

- One trade per window, mid fills, quoted spread only; no price impact and no queue position.
- The 99th-percentile calibration fires on half of quiet mornings; a stricter rule (say the maximum
  of the history) would trade less and might change the own-asset numbers. Not run, by the rules.
- Horizons stop at 300 s for macro windows (the 1 s panel ends at +360 s).
