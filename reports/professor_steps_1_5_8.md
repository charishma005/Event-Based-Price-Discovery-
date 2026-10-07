# Professor's next steps 1, 5 and 8: results (October 2026)

Three of the eight "suggested next steps" from the professor meeting, done with
the Databento history and public release calendars. Steps 2, 3, 4, 6 and 7 are
done separately and are not covered here. Everything below is reproducible
from the scripts listed at the end, apart from two one-off checks that are
marked as such. No Databento request cost anything: every quote was $0.00.

## Where the three steps stand

| # | Step | Headline |
|---|---|---|
| 1 | Short-horizon quote-revision measure for Q1 | Pre-declared and frozen before any 2015-2023 window was run. Out of sample, every arrival with a clock (CPI/PPI, jobs report, FOMC statement) is *more* trade-driven than ordinary trading two minutes earlier; the press conference is not. H1 fails as written. The scalar-over-narrative gap is small and changes sign across samples. |
| 5 | Extend macro back in time | 437 release mornings, 2015-2026 (was 77, all in 2024-25), with 112 control mornings. Before 8:30 a.m. releases touch depth falls relative to control mornings in ES and ZN; NQ widens its spread instead. |
| 8 | Broaden the unscheduled test; why NQ does not withdraw | 107 unscheduled arrivals with 373 control windows: no withdrawal before the arrival (ES depth 92% of control days in the final minute, the same as half an hour earlier); depth falls to about two thirds of normal after it. NQ does withdraw, through the spread: it is not tick-constrained. |

What these steps say about the hypotheses:

| | Reading | Basis |
|---|---|---|
| H1 | Rejected | First-quote share of the five-minute move: median 0, above 70% in under 3% of releases in every contract. New arrival share: median 0.32 (2015-2023), above 0.70 in 27 of 212 scalar releases. |
| H2 | Half right | Statements are trade-driven at arrival (below their own placebo and below control days, out of sample). Press conferences look like ordinary trading. But scalar releases are trade-driven too: the scalar-over-narrative gap is +0.10 in 2015-2023 and reverses in 2024-2026, so the taxonomy contrast that H1 and H2 were meant to carry is weak and unstable. |
| H4 | Supported on the two parts tested here | 8:30 a.m. releases against control mornings, 2015-2026 (step 5). No withdrawal before 107 unscheduled arrivals (step 8). The control-day tests for FOMC statements are step 3. |

---

## Step 1. A pre-declared short-horizon measure for Q1

**What was fixed, and when.** `config/q1_short_horizon_prereg.yaml` and
`reports/q1_short_horizon_preregistration.md` define the measure. They were
frozen on 2026-10-05 06:52 UTC with hashes of the measure code, the analysis
script and the event registry, after the 2024-01 to 2025-09 development sample
had been inspected and before any 2015-2023 window was processed. The
extraction script refuses out-of-sample windows unless the freeze exists and
the measure code still matches it.

**Why not a fixed 50 ms to 1 s window.** In the development sample the market
does not react at the scheduled second: after CPI and PPI releases the move
starts a median 1.05-1.09 s after 8:30:00 (1.02-1.08 s after jobs reports and
retail sales). A window on the scheduled clock measures pre-arrival noise. The
measure is therefore anchored on the market's own arrival: the 100 ms window
with the largest net midpoint move in the first ten seconds.

**Measure.** Every midpoint change is attributed to a trade (the book update
that carries a trade's timestamp) or to a quote revision (any other change
between two valid book states). S = quote-attributed move / (quote + trade)
over the 100 ms arrival window. Each announcement has its own placebo: the same
statistic on a pseudo clock two minutes earlier, plus matched control days.

**Out-of-sample result, 2015-2023** (median across events of the difference in
S, taken within contract and averaged over the contracts where both sides are
defined, as pre-declared; Holm across the seven pre-declared contrasts):

