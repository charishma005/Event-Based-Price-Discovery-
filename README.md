# How Markets Absorb News

This repository implements the proposal's central empirical object: the share of an announcement-related price adjustment attributable to an immediate quote revision before any trade versus later adjustment fitted to signed order flow. It is deliberately not a generic event study. The first goal is to establish that timestamps, quotes, trades, and aggressor signs are mechanically valid before estimating a cross-event model.

## Current research scope

- **Original pilot:** September 8–19, 2025.
- **Completed FOMC expansion:** thirteen cached meetings from January 2024 through July 2025, with twelve available-quality meetings in primary inference and twenty-four matched 2:00 p.m. control windows.
- **First event:** September 17 FOMC statement/SEP at 2:00 p.m. EDT and press conference at 2:30 p.m. EDT.
- **First instruments:** ES, NQ, and ZN futures; then SPY, NVDA, and JPM where feed structure permits.
- **Broader equities:** the 22-name S&P 500 basket in `config/universe.yaml`. All were constituents during the pilot; the theme labels are hypotheses, not accepted empirical classifications.
- **Data tiers:** one-second screening, MBP-1 message sequences over narrow event windows, and selected MBP-10 windows for levels 1/5/10. Full MBO remains reserved for questions that genuinely need order-level reconstruction.

The verified event calendar is at `data/events/event_calendar.csv`. It includes separate rows for the FOMC statement, SEP, and press-conference opening, as well as concurrent releases that can contaminate a macro window.

## October 2026: the professor's next steps 1, 5 and 8

`reports/professor_steps_1_5_8.md` reports three of the eight next steps from
the professor meeting. Steps 2, 3, 4, 6 and 7 are done separately and are not
in that report. In short:

- **Step 1 (Q1).** A short-horizon quote-revision share, anchored on the market's own arrival, was pre-declared (`config/q1_short_horizon_prereg.yaml`) and frozen before any 2015-2023 window was run. Out of sample, CPI/PPI, the jobs report and the FOMC statement are all more trade-driven than ordinary trading; the press conference is not. H1 fails as written and the scalar-versus-narrative ordering does not replicate.
- **Step 5 (macro arm back to 2015).** 437 release mornings (was 77, all in 2024-25) and 112 control mornings. Touch depth is withdrawn before 8:30 a.m. releases relative to the control mornings in ES and ZN; in NQ the spread widens instead.
- **Step 8 (unscheduled arrivals, NQ).** Before 107 unscheduled arrivals (price-identified, two to four control days each) there is no withdrawal. NQ does withdraw before scheduled arrivals, through the spread, because it is not tick-constrained.

One new local setting (optional, unset by default):

- `T3_EXTRA_RAW_DIRS`: extra read-only folders of Databento files, searched after `data/raw/databento/`. Lets an existing raw cache outside the repository be reused instead of copied or downloaded again.

The run order for the new scripts is at the end of the report, and
`reports/data_files_steps_1_5_8.csv` lists every raw file they read, with its
SHA-256. The raw files and the one-second panels are local only;
`data/processed/tick_features/events.parquet` (per-event measures, no vendor
records) is small enough to track.

## Liquidity stress, move size and execution (pre-declared, not yet run)

`config/liquidity_trading_prereg.yaml` fixes one liquidity-stress measure,
ELS = log(depth ratio) - log(spread ratio) (the log of depth per tick of spread),
and five tests on the one-second FOMC session panel: A) |move| and continuation on
ELS; B) out-of-sample prediction of top-quartile moves; C) execution cost of a
user schedule, TWAP, a fixed blackout around 2:00 p.m. and an ELS-adaptive rule;
D) a stressed-move fade and E) short momentum, both exploratory and confirmed
only on meetings after the freeze. Run order:

```bash
python -m scripts.extract_session_panels && python -m scripts.extract_session_panels --merge  # if not built
python -m scripts.analyze_liquidity_trading --check-data      # coverage only, no outcomes
# complete inspection_before_freeze in the YAML, then:
python -m scripts.freeze_liquidity_trading_preregistration
python -m scripts.analyze_liquidity_trading                   # tables/liq_*.csv, figures/liquidity_trading/
```

An optional `data/external/implied_vol.csv` (columns `date`, `implied_vol`) is
added to the baseline of part B if present at the freeze.

## Data sources

### Databento

- `GLBX.MDP3`: preferred ES/NQ/ZN feed. MBP-1 is the baseline Q1 schema; MBO is reserved for selected full-depth windows.
- `XNAS.ITCH`: venue-specific Nasdaq full depth for a transparent NVDA case study; it is not consolidated NBBO.
- `EQUS.MINI`: aggregated cross-venue top of book for SPY and the stock cross-section. It has no deeper book and its anonymized records have `sequence=0`, so same-timestamp ties can be unresolved. Its one-second BBO can also be stale or very wide for less-active names; broad-stock returns therefore use one-second OHLCV trade closes, while suspect BBO observations are flagged.

`ts_event` is the canonical exchange/matching-engine clock. `ts_recv` is retained only for latency diagnostics. TBBO alone is not sufficient for Q1 because it samples the BBO at trades and can miss a quote-only public-signal jump.

### Alpha Vantage

Alpha Vantage `NEWS_SENTIMENT` is the **primary news and sentiment source for the pilot**. It supplies historical articles, topics, overall sentiment, and ticker-specific relevance/sentiment. The pipeline queries one ticker per request because a comma-separated ticker filter requires every listed ticker to co-occur; it is not an OR query. Alpha Vantage news will be used for company-news contamination flags and exploratory unscheduled events. It does not provide the ordered quote/trade data needed for Q1, and a provider publication timestamp is not treated as first market arrival until it passes a source-level audit.

That audit now supports two source-verified corporate-news pilots. Alpha Vantage discovered and scored NVIDIA's September 18 Intel partnership/investment announcement; GlobeNewswire supplied the defensible 07:00 ET clock, and Databento supplied the NVDA Nasdaq message sequence. Meta's September 11 dividend release uses PR Newswire's 16:35 ET clock. The liquid NVIDIA case supports a mechanism estimate; the sparse after-hours Meta case fails primary sequencing eligibility and is retained as a counterexample.

### Official event sources

The calendar uses BLS, Census/HUD, and Federal Reserve archival releases. Official sources provide timestamps and realized/prior values, but not the vintage analyst consensus distribution. Expected values, forecast dispersion, and standardized surprise are therefore left blank rather than imputed.

## Credentials

Create a local `.env` or export environment variables:

```bash
cp .env.example .env
```

Populate only:

```text
DATABENTO_API_KEY=...
ALPHAVANTAGE_API_KEY=...
```

`.env` and all raw provider payloads are ignored by Git. The code never saves keys in request URLs, logs, manifests, or reports. Databento account name and user ID are not required for normal API-key authentication.

The local `.env` has been configured and restricted to owner-only permissions. It remains ignored by Git. Do not commit or print it; rotate either provider key if it is exposed elsewhere.

## Setup and validation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -q
```

There is intentionally no giant notebook. Core transformations live in `src/`, while small CLI commands perform discovery and the mechanical pilot.

## Exact execution sequence

1. Inspect account-specific availability, schema fields, data conditions, continuous-contract mappings, and candidate costs. This does **not** download market data:

```bash
python -m scripts.inspect_databento
```

Review `reports/databento_cost_estimates.json` before proceeding.

2. Estimate the cheapest futures screening request:

```bash
python -m scripts.download_databento \
  --dataset GLBX.MDP3 \
  --schema ohlcv-1s \
  --symbols ES.v.0 NQ.v.0 ZN.v.0 \
  --stype-in continuous \
  --start 2025-09-17T17:30:00Z \
  --end 2025-09-17T19:30:00Z
