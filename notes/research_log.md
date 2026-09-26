# Research log

## 2026-09-23 — Initial feasibility pass

- Read and visually checked all 10 pages of `proposal.pdf`.
- Preserved the proposal's Q1 decomposition; one-second bars are not treated as a substitute.
- Verified the core pilot releases from BLS, Census, and Federal Reserve archival pages.
- Confirmed September 17 contains distinct 2:00 p.m. EDT statement and SEP arrivals plus a 2:30 p.m. press conference. A precise Q&A boundary is not yet established from the official transcript/video.
- Official agency pages do not supply the real-time consensus distribution needed for standardized surprises and H3. Expected values and dispersion remain missing, not imputed.
- Databento documents `ts_event` as exchange/matching-engine event time and `ts_recv` as capture receipt time. Historical filtering can use `ts_recv`; analysis must re-filter on `ts_event`.
- `EQUS.MINI` has aggregated MBP-1 but anonymized venues and `sequence=0`. It is useful for broad-stock top-of-book work, but same-timestamp sequencing ambiguities must be flagged.
- `XNAS.ITCH` provides Nasdaq single-venue full depth and sequence information. It is strong for Nasdaq-listed deep-book pilots but is not consolidated NBBO.
- `GLBX.MDP3` is the preferred feed for ES/NQ/ZN and supplies full-depth CME data. For September 17, equity-index futures were already past the customary September 15 roll; the December contracts should be validated through Databento definitions/continuous mappings before retrieval.
- Provider credentials were absent from the process environment during this pass. No authenticated metadata, cost estimates, or market payloads were downloaded.
- All 22 proposed stocks were S&P 500 members during the pilot. WMT traded on NYSE during the pilot; its later Nasdaq transfer must not be back-applied.
- Calendar parsing and synthetic mechanism edge cases passed a local manual validation. The base environment did not include `pytest`; the reproducible test command works after installing `requirements.txt`.
- Both provider commands were exercised without credentials and failed before any API request, without printing a secret.
- WRDS lists `ravenpack_trial` as ending 2020-12-31. It cannot supply September 2025 news; retain it only for schema/prototype work or obtain a current RavenPack edition.
- The separate statement and SEP rows share the exact same 18:00:00 UTC timestamp. They are separable as documents, not as price treatments in this meeting; the first market analysis must label the response as a joint bundle.

## 2026-09-23 — Alpha Vantage selected as pilot news provider

- Alpha Vantage `NEWS_SENTIMENT` is now the primary source for company news, relevance, sentiment, and contamination flags; RavenPack and Bloomberg are not required for the pilot news dataset.
- Retrieval is one request per ticker plus separate monetary-policy, macro, and financial-market topic requests. Alpha Vantage documents comma-separated filters as simultaneous/co-occurring filters, so combining the universe or topics in one query would omit most relevant stories.
- Implemented immutable cached retrieval for the full September 8–19 window, normalized article-ticker Parquet output, query-coverage auditing, duplicate-title grouping, and event-by-stock contamination flags.
- Provider timestamps are stored in UTC with inferred precision, but are labeled `provider_publication_time_unverified`; no story is admitted as an exact unscheduled-event clock until a source-level first-publication check succeeds.
- `ALPHAVANTAGE_API_KEY` was not visible in the process environment, so no authenticated request was made in this update. The key pasted in chat was not copied into source, commands, or project files.

## Open researcher decisions

- Choose/licence a vintage-consensus source with cross-sectional forecasts (Bloomberg survey, Refinitiv/I/B/E/S, FactSet, Haver, or equivalent) for expected values and dispersion.
- Decide whether baseline equity Q1 should be consolidated (`EQUS.MINI`, weaker sequencing) or venue-specific (`XNAS.ITCH`, stronger sequencing but not NBBO).
- After authenticated cost estimates, select the narrowest MBP-1/MBO windows that cover the statement and press conference without crossing the equity-index roll ambiguity.

## 2026-09-23 — Authenticated pilot execution