| Contrast | Development 2024-25 | Out of sample 2015-2023 | Replicated? |
|---|---|---|---|
| CPI and PPI minus own pseudo clock | -0.38 (n = 39, Holm 0.0002) | -0.17 (n = 202, Holm < 0.0001) | Yes |
| Jobs report minus own pseudo clock | -0.31 (n = 38, Holm 0.004) | -0.21 (n = 107, Holm 0.001) | Yes |
| FOMC statement minus own pseudo clock | -0.22 (n = 13, Holm 0.65) | -0.25 (n = 71, Holm 0.003) | Yes, now significant |
| Press conference minus own pseudo clock | -0.17 (n = 13, n.s.) | -0.03 (n = 55, p = 0.31) | No difference in either |
| Statement minus press conference, same meeting | -0.05 (n = 13, Holm 0.11) | -0.20 (n = 55, Holm 0.003) | Yes |
| Scalar minus narrative | -0.23 (n.s.) | +0.10 (Holm 0.014) | Sign differs |
| Scalar minus multi-dimensional | -0.04 (n.s.) | +0.08 (Holm 0.029) | Sign differs |

"Jobs report" is the multi-dimensional class: jobs reports only in 2015-2023;
in the development sample the class also holds the 17 retail sales releases.

The development column includes one meeting that the vendor flags as degraded
(17 September 2025) and one such control afternoon (24 September 2025): the
vendor's day flags were merged into the registry after the development windows
had been replayed, and the frozen analysis reads a missing flag as available.
Without them (`tables/q1_vendor_flag_check.csv`) the development figures are
-0.23 for the statement (n = 12, Holm 0.80), -0.17 for the press conference,
-0.05 for statement minus press conference (Holm 0.21) and -0.24 for scalar
minus narrative. No out-of-sample figure is affected.

Median S, 2015-2023: scalar 0.32, jobs report 0.24, statement 0.22, press
conference 0.42; pseudo clocks 0.37 to 0.50; control days 0.50. The forward
sample (2025-10 to 2026-09, 8 to 21 events per class) agrees for scalar
releases (-0.56, Holm 0.02) and is too small elsewhere.

Reading: an announcement with a clock is absorbed mostly by trades hitting the
book, more so than ordinary price changes, and this holds for a single number
as well as for a statement. A press conference has no arrival: its largest 100
ms move in the first ten seconds is a median 1.3 bp against 5.4 bp for the
statement (2015-2023, all three contracts), and its split looks like the same
window two minutes earlier. Against the matched control afternoons, whose
clock is 2:00 p.m. (not one of the seven pre-declared contrasts, unadjusted),
the statement is far lower (-0.28, p < 0.0001); the press conference, which
starts at 2:30 p.m., is slightly lower (-0.08, p = 0.04).

On the proposal's ordering (scalar most quote-driven, speech least): in
2015-2023 scalar releases do have a somewhat higher share than statements
(+0.10) and jobs reports (+0.08), which is the predicted direction. In
2024-2026 the sign is the other way (-0.23 in development, -0.19 in the
forward sample, neither significant). The gap is small next to the distance
from ordinary trading, it is not stable across samples, and the press
conference, which the proposal puts last, has the highest share of all. The
ordering is not supported as stated.

**H1 and H2 as written.** S is above 0.70 in 27 of 212 scalar releases
(2015-2023) and 2 of 39 (development). It is below 0.40 in 51 of 71 statements
(sign test p = 0.0002) and 26 of 55 press conferences. The pseudo clocks are
below 0.40 in 39 of 71 and 20 of 55, so the 0.40 threshold says little without
the placebo.

**How often a trade intervenes** (share of events with a trade before the
first quote revision, 2015-2023; ES / NQ / ZN):

| | Event | Pseudo clock | Control day |
|---|---|---|---|
| Scalar (CPI, PPI) | 32% / 36% / 24% | 57% / 42% / 4% | 30% / 17% / 13% |
| Jobs report | 30% / 31% / 34% | 53% / 46% / 6% | same control days |
| FOMC statement | 42% / 52% / 41% | 28% / 30% / 8% | 22% / 12% / 18% |
| Press conference | 15% / 15% / 13% | 11% / 15% / 7% | same control days |

