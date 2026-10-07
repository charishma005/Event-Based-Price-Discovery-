# Pre-declared short-horizon quote-revision measure (Q1)

Written before the measure was run on any 2015-2023 or post-September-2025 window.
The machine-readable version, with the freeze time and code hashes, is
`config/q1_short_horizon_prereg.yaml`. This is an internal pre-declaration made at
the professor's request, not an external preregistration.

## Why a new measure

The proposal's statistic is the midpoint change from the last quote before the
scheduled second to the first quote after it, with no trade in between. That first
record is almost always a depth-only update, so the statistic is about zero for
scalar releases, statements, press conferences and control days alike. It cannot
separate scalar from narrative news, and it leaves the mechanism regression with
nothing to explain.

## What the development sample showed (2024-01 to 2025-09)

1. **The market does not react at the scheduled second.** For BLS releases the
   largest 100 ms move of the first ten seconds starts a median 1.05-1.09 s after
   8:30:00; for FOMC statements, 1.4-3.0 s after 2:00:00. A window of 50 ms to 1 s
   measured from the scheduled second therefore captures pre-arrival noise: the
   median absolute one-second return is about 5% of the five-minute move for
   scalar releases, against 50-86% at two seconds. Dissemination was different
   before 2020, so a fixed offset cannot be carried back to 2015. The short
   horizon is anchored on the market's own arrival instead.
2. **The arrival is mostly one sweep.** In the example that motivated the
   attribution rule (CPI, 15 January 2025), ES moved 26.6 bp in a single
   matching-engine event with 121 trades; quotes then pulled back by 14 bp inside
   the next 100 ms.

## Definition

**Attribution.** Every change of the valid top-of-book midpoint between two
consecutive book updates is assigned to one of three buckets.

| Bucket | Rule |
|---|---|
| Trade | The update carries the exchange timestamp of the most recent preceding trade of that instrument, or is the first update after that trade and is stamped within the tolerance. |
| Quote | Any other change between two valid book states. |
| Gap | A change across a locked, crossed or one-sided book. Reported separately; in neither share. |

The tolerance depends only on the feed format, never on prices. It is zero when a
trade and its book update share a timestamp, and 100 microseconds in the
December 2015 to May 2017 history, where the two are stamped about 15-40
microseconds apart. The format is detected per window from the share of trades
whose next book update has the same timestamp.

**Arrival anchor.** The first midpoint change of the 100 ms window with the
largest absolute net attributed move among windows starting in the ten seconds
after the scheduled second.

**Primary outcome.** `S = QR / (QR + TR)` over the 100 ms from the arrival
anchor, where QR and TR are the quote- and trade-attributed moves in basis points.
S is 1 when the price moved with no trade, 0 when it moved only through trades,
and negative when quotes moved against the trade-driven move.

**Key secondary outcome.** The same share cumulated from the scheduled second
until the midpoint has covered half of its five-minute move. It needs no anchor,
but it depends on the five-minute endpoint and has heavier tails.

**Placebo.** The same rule applied at a pseudo clock two minutes before every
event, inside the same raw file. Matched-day controls are used as well wherever
they exist.

**Reported alongside.** The proposal's first-quote revision, the last quote
before the first trade, the share over 0 / 50 / 250 / 500 / 1000 ms after the
anchor and over 50 ms to 5 s after the scheduled second, and how often a trade
intervenes, by representation class.

## Tests fixed in advance

Seven two-sided tests form the primary family, Holm-adjusted within each sample:
each of the four classes against its own pseudo clock (paired), statement against
press conference within meeting (paired), scalar against narrative, and scalar
against multi-dimensional. Reported outside the family: each class against
matched-day controls, the proposal's literal thresholds (share above 0.70 for
numeric releases, below 0.40 for statements and press conferences), a Spearman
trend across the four classes, and a clustered regression on class and instrument.

A development result counts as replicated when the 2015-2023 estimate has the
same sign and a Holm-adjusted p-value below 0.05. Results that fail are reported
the same way as results that pass.

## Development results at the freeze

Event-level medians of the primary share (mean over the instruments where it is
defined):

| Class | Events | At the announcement | Two minutes earlier | Paired difference | Holm p |
|---|---:|---:|---:|---:|---:|
| Scalar numeric (CPI, PPI) | 39 | 0.105 | 0.542 | -0.380 | 0.0002 |
| Multi-dimensional numeric (jobs, retail) | 38 | 0.150 | 0.476 | -0.311 | 0.0044 |
| Narrative text (FOMC statement) | 13 | 0.335 | 0.528 | -0.218 | 0.65 |
| Speech (press conference) | 13 | 0.512 | 0.574 | -0.172 | 1.00 |

Matched-day controls sit at 0.585 (8:30 a.m.) and 0.542 (2:00 p.m.). Statement
minus press conference within meeting: median -0.053, raw p = 0.022, Holm p = 0.11.
Scalar against narrative: -0.230, raw p = 0.14. Only 2 of 39 scalar events and 1
of 38 multi-dimensional events exceed 0.70. The trend across classes has
Spearman rho = 0.31 (p = 0.002).

So in the development sample the share has variation across the taxonomy, and
the ordering is the opposite of the one H1 and H2 predict: hard numeric news is
the least quote-driven, speech looks like an ordinary no-news minute. That is
the pattern the out-of-sample years are asked to confirm or reject.

## What was looked at before the freeze

- Every development window, including definitions that were tried and dropped
  (fixed scheduled-clock windows; an anchor on the first 25% crossing of the
  five-minute move; an unsigned share).
- In out-of-sample files, only feed-format properties of records at least ten
  seconds before each scheduled macro release: timestamp resolution, action
  codes, flags, and the lag between a trade and its book update
  (`reports/feed_format_census_pre_event.csv`). No post-event record entered any
  statistic.
- The team's earlier 2015-2026 FOMC tables for the legacy measures. The measures
  defined here had not been computed on any out-of-sample window.

## Known limits

- The split is an accounting of how the displayed midpoint moved. It does not
  identify a causal share of public versus private information.
- In a one-tick-spread market a full price step is half a tick by the trade that
  empties the best level and half a tick by the quote that refills the other
  side, so the no-news share is close to 0.5 by construction. Comparisons are
  with the pseudo clock or matched controls, not with zero.
- 2015 timestamps have millisecond resolution; updates in the same millisecond as
  a trade cannot be separated from it. The robustness table drops those windows.
- The arrival anchor is chosen from the outcome path. The pseudo clock receives
  the identical rule, so the comparison is like for like, but the anchor is not
  an independent measurement of when the news arrived.