- Stored both provider keys only in the Git-ignored `.env` and set file mode `0600`. Databento account name/user ID were not used.
- Authenticated Databento discovery confirms `GLBX.MDP3`, `XNAS.ITCH`, and `EQUS.MINI` are available. All requested pilot estimates were $0.00 under the account.
- Executed ten bounded requests totaling 1,904,697 records and about 41 MB compressed. The smaller six-minute Retail Sales file is retained immutably but superseded analytically by the extended 15-minute request.
- Databento marks `GLBX.MDP3` on 2025-09-17 as `degraded`. All FOMC futures outputs are explicitly provisional. September 10 and September 16 are marked available.
- FOMC five-second midpoint returns were approximately 16.30 bp (ES), 15.37 bp (NQ), and 19.97 bp (ZN), despite zero literal first-quote revision in ES/ZN and a trade-before-quote failure in NQ.
- Final-minute touch-depth ratios were 0.167 (ES), 0.691 (NQ), and 0.126 (ZN), versus matched-placebo ratios of 1.191, 1.041, and 0.983. This is strong pilot evidence for scheduled liquidity withdrawal, not yet a statistical test.
- Retail Sales on an available-quality day gives mechanically eligible ES/NQ observations. Both have zero first-quote revision. At 60 seconds the pre-event linear-flow calibration covers only 9.7% of the ES move and has the wrong sign for NQ; the residual dominates.
- Completed all 25 Alpha Vantage news requests: 3,006 raw article occurrences, 1,811 canonical unique articles, 3,964 article-ticker rows, 627 sources, and zero timestamp parse failures.
- Found and fixed two material news issues: comma-separated filters use AND semantics, and tracking query parameters created hundreds of duplicate MarketWatch URLs. Also added alias/relevance screening after observing false ticker associations.
- Alpha Vantage publication timestamps are second-resolution in the response, but every story remains ineligible as an exact unscheduled event until its first-publication semantics are checked against the originating source.

## 2026-09-23 — Scheduled-event and cross-sectional expansion

- Added bounded MBP-1 windows for PPI, CPI, industrial production, housing, and September 9 matched clocks. All estimates were $0.00; no MBO data were requested.
- Centralized processed-event metadata in `config/pilot_events.yaml` so timestamp, representation, and provider-condition flags no longer live in multiple scripts.
- The canonical panel now has 3,782,492 rows and 33 event-instrument pairs. Dynamic flow, residual, and mechanism-share fields use instrument-specific leave-one-event-out coefficients rather than the focal event's own move.
- Seven futures event-instrument cases are both mechanically valid and on available-quality days: PPI NQ/ZN, CPI ES, Retail Sales ES/NQ, and industrial-production ES/NQ/ZN.
- PPI and CPI have 60-second absolute responses materially above the September 9 8:30 a.m. control; industrial production does not. FOMC remains strong relative to the Wednesday 2:00 p.m. control but is provider-degraded.
- Added a 22-stock one-second FOMC panel. `EQUS.MINI` BBO snapshots produced false midpoint jumps for wide/stale books, so broad returns now use OHLCV trade closes. BBO spread/depth remain diagnostic and receive a wide/stale flag above 50 bp.
- The leave-one-event-out flow fits use 2,880–3,360 one-second intervals from six or seven other events. Residual price adjustment remains large in many cases; this is a substantive result and not normalized away.
- Official BLS and Census calendars list no September 9 release at 8:30 or 9:15 a.m. ET; listed releases begin at 10:00 a.m. The Federal Reserve G.17 release schedule confirms industrial production was September 16, not September 9.

## 2026-09-24 — News clock validation

- Source-checked three high-relevance Alpha Vantage stories. The Meta quarterly-dividend story is the decisive failure case: Alpha Vantage reports 2025-09-11 10:57:28 UTC, while the originating PR Newswire page reports 16:35 ET / 20:35 UTC. The provider timestamp is 34,652 seconds early.
- The Microsoft source page exposes only a publication date and the Broadcom page did not expose a usable time. Neither is eligible as a precise unscheduled event.
- Added source-time validation fields without overwriting provider data. Contamination matching prefers a verified source time and otherwise uses the unverified provider time conservatively.
- Correcting the Meta timestamp removed a false CPI contamination flag: the dividend release was actually after the close.
- Added a one-second ES/NQ/ZN FOMC lead–lag screen. Every pair's maximum absolute return correlation occurs at lag zero, so no stable Q3 leader is resolvable at one-second frequency.

## 2026-09-24 — Objective stock-sensitivity screen