Caveat: 8:28:00 is itself a busy second for ES and NQ (algorithmic orders on
the minute), which inflates the pseudo-clock rate for macro releases. The
selection the professor asked about is real for statements: a trade comes
first two to four times as often as on control afternoons.

**Robustness** (`tables/q1_short_horizon_robustness.csv`). The
event-minus-pseudo results hold on the nanosecond same-timestamp feed only
(2017-06 onward), without invalid-book gaps, and for arrival moves of at least
2 bp. Statement minus press conference holds in the first two; with moves of at
least 2 bp only 21 meetings are left (-0.31, p = 0.02, Holm 0.07). By
instrument NQ carries most of it (event minus pseudo -0.31 to -0.42, statement
minus press -0.56, all p < 0.001); ES has the same sign and is not significant
alone; ZN shows nothing significant. Controlling for the size of the arrival
move, larger moves are more trade-driven (log size -0.08, p < 0.0001) and
statements remain below scalar releases (-0.08 to -0.10, p = 0.01); the press
conference does not differ.

**Not replicated.** The upward trend in S over 2024-25 (rho +0.31) is absent in
2015-2023 (rho -0.03); it shows again in the small forward sample (rho +0.41,
48 events). Without the flagged September 2025 meeting the development value is
+0.29. The secondary outcome (share up to half of the five-minute move) shows
nothing out of sample.

**Added after the freeze.** 92 rule-based control mornings for the macro arm
(step 5). The rule and the eligibility flag were already in the frozen code;
only the "versus matched-day macro control" rows gained observations (scalar
-0.18, p = 0.0015; jobs report -0.26, p < 0.0001 in 2015-2023). Logged in the
`post_freeze_log` of the YAML, as is the note on the vendor's day flags above.

Tables: `tables/q1_short_horizon_*.csv`, `q1_trade_intervention.csv`,
`q1_arrival_latency.csv`, `q1_vendor_flag_check.csv`. Figures:
`figures/q1_short_horizon/`.

---

## Step 5. The numeric-release arm back to 2015

Every CPI, PPI and Employment Situation release from January 2015 to September
2026 on the official BLS schedule, plus the 2024-25 retail sales releases: 437
release mornings (277 scalar, 157 multi-dimensional, 3 same-clock bundles)
against 77 before, all of them in 2024-25, and 112 control mornings (20
hand-screened for 2024-25, 92 by rule). Days the vendor flags as degraded are
excluded from every test.

2015-2026, medians (`tables/macro_extension_summary_2015_2026.csv`):

| | ES | NQ | ZN |
|---|---|---|---|
| Arrival after 8:30:00 | 1.31 s | 1.35 s | 1.27 s |
| Absolute move after 5 s / 60 s / 5 min, bp | 5.2 / 9.0 / 11.7 | 6.4 / 10.3 / 14.3 | 7.9 / 9.2 / 10.3 |
| Time to half / 90% of the 5-minute move | 6.8 s / 31 s | 7.4 s / 38 s | 1.5 s / 10 s |
| First-quote share of the 5-minute move (H1 as written) | 0.000 | 0.000 | 0.000 |
| Releases with that share above 70% | 0.9% | 2.3% | 0.0% |
| Quote-revision share at arrival / at pseudo clock | 0.19 / 0.50 | 0.29 / 0.66 | 0.15 / 0.50 |

- The response is later than the scheduled second in every year: for CPI and
  PPI about 1.3 to 1.45 s in 2015-2020 and 1.05 to 1.2 s since 2021; for jobs
  reports 1.3 to 1.75 s and then 1.0 to 1.15 s (`tables/q1_arrival_latency.csv`).
- Absorption has become faster: ES reached half of its five-minute move in a
  median 13.8 s in 2015-2019 and 1.3 s in 2024-2026.
