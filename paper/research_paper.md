# How Markets Absorb News

## Quote Revision, Signed Order Flow, and Liquidity Withdrawal Across Macro and FOMC Announcements

### Abstract

This paper studies how public information becomes a market price. It uses exchange-time, message-level CME data for E-mini S&P 500 (ES), E-mini Nasdaq-100 (NQ), and 10-year Treasury note (ZN) futures around 77 scheduled macro announcement bundles from January 2024 through August 2025 and twelve clean Federal Open Market Committee meetings from January 2024 through July 2025. The analysis separates the first valid pre-trade quote revision from later price adjustment associated with explicitly signed order flow. Contrary to the proposal's scalar-news benchmark, the literal first quote contributes a median of zero percent of the five-minute macro response; the one-sided tests strongly reject a quote fraction above 70%. Sub-second and liquidity-conditioned order-flow calibrations improve pre-event fit but do not uniformly improve event-window prediction, so a material residual is retained. Written FOMC statements produce faster price discovery than press-conference openings. Matching the twelve meetings to USMPD high-frequency policy surprises rejects the proposal's speed-magnitude prediction for statements: larger statement surprises are reached faster, not slower (meeting-average Spearman rho = -0.79, two-sided p = 0.002), and hawkish-slower asymmetry appears only in equity first crossings after press openings. At 100 millisecond resolution, ES and NQ return correlations peak at zero lag in all twelve meetings; first-material-move thresholds provide limited ES-leading evidence after statements but no universal leader. Displayed touch depth falls before scheduled information: the FOMC ratio is 0.563 versus 1.026 at controls, and the twenty-month macro ratio is 0.623 versus 0.976. A six-case source-verified corporate-news sample adds a caution: all five nominally unscheduled events also have lower depth than their matched clocks (0.448 versus 1.568; p = 0.031), so scheduled-event specificity is not established. The evidence supports strategic liquidity withdrawal while rejecting a mechanically simplistic interpretation of the first displayed quote as the dominant public-signal channel.

## 1. Introduction

Most announcement studies compare prices before and after a release. That design measures the magnitude of the response but discards the path by which the new price is reached. Two announcements can generate the same five-minute return while operating through different market mechanisms. Dealers may revise displayed quotes immediately upon seeing a public signal, before any transaction occurs. Alternatively, the market may learn from the signed trades of participants who interpret the signal differently. The distinction matters because it links the observed price path to disagreement, adverse selection, and liquidity provision.

This paper implements the proposal's primary mechanism directly. For each event and instrument, it identifies the last valid quote before the official release time and the first valid quote after it, conditional on no intervening trade. It then estimates a Kyle-style relationship between short-interval returns and explicit signed order flow using other meetings, and applies that coefficient to post-event flow. The difference between the observed return and the two measured components is retained as a residual.

The completed samples cover two complementary settings. The macro panel contains 80 official CPI, PPI, Employment Situation, and retail-sales releases from January 2024 through August 2025. Three simultaneous-release dates leave 77 distinct arrival clocks. The FOMC panel offers a within-day contrast between the written statement at 2:00 p.m. Eastern and the press conference at 2:30 p.m. The repository also contains a September 2025 pilot, a 22-stock cross-section, a 44-event corporate-news audit sample, and six source-verified corporate-news event/control pairs. The main inference in this draft uses 231 macro event-instrument observations and twelve clean FOMC meetings.

Three results stand out. First, the literal first valid quote revision is usually zero in both numeric macro and FOMC samples. The public signal is not captured by a single gap in the first eligible top-of-book record. Second, signed flow is related to subsequent returns but does not exhaust the observed adjustment; residual changes are economically important. Third, displayed depth withdraws sharply before scheduled releases, especially in ZN. This result survives independently screened exact-clock controls in both samples.

## 2. Data and Event Construction

### 2.1 Market data

The primary market data are Databento `GLBX.MDP3` MBP-1 records for ES, NQ, and ZN futures. MBP-1 preserves each top-of-book update and trade with nanosecond exchange event timestamps, receipt timestamps, bid and ask prices, displayed sizes, sequence information, and aggressor side where supplied by CME. The analysis orders records by exchange event time and sequence. Vendor receipt time is used only for latency diagnostics.