- Added zero-cost `ohlcv-1d` histories for 22 stocks plus SPY and ES/NQ/ZN from September 2024 through September 19, 2025. Total Databento usage is now 19 bounded requests, 3,429,711 records, 74,079,368 compressed bytes, 443,228,440 estimated billable bytes, and $0.00 estimated account cost.
- Estimated each stock's daily return on SPY and the ZN futures price return using 240 non-event observations; all 9 FOMC decision dates and 13 CPI release dates in the sample were excluded from coefficient estimation.
- The market-beta ranking supports the original high-beta interpretation for TSLA, AMD, NVDA, and AVGO. AMT and PLD have the strongest positive ZN-price betas, consistent with benefiting when intermediate yields fall.
- The growth basket's conditional ZN coefficient is negative on average after controlling for SPY. This may reflect correlated-factor interpretation and the one-year sample; it is documented rather than relabeled as a causal duration effect.
- Daily abnormal absolute-return ratios identify MSFT/META/GOOGL/NVDA as especially elevated on FOMC days and HD/NVDA/WMT/XOM on CPI days. With only 9 and 13 dates and no vintage surprises, these outputs are ranking diagnostics, not H5/H6 tests.

## 2026-09-24 — Source-verified unscheduled-news pilot

- Audited two additional Alpha Vantage clocks. The Google Cloud/Qualcomm release appears at 08:30 UTC in Alpha Vantage but the source says 08:30 ET, a four-hour error. NVIDIA's Intel partnership/investment appears as midnight UTC; GlobeNewswire gives 07:00 ET / 11:00 UTC, an eleven-hour error.
- Added the verified source times without overwriting provider fields. The NVIDIA article has NVDA relevance 1.00 and bullish ticker sentiment 0.429 in Alpha Vantage, making it a strong discovery candidate once the clock is corrected.
- Downloaded a zero-cost 15-minute NVDA `XNAS.ITCH` MBP-1 window around the NVIDIA release and a zero-cost prior-day same-clock control. Total Databento usage is now 21 requests, 3,445,449 records, 74,417,827 compressed bytes, 444,765,400 estimated billable bytes, and $0.00 estimated account cost.
- The first valid quote at +11.886 ms was unchanged. The first trade and first nonzero quote change occurred at +88.547 ms. Returns were -6.31 bp at 500 ms, +30.64 bp at 30 seconds, +15.76 bp at 60 seconds, and -3.44 bp at five minutes.
- A one-second flow coefficient trained only on 898 prior-day placebo intervals has R-squared 0.148 and materially overshoots the 30- and 60-second response. The residual remains large, so the result validates the workflow but not a stable mechanism estimate.
- Added the news event and its placebo to the canonical event panel. It now has 3,798,230 rows and 35 event-instrument pairs.

## 2026-09-24 — Multi-meeting FOMC sample and matched-control inference

- Downloaded eight additional 45-minute `GLBX.MDP3` MBP-1 meeting windows for ES/NQ/ZN from September 2024 through July 2025. September 2024 is provider-degraded and excluded from primary inference; seven meetings remain.
- Added fourteen 15-minute same-clock control windows. The portfolio estimate was 548.61 MiB and $0.00. March 12 and June 11, 2025 were rejected during calendar validation because the Monthly Treasury Statement was scheduled for exactly 2:00 p.m. ET.
- Total Databento usage is now 43 immutable requests, 23,235,384 records, 520,334,981 compressed bytes, 2,234,068,840 estimated billable bytes, and $0.00 estimated cost.
- The primary FOMC sample has 21 statement-instrument and 21 press-instrument observations. Fifteen statement observations and eighteen press observations pass the literal no-intervening-trade requirement.
- At 60 seconds, twelve of fifteen eligible statement cases and fifteen of eighteen eligible press cases have zero literal first-quote revision. Leave-one-meeting-out flow fits explain part of the move but leave material residuals.
- Relative to the five-minute return, median statement 50% crossing times are 10 seconds for ES, 12.5 for NQ, and 5 for ZN. Press-opening medians are approximately 95, 95, and 11 seconds. Overshoots and reversals make first crossing a descriptive speed measure.
- The meeting-cluster touch-depth ratio averages 0.571 before FOMC statements versus 1.011 at matched clocks. Every one of the seven meeting differences is negative; one-sided sign and Wilcoxon p-values are 0.0078. ZN is strongest, ES is also significant by Wilcoxon, and NQ alone is weaker.
- Created paper-facing CSV/LaTeX tables, three publication figures, and a manuscript draft. H3, H5, and H6 remain unidentified without a licensed vintage consensus/dispersion source; no proxy was invented.

## 2026-09-24 — Eight-month macro sample and matched controls