- Which contract moves first (Q3, exploratory; `tables/q3_first_mover_2015_2026.csv`):
  after jobs reports since 2020, ZN moves before ES in 33 of 43 untied cases
  (median 19 ms; sign test p = 0.0006, 0.014 after Holm across the 24 tests in
  that table). No consistent order for CPI or PPI. FOMC statements, shown for
  comparison, went the other way in 2015-2019: ES first in all 12 untied cases
  (median 71 ms).

**Depth before the release, against control mornings**
(`tables/macro_depth_vs_control_mornings_2015_2026.csv`). A control morning is
the same 8:30 a.m. window on a day of the same month without a release. Final
minute against the prior three minutes (tick data, time-weighted), releases
minus control mornings, paired by month:

| 2015-2026, 112 months | Releases | Control mornings | Difference (95% CI) | Months lower |
|---|---|---|---|---|
| ES depth ratio | 0.68 | 0.94 | -0.26 (-0.31, -0.20) | 93 of 112 |
| ZN depth ratio | 0.38 | 0.89 | -0.51 (-0.55, -0.46) | 105 of 112 |
| NQ depth ratio | 1.04 | 1.01 | +0.04 (n.s.) | 55 of 112 |
| NQ spread change, ticks | +2.52 | +0.11 | +2.41 (1.99, 2.86) | |

2015-2023 alone (82 months): ES -0.24, ZN -0.48, NQ -0.01. The 92 rule-based
control mornings are screened for BLS releases and Thursday jobless claims
only, so 25 of them turn out to have a volume spike at 8:30 (at least three
times the ten minutes before, in ES or ZN), most likely a Census or BEA
release. Dropping them leaves the result unchanged (87 months: ES -0.27,
ZN -0.54). `scripts/screen_macro_controls_by_volume.py` builds that screen.

---

## Step 8. The unscheduled test, and why NQ does not withdraw

### More unscheduled arrivals, several controls each

The earlier test had five hand-picked corporate announcements in single stocks
with one control each, and news-wire clocks that were sometimes hours off. The
new sample is built from prices in the same three contracts as the scheduled
tests:

- One-minute bars for ES, NQ and ZN, 2015-2026. A candidate is a one-minute
  move of at least 8 local standard deviations and at least 12 bp (ES) or 5 bp
  (ZN).
- Scheduled news is removed by construction: only minutes that are not within
  three minutes of :00, :15, :30 or :45; not 8:30-9:00 or 10:00-10:30; not the
  cash open, auction results or the close; not FOMC afternoons; not in the 45
  minutes after a BLS release; no holiday sessions or degraded days.
- The first candidate in any hour is the arrival: 107 arrivals (75 detected in
  ES, 32 in ZN only), spread over all twelve years.
- Controls: the same weekday one and two weeks before and after, at the
  arrival's UTC time, kept when clean: 373 control windows, two to four per
  arrival. Nineteen of them lie across a daylight-saving change and are
  therefore one hour off the arrival's New York clock; the result without
  them is given below.
- Thresholds were fixed from the number of candidates they produce, before any
  depth data for these windows existed.

"Before" is measured up to five seconds before the jump minute opens, so it is
before the news by construction.

| Touch depth, event day / control days | ES | NQ | ZN |
|---|---|---|---|
| **Unscheduled arrivals (107)** | | | |
| 30 to 10 minutes before | 0.93 | 0.97 | 0.91 |
| Final minute before | 0.92 (0.84, 1.01) | 0.93 (0.86, 1.00) | 0.87 (0.79, 0.95) |
| Change from the early window to the final minute | 0.99 (p = 0.41) | 0.95 (p = 0.08) | 0.95 (p = 0.04, Holm 0.11) |
| Final minute / own prior three minutes, minus controls | +0.01 | +0.01 | -0.01 |
| Minutes 1 to 5 after | 0.65 | 0.74 | 0.68 |
| Minutes 5 to 15 after | 0.66 | 0.79 | 0.72 |
| **Scheduled FOMC statements (90), same windows** | | | |
| Final minute before | 0.30 | 0.69 | 0.09 |
| Change from the early window to the final minute | 0.29 | 0.70 | 0.10 |
| Final minute / own prior three minutes, minus controls | -0.37 | +0.04 | -0.64 |