The macro sample contains 77 distinct 11-minute windows from 8:25 to 8:36 a.m. Eastern. Official BLS and Census calendars verify 20 releases each for CPI, PPI, employment, and retail sales; simultaneous-release dates are treated as bundles. Simultaneous Real Earnings, Import/Export Prices, and International Trade releases are recorded as contamination metadata rather than ignored. All 77 windows have available provider condition. The FOMC sample contains thirteen cached meetings from January 2024 through July 2025 plus the separately retained September 2025 pilot. September 18, 2024 is excluded because Databento marks it degraded, leaving twelve meetings for primary inference. Standard meeting requests span 1:55 to 2:40 p.m. Eastern. Twenty-four FOMC controls cover matched 2:00 p.m. clocks, while twenty macro controls cover one screened 8:30 a.m. clock for every month from January 2024 through August 2025. Raw files are immutable and have provider, schema, symbol, request window, library version, record count, file size, and checksum metadata.

### 2.2 Events and matched controls

Statement and press-conference timestamps come from the Federal Reserve's official FOMC calendar. Summary of Economic Projections releases occur simultaneously with the statement and cannot be separately identified from price data alone. They remain separate metadata concepts but form a joint 2:00 p.m. information bundle on SEP dates.

Placebos match the weekday and exact 2:00 p.m. Eastern clock time as closely as practical. Dates containing FOMC minutes, the Beige Book, the Senior Credit Officer Opinion Survey, or a 2:00 p.m. Monthly Treasury Statement are excluded. This screen caught two initially plausible but invalid control dates: March 12 and June 11, 2025 were both scheduled Monthly Treasury Statement releases. The primary comparison averages the clean controls for each meeting; a pre-Thanksgiving session is retained only as a secondary robustness observation.

Macro controls use exactly 8:30 a.m. Eastern and are screened against BLS, Census, BEA, and Federal Reserve release calendars. Candidate dates on June 26, July 24, and September 25, 2024 were rejected after that screen identified a BEA or Census release at the same clock. January 7, 2025 was rejected because international trade was released at that clock, and January 8 was used instead. Because each monthly control is reused for several releases, inference first averages announcements within month. The tests therefore have twenty independent month clusters rather than treating 77 event/control bundles as independent.

### 2.3 News data and unscheduled events

Alpha Vantage `NEWS_SENTIMENT` supplies article discovery, topic classification, relevance, and ticker-level sentiment; it is not used as the market feed. The cached January-September 2025 corpus contains 10,005 unique articles and 30,406 article-ticker rows. A stratified high-relevance audit sample contains 44 candidate announcements across all 22 stocks and six announcement categories. Source-page metadata were machine-extractable for 21 candidates, but only three clocks matched Alpha Vantage within five minutes and the median absolute discrepancy was 8.4 hours. Machine-extracted metadata are themselves review candidates, not automatic proof of first publication. The exact-event sample therefore admits a story only after validation against an originating company or wire page. Six completed event/control pairs cover NVIDIA-Intel, a Meta dividend, Google-Qualcomm, NVIDIA earnings, an AMD buyback, and an Absci/Oracle/AMD collaboration. Every matched clock has ticker-query coverage and zero direct high-relevance company articles within one hour. Alpha Vantage sentiment and relevance enter descriptive contamination controls; they do not replace a verified event clock.

## 3. Empirical Design

### 3.1 Immediate quote revision

Let `m-` be the midpoint of the final valid quote before the official release time and `m+` the midpoint of the first valid quote after it. The immediate quote component is:

`QR = log(m+ / m-)`.

The observation is eligible only if no trade intervenes. Locked or crossed books, missing quotes, a trade before the first post-event quote, same-timestamp ordering ambiguity, degraded provider condition, halts, and auctions are flagged rather than silently repaired. The proposal's literal first-valid-quote measure is primary. The last quote before the first post-event trade is reported as a declared robustness definition.

### 3.2 Signed-flow component and residual

Trades use the exchange-provided aggressor side. Returns are regressed on contemporaneous signed contract volume in pre-event intervals from other available-quality events. The baseline uses one-second intervals. Robustness models use 100, 250, and 500 millisecond buckets and interact signed flow with inverse lagged touch depth. Leaving the focal event out prevents its own response from determining its impact coefficient. For event `i` and horizon `h`, the fitted flow component is:

`OF(i,h) = beta(-i) * cumulative signed volume(i,h)`.