```

3. Estimate the primary statement MBP-1 window:

```bash
python -m scripts.download_databento \
  --dataset GLBX.MDP3 \
  --schema mbp-1 \
  --symbols ES.v.0 NQ.v.0 ZN.v.0 \
  --stype-in continuous \
  --start 2025-09-17T17:50:00Z \
  --end 2025-09-17T18:10:00Z
```

Only after reviewing the printed cost/size, repeat the exact command with `--execute`. Every download is also blocked if it exceeds `$1.00` or 250 MB under `config/settings.yaml`, and raw files are opened exclusively so they cannot be overwritten silently.

4. Build per-instrument timestamp diagnostics and Figures A–C from a downloaded MBP-1 DBN file:

```bash
python -m scripts.build_fomc_pilot \
  --dbn data/raw/databento/GLBX.MDP3-mbp-1-0055628d87519646.dbn.zst \
  --instrument ES.v.0 \
  --event statement
```

Repeat with `--event press_conference`, then NQ and ZN. The script saves processed Parquet, signed-flow buckets, a timestamp diagnostic, and figures. It does not invent an order-flow impact coefficient or mechanism share from one event.

After building the individual instruments, reproduce the consolidated horizon, liquidity, placebo, and exploratory mechanism outputs:

```bash
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_fomc_results
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_macro_panel
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_placebos
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_lead_lag
```

The second command estimates instrument-specific signed-flow impact using pooled pre-event intervals while leaving the focal event out. The third writes matched-clock liquidity and return comparisons.

5. Preview the 25 Alpha Vantage news requests for the complete pilot: 22 ticker-specific queries plus separate monetary-policy, macro, and financial-market topic queries.

```bash
python -m scripts.download_alpha_vantage_news
```

After checking the plan and confirming `ALPHAVANTAGE_API_KEY` is in the environment, execute it:

```bash
python -m scripts.download_alpha_vantage_news --execute
python -m scripts.build_news_panel
python -m scripts.build_news_timestamp_audit
```

For a two-name smoke test before the full basket:

```bash
python -m scripts.download_alpha_vantage_news \
  --tickers NVDA JPM \
  --topics \
  --delay-seconds 13 \
  --execute
python -m scripts.build_news_panel
```

The build command produces `data/processed/alpha_vantage_news.parquet`, a query-coverage audit, and event-by-stock contamination flags. A missing query is represented as unknown coverage rather than a false zero-news observation.

For the expanded January-September 2025 corporate-news sample and audit:

```bash
python -m scripts.download_alpha_vantage_news \
  --time-from 20250101T0000 --time-to 20250920T0000 \
  --topics --max-requests 22 --delay-seconds 13