- Verified and retrieved 31 unique 11-minute `GLBX.MDP3` MBP-1 macro windows for ES/NQ/ZN, representing 32 official CPI, PPI, Employment Situation, and retail-sales releases from January-August 2025. All requests were cost-gated and estimated at $0.00.
- Preserved the May 15 simultaneous PPI/retail-sales release as one market-arrival bundle and stored other known concurrent releases rather than attributing the response to one headline.
- The macro sample contains 93 event-instrument timing observations; 64 satisfy the literal no-intervening-trade rule. Sixty of 93 first valid post-event quotes are unchanged.
- At five minutes, scalar releases have a median absolute first-quote fraction of zero in ES, NQ, and ZN. No scalar observation exceeds the proposal's 70% H1 benchmark. Opposite-direction Wilcoxon p-values are 0.00049, 0.0156, and 0.00012.
- Added eight exact-8:30 controls screened against BLS, Census, BEA, and Federal Reserve calendars. January 7 was rejected because international trade was released at that clock; January 8 was used.
- Corrected the placebo inference for reuse of one control within each month. Tests aggregate first to eight month clusters rather than treating 31 comparisons as independent. The all-instrument depth ratio is 0.678 on event mornings versus 0.969 at controls; seven of eight monthly differences are negative (sign p=0.0352, Wilcoxon p=0.0078).
- ES averages 0.718 versus 1.007 (Wilcoxon p=0.0078), ZN 0.232 versus 0.911 (p=0.0039), and NQ 1.083 versus 0.991 (no withdrawal evidence). This heterogeneity is retained in the paper.
- Databento usage now totals 82 immutable requests, 33,108,263 records, 737,984,074 compressed bytes, 3,509,408,680 estimated billable bytes, and $0.00 estimated cost.
- Expanded the manuscript and rendered paper to include macro H1, response distributions, and matched liquidity evidence. H3/H5/H6 remain unestimated because no vintage analyst-consensus distribution is available.

## 2026-09-24 — Six-part publication expansion

- Added 46 available-quality 2024 macro bundles, yielding 77 bundles, 80 official releases, and 231 ES/NQ/ZN observations from January 2024-August 2025. Of these, 148 pass the literal Q1 sequencing rule and 144 have an unchanged first post-event quote.
- In the pooled scalar sample, median absolute five-minute first-quote shares remain zero and no observation exceeds 70%. Opposite-direction Wilcoxon p-values are 2.98e-8 (ES), 4.77e-7 (NQ), and 4.66e-10 (ZN).
- Added five early-2024 FOMC meetings and ten matched clocks. Primary FOMC inference now uses 12 clean meetings and 24 controls. The meeting-average depth ratio is 0.563 versus 1.026; all 12 paired differences are negative (sign and Wilcoxon p=0.00024).
- Added 100/250/500 ms leave-one-bundle-out flow models. Lagged-depth conditioning raises pre-event R-squared by 0.014-0.078 but improves median event-window error in only 11 of 27 cells, so it is retained as a robustness model rather than replacing the linear baseline.
- Downloaded nine cost-gated MBP-10 event-instrument windows. Level-5 and level-10 final-minute depth are below baseline in 8 of 9 observations. NQ before the August employment release is the important counterexample.
- Expanded Alpha Vantage to 22 ticker histories from January-September 2025. The normalized corpus has 10,005 unique articles and 30,406 article-ticker rows; four tickers hit the 1,000-result cap.
- Selected 44 corporate-news candidates across all stocks and six categories. Source-page timestamps were extractable for 21, but only three were within five minutes of Alpha Vantage and the median absolute discrepancy was 8.4 hours. Automated source metadata remain review evidence, not certified arrival times.
- Added descriptive news contamination/sentiment controls to the 220-row FOMC stock screen. Neither term is statistically distinguishable from zero; the result is documented as robustness, not causal sentiment evidence.
- Databento usage now totals 152 immutable requests, 65,383,293 records, 1,462,574,579 compressed bytes, 7,870,357,880 estimated billable bytes, and $0.00 estimated account cost.

## 2026-09-24 — Twenty-month macro matched controls

- Screened one 8:30 a.m. Eastern control per month from January 2024 through August 2025 against official BLS, Census, BEA, and Federal Reserve calendars. Rejected initially plausible June 26, July 24, and September 25, 2024 dates because official BEA or Census releases occurred at the same clock.
- Cost-estimated twelve new 11-minute `GLBX.MDP3` MBP-1 windows for ES/NQ/ZN at 134.41 MiB and $0.00, then stored immutable DBN files and manifests.
- Formal macro placebo inference now uses twenty independent month clusters and all 231 event-instrument observations. The all-instrument event/control depth ratios are 0.623/0.976; nineteen of twenty paired differences are negative (sign p=0.000020, Wilcoxon p=0.0000019).
- ES is lower in 19/20 months (0.570 versus 0.999; Wilcoxon p=0.0000019), ZN in 20/20 (0.211 versus 0.934; sign and Wilcoxon p=0.00000095), while NQ remains a deliberate counterexample (1.088 versus 0.996).
- Databento usage now totals 164 immutable requests, 66,364,091 records, 1,484,292,264 compressed bytes, 8,011,300,040 estimated billable bytes, and $0.00 estimated account cost.