The residual is:

`RES(i,h) = total return(i,h) - QR(i) - OF(i,h)`.

The proposed mechanism share is `QR / (QR + OF)`. Near-zero denominators, opposing signs, reversals, and shares outside zero to one are retained as diagnostic outcomes. The decomposition is not normalized to force coverage of the observed return.

### 3.3 Speed and liquidity

Speed is measured relative to the midpoint return at five minutes. The analysis records the first crossing of 50% and 90% of that terminal move, the first time the path remains within 10% of it, and the maximum overshoot. Events with a terminal move below one basis point are flagged because percentage convergence becomes unstable.

For the proposal's price-discovery-location question, a complementary message-level test records the first post-event quote that crosses 0.5, 1, and 2 basis points in absolute value. It also resamples quote-to-quote returns onto a 100 millisecond grid and searches pairwise cross-correlations over leads and lags of one second. These are transparent timing diagnostics across different assets, not Hasbrouck information shares: ES, NQ, and ZN are not multiple trading venues for the same security, and an equal basis-point threshold need not represent an equal economic shock across them.

Liquidity is measured using displayed depth at the best bid and ask. The pre-event depth ratio equals mean touch depth in the final 60 seconds divided by mean touch depth from four minutes to one minute before the event. A ratio below one indicates withdrawal. Each meeting-instrument ratio is compared with the average of its clean matched controls. Because the meeting count is small, inference uses transparent paired sign and Wilcoxon tests rather than asymptotic panel standard errors.

For Hypothesis 1, the five-minute absolute quote fraction is the absolute first-quote revision divided by the observed five-minute adjustment, excluding total changes below 0.1 basis point. The pre-specified scalar-news benchmark is 70%. The analysis reports both the test in the hypothesized direction and the opposite-direction test; it does not reinterpret a near-zero mechanism denominator as evidence for either channel. Representation comparisons use scalar releases versus multi-dimensional employment and retail-sales releases, while the simultaneous May 15 bundle is kept separate.

## 4. Results

### 4.1 Macro announcement response and the scalar-news hypothesis

The 77 macro bundles generate heterogeneous but economically meaningful responses. At 60 seconds, median absolute CPI moves are 38.17 basis points in ES, 46.08 in NQ, and 28.41 in ZN. Employment medians are 20.33, 24.28, and 33.24 basis points; PPI medians are 13.96, 14.85, and 11.05; retail-sales medians are 3.42, 5.08, and 9.40. The cross-release ordering is descriptive because realized-minus-consensus surprises are not yet available.

The proposal's H1 benchmark is decisively unsupported under its literal quote definition. Among mechanically eligible scalar observations, the median absolute first-quote fraction of the five-minute move is zero in ES, NQ, and ZN, and no observation exceeds 70%. One-sided Wilcoxon tests in the hypothesized greater-than-70% direction return p = 1.000; tests in the opposite direction return p = 2.98e-8 for ES, 4.77e-7 for NQ, and 4.66e-10 for ZN. Multi-dimensional releases also have near-zero median fractions. A scalar-versus-multi-dimensional rank comparison is uninformative because both distributions concentrate at zero (one-sided p = 0.998).

Mechanically, 148 of 231 event-instrument observations satisfy the primary no-intervening-trade rule. One hundred forty-four of the 231 literal first post-event quotes are unchanged. The last-pretrade-quote robustness definition raises some quote revisions but retains a median of zero. These facts indicate that economically rapid adjustment occurs over a sequence of messages and trades, not in one universal first quote.

The sub-second robustness results sharpen, but do not overturn, the baseline. Across leave-one-bundle-out fits, liquidity conditioning raises median pre-event R-squared by 0.014 to 0.078 depending on instrument and frequency. Yet it lowers median event-window absolute error in only 11 of 27 frequency-instrument-horizon comparisons. Its clearest gains are for ES at five and sixty seconds; at five minutes it often overpredicts, and ZN is especially unstable. The extra state variable is therefore useful evidence of state-dependent impact, not a license to relabel the residual as order flow.

### 4.2 FOMC market response

Written statements generate economically important one-minute moves. Across the twelve usable meetings, median absolute 60-second responses are 17.11 basis points in ES, 18.99 in NQ, and 11.94 in ZN. Press-conference-opening responses are smaller: 3.66, 4.67, and 1.41 basis points, respectively. These values mask meaningful sign and date variation, which is reported in `tables/fomc_60s_returns.csv` rather than collapsed into one average treatment effect.

