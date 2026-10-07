# Follow-up ideas: results

Specification: `reports/followup_ideas_registry.md` (written before the run). Code:
`scripts/run_followup_ideas.py`. Tables: `tables/followup_strategies.csv`,
`tables/followup_regressions_ideas_1_3.csv`, `tables/followup_idea4_withdrawal_magnitude.csv`,
`tables/followup_idea5_lead_lag.csv`. Events: 432 macro releases (284 development / 148 holdout),
92 FOMC statements (63 / 29) and 76 press conferences (47 / 29); ES, NQ, ZN. Development = before
2023; every threshold and prediction coefficient comes from development. Returns are midpoint returns;
"net" subtracts an approximate quoted-spread cost.

## Summary

| Idea | Question | Answer |
|---|---|---|
| 1 | Do large, stressed moves fade (minutes 1-5, macro releases)? | **No as a trade.** The interaction pointed to reversal in 2015-2022 macro data (ES and NQ, p < 0.001) but vanished in 2023-2026. The fade rule loses after costs. |
| 1 (FOMC) | Same rule at FOMC, minutes 1-5 | **The opposite holds.** Large FOMC moves continue from +1 to +5 min, more so when the book is stressed (pooled interaction +0.13, p = 0.006). |
| 3 | Does the press conference reverse the statement move? | **No.** Slopes about 0 in every market and sample. Fading at the press-conference start makes nothing. |
| 4 | Does pre-event liquidity withdrawal predict the *size* of the move? | **Partly yes.** A wider spread in the last minute before the release predicts a larger move (full sample p < 0.001). Adding liquidity improves the holdout fit of log abs(move) by 0.15-0.21 R2 over event-type fixed effects alone. This works for macro releases, not for FOMC. |
| 5 | Does ZN's first 5 s predict ES and NQ over the next minute? | **Not reliably.** Strong in 2015-2022 (ZN -> ES +1.05, ZN -> NQ +1.45, p = 0.001), weak in 2023-2026 (+0.19, +0.28, p > 0.1). The development fit predicts the holdout worse than the target's own lag (out-of-sample R2 -1.4 vs -0.15). |

## Idea 1: stress -> fade at the minute scale

Rule: decision at +60 s; large = abs(ret 0->60 s) >= development 75th percentile; stressed =
depth/spread stress >= development 75th percentile; hold +60 s to +300 s.

| Events | Rule | Instrument | Development net | Holdout net | Full sample (95% CI) | Class |
|---|---|---|---|---|---|---|
| Macro | T1-fade | ES | -7.3 bp (33) | +2.3 (67) | -0.9 [-4.9, +3.2] | NOT SUPPORTED |
| Macro | T1-fade | NQ | +2.7 (14) | +0.5 (28) | +1.2 [-7.2, +10.5] | WEAK |
| Macro | T1-fade | ZN | -2.7 (28) | -0.6 (52) | -1.4 [-4.1, +1.5] | NOT SUPPORTED |
| Macro | T1-follow | portfolio | +3.7 (108) | -2.2 (103) | +0.8 [-1.6, +3.2] | NOT SUPPORTED |
| Macro | T1-follow-calm | ES | +6.9 (38) | +9.9 (6) | +7.3 [+2.1, +12.4], p = 0.008 | SUPPORTED* |
| FOMC | T1-fade | NQ | -37.1 (7) | -2.3 (10) | -16.6 [-30.4, -3.8] | NOT SUPPORTED |
| FOMC | T1-follow | ES | +8.3 (16) | +2.6 (12) | +5.9 [-4.3, +15.6] | WEAK |

\*T1-follow-calm ES is the only row in 28 strategy x instrument rows that passes the rule. It rests on
6 holdout trades, NQ and ZN do not confirm it, and one pass in 28 tries is about what chance gives at
the 5% level. It is a lead to retest, not a finding.

Regression of continuation (+1 -> +5 min) on abs(move) x stress:
- macro, development: ES -0.065 (p < 0.001), NQ -0.143 (p < 0.001), pooled -0.071 (p = 0.003);
- macro, holdout: ES -0.028 (p = 0.40), NQ +0.048 (p = 0.64), pooled -0.002 (p = 0.89);
- FOMC statements, full sample: ES +0.148 (p = 0.002), pooled +0.131 (p = 0.006).

