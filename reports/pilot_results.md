# Pilot empirical results

## Data acquired

Twenty-one Databento requests were executed only after cost estimation. Their estimated account cost was $0.00. They contain 3,445,449 records, about 74.4 MB compressed on disk, and approximately 445 MB of estimated billable data. The bounded downloads cover FOMC statement/SEP and press-conference windows; PPI, CPI, Retail Sales, industrial production, and housing; matched clocks at 8:30 a.m., 9:15 a.m., and 2:00 p.m. ET; one-second BBO/OHLCV for the 22-stock FOMC cross-section; daily stock/futures bars from September 2024 through the pilot; and a source-verified NVDA unscheduled-news window plus prior-day control.

The canonical event-time panel contains 3,798,344 message rows across 37 event-instrument pairs and occupies about 176 MB as Parquet. It contains 222,780 trades; 212,709 have an explicit buyer/seller aggressor side and 10,071 remain unknown rather than being imputed. For futures events with a leave-one-event-out impact estimate and for the mechanically eligible source-verified NVIDIA case, the panel carries dynamic quote-revision, cumulative fitted-flow, residual, and mechanism-share fields.

The continuous contracts resolve on September 17 to ESZ5, NQU5 until the September 18 mapping change to NQZ5, and ZNZ5. ES had already mapped from ESU5 to ESZ5 on September 17.

## Price response and sequencing

The joint FOMC statement/SEP bundle caused a fast response but not always a literal first-message jump. Five-second responses were 16.30 bp in ES, 15.37 bp in NQ, and 19.97 bp in ZN; 60-second responses were 10.12, 5.88, and 15.16 bp. At the press-conference opening the corresponding 60-second responses were -6.00, -6.61, and -4.13 bp, supporting separate treatment of the two arrivals.

The added scheduled releases broaden the comparison:

| Event | ES 60s (bp) | NQ 60s (bp) | ZN 60s (bp) |
|---|---:|---:|---:|
| PPI | 19.09 | 21.02 | 13.10 |
| CPI bundle | 8.96 | 8.30 | 24.08 |
| Retail Sales bundle | -2.45 | -2.05 | -6.89 |
| Industrial Production | 0.38 | 0.21 | 0.00 |
| Housing | 1.69 | 2.01 | 0.00 |

Seven futures event-instrument observations pass both the no-intervening-trade rule and the provider-quality rule: PPI NQ/ZN, CPI ES, Retail Sales ES/NQ, and all three industrial-production contracts. Housing and FOMC futures observations remain provisional because Databento marks September 17 `degraded`. The pipeline retains all failed observations with reasons instead of silently dropping or repairing them.

## Liquidity and matched placebos

Before the FOMC statement, average touch depth in the final 60 seconds relative to the earlier baseline was 0.167 for ES, 0.691 for NQ, and 0.126 for ZN. At the same Wednesday 2:00 p.m. clock on the matched non-event day, the ratios were 1.191, 1.041, and 0.983.

September 9 at 8:30 and 9:15 a.m. ET provides additional controls. Official BLS and Census calendars list no release at those clocks; their listed September 9 releases begin at 10:00 a.m. ET. Relative to the matched clock, mean 60-second absolute-return differences across ES/NQ/ZN are +14.76 bp for PPI, +10.80 bp for CPI, +0.82 bp for Retail Sales, -0.31 bp for industrial production, and +8.94 bp for the FOMC statement. Housing is -1.75 bp and is on a degraded data day. CPI, Retail Sales, and the statement also show materially lower pre-event depth than their controls. These are pilot comparisons, not hypothesis tests.

## Leave-one-event-out mechanism estimates

The preferred exploratory order-flow coefficient is instrument-specific and estimated on pooled one-second pre-event intervals from the other available-quality events and placebos. Each focal event is excluded from its own training set. The fits use 2,880–3,360 intervals from six or seven training events, with in-sample R-squared around 0.2–0.3.

For the clean Retail Sales cases at 60 seconds:

| Instrument | Total move (bp) | First quote (bp) | Fitted flow (bp) | Residual (bp) | Component coverage | Mechanism share |
|---|---:|---:|---:|---:|---:|---:|
| ES | -2.45 | 0.00 | -0.07 | -2.38 | 2.7% | 0.00 |
| NQ | -2.05 | 0.00 | 0.08 | -2.13 | -3.8% | 0.00 |

The numerical mechanism share is zero because the first valid post-arrival quote did not move. It does not mean order flow explains everything: component coverage shows that fitted flow explains little and has the wrong sign for NQ. The residual is therefore economically central. PPI also illustrates why pathological values are retained: ES has opposing quote and flow signs and fails the sequencing rule, so its share is outside the unit interval and flagged rather than normalized away.