### 4.3 FOMC mechanism decomposition

Of 36 available-quality statement-instrument observations, 23 satisfy the no-intervening-trade condition. Thirty-three of 36 press-conference observations are mechanically eligible. At 60 seconds, the median literal first-quote revision is zero for every instrument and sub-event. Eighteen of 23 eligible statement observations and 28 of 33 eligible press observations have exactly zero first-quote revision.

The leave-one-meeting-out signed-flow slopes have median R-squared values of 0.246 for ES, 0.255 for NQ, and 0.108 for ZN. They explain a meaningful part of some moves but are not a complete structural decomposition. Median absolute statement residuals are 9.19 basis points in ES, 8.39 in NQ, and 9.33 in ZN. The residual is likewise material at the press-conference opening, particularly for NQ. Figure `figures/paper/fomc_mechanism_components.png` makes the central measurement point visible: the first quote contributes little, fitted flow contributes something, and neither should be forced to explain the entire price change.

This result is inconsistent with interpreting the first displayed quote as the complete public-signal response. It is, however, consistent with the proposal's prediction that narrative and extemporaneous communication has a low immediate quote share. The stronger claim that the remainder is wholly order-flow-driven is not supported because the residual remains large.

Hypothesis 2 is formally supported under the operational absolute-share definition. Among observations that pass the no-intervening-trade rule and move by more than 0.1 basis point at 60 seconds, all 23 statement observations and all 28 press-conference observations have an absolute first-quote fraction below 40%. One-sided Wilcoxon p-values are 0.0000042 and 0.00000035, respectively. This supports a low literal first-quote share for narrative communication, not a claim that the remaining adjustment is entirely caused by signed flow.

### 4.4 Speed of price discovery

Using the five-minute midpoint as the terminal benchmark, the median first crossings after written statements occur at 9, 7.5, and 4.5 seconds for 50% of the ES, NQ, and ZN move. The corresponding 90% crossings are 19, 37.5, and 14 seconds. At the press-conference opening, all three instruments are much slower: median 50% crossings are 97, 95.5, and 63.5 seconds, and 90% crossings are 127, 119, and 99 seconds.

The first-crossing measure is descriptive rather than a proof of permanent convergence. Price paths frequently overshoot and reverse, and the stricter "remain within 10%" measure often occurs close to the five-minute endpoint. A state-space efficient-price decomposition remains a robustness extension rather than a completed identifying model.

Paired tests sharpen the descriptive comparison. Restricting to ten meetings with both crossings observed, statement 50% crossings are faster than press openings by one-sided Wilcoxon tests in ES (p = 0.0068), NQ (p = 0.0137), and ZN (p = 0.0137). The 90% result remains significant for ES and NQ but not ZN. By contrast, none of the stable-within-10% comparisons is significant. Written statements therefore generate earlier material adjustment, while permanent convergence remains uncertain because of reversals.

### 4.5 Subsecond location of price discovery

ES and NQ reprice nearly synchronously at the resolution available here. For both the statement and press-conference opening, their largest absolute 100 millisecond return correlation occurs at zero lag in all twelve meetings. Median absolute correlations are 0.844 after the statement and 0.822 after the press opening. The statement-period ES-ZN and NQ-ZN correlations also most often peak at zero lag, in eight of twelve meetings, but are much weaker at 0.272 and 0.248. During the press opening, rate-equity timing is unstable and correlations are weaker still.

First-material-move thresholds reveal a small qualification. After the written statement, ES reaches the 1 basis-point threshold before NQ in ten of twelve meetings (one-sided sign p = 0.019; Wilcoxon p = 0.065), with median delays of 129 and 213 milliseconds. ES also reaches that threshold before ZN in nine of twelve meetings (Wilcoxon p = 0.026), while NQ-versus-ZN evidence is marginal. These comparisons are threshold-dependent: at the press opening NQ is typically faster than ES, and only two ZN press observations cross 2 basis points within 30 seconds. The accompanying figure reports all thresholds and makes the incomplete crossing coverage visible.