- Before an unscheduled arrival depth is where it was half an hour earlier.
  Days with a jump are slightly thin to begin with (3 to 9% below control
  days), which is expected when arrivals are identified from price jumps; what
  anticipation would add is a decline into the arrival, and there is none in
  ES and at most 5% in ZN and NQ.
- Scheduled against unscheduled, arrival by arrival: p < 0.0001 for the level
  and for the decline in all three contracts.
- Sixteen of the arrivals fall before 10:34 a.m. or within 45 minutes of a
  BLS or Federal Reserve release, where the half hour before the arrival can
  overlap the run-up to a scheduled release. (The arrival with the largest fall
  in ES depth, 3 January 2020 at 1:39 p.m., came 21 minutes before FOMC
  minutes.) Leaving those out and holding control days to the same screen,
  which leaves one more arrival with a single control day and drops it too,
  changes nothing: 90 arrivals, ES 0.93 in the final minute (0.84, 1.02) and
  0.98 relative to the early window (p = 0.22); ZN 0.87 and 0.95 (p = 0.03,
  Holm 0.10).
- Keeping only the control windows at the arrival's New York clock (106
  arrivals) changes nothing either: ES 0.93 in the final minute (0.85, 1.01)
  and 0.99 relative to the early window (p = 0.46); ZN 0.87 and 0.96
  (p = 0.05, Holm 0.16).
- After the arrival depth falls to about two thirds of control-day levels (ES)
  within a minute and stays there for at least 15 minutes. This is the
  proposal's "no pre-event withdrawal but a sharp post-event liquidity shock".
- The earlier five-case result (0.45 against 1.57) does not generalise to
  these markets.
- Unscheduled Federal Reserve announcements in trading hours (USMPD; six since
  2015, four of them in March 2020) are listed in
  `tables/unscheduled_arrivals_per_event.csv`. They are too few and too
  unusual to test (and 2 of their 19 control windows are an hour off for the
  same daylight-saving reason). Two of the six show a marked fall in ES depth beforehand
  (19 March and 27 August 2020); the August announcement coincided with the
  Chair's Jackson Hole speech at 9:10 a.m., a scheduled appearance.

What this sample is not: verified news. A jump off the release clocks can be a
headline, a remark inside a scheduled speech, or a large order. None of these
can be anticipated to the minute, which is what the test needs, but the list
in `data/events/unscheduled_jump_events.csv` should be labelled against news
before individual events are quoted.

Figure: `figures/unscheduled/depth_before_scheduled_and_unscheduled_arrivals.png`.
Tables: `tables/unscheduled_arrivals_*.csv`, `unscheduled_vs_scheduled_contrast.csv`.

### Why NQ does not withdraw

It does; it shows up in the spread. ES and ZN trade at a one-tick spread
almost all the time, so showing less can only mean a smaller size at the
touch. NQ's normal spread is wider than a tick, so the same decision appears
as a wider quote.

FOMC statement, the last 60 seconds against control days in the same seconds
(`tables/h4_tick_constraint_by_period.csv`; the table above stops five seconds
before the clock, hence 0.30 there and 0.28 here for ES):

| | ES | NQ | ZN |
|---|---|---|---|
| Normal spread, ticks (share of time at one tick) | 1.01 (99%) | 1.73 (42%) | 1.00 (100%) |
| Depth ratio | 0.28 | 0.66 | 0.08 |
| Spread ratio | 1.36 | 2.57 | 1.19 |
| Depth per tick of spread (depth ratio / spread ratio) | 0.20 | 0.26 | 0.07 |

