# FOMC statement vs press conference: results

Script: `scripts/analyze_statement_vs_pc.py` (specification in its docstring, written before the run).
Data: one-second BBO session panel, 75 meetings with a press conference (47 development before 2023,
28 holdout), 16 meetings without one (2015-2018), 174 control days at the same clock. Tables:
`tables/statement_pc_*.csv`; figures: `figures/statement_pc/`.

## Correlations

| Pair (ES / NQ / ZN) | Development (47) | Holdout (28) | Full (75) | Control days (174) |
|---|---|---|---|---|
| Press conference first 15 min ~ statement 0-30 min | -0.31 / -0.29 / -0.03 | +0.04 / -0.01 / +0.29 | -0.24 / -0.24 / +0.08 | +0.08 / +0.02 / +0.11 |
| Press conference 0-60 min ~ statement 0-30 min | -0.15 / -0.22 / -0.05 | +0.31 / +0.29 / +0.32 | -0.06 / -0.12 / +0.09 | +0.09 / +0.05 / -0.07 |
| Hour after the press conference ~ press conference | +0.14 / +0.22 / +0.06 | +0.05 / +0.08 / +0.29 | +0.10 / +0.15 / +0.17 | -0.24 / -0.22 / -0.02 |

(Pearson correlations. `pc_0_60 ~ pc_0_15` in the table is mechanically positive because the first 15
minutes are part of the 60; the real momentum test is SP3 below.)

- The statement move does not predict the press-conference move in a stable way. In 2015-2022 the
  first 15 minutes of the press conference leaned against the statement move in ES and NQ (slope
  about -0.29). In 2023-2026 the relation is zero to positive (whole press conference +0.3). Over the
  full sample it is indistinguishable from zero.
- The press conference is where most of the afternoon's movement happens. The median absolute
  30-to-90-minute move is 38 bp (ES), 43 bp (NQ) and 16 bp (ZN) on press-conference days, against 11,
  17 and 3 bp on control days at the same clock, and 16, 18 and 4 bp on 2015-2018 meetings without a
  press conference. The press conference adds roughly three to five times the normal volatility.

## Strategies (executable bid/ask, entry one second after the decision; fees ignored)

| Rule | ES dev / hold | NQ dev / hold | ZN dev / hold | Class |
|---|---|---|---|---|
| SP1-fade: fade statement move at press-conference start, exit +60 min | +2.4 / -6.4 | +10.1 / -21.6 | -0.4 / -0.6 | NOT SUPPORTED |
| SP1-follow: follow it | -4.1 / +5.5 | -11.2 / +20.8 | -2.0 / -2.2 | NOT SUPPORTED |
| SP2-fade-large: fade large statement moves only | +29.3 (12) / -38.1 (4) | +47.8 (12) / -98.2 (2) | +5.9 / -21.8 | NOT SUPPORTED |
| SP3: follow the press conference's first 15 min to +60 min | +12.9 / -3.5 | +27.1 / -10.8 | +1.0 / -3.1 | NOT SUPPORTED |

Every rule flips sign between development and holdout. SP3's development profit comes mostly from
2022 (+47 bp a meeting); 2023, 2025 and 2026 are negative. The same rules on control days and on
meetings without a press conference earn about zero, so nothing here is a general 2:30 p.m. effect
either.

## Conclusion

There is no tradeable link between the statement reaction and the press-conference reaction. The
2015-2022 "press conference reverses the statement" tendency did not survive into 2023-2026. The
robust fact is descriptive: the press conference is a second, larger information event, moving
prices three to five times more than the same hour on ordinary days. It is not predictable in
direction from the statement window.