The defensible conclusion is therefore narrower than a stable leader ranking. ES may lead the first material equity-index adjustment to written statements by tens of milliseconds, but ES and NQ are simultaneous on a 100 millisecond return grid and no instrument leads universally across sub-events and thresholds. ZN's longer equal-basis-point crossing time partly reflects a different response scale, so it is not itself a structural price-discovery share.

### 4.6 Pre-scheduled liquidity withdrawal

The clearest hypothesis test supports pre-announcement liquidity withdrawal. Averaged across instruments within each meeting, the FOMC final-minute depth ratio is lower than its matched-control counterpart in all twelve meetings. The overall mean ratio is 0.563 on FOMC days versus 1.026 on control days, a difference of -0.462. The one-sided meeting-cluster sign test and Wilcoxon test both yield p = 0.00024.

The result is strongest in the Treasury future. ZN's mean event ratio is 0.171 versus 1.041 for controls, with all twelve meetings lower (sign and Wilcoxon p = 0.00024). ES averages 0.567 versus 1.003; eleven of twelve meetings are lower and the one-sided Wilcoxon p is 0.00073. NQ averages 0.951 versus 1.033 and is lower in six of twelve meetings; its paired evidence remains weak (Wilcoxon p = 0.190). The instrument heterogeneity is economically plausible: an FOMC statement directly changes the rate path represented by Treasury futures, while index-future depth also reflects broader equity risk and hedging demand.

These tests support withdrawal before scheduled events. They do not by themselves establish the proposal's stronger claim that withdrawal is specific to scheduled information; the corporate-news counter-sample below prevents that extrapolation.

The independent macro sample reinforces that conclusion. After clustering by month to account for the reused controls, the mean depth ratio across instruments is 0.623 on announcement mornings versus 0.976 at quiet 8:30 clocks. Nineteen of twenty monthly differences are negative (one-sided sign p = 0.000020; Wilcoxon p = 0.0000019). ES averages 0.570 versus 0.999, with nineteen negative months (Wilcoxon p = 0.0000019). ZN averages 0.211 versus 0.934, with all twenty negative (sign and Wilcoxon p = 0.00000095). NQ instead averages 1.088 versus 0.996 and supplies no withdrawal evidence. The replication across two clocks and event families makes liquidity withdrawal the paper's strongest result, while NQ prevents an overbroad claim that every liquid market withdraws.

The selected MBP-10 robustness sample asks whether this is only a best-quote phenomenon. It contains CPI on February 12, 2025, Employment Situation on August 1, 2025, and the March 19, 2025 FOMC statement. Eight of nine event-instrument observations have lower cumulative level-5 and level-10 depth in the final minute; the exception is NQ before the employment release. ZN level-10 ratios range from 0.084 to 0.189, while ES ranges from 0.470 to 0.593. These pre-specified windows indicate that withdrawal usually extends beyond the touch, although three selected events are too few for formal population inference. The deeper-book figure reports all nine paths.

### 4.7 Source-verified corporate news

The six-case corporate sample demonstrates why source accuracy and mechanical eligibility are separate gates. Three events satisfy the literal no-intervening-trade sequence: NVIDIA-Intel, Google-Qualcomm, and AMD-Absci. The first quote is unchanged in the first two; AMD-Absci has a +1.90 basis-point first quote and a +8.87 basis-point last-pretrade quote. At one minute, their news/control returns are +15.76/+4.06, +1.06/-0.24, and +6.02/-14.68 basis points, respectively.

The largest responses are not Q1-eligible. NVIDIA's scheduled earnings release moves +331.53 basis points at one minute versus -0.72 at its control, while AMD's unscheduled buyback moves +143.80 versus -16.51. In both cases, a trade precedes the first post-release quote, so the primary quote revision is rejected rather than relaxed after seeing a large return. Meta's after-hours dividend is also sequence-ineligible and moves only -1.46 basis points at one minute.

The liquidity comparison challenges a schedule-specific interpretation. All five nominally unscheduled events have lower final-minute depth ratios than their matched clocks: 0.448 versus 1.568 on average, with one-sided paired sign and Wilcoxon p = 0.03125. The accompanying corporate-news figure shows substantial response heterogeneity and the matched paths. Five selected events and one control per event cannot identify a population scheduled-versus-unscheduled difference. The result may reflect routine wire-release conventions, anticipation or leakage, or day-specific liquidity. It does show that the current evidence supports pre-event withdrawal, not the stronger claim that only scheduled announcements produce it.

