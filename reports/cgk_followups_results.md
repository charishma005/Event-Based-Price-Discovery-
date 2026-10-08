# Two CGK (2018) follow-ups: results

Written 2026-10-07 after one run of `scripts/analyze_cgk_followups.py`; rules in
`reports/cgk_followups_preregistration.md`. Numbers from `tables/cgk_prerelease_second*.csv` and
`tables/cgk_drift_by_book_state.csv`.

## Test A: the pre-release second. Verdict: no pre-release move.

Signed return of the mid from -1.00 s to -0.02 s before the clock, macro releases 2015-2026:

| Direction | Contract | Live n | Live mean (t) | Control n | Control mean (t) |
| --- | --- | --- | --- | --- | --- |
| surprise (primary) | ZN | 382 | 0.06 bp (0.8) | 111 | 0.04 (1.4) |
| surprise | ES | 333 | 0.11 (1.5) | 102 | -0.05 (-0.9) |
| surprise | NQ | 334 | 0.32 (1.5) | 102 | -0.03 (-0.5) |
| realized 5-min sign | ZN | 419 | 0.05 (0.6) | 77 | -0.05 (-1.4) |
| realized 5-min sign | ES | 423 | 0.02 (0.3) | 105 | 0.09 (1.6) |
| realized 5-min sign | NQ | 432 | 0.12 (0.7) | 111 | 0.05 (0.8) |

The half-second window is the same picture. Before March 2020 the ZN mean is 0.05 bp (t 1.0),
after it 0.08 bp (t 0.6); NQ after the lockup change is 0.51 bp (t 1.5) and is the largest
number in the table, still inside noise. The mid moves at all in the last second on only 6% to 22%
of mornings in any year. CGK's 0.6 bp in SPY does not appear in ES, NQ or ZN in 2015-2026.

## Test B: post-burst drift and the book. Verdict: not supported.

Net drift 100 ms after the burst to 300 s (surprise direction), low minus high tercile, pooled
per release morning across the three contracts:

| Split | n low / high | Low | Mid | High | Low minus high (t) |
| --- | --- | --- | --- | --- | --- |
| last-second depth over baseline | 247 / 253 | 3.1 bp | 5.4 | 2.1 | +1.0 (0.4) |
| quote-to-trade ratio, -60 to -1 s | 237 / 233 | 4.9 | 6.0 | 1.2 | +3.6 (1.3) |

The quote-to-trade split has CGK's sign (fast makers before the release, less drift after it) in
ZN (+3.7 bp, t 1.8) and NQ (+6.6, t 1.4) and nothing in ES, and it rests on 2020-2023 (+9.9, t
1.5). The depth split flips sign across periods (+4.2 in 2015-2019, -6.2 in 2020-2023, +7.0 in
2024-2026). Neither reaches the pre-declared threshold. On this evidence the drift after the burst
does not depend on how hollow the book was, and the hollow-book question is closed for the
five-minute horizon; what remains open is the depth at the arrival itself (the sweep), which these
tests do not touch.

## For the paper

One sentence each: no detectable move in the direction of the news in the second before the clock,
in any contract or regime; and the small post-burst drift is not conditioned on pre-event depth,
with a weak quote-to-trade pattern in the CGK direction that does not survive a t-test.