On the combined measure NQ is close to ES (0.26 against 0.20; the difference is
still significant, p = 0.0001) instead of far above it, as the depth ratio
alone suggests (0.66 against 0.28). Over time NQ became less tick-constrained
as the index rose (one tick was 0.52 bp of price in 2015-2017 and 0.11 bp in
2024-2026; time at a one-tick spread fell from 80% to 8%), and its depth
withdrawal faded in step (depth ratio 0.42, 0.65, 0.84, 0.87 across the four
periods) while the combined measure stayed between 0.18 and 0.35. Across
meetings, the share of time NQ normally spends at one tick predicts how much of
the withdrawal shows up as depth (rho -0.72). The same holds, more weakly, for
ES (-0.41), and for the 8:30 a.m. releases (NQ depth ratio 0.79 in 2015-2017
and 1.18 in 2024-2026, combined measure 0.55 to 0.65).

Top-of-book size cannot show this directly: NQ's liquidity moves to wider
prices rather than disappearing. A direct check needs ten-level data (MBP-10)
for a dozen meetings.

---

## Clocks

- Exchange timestamps (`ts_event`) are used throughout. The vendor's receive
  clock runs exactly one second ahead of the exchange clock in all 31 cached
  files from 9 May to 3 August 2018 and in none of the other 1,664
  (`reports/timestamp_latency_census.csv`); one-second BBO samples are stamped
  on that clock and are corrected file by file.
- The one-second panels show the same best bid and ask as the tick-derived
  book at 99.5% of 1.05 million common second boundaries (a one-off check, not
  kept as a script).
- Feed format changes in the sample (millisecond stamps to November 2015; a
  trade and its book update stamped 15-40 microseconds apart to May 2017; the
  same timestamp afterwards) are handled by the attribution rule and listed in
  `reports/feed_format_census_pre_event.csv`.

## Data files used

Databento, dataset GLBX.MDP3, continuous front contracts ES.v.0, NQ.v.0 and
ZN.v.0. `reports/data_files_steps_1_5_8.csv` lists all 1,701 files with their
window, what they are, the steps that read them, record counts, sizes and
SHA-256.

| Schema | Files | Size | What |
|---|---|---|---|
| MBP-1 (every book update and trade) | 818 | 5.76 GB | 437 release mornings, 112 control mornings, 93 FOMC meetings, 176 FOMC control afternoons: steps 1 and 5, and the macro part of the NQ analysis |
| BBO, one second | 774 | 0.28 GB | 269 FOMC and control afternoons (1:30-4:00 p.m.), 505 unscheduled arrival and control windows: step 8 |
| One-minute bars | 16 | 0.17 GB | ES, NQ, ZN, January 2015 to September 2026: the unscheduled scan (step 8) and the volume screen of the control mornings (step 5) |
| Trades | 93 | 0.55 GB | FOMC afternoons. They only fill the trade-volume columns of the one-second FOMC panel, which none of the tables here reads |

254 of the MBP-1 files were already on hand (CPI 2015-2026 and the 2024-25
samples); the rest were downloaded on 5 October 2026. Every request was
cost-checked first, and the quote recorded in each of the 1,701 request
manifests is $0.00. Seven FOMC windows exceeded the 250 MB size guard in
`config/settings.yaml` (up to 358 MB) and were fetched with an explicit
per-run override; the guard itself is unchanged.

The raw files are not in the repository (git ignores `data/raw/databento/`).
They are shared inside the team as `steps_1_5_8_data.zip` (7.1 GB: the raw
files with their request manifests, plus the merged feature files), which
unpacks at the repository root. `steps_1_5_8_features_only.zip` (0.3 GB) holds
the feature files alone, which is enough to rerun the analysis scripts.
`scripts/package_steps_1_5_8_data.py` writes
the list above, builds that archive and, with `--verify`, checks local files
against the list. Tracked inputs that are not vendor data: the calendars and
samples under `data/events/` and `config/`, and
`data/processed/tick_features/events.parquet` (one row per event and contract
with the measures; no book or trade records).

## Limits