### 4.8 Policy surprises, speed, and asymmetry

H5 and H6 require a surprise sign and magnitude for each event. For FOMC meetings these come from the U.S. Monetary Policy Event-Study Database (USMPD; Acosta, Ajello, Bauer, Loria, and Miranda-Agrippino, 2025): the statement surprise (STMT) and press-conference surprise (PC) are the first principal component of intraday federal funds and eurodollar/SOFR futures changes, scaled to the one-year Treasury yield, and positive values are hawkish. Recomputing STMT from the USMPD futures reproduces the published series exactly. Because the published factors are estimated on the full 1994-2026 sample, each test is repeated with real-time factors that re-estimate the principal component and scaling using only events up to each meeting; for statements the two series have identical rankings across the twelve meetings. The GSS (2005) target and path factors are also reported. The raw MP1 surprise is exactly zero in seven of twelve meetings, and the target factor is positive in eleven of twelve, so neither can support a magnitude or sign test in this sample. These are market-implied surprises, not the proposal's realized-minus-consensus survey surprise, and with twelve meetings every estimate is suggestive.

H5 is not supported. After written statements, larger absolute surprises are associated with faster, not slower, 50% crossings: Spearman rho is -0.60 in ES (two-sided p = 0.050), -0.74 in NQ (p = 0.015), -0.30 in ZN (p = 0.34), and -0.79 for the meeting-average log horizon (p = 0.002). The December 18, 2024 meeting, the largest statement surprise in the sample and one driven almost entirely by the path factor (path 0.337 against target -0.001), reaches 50% of its five-minute move within one second in all three contracts. The sign weakens at the 90% crossing (meeting-average rho = -0.45) and vanishes for the stable-within-10% measure (0.08). Clear statement surprises are therefore priced almost immediately, while small surprises produce slower and noisier paths. At press-conference openings the evidence is mixed: the meeting-average correlation is positive (0.44, p = 0.15 with the published factor; 0.62, p = 0.033 with the real-time factor), but ES and NQ correlations are near zero and change sign across the two factor versions.

H6 is inconclusive. After press openings, hawkish surprises take longer to reach 50% of the equity move: median 105.5 versus 68 seconds in ES (Mann-Whitney p = 0.009; hawkish coefficient controlling for surprise magnitude p = 0.003) and 106.5 versus 49 seconds in NQ (p = 0.004; p = 0.012). The pattern weakens with the real-time factor (ES p = 0.071, NQ p = 0.027 with the magnitude control), disappears at the 90% and stable-within-10% measures, does not appear in ZN or the meeting average, and does not appear after statements, where hawkish path surprises are if anything absorbed faster. Given the number of cells examined, this is a hypothesis for a longer panel rather than evidence of asymmetric absorption. Full results are in `tables/fomc_h5_surprise_speed.csv` and `tables/fomc_h6_surprise_asymmetry.csv`.

### 4.8b Extension: 93 FOMC meetings, 2015-2026

The twelve-meeting sample above is extended to 93 scheduled meetings (77 with press conferences) from 2015 through September 2026, using the same USMPD surprise construction and the same eligibility filters, to check whether the twelve-meeting H2, H4, H5, and H6 results replicate at scale. Full results are in `tables/fomc_h2_quote_fraction_2015_2026.csv`, `fomc_h4_depth_withdrawal_2015_2026.csv`, `fomc_h5_surprise_speed_2015_2026.csv`, and `fomc_h6_surprise_asymmetry_2015_2026.csv`.

H2 strengthens: 155/155 eligible statement observations and 173/174 eligible press observations keep an absolute first-quote fraction below 40% (medians of 0.0; one-sided Wilcoxon p = 2.40e-32 and p = 1.80e-34, across 84 and 75 meetings respectively), versus 23/23 and 28/28 in the original twelve.

H4 also strengthens for statements and stays present for press openings: the meeting-cluster-average pre-event depth ratio is below 1 in 92/92 statement events (mean 0.584, median 0.569; sign p = 2.02e-28, Wilcoxon p = 4.07e-17) and 59/76 press events (mean 0.923, median 0.914; sign p = 6.98e-7, Wilcoxon p = 2.72e-8).