Reading: the "stressed big move reverses" pattern did appear in 2015-2022 macro releases, the same
era as the FOMC development sample, but it did not survive into 2023-2026. At FOMC the first five
minutes show momentum, stronger when the book is stressed, consistent with H5 (the move roughly
doubles from 1 to 5 min). Together with the main strategy test, the FOMC picture is overshoot built
during minutes 1-5 that partly unwinds after +5. Neither leg is reliable enough to trade after costs.

## Idea 3: press conference vs statement

Press-conference 0->5 min return regressed on the statement 0->30 min move: ES -0.02, NQ -0.01,
ZN -0.01 (full sample, all p > 0.8). Holdout slopes are slightly negative (-0.06 to -0.12, p > 0.19).
The drift from statement +5 min to the press conference does not depend on the first 5 minutes
either. T3 (fade the statement move at the press-conference start, exit +5 min) nets +1.7 / -1.3 /
-1.6 bp for ES / NQ / ZN. NOT SUPPORTED everywhere.

## Idea 4: pre-event liquidity predicts move size

ln(1 + abs(ret)) on pre60_depth_ratio and pre60_spread_change_ticks, event-type x instrument fixed
effects, clustered by event:

| Sample | y | Depth-ratio coef | Spread-change coef | Holdout R2 (with liquidity / fixed effects only) |
|---|---|---|---|---|
| All, development | abs(ret 0-5 min) | +0.12 (p = 0.010) | +0.15 (p = 0.033) | -0.18 / -0.32 |
| All, holdout | abs(ret 0-5 min) | +0.19 (p = 0.35) | +0.03 (p = 0.17) | |
| All, full sample | abs(ret 0-5 min) | +0.11 (p = 0.039) | +0.12 (p < 0.001) | |
| All, development | abs(ret 0-60 s) | +0.13 (p = 0.006) | +0.18 (p = 0.004) | -0.03 / -0.22 |
| Macro only | abs(ret 0-60 s) | | | 0.00 / -0.21 |
| FOMC only | abs(ret 0-5 min) | | | -1.47 / -0.10 |

- **Spread widening before the release predicts a bigger move** in every market. Full-sample
  coefficients: ES +0.48, NQ +0.12, ZN +1.15 per tick, all p < 0.01.
- **Depth goes the predicted way only in ZN.** A thinner ZN book before the release means a bigger
  move (-0.77, p = 0.004). In NQ the sign is the opposite.
- Both holdout R2 values are negative because 2023-2026 moves are on a different level than
  2015-2022. The comparison that matters is the difference: pre-event liquidity improves the
  out-of-sample fit by 0.15-0.21. This is the only idea whose predictive content carries into the
  holdout, but it is a volatility forecast (sizing, options), not a direction signal. It does not
  work for FOMC (92 events).

## Idea 5: cross-market lead-lag in the first seconds

Target 5 s -> 60 s return on the leader's 0 -> 5 s return, controlling for the target's own 0 -> 5 s:

| Leader -> target | Development | Holdout | Holdout R2 (with leader / own only) |
|---|---|---|---|
| ZN -> ES | +1.05 (p = 0.001) | +0.19 (p = 0.16) | -1.42 / -0.15 |
| ZN -> NQ | +1.45 (p = 0.001) | +0.28 (p = 0.13) | -1.62 / -0.35 |
| ES -> NQ | +0.87 (p = 0.14) | +0.90 (p = 0.002) | -0.11 / -0.35 |
| ES or NQ -> ZN | +0.10-0.12 (p < 0.03) | about 0 | |

- The 2015-2022 ZN-leads pattern is not stable, and using it makes holdout forecasts worse.
- ES leading NQ is the more stable relationship, though it is significant only in 2023-2026. At
  FOMC, ZN -> NQ stays positive in the holdout (+0.80, p = 0.04).
- None of this is tradeable without a tick-level latency model.

## What to take from this

1. Direction after the first minutes is not predictable from the book in a way that survives a
   chronological holdout. This holds for FOMC (main test), macro releases (idea 1) and the press
   conference (idea 3).
2. Liquidity before a release does forecast **how much** the price will move (idea 4). That is the
   result to build on: a volatility or sizing model for scheduled macro releases, with FOMC as a
   separate case.
3. Relationships estimated on 2015-2022 (stress reversal, ZN lead) weakened after 2023. That is a
   regime change worth a slide in its own right.