# Review the plan, then repeat with --execute.
python -m scripts.build_news_panel
python -m scripts.select_news_events --target 44
python -m scripts.audit_news_source_timestamps --workers 4 --timeout 12
python -m scripts.analyze_news_controls
```

The source audit makes ordinary page requests and may encounter paywalls, robots restrictions, removed pages, or metadata that represents an update rather than first publication. Its output is a review queue, not automatic event-time certification.

6. Rebuild the consolidated message-level research table after the event-specific files and news flags exist:

```bash
python -m scripts.build_event_time_panel
```

This writes `data/processed/event_time_panel.parquet` with exchange and receipt timestamps, Eastern time, event time, BBO/liquidity, trades, explicit aggressor side, signed flow, dynamic quote/flow/residual components, contamination candidates, and dataset/sequence quality flags.

7. Reproduce the 22-stock one-second FOMC cross-section from the bounded `EQUS.MINI` BBO and OHLCV files:

```bash
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_stock_cross_section
```

8. Estimate objective historical market/rate exposures and descriptive CPI/FOMC-day abnormal-return rankings from the cached daily bars:

```bash
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_historical_sensitivity
```

The event dates are source-controlled in `config/historical_event_dates.yaml`. The coefficients exclude those dates from estimation. Outputs include stock/theme tables, event-day residuals, and two compact figures under `figures/stock_cross_section/`.

9. Reproduce the six source-verified corporate-news event/control pairs:

```bash
python -m scripts.download_unscheduled_news_sample
# Review the estimates, then repeat with --execute.
python -m scripts.process_unscheduled_news_sample
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_unscheduled_news_sample
python -m scripts.build_event_time_panel
```

This writes timing, horizon, mechanism, depth, and news-screen tables under `data/processed/unscheduled_news/` and adds all twelve event/control windows to the canonical panel.

10. Reproduce the multi-meeting FOMC sample, matched controls, statistical comparisons, and paper outputs from the immutable raw cache:

```bash
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_fomc_sample
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_fomc_sample
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_fomc_placebos
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.make_paper_outputs
```

To reproduce provider retrieval rather than use the cache, first run `python -m scripts.download_fomc_sample` and `python -m scripts.download_fomc_placebos` without `--execute`. They print every window, byte estimate, price estimate, and cache status. The five added meeting windows were estimated at 947.42 MiB and the ten added controls at 287.17 MiB; both portfolios were $0.00 and every individual request passed the guard.

10b. Extend the FOMC sample to 2015 through September 2026 (93 scheduled meetings, 77 with press conferences) and rerun H5/H6 against the USMPD surprises. `config/fomc_sample_2015_2026.yaml` is generated from the USMPD statement and press-conference clocks; pre-2019 meetings without a press conference get a statement-only window. fomc_20240918 is marked `degraded` by hand, as in the 2024-2025 config; regenerating the config drops that flag unless it comes from a `--conditions` report. Every step writes to `fomc_sample_2015_2026` folders and `_2015_2026` tables, so the 2024-2025 results are untouched. At roughly 200 MiB per meeting window, expect about 18-19 GB of raw DBN files.

```bash
python -m scripts.build_fomc_sample_config                       # already committed; rerun only to change dates
python -m scripts.audit_macro_conditions --config fomc_sample_2015_2026.yaml --output fomc_2015_2026_dataset_conditions.json
python -m scripts.build_fomc_sample_config --conditions fomc_2015_2026_dataset_conditions.json
python -m scripts.download_fomc_sample --config fomc_sample_2015_2026.yaml             # estimate only
python -m scripts.download_fomc_sample --config fomc_sample_2015_2026.yaml --execute   # after reviewing cost
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_fomc_sample --config fomc_sample_2015_2026.yaml --output-name fomc_sample_2015_2026
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_fomc_sample --config fomc_sample_2015_2026.yaml
python -m scripts.analyze_fomc_surprises --config fomc_sample_2015_2026.yaml
```

`process_fomc_sample` writes to `data/processed/fomc_sample` unless `--output-name` is given, so always pass it for other configs.

Multi-horizon H5 (statements only). `process_fomc_sample` now also records statement returns at 10, 20 and 30 minutes; 30 minutes is the press-conference start, so it is the last horizon before new scheduled information. Only the 77 meetings with a press conference have windows that long (statement-only meetings end 15 minutes after the statement). Rebuild the processed files from the raw cache, then run:

```bash
MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_fomc_sample --config fomc_sample_2015_2026.yaml --output-name fomc_sample_2015_2026
python -m scripts.analyze_fomc_h5_horizons --config fomc_sample_2015_2026.yaml
python -m scripts.analyze_fomc_h6_horizons --config fomc_sample_2015_2026.yaml
python -m scripts.analyze_fomc_h5_h6_extra --config fomc_sample_2015_2026.yaml   # extra p-value tests, ~1-2 minutes
MPLBACKEND=Agg python -m scripts.make_slide_figures
```

This writes `tables/fomc_h5a_response_magnitude_2015_2026` (|surprise| vs |return| at 1s-30m), `fomc_h5b_response_fraction_2015_2026` (|surprise| vs the share of the 30-minute move already done; events with bottom-quartile 30-minute moves excluded), and `fomc_h5_response_profile_2015_2026` (small/medium/large surprise terciles), plus the H5 profile figures. `analyze_fomc_h6_horizons` uses the same returns for H6, dropping the smallest 25% of surprises: `fomc_h6a_direction_2015_2026` (share of meetings moving the way the news implies), `fomc_h6b_size_asymmetry_2015_2026` (hawkish effect on move size, given surprise size) and, once the 30-minute horizon exists, `fomc_h6c_speed_asymmetry_2015_2026` (hawkish effect on the share of the 30-minute move done early).

`analyze_fomc_surprises` also writes `_large_moves` versions of the H5/H6 tables (near-zero and bottom-quartile five-minute moves dropped) and an `equity_average` row (ES and NQ only, since ZN shares inputs with the USMPD surprise). Every H5/H6 table has `holm_p` and `bh_q` columns adjusted across all of its cells; read those rather than raw p-values.

11. Reproduce the January 2024-August 2025 macro sample, sub-second flow models, and the independently screened 8:30 a.m. controls:

```bash
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_macro_sample
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_macro_sample \
  --config macro_sample_2024.yaml \
  --conditions macro_dataset_conditions_2024.json \
  --output macro_sample_2024
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_macro_sample_full \
  --samples macro_sample macro_sample_2024 --output macro_multiyear