H5's direction is unchanged but its magnitude shrinks once averaged over many more meetings. The statement meeting-average Spearman rho between |surprise| and the 50% crossing horizon is -0.284 (n = 92, two-sided p = 0.0061), still negative as in the twelve-meeting result (rho = -0.79) but far weaker; it vanishes at the 90% crossing (rho = 0.061, p = 0.56) and the stable-within-10% measure (p = 0.061). The press-conference correlation is marginally positive at the 50% crossing (rho = 0.229, n = 76, p = 0.046) and at 90% (rho = 0.273, p = 0.017), consistent with the original mixed reading rather than resolving it. H5 remains not supported for statements.

H6 does not replicate. None of the ES, NQ, or ZN 50%-crossing comparisons that were significant in the twelve-meeting press-conference sample (ES p = 0.003, NQ p = 0.012) remain significant at 93 meetings (ES p = 0.75, NQ p = 0.52, ZN p = 0.32; meeting-average p = 0.45), and no statement-side comparison is significant at 50% or 90% crossings. The only significant cell is a different one, ZN at the stable-within-10% horizon (hawkish median 287s versus dovish 270s, two-sided p = 0.0104), which was not part of the original finding. Given that the original asymmetry does not hold up under an approximately eightfold increase in meetings and reappears, if at all, in an unrelated instrument-horizon cell, H6 should be read as not supported rather than merely inconclusive.

### 4.9 Proposal-wide hypothesis assessment

The completed evidence produces several different outcomes rather than one blanket conclusion. H1 is rejected: scalar numeric releases do not place more than 70% of the five-minute move in the literal first quote. H2 is supported in the current sample and strengthens under the 93-meeting extension. H4 is partly supported: withdrawal before scheduled events is highly significant and holds at scale, but the corporate counter-sample does not establish scheduled-event specificity. H5 is not supported for FOMC meetings: statement horizons shorten rather than lengthen with surprise size, in both the twelve-meeting and 93-meeting samples, though the effect weakens with more meetings. H6 does not replicate at scale: the twelve-meeting hawkish-slower pattern in ES/NQ press first crossings disappears in the 93-meeting extension and should be read as not supported rather than inconclusive. H3 remains unidentified because vintage forecast dispersion is absent from every available source, and H5 and H6 remain untested for macro releases, which need realized-minus-consensus surprises. The summary table distinguishes a rejected hypothesis from an insignificant test and from a hypothesis that cannot be estimated.

## 5. Interpretation and Limitations

The first valid quote often being unchanged is not evidence that quotes are irrelevant. It means the proposal's literal one-record public-signal measure is stricter than common descriptions of an "instantaneous" adjustment. Several quote updates can occur before the first trade, and a last-pretrade-quote robustness measure captures more of that path. The primary measure is retained because changing it after seeing results would create specification risk.

The order-flow component is predictive rather than structural. Linear slopes compress nonlinear impact, cross-instrument learning, and quote revisions that occur between trades. Sub-second buckets and lagged-depth interactions improve fit but fail to improve event-window prediction uniformly, especially at five minutes. Their limited explanatory power is informative but should not be called a causal fraction of price discovery. A multivariate efficient-price state remains an important extension.

H3 cannot be honestly estimated from the available providers, and H5 and H6 can be estimated only for FOMC meetings. Official release pages give realized and prior values but not the vintage analyst consensus distribution required for forecast dispersion. Alpha Vantage economic endpoints do not fill that gap. The FOMC tests of H5 and H6 use market-implied USMPD policy surprises, which measure the size and sign of the surprise but say nothing about pre-event disagreement, so they cannot substitute for dispersion in H3. The dispersion hypothesis and macro-release versions of H5 and H6 therefore require Bloomberg, Refinitiv, FactSet, Haver, or an equivalent vintage survey source. No proxy is substituted.

The current samples cover twenty months of macro releases, twelve clean FOMC meetings, and six source-verified corporate events, not the proposal's five-to-ten-year panel. The macro matched-control result now covers all twenty months, but one independently screened control per month cannot absorb every day-specific latent condition. The corporate sample is selected for source-verifiable clocks and has only one control per event, so its p-value is a diagnostic countercheck rather than a population estimate. The cross-asset timing exercise is a descriptive Q3 implementation, not a common-efficient-price decomposition; estimating structural information shares would require comparable claims traded across venues or a justified multivariate permanent-transitory model. September 2024 and September 2025 CME windows carry provider degradation flags and are excluded from primary multi-meeting inference. Alpha Vantage queries for NVDA, MSFT, AMZN, and JPM reach the 1,000-article cap, so the corpus is a discovery sample rather than a complete news archive. The research contribution is a transparent message-level measurement, a direct rejection of the literal scalar-first-quote benchmark in this sample, and replicated liquidity evidence - not a definitive taxonomy regression.