## Stock cross-section

The 22-stock FOMC screen uses `EQUS.MINI` one-second OHLCV trade-bar closes for returns and volume. At 60 seconds after the statement, returns range from -3.51 bp for NVDA to +37.67 bp for CAT. After the press-conference opening most growth/high-beta names fall, including AMZN -19.03 bp, AMD -19.01 bp, TSLA -16.61 bp, and NVDA -8.82 bp. These are exploratory raw responses, not beta-adjusted causal estimates.

`EQUS.MINI` one-second BBO is not reliable enough to use as the broad cross-sectional return source: several less-active names show stale or hundreds-of-basis-points-wide books. The code now uses trade-bar prices for returns and retains BBO spread/depth only with explicit `wide_or_stale_eq_us_mini_bbo` flags. This limitation does not affect the CME message-level futures analysis.

### Measured historical sensitivities

The project now measures rather than assumes the universe labels. Daily regressions from September 2024 through September 2025 use SPY return and the ZN futures price return as joint factors and exclude 9 FOMC decision days plus 13 CPI release days from coefficient estimation. TSLA has the largest market beta (2.26); AMD, NVDA, and AVGO are also high at 1.75–2.00. The real-estate pair has the largest positive ZN-price beta (AMT 2.00, PLD 1.07), consistent with sensitivity to falling intermediate yields. After controlling for SPY, the growth basket instead has a negative average ZN-price coefficient (-0.53). This is a conditional daily association, not a structural duration estimate, and is retained even though it complicates the original theme label.

Daily market-and-ZN-adjusted absolute residuals are descriptively elevated on FOMC days for MSFT (2.77 times its ordinary-day mean), META (1.69), GOOGL (1.60), NVDA (1.58), AMT (1.54), and JPM (1.40). CPI-day ratios are largest for HD (1.86), NVDA (1.69), WMT (1.40), XOM (1.34), and AMD/PLD (1.32). Across themes, the median ratio is 1.36 for growth names on FOMC days and 1.40 for consumer names on CPI days. These 9- and 13-day samples are ranking diagnostics, not inferential tests, and contain no analyst-surprise measure.

## Coarse price-discovery location

A one-second ES/NQ/ZN return lead–lag screen around the FOMC statement and press-conference opening finds each pair's maximum absolute correlation at lag zero. At this resolution there is no stable leader: the common response is effectively contemporaneous. This is a useful negative pilot result, not the proposal's definitive Q3 test. Sub-second synchronized prices and the planned Hasbrouck/permanent–transitory estimators are still needed, and September 17 is provider-degraded.

## Source-verified unscheduled news

Alpha Vantage discovered and scored NVIDIA's September 18 Intel partnership/investment announcement as bullish with NVDA relevance 1.00, but its timestamp is midnight UTC. The originating GlobeNewswire release is stamped 07:00 ET / 11:00 UTC, making the provider clock eleven hours early. A zero-cost NVDA `XNAS.ITCH` MBP-1 window and prior-day same-clock control complete the first end-to-end unscheduled case.

A second case uses Meta's September 11 dividend declaration at the original PR Newswire clock of 16:35 ET. The after-hours Nasdaq sequence is sparse: no message arrives for 28.799 seconds and a trade intervenes before the first quote. The one-minute move is -1.46 bp versus zero at the matched clock. It is a useful source-verified counterexample but not eligible for the primary mechanism estimate.

The first valid post-release quote arrived after 11.886 ms and was unchanged. The first trade and first nonzero quote change occurred at 88.547 ms, so the literal pre-trade quote component is zero. NVDA moved -6.31 bp by 500 ms, +30.64 bp by 30 seconds, +15.76 bp by one minute, and -3.44 bp by five minutes. The prior-day values were +7.83, +6.38, +4.06, and +11.60 bp. A placebo-trained order-flow fit substantially overshoots the 30- and 60-second response and leaves large residuals; this is a feasibility success, not a stable causal decomposition.

## Feasibility conclusion

The empirical object is implementable with Databento MBP-1, explicit aggressor side, and exchange event timestamps. The pilot now supports Q1 mechanics, Q2 representation comparisons, Q4 liquidity/placebo diagnostics, a preliminary stock cross-section, and two source-verified corporate-news cases. Three limits remain substantive: first-quote eligibility is selective, the quote-plus-flow model can leave a dominant residual, and one September 17 futures day is provider-degraded.

The next statistically meaningful expansion is additional release months and FOMC meetings, needed for inference and to separate representation class from event identity. Analyst-consensus dispersion is still required for H3. MBO is not yet necessary for baseline Q1 and should be reserved for selected deeper-book Q4 windows.