python -m scripts.analyze_multiscale_flow
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.process_macro_placebos
python -m scripts.process_depth_sample
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.make_paper_outputs
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/t3-mpl-cache python -m scripts.analyze_subsecond_price_discovery
python -m scripts.build_final_results_summary
python -m scripts.build_paper_pdf
```

For fresh retrieval, run the relevant download command without `--execute` first. The 46 added 2024 macro windows were estimated at 1.76 GiB and the nine instrument-specific MBP-10 requests at 1.09 GiB; both portfolios were $0.00. MBP-10 is split by instrument so every request remains below the 250 MiB guard.

## Current findings

- Authenticated Databento discovery found `GLBX.MDP3`, `XNAS.ITCH`, and `EQUS.MINI` available. The immutable cache contains 174 bounded requests at an estimated account cost of $0.00, producing 66,449,821 records and 1.49 GB of compressed files. Raw manifests sum to 8,018,652,760 estimated billable bytes.
- The primary numeric-macro panel has 77 unique 8:30 a.m. arrival bundles (80 official releases) from January 2024-August 2025 in ES/NQ/ZN. All provider conditions are available; 148 of 231 instrument-bundle observations pass the literal no-intervening-trade rule.
- H1 is not supported under the proposal's literal definition. The median absolute first-quote fraction of the five-minute move is zero for scalar releases in all three instruments; none exceeds 70%. Opposite-direction Wilcoxon p-values are 2.98e-8 (ES), 4.77e-7 (NQ), and 4.66e-10 (ZN).
- The macro liquidity result survives twenty month-clustered matched controls: the all-instrument mean depth ratio is 0.623 on event mornings versus 0.976 at quiet clocks, with nineteen of twenty monthly differences negative (sign p=0.000020; Wilcoxon p=0.0000019). ES and ZN show withdrawal; NQ does not.
- The expanded FOMC sample contains 36 statement-instrument and 36 press-instrument observations across twelve primary meetings. Twenty-three statement and thirty-three press observations pass the no-intervening-trade condition.
- Matched controls provide the strongest formal result: the final-minute touch-depth ratio averages 0.563 on FOMC days versus 1.026 at matched clocks. All twelve meeting-cluster differences are negative (one-sided sign and Wilcoxon p=0.00024); ZN is especially strong, while NQ remains weak.
- Using the five-minute response as a benchmark, median statement 50% crossing times are 9 seconds (ES), 7.5 (NQ), and 4.5 (ZN). Press-opening medians are 97, 95.5, and 63.5 seconds, respectively. Reversals mean these first crossings are descriptive, not permanent-convergence estimates.
- In the paired ten-meeting subset, statement 50% crossings are faster by Wilcoxon tests in ES (p=0.0068), NQ (p=0.0137), and ZN (p=0.0137). Stable-within-10% differences are not significant, so early adjustment is faster but permanent convergence is not established.
- H2 is formally supported in this sample: all 23 eligible statement and 28 eligible press observations have an absolute 60-second first-quote fraction below 40% (p=0.0000042 and p=0.00000035).
- At 100 millisecond resolution, ES/NQ absolute return correlations peak at zero lag in all 12 clean meetings for both statement and press windows. ES reaches 1 bp before NQ in 10/12 statements (sign p=0.019; Wilcoxon p=0.065), but not at press openings, so the evidence does not support a universal leader.
- Q1 is mechanically implementable with MBP-1. The FOMC statement produced roughly 15–20 bp five-second midpoint responses in ES/NQ/ZN, but the literal first valid post-event quote was unchanged for ES and ZN, while NQ had a trade before its first clean quote.
- Databento marks `GLBX.MDP3` on September 17 as `degraded`. The FOMC futures estimates are therefore provisional even though message timing and capture-latency diagnostics look coherent.
- On the fully available September 16 Retail Sales window, ES and NQ pass the no-intervening-trade condition. Their literal first-quote revisions are again zero; most of their smaller one-minute movements occur later.
- PPI NQ/ZN, CPI ES, and all three industrial-production futures add five more non-degraded, mechanically eligible observations. The pilot now has seven eligible event-instrument Q1 cases.
- PPI and CPI 60-second moves are much larger than the September 9 matched-clock controls; industrial production is not. CPI, Retail Sales, and FOMC show lower final-minute depth than their controls.
- Final-minute touch depth before the FOMC fell to 17% of its earlier baseline in ES and 13% in ZN. At the matched non-event Wednesday time, the corresponding ratios were 119% and 98%.
- Leave-one-event-out pooled one-second signed-flow calibrations explain only part of most subsequent moves. The residual is often dominant, demonstrating why it must not be normalized away.
- The official FOMC statement and SEP both arrived at 18:00:00 UTC; the press conference began at 18:30:00 UTC. A precise Q&A boundary is not yet asserted.
- Because the statement and SEP are simultaneous, the 2:00 p.m. return is a joint response even though the calendar keeps separate metadata IDs. Market timestamps alone cannot identify a statement-only versus SEP-only effect.
- Every official numeric release lacks the forecast dispersion needed for H3. That is a real data gap, not a coding gap.
- The expanded Alpha Vantage cache has 10,005 unique articles and 30,406 article-ticker rows, with no timestamp parse failures. Four extended ticker queries reach the 1,000-result ceiling, so this is a discovery corpus rather than a complete archive.
- A reproducible ranking selects 44 high-relevance corporate-news candidates across all 22 stocks and six categories. Source-page metadata were extractable for 21; only three matched the provider clock within five minutes, and the median absolute discrepancy was 8.4 hours.
- The liquidity-conditioned sub-second flow model raises pre-event fit but improves event-window median absolute error in only 11 of 27 model cells. This supports state-dependent impact while confirming that the residual cannot be normalized away.
- Three pre-specified MBP-10 windows show lower level-5 and level-10 depth in eight of nine event-instrument observations; NQ before the August employment report is the exception.
- Alpha Vantage ticker mappings contain incidental/false associations, so contamination flags now require a direct company alias plus relevance thresholds. No story is admitted as an exact unscheduled event without source-level timestamp validation.
- Source audits prove why that gate matters: three Alpha Vantage clocks are 4–11 hours early. The pipeline preserves both fields, uses verified source time for matching, and no longer falsely marks the Meta dividend as pre-CPI contamination.
- The source-verified corporate sample now has six event/control pairs. Three news events pass Q1 mechanically. NVIDIA earnings and AMD's buyback move +331.5 and +143.8 bp at one minute but fail the no-intervening-trade condition; the failure is preserved rather than waived for material events.
- All five nominally unscheduled cases have lower final-minute depth ratios than their clean matched clocks: 0.448 versus 1.568 on average, with paired sign and Wilcoxon p=0.031. This selected sample cautions against claiming withdrawal is unique to scheduled events.
- The canonical event-time panel contains 3,883,960 message rows across 45 event-instrument pairs and preserves explicit aggressor signs and event-level quality flags.
- The 22-stock FOMC screen uses one-second trade closes. Statement 60-second returns range from -3.51 bp (NVDA) to +37.67 bp (CAT); the press-conference opening is negative for most growth/high-beta names. These are raw exploratory responses, not beta-adjusted estimates.
- One year of daily data confirms very high market betas for TSLA (2.26), AMD (2.00), NVDA (1.94), and AVGO (1.75), and strong positive ZN-price sensitivity for AMT (2.00) and PLD (1.07). Conditional Treasury coefficients for the growth group are negative after controlling for SPY, so the original theme labels are retained as hypotheses rather than facts.
- On 9 FOMC decision days, the largest market-and-rate-adjusted absolute-return ratios relative to ordinary days are MSFT 2.77, META 1.69, GOOGL 1.60, NVDA 1.58, and AMT 1.54. On 13 CPI dates, HD is 1.86 and NVDA 1.69. These are descriptive rankings without surprise controls.
- Q3 is now implemented descriptively with message-level first-move thresholds and 100 millisecond lead-lag correlations. A structural Hasbrouck share is not claimed because ES, NQ, and ZN are different assets rather than multiple venues for one claim.

## Outstanding limitations

- The September 17 CME futures dataset carries a provider-level degraded flag; it cannot be treated as definitive without clarification or replication.
- `EQUS.MINI` offers aggregated BBO but no venue sequence or deeper depth; `XNAS.ITCH` offers strong sequencing/depth but only the Nasdaq venue.
- `EQUS.MINI` one-second BBO can be stale and too wide for a reliable broad-stock midpoint return. OHLCV trade closes are used for Tier A returns; spread/depth outputs retain quality flags.
- Analyst consensus and cross-sectional dispersion need a licensed vintage source such as Bloomberg survey data, Refinitiv, FactSet, or Haver. Alpha Vantage economic series are not substitutes.
- Alpha Vantage publication timestamps have second resolution in this sample, but source checks reveal multi-hour errors. Six stories now have corrected or confirmed source clocks and complete tick-data event/control windows; every additional story still needs the same gate.
- The broad Alpha Vantage `financial_markets` topic query reached its 1,000-result ceiling. Ticker-specific histories did not.
- The Q&A marker must come from validated official video/caption time rather than an approximate transcript line.

## Submission artifacts and next recommended step

The current paper draft is `paper/research_paper.md`, and the rendered submission PDF is `output/pdf/how_markets_absorb_news.pdf`; reproducible CSV and LaTeX tables are in `tables/`, with figures in `figures/paper/`. The next empirical expansion should add a vintage consensus/dispersion source for H3/H5/H6 and source-verify more corporate announcements. The code required for mechanism, speed, liquidity, news controls, and deeper-book analysis is reusable; the binding limitation is vintage event metadata and exact news clocks, not OHLCV or plotting code.

The main empirical summary is in `reports/pilot_results.md`; proposal coverage is tracked in `reports/proposal_progress.md`; subsecond timing is documented in `reports/price_discovery_results.md`; timestamp details are in `reports/timestamp_validation.md`; the news quality audit is in `reports/alpha_vantage_news_audit.md`; and the unscheduled-news result is in `reports/unscheduled_news_pilot.md`.
