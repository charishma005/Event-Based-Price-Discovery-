# January 2024-August 2025 macro-announcement results

## Sample

The sample contains 77 distinct 8:30 a.m. Eastern arrival bundles from January 2024 through August 2025: twenty official releases each for CPI, PPI, the Employment Situation, and retail sales, with simultaneous-release dates treated as mixed bundles. Known concurrent official releases are stored as contamination metadata. Each window contains exchange-time `GLBX.MDP3` MBP-1 messages for ES, NQ, and ZN from five minutes before through six minutes after the clock. All 77 provider conditions are available.

There are 231 event-instrument observations. One hundred forty-eight pass the proposal's literal primary rule requiring a valid first post-event quote with no intervening trade. One hundred forty-four of 231 first valid quotes are unchanged. The last-pretrade-quote definition is retained as a declared robustness measure rather than substituted after observing the result.

## H1: first-quote share

The proposal predicts that more than 70% of a scalar numeric announcement's five-minute adjustment occurs in the immediate pre-trade quote revision. The data do not support that benchmark. Among eligible scalar observations, the median absolute quote fraction is zero for ES, NQ, and ZN, and no observation exceeds 70%. One-sided Wilcoxon tests in the hypothesized direction have p=1.000. Tests below 70% have p=2.98e-8 for ES, 4.77e-7 for NQ, and 4.66e-10 for ZN.

This is a rejection of the literal one-record definition, not evidence that public information is irrelevant to quotes. Economically meaningful adjustment occurs over later messages and trades. Sub-second liquidity-conditioned fits raise pre-event R-squared but improve event-window median absolute error in only 11 of 27 model cells. Material residuals remain, so the remainder cannot honestly be labeled wholly order-flow-driven.

## Responses by release class

At 60 seconds, median absolute CPI responses are 38.17 bp (ES), 46.08 (NQ), and 28.41 (ZN). Employment medians are 20.33, 24.28, and 33.24 bp; PPI medians are 13.96, 14.85, and 11.05 bp; retail-sales medians are 3.42, 5.08, and 9.40 bp. These comparisons are descriptive because vintage realized-minus-consensus surprises are unavailable.

## Matched-clock liquidity

The formal placebo analysis remains the independently screened January-August 2025 subsample, with one quiet 8:30 a.m. clock per month. BLS, Census, BEA, and Federal Reserve calendars were checked; January 7 was rejected because international trade arrived at that clock. Unscheduled information cannot be ruled out, and matched 2024 macro controls remain to be constructed.

Because one control is reused for several releases within a month, inference first averages event ratios within each of twenty months. Across instruments, the final-minute/prior-four-minute depth ratio averages 0.623 on event mornings and 0.976 at controls. Nineteen of twenty monthly differences are negative (one-sided sign p=0.000020; Wilcoxon p=0.0000019). ES averages 0.570 versus 0.999, with nineteen negative months (Wilcoxon p=0.0000019). ZN averages 0.211 versus 0.934, with all twenty negative (sign and Wilcoxon p=0.00000095). NQ averages 1.088 versus 0.996 and shows no withdrawal evidence.

The FOMC sample independently shows lower depth in all seven meeting clusters. Replication across 8:30 a.m. numeric releases and 2:00 p.m. policy statements makes scheduled liquidity withdrawal the strongest completed result, with meaningful instrument heterogeneity.

## Remaining identification limits

H3, H5, and H6 require vintage analyst consensus, cross-sectional forecast dispersion, and standardized surprises. Official agencies and Alpha Vantage do not provide the required vintage distribution. Those fields remain unavailable rather than replaced with an ex-post proxy. Deeper-book liquidity also requires selected MBP-10 or MBO windows; the completed tests concern displayed touch depth.