## 2026-09-24 — Second source-verified corporate-news case

- Verified Meta's September 11, 2025 dividend declaration against the original PR Newswire distribution at 16:35 ET / 20:35 UTC. Alpha Vantage's provider clock is 9 hours 37 minutes 32 seconds early.
- Retrieved event and prior-week same-weekday control `XNAS.ITCH` MBP-1 windows after separate cost estimates of 9.06 KiB and 7.81 KiB, both $0.00.
- The after-hours event is mechanically ineligible: the first post-event market message arrives 28.799 seconds after the source clock and a sell trade intervenes before the first quote. The midpoint is unchanged through five seconds, -1.46 bp at one minute, and +1.60 bp at five minutes.
- The canonical panel now contains 3,798,344 rows and 37 event-instrument pairs. Databento usage totals 166 requests, 66,364,205 records, 1,484,295,357 compressed bytes, 8,011,317,320 estimated billable bytes, and $0.00 estimated cost.

## 2026-09-24 — Subsecond FOMC price-discovery location

- Added message-level first-crossing diagnostics at absolute 0.5, 1, and 2 basis-point thresholds for ES, NQ, and ZN across all twelve clean meetings and both FOMC sub-events.
- Added pairwise 100 millisecond return correlations over +/-1 second. ES/NQ best absolute correlation occurs at zero lag in all twelve meetings for both statement and press windows; median absolute correlations are 0.844 and 0.822.
- After statements, median 1 bp crossing delays are 129 ms (ES), 213 ms (NQ), and 1,006 ms (ZN). ES is earlier than NQ in 10/12 meetings (sign p=0.019; Wilcoxon p=0.065).
- The ranking is not stable at press openings or every threshold. ZN equal-basis-point comparisons also mix response speed and scale. The paper therefore reports descriptive cross-asset timing and explicitly does not label it a Hasbrouck information share.
- A final credential scan found the Alpha Vantage token embedded once in a provider-returned article `banner_image` URL inside the raw news cache. The token was replaced with a redaction marker, and the adjacent file-size/checksum metadata were updated with an explicit security-redaction audit record. A repeat repository scan was clean outside `.env`.

## 2026-09-24 — Six-case source-verified corporate-news sample

- Added exact original-wire clocks for NVIDIA Q4 FY2025 earnings, AMD's $6 billion buyback, and the Absci/Oracle/AMD collaboration. Together with Google-Qualcomm and the two prior cases, the sample now has six source-verified event/control pairs.
- Cost-estimated eight new `XNAS.ITCH` MBP-1 windows at 7.00 MiB and $0.00, then downloaded and processed them. Every matched clock has Alpha Vantage ticker coverage and zero direct high-relevance article within one hour.
- Three of six events pass the literal no-intervening-trade requirement. NVIDIA earnings (+331.5 bp at 60 seconds) and AMD buyback (+143.8 bp) are economically largest but sequence-ineligible because a trade precedes the first quote.
- All five nominally unscheduled cases have lower final-minute touch-depth ratios than their matched clocks (mean 0.448 versus 1.568; paired sign and Wilcoxon p=0.03125). This is a selected small sample, but it prevents any claim that the current evidence proves withdrawal is unique to scheduled events.
- Rebuilt the canonical panel to 3,883,960 rows and 45 event-instrument pairs.
- Databento usage now totals 174 immutable requests, 66,449,821 records, 1,485,951,736 compressed bytes, 8,018,652,760 estimated billable bytes, and $0.00 estimated cost.

## 2026-09-24 — Final proposal-status and submission wrap-up

- Added formal H2 tests: every mechanically eligible 60-second statement observation (23/23) and press observation (28/28) has an absolute literal first-quote fraction below 40%; one-sided Wilcoxon p-values are 0.0000042 and 0.00000035.
- Added paired statement-versus-press speed tests. The 50% crossing is faster after statements in ES, NQ, and ZN by Wilcoxon tests (p=0.0068, 0.0137, 0.0137), while stable-within-10% differences are not significant.
- Added reproducible Q1-Q5 and H1-H6 status tables plus `reports/submission_readiness.md`. The paper now distinguishes rejected, supported, insignificant, and unidentified claims.