## 6. Conclusion

Message-level data reveal market mechanics that are invisible in ordinary event returns. Across 77 numeric macro bundles and twelve clean FOMC meetings, the literal first eligible quote rarely carries the observed price adjustment. Scalar news therefore does not satisfy the proposal's 70% first-quote benchmark in this sample. Signed order flow explains part of what follows, but a residual remains too large to ignore even after sub-second and liquidity-conditioned extensions. Written FOMC statements generate faster price discovery than the press-conference opening. ES has limited first-threshold timing advantages after statements, but ES and NQ are simultaneous at 100 millisecond resolution and there is no universal cross-asset leader. Liquidity providers withdraw displayed depth before scheduled information: the result replicates across FOMC and macro samples and extends beyond the touch. Yet all five nominally unscheduled corporate events also have lower depth than matched clocks, so the stronger claim that withdrawal is unique to scheduled information is not supported by the current sample.

The findings support the proposal's emphasis on representation and scheduled liquidity while disciplining its decomposition. The expanded evidence is suitable as a serious research draft, but a test of H3, and of H5 and H6 for macro releases, still requires a licensed vintage consensus/dispersion source; Alpha Vantage and Databento do not contain that object. A longer panel and source-verified corporate announcements would improve external validity. The repository is designed so those inputs can be added without changing the event definitions after observing the results.

## 7. Submission Scope

The project is ready to submit as a transparent empirical research paper or independent-study draft. It is not a complete five-to-ten-year execution of every proposal hypothesis. Q1 is directly implemented with exchange-time sequencing, explicit aggressor side, order-flow calibration, residuals, and pathological-case flags. Q2 is implemented with crossing, stable-band, and overshoot measures plus paired tests. Q3 is implemented descriptively at 100 millisecond resolution, without claiming a structural information share. Q4 is implemented at the touch, in selected ten-level books, and against scheduled and corporate controls. Q5 is answered for FOMC meetings using USMPD policy surprises, with no robust asymmetry in twelve meetings; for macro releases it still requires vintage expectations.

The minimum remaining input for a full proposal claim is a licensed vintage consensus and forecast-dispersion source. Extending the panel toward five to ten years, pre-declaring a broader corporate-news sample, using multiple controls per news event, and adding more MBP-10 windows would strengthen external validity. These are substantive extensions; the core timestamp, quote/trade, placebo, and reporting pipeline is complete and reproducible.

## References

Acosta, M., Ajello, A., Bauer, M., Loria, F., and Miranda-Agrippino, S. (2025). Financial market effects of FOMC communication: Evidence from a new event-study database. *Federal Reserve Bank of San Francisco Working Paper* 2025-30.

Andersen, T., Bollerslev, T., Diebold, F., and Vega, C. (2003). Micro effects of macroeconomic announcements. *American Economic Review*.

Balduzzi, P., Elton, E., and Green, T. C. (2001). Economic news and bond prices. *Journal of Financial and Quantitative Analysis*.

Glosten, L., and Milgrom, P. (1985). Bid, ask and transaction prices in a specialist market. *Journal of Financial Economics*.

Green, T. C. (2004). Economic news and the impact of trading on bond prices. *Journal of Finance*.

Gurkaynak, R., Sack, B., and Swanson, E. (2005). Do actions speak louder than words? *International Journal of Central Banking*.

Hasbrouck, J. (1993). Assessing the quality of a security market. *Review of Financial Studies*.

Hasbrouck, J. (1995). One security, many markets. *Journal of Finance*.

Kim, O., and Verrecchia, R. (1994). Market liquidity and volume around earnings announcements. *Journal of Accounting and Economics*.

Kuttner, K. (2001). Monetary policy surprises and interest rates. *Journal of Monetary Economics*.

Kyle, A. (1985). Continuous auctions and insider trading. *Econometrica*.

Tetlock, P. (2007). Giving content to investor sentiment. *Journal of Finance*.
