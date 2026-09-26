# Six-part research expansion results

## Scope completed

1. **Longer macro sample.** The exchange-time `GLBX.MDP3` MBP-1 sample now covers January 2024 through August 2025: 80 official releases, 77 distinct arrival bundles, three futures, and 231 event-instrument observations. All 77 windows have `available` provider condition. The requests were cost-estimated before retrieval at 1.76 GiB and $0 for the added 2024 year.
2. **FOMC expansion and controls.** Five early-2024 meetings were added. The primary panel now contains 12 available-quality meetings, 36 statement observations, 36 press-conference observations, and 24 matched-clock control windows. Two controls with same-day Federal Reserve announcements of uncertain time and one pre-holiday control are retained as secondary flags and excluded from primary control means.
3. **Deeper book.** Nine instrument-specific MBP-10 requests cover CPI on 2025-02-12, Employment Situation on 2025-08-01, and the FOMC statement on 2025-03-19. Splitting by instrument kept every request below the 250 MiB guard; the portfolio estimate was 1.09 GiB and $0.
4. **Corporate-news sample.** Twenty-two Alpha Vantage ticker histories from 2025-01-01 through 2025-09-20 returned 12,197 article responses before deduplication. Combined with the pilot caches, the normalized corpus has 10,005 unique articles and 30,406 article-ticker rows. A transparent ranking selects 44 high-relevance candidates across all 22 stocks and six announcement categories.
5. **News descriptors and contamination controls.** Ticker relevance, absolute sentiment, direct company mentions, query coverage, and validated clocks are retained separately. They now produce 946 event-stock contamination rows over 43 calendar events. A descriptive FOMC stock-response regression includes contamination and sentiment alongside event, horizon, and theme effects; neither news term is distinguishable from zero in the 220-row pilot (`p=0.84` and `p=0.39`). This is a robustness control, not a causal sentiment estimate.
6. **Sub-second and liquidity-conditioned impact.** The flow model now runs at 100, 250, and 500 milliseconds. The liquidity-conditioned version interacts signed flow with inverse lagged touch depth and is estimated leave-one-bundle-out. It raises median pre-event R-squared in every instrument-frequency comparison, by 0.014 to 0.078, but reduces median event-window error in only 11 of 27 frequency-instrument-horizon cells. The gain is clearest for short-horizon ES; long-horizon and ZN performance often deteriorates.

## Main empirical results after expansion

The literal first-quote result is stable in the larger sample. Of 231 macro event-instrument observations, 148 pass the no-intervening-trade rule and 144 first post-event quotes are unchanged. For the 77 usable scalar event-instrument observations with non-negligible five-minute moves, the median absolute first-quote fraction is zero in ES, NQ, and ZN; none exceeds 70%. Opposite-direction Wilcoxon p-values are `2.98e-8`, `4.77e-7`, and `4.66e-10`. This rejects H1 as literally operationalized; it does not imply that all later movement is caused by order flow.

The FOMC liquidity result becomes stronger with twelve meetings. The meeting-cluster mean final-minute/prior-four-minute depth ratio is 0.563 on FOMC days and 1.026 at screened controls. Every meeting-level difference is negative; the one-sided sign and Wilcoxon p-values are both 0.00024. ES is lower in 11 of 12 meetings (Wilcoxon `p=0.00073`), ZN is lower in all 12 (`p=0.00024`), and NQ remains weak (`p=0.190`). Statement 50% crossing medians are 9, 7.5, and 4.5 seconds for ES, NQ, and ZN; press-opening medians are 97, 95.5, and 63.5 seconds.

Selected deeper-book evidence is consistent with broad liquidity withdrawal. Eight of nine observations have lower cumulative level-5 and level-10 depth in the final minute. ZN level-10 ratios range from 0.084 to 0.189, and ES from 0.470 to 0.593. NQ before the August employment release is the exception: its touch falls to 0.680 of baseline while level-5 and level-10 depth rise to 2.021 and 1.248. Three selected events support robustness but are not enough for formal inference.

## Alpha Vantage timestamp conclusion

Alpha Vantage works well for discovering and describing relevant company news, but not as an unaudited millisecond event clock. Of the final 44 candidates, source-page timestamps were machine-extractable for 21; only three were within five minutes of the provider clock, 17 differed by more than one hour, and the median absolute discrepancy was 8.4 hours. Sixteen pages blocked or removed automated access and seven exposed no usable timestamp metadata. The machine-extracted field is therefore a review aid only. Exact unscheduled-event studies still require an originating company/wire timestamp; provider relevance and sentiment remain valid descriptive covariates.

## What remains incomplete

Databento and Alpha Vantage cannot supply the vintage analyst-consensus distribution required for H3, H5, and H6. Expected values, forecast dispersion, standardized surprises, and surprise signs therefore remain unavailable rather than proxied with ex-post information. The formal macro matched-control test now covers all twenty months from January 2024 through August 2025: aggregate event depth is 0.623 of baseline versus 0.976 at controls, with nineteen negative month differences (Wilcoxon p=0.0000019). The news sample is a discovery corpus rather than a complete archive because four extended ticker queries reached Alpha Vantage's 1,000-article cap.

## Reproducible products

- Multi-year mechanism outputs: `data/processed/macro_multiyear/`
- Twelve-meeting FOMC outputs: `data/processed/fomc_sample/`
- Twenty-four FOMC controls: `data/processed/fomc_placebos/`
- Deeper-book outputs: `data/processed/depth_sample/`
- Corporate-news candidates and audits: `data/processed/news_event_candidates.csv` and `data/processed/news_source_timestamp_audit.csv`
- News-control outputs: `data/processed/news_controls/`
- Updated paper: `paper/research_paper.md` and `output/pdf/how_markets_absorb_news.pdf`