- Step 1's measure is an internal pre-declaration, not an external
  preregistration. The 2015-2023 FOMC tables on the old measures had been seen
  before the freeze; the new measure had not been computed on those years.
- The macro control rule could not be screened for Census and BEA releases
  (the release calendars could not be fetched); the volume-spike check stands
  in for that.
- Steps 1 and 8 compare FOMC days with 176 control afternoons, of which four
  or five are set aside by the vendor-condition and clean-flag screens: the 24
  already in `config/fomc_placebos.yaml` and 152 added by `scripts/build_placebo_configs.py`
  (`config/fomc_placebos_2015_2026.yaml`: same weekday and clock one week
  before and after each meeting, two weeks if a candidate is excluded,
  screened for other Federal Reserve releases, the Monthly Treasury Statement
  and holidays). This is a different set from `config/fomc_placebos_2015_2023.yaml`
  (one and two weeks before each meeting, not screened), which the FOMC
  pipeline in `scripts/run_fomc_pipeline.sh` uses. The event registry frozen
  for step 1 contains the first set.
- The tick-constraint and Q3 analyses are exploratory and their p-values are
  unadjusted, except where a Holm value is given.
- The control windows for the unscheduled arrivals were placed at the
  arrival's UTC time, so 19 of 373 are one hour off in New York time. The
  sample was left as fixed and the test repeated without them.
- The unscheduled arrivals are price-identified, in futures. The original
  five corporate announcements in single stocks are a different market and
  remain five.
- Days the vendor flags as degraded are left out: 2024-09-18 and 2025-09-17
  (FOMC), 2026-04-10 (CPI), two PPI dates in 2019 and two control afternoons.
  The exception is step 1's development sample, which includes the 17
  September 2025 meeting and the 24 September 2025 control afternoon (see the
  note under the step 1 table).

## Reproduce

```bash
export T3_EXTRA_RAW_DIRS=../data/raw/databento     # optional: an older raw cache outside the repo

# With the shared archive: unpack it here and go straight to "analyses".
unzip -n /path/to/steps_1_5_8_data.zip

# calendars, samples, registry (their outputs are tracked)
python -m scripts.fetch_dataset_conditions --output check.json   # vendor day flags; the tracked copy is never replaced without --force
python -m scripts.build_bls_release_calendar && python -m scripts.build_fed_calendar
python -m scripts.build_extended_cpi_calendar
python -m scripts.build_macro_extension_config && python -m scripts.build_placebo_configs
python -m scripts.build_event_registry && python -m scripts.build_fomc_session_windows

# downloads: an estimate without --execute; add --execute to fetch
python -m scripts.download_registry_windows --require-zero-cost      # seven FOMC windows also need --size-guard-mb 400
python -m scripts.download_registry_windows --registry fomc_session_windows.csv --schema bbo-1s --require-zero-cost
python -m scripts.download_registry_windows --registry fomc_session_windows.csv --schema trades --families fomc --require-zero-cost   # optional
python -m scripts.download_databento --dataset GLBX.MDP3 --schema ohlcv-1m --symbols ES.v.0 NQ.v.0 ZN.v.0 \
    --stype-in continuous --start 2015-01-01T00:00:00Z --end 2016-01-01T00:00:00Z
    # ...16 requests in all; the windows are in reports/data_files_steps_1_5_8.csv
python -m scripts.build_unscheduled_jump_sample
python -m scripts.download_registry_windows --registry unscheduled_windows.csv --schema bbo-1s --require-zero-cost

# features (resumable)
python -m scripts.extract_tick_features && python -m scripts.extract_tick_features --merge
python -m scripts.extract_session_panels && python -m scripts.extract_session_panels --merge
python -m scripts.extract_session_panels --registry unscheduled_windows.csv --output unscheduled \
    --start-seconds -1800 --end-seconds 960
python -m scripts.extract_session_panels --registry unscheduled_windows.csv --output unscheduled --merge

# analyses
python -m scripts.analyze_q1_short_horizon          # step 1
python -m scripts.check_q1_vendor_flags             # step 1: development sample with the vendor's day flags applied
python -m scripts.screen_macro_controls_by_volume   # step 5 (reads the one-minute bars)
python -m scripts.analyze_macro_extension           # step 5
python -m scripts.analyze_unscheduled_arrivals      # step 8
python -m scripts.analyze_tick_constraint           # step 8

# data list, archive, check
python -m scripts.package_steps_1_5_8_data
python -m scripts.package_steps_1_5_8_data --zip ../steps_1_5_8_data.zip
python -m scripts.package_steps_1_5_8_data --verify
python -m scripts.census_timestamp_latency          # receive-clock census of the cached files
```

