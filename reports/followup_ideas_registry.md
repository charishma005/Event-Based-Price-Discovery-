# Follow-up ideas: pre-registered specification

Written on 2026-10-07, after the FOMC strategy holdout and before any of these tests was run.
Code: `scripts/run_followup_ideas.py`. Data: `data/processed/tick_features/events.parquet`
(tick-level MBP-1 measures; FOMC windows from -5 min to +15/+40 min, macro releases from -5 to +6 min).

Common rules
- Events: FOMC statements (93), FOMC press conferences (77), and CPI, PPI, employment and retail-sales
  releases at 8:30 ET (435), for ES, NQ and ZN. Rows with `dataset_condition == "degraded"` or an
  invalid pre-event book are dropped.
- Split: development = before 2023-01-01; holdout = 2023-01-01 onward. Every threshold, z-score
  moment and regression coefficient used to predict comes from development only.
- Returns are midpoint log returns in bp from the tick table (`wXs_total_bp` = event to +X s).
- Approximate executable cost (no quote at the exact fill second in this table): one round trip =
  the average quoted spread over the entry window plus the average over the exit window, each half
  a spread, converted to bp at the pre-event price.
- Standard errors are clustered by event. The classification rule is the same as for the FOMC
  strategies: SUPPORTED = positive after cost in development and holdout, at least 3 holdout trades,
  full-sample event-bootstrap 95% CI above 0.

Idea 1: stress -> fade, minute scale, on macro releases (fresh events)
- Decision at +60 s. Large move: |ret 0->60s| >= development 75th percentile (per instrument).
  Stress at +60 s: z(1 - post60_depth_ratio) + z(post60_spread_change_ticks), development moments;
  stressed = stress >= development 75th percentile.
- T1-fade: large AND stressed -> fade; hold +60 s to +300 s. T1-follow: large -> follow (price-only).
  T1-follow-calm: large AND NOT stressed -> follow. (This third rule was in the code before the first
  run but was left out of this text by mistake; added here after the run, unchanged.)
- Regression: continuation_1_5 = sign(ret_0_60) x (ret_0_300 - ret_0_60) on |ret_0_60|, stress and
  |ret_0_60| x stress. Prediction from the FOMC result: the interaction is negative.
- The same specification on FOMC statements is reported as secondary (FOMC thresholds estimated on
  FOMC development events).

Idea 3: does the press conference reverse the statement move?
- Meetings with a press conference. x = statement 0 -> +5 min return. y1 = drift from statement +5 min
  to the press-conference start (+30 min). y2 = press conference 0 -> +5 min.
- Regressions y1 on x and y2 on x. Prediction: negative slopes (reversal).
- T3: at the press-conference start, fade the statement 0 -> +30 min move; exit at press conference
  +5 min.

Idea 4: pre-event liquidity withdrawal predicts the size of the move (not its direction)
- y = ln(1 + |ret 0->300s|) and ln(1 + |ret 0->60s|). x = pre60_depth_ratio and
  pre60_spread_change_ticks (both measured -60 s to 0 against the -240 to -60 s baseline), with
  event-type x instrument fixed effects. Prediction: negative depth coefficient, positive spread
  coefficient.
- Out of sample: development fit, holdout R2 compared with the fixed-effects-only model.

Idea 5: first-seconds lead-lag across markets
- For each target T in {ES, NQ, ZN} and each leader L != T: y = T's 5 s -> 60 s return; x = L's
  0 -> 5 s return, controlling for T's own 0 -> 5 s return. Pooled over FOMC statements and macro
  releases, by event type. Prediction: ZN leads ES and NQ.
- Out of sample: holdout R2 of the development fit.

Idea 2 (pre-FOMC drift) needs one-minute ES bars that are not in this table; it is not run here.