`reports/feed_format_census_pre_event.csv` was written before the freeze by a
one-off pass over the pre-event records of 197 tick windows; that pass was not
kept as a script.

## What changed in the repository

**Edited existing files (5)**
- `src/utils/config.py`: `raw_databento_dirs()` (the optional `T3_EXTRA_RAW_DIRS` setting).
- `src/data/databento_client.py`: a download is skipped when the file is already in any raw folder; downloads are written to a temporary name and renamed when complete; a per-call size-guard argument. Guards in `config/settings.yaml` are untouched.
- `README.md`, `reports/fomc_2015_2026_h1_h6_summary.md`: a pointer to this report; the earlier text is kept.
- `.gitignore`: ignores `data/raw/bloomberg/`; tracks the two new figure folders and `data/processed/tick_features/events.parquet`. Raw files and one-second panels stay local.

**New**
- Pre-declaration for step 1: `config/q1_short_horizon_prereg.yaml`, `reports/q1_short_horizon_preregistration.md`.
- Measure code (frozen for step 1): `src/microstructure/tick_arrays.py`, `quote_revision.py`, `event_features.py`; and `src/data/raw_index.py`.
- Calendars and samples: `scripts/build_bls_release_calendar.py`, `build_fed_calendar.py`, `build_extended_cpi_calendar.py`, `build_macro_extension_config.py`, `build_placebo_configs.py`, `build_event_registry.py`, `build_fomc_session_windows.py`, `build_unscheduled_jump_sample.py`, `screen_macro_controls_by_volume.py`, with their outputs under `config/` and `data/events/`.
- Data handling: `scripts/fetch_dataset_conditions.py`, `download_registry_windows.py`, `download_extended_cpi.py`, `extract_tick_features.py`, `extract_session_panels.py`, `freeze_q1_preregistration.py`, `census_timestamp_latency.py`, `package_steps_1_5_8_data.py`.
- Analyses: `scripts/analyze_q1_short_horizon.py` and `check_q1_vendor_flags.py` (step 1), `analyze_macro_extension.py` (step 5), `analyze_unscheduled_arrivals.py` and `analyze_tick_constraint.py` (step 8).
- Results: this report, `reports/data_files_steps_1_5_8.csv`, four small data-quality files under `reports/`, the per-event measures in `data/processed/tick_features/events.parquet`, the tables `tables/q1_*`, `macro_extension_summary_2015_2026`, `macro_depth_vs_control_mornings_2015_2026`, `q3_first_mover_2015_2026`, `unscheduled_*`, `h4_tick_constraint_*`, and the figures in `figures/q1_short_horizon/` and `figures/unscheduled/`.
- Tests: `tests/test_quote_revision.py`, `test_unscheduled_scan.py`, `test_macro_controls.py`, `test_package_data.py` (26 tests). The two failures in `tests/test_unscheduled_news_sample.py` predate this work and need the corporate-news files that git ignores.

## Still open on these three steps

1. Label the 107 unscheduled arrivals against news, and run the step 1 split
   on them (needs MBP-1 for those windows).
2. A Census and BEA release calendar to replace the volume-spike screen on the
   macro control mornings.
3. Ten-level data for NQ around a dozen meetings, to see the size move to
   wider prices directly.
