# Alpha Vantage news audit

## Result

Alpha Vantage is usable as the pilot's primary news and sentiment source, but it is not a machine-perfect event clock. The authenticated September 8–19, 2025 pull made 25 cached requests: one for each of the 22 stocks and one each for `economy_monetary`, `economy_macro`, and `financial_markets`.

The subsequent January 1-September 20, 2025 expansion added 22 ticker-specific histories. Across all 47 cached queries, normalization now yields 10,005 unique articles and 30,406 article-ticker rows with no timestamp parse failures. NVDA, MSFT, AMZN, and JPM reach the 1,000-article ceiling in the expanded request, so these are rich discovery histories rather than complete archives.

A reproducible ranking selects 44 candidates across all 22 stocks: 16 earnings/guidance, 13 product/strategy, six regulatory/litigation, three M&A, three management/operations, and three capital-distribution cases. Source pages exposed machine-readable timestamp candidates for 21. Only three were within five minutes of the Alpha Vantage clock; 17 differed by more than an hour, 14 by more than four hours, and the median absolute discrepancy was 8.4 hours. Sixteen pages blocked or removed automated access and seven exposed no usable metadata. Because page metadata can itself be an update time or syndication time, these 21 are audit candidates—not automatically certified first-publication clocks.

The raw responses contained 3,006 article occurrences. After canonicalizing tracking URLs, merging repeated query results, and expanding ticker sentiment, the processed table contains:

- 3,964 article-ticker rows;
- 1,811 unique articles;
- 1,810 unique canonical URLs;
- 627 named sources;
- zero timestamp parse failures;
- second-resolution provider timestamps spanning 2025-09-08 00:00:00 through 2025-09-19 22:39:21 UTC.

The September stock-specific queries did not reach their 1,000-row ceilings. The broad `financial_markets` topic query did, and four expanded ticker histories later reached the cap. Coverage fields preserve those truncation warnings.

## Problems found and fixed

1. **Comma-separated filters are AND filters.** A single `NVDA,JPM` query would require both tickers to appear. Retrieval now makes one request per ticker.
2. **Tracking URLs created massive duplicates.** One MarketWatch article appeared hundreds of times with different `gaa_*` query parameters. URLs are now canonicalized by removing common tracking parameters before constructing `article_id`.
3. **Ticker mappings include false or incidental associations.** Examples included a Delta flight story mapped to Boeing and a Tyler Technologies insider-sale story mapped to Amazon. Automated contamination now requires a direct company-name/alias mention plus ticker relevance of at least 0.60. A high-confidence flag additionally requires relevance of at least 0.80.
4. **Second precision does not imply a correct event clock.** Source-level validation found three material failures. The Meta dividend is 34,652 seconds early; a Google Cloud/Qualcomm release is four hours early because an 08:30 ET wall clock appears as 08:30 UTC; and the NVIDIA–Intel announcement is stored as midnight UTC instead of its 07:00 ET wire time, an eleven-hour error. The pipeline preserves both values and uses the verified source time for event matching.
5. **Missing coverage is not zero news.** The event-stock panel records query coverage separately and uses an unknown contamination value when the ticker was not queried.

## Source-level timestamp spot checks

| Article | Alpha Vantage UTC | Source UTC | Result | Exact-event eligible? |
|---|---|---|---|---|
| Meta quarterly dividend | 2025-09-11 10:57:28 | 2025-09-11 20:35:00 | Provider clock differs by -34,652 seconds; originating wire time retained | Yes, using source time only |
| Google Cloud–Qualcomm partnership | 2025-09-08 08:30:00 | 2025-09-08 12:30:00 | Alpha Vantage is four hours early; source lists 08:30 ET | Yes, using source time only |
| NVIDIA–Intel partnership/investment | 2025-09-18 00:00:00 | 2025-09-18 11:00:00 | Date-midnight placeholder is eleven hours early; originating wire lists 07:00 ET | Yes, using source time only |
| Microsoft–Maryland quantum collaboration | 2025-09-17 18:01:09 | unavailable | Microsoft page exposes the date but no clock time | No |
| Broadcom–Lloyds partnership | 2025-09-17 16:49:46 | unavailable | Source page did not expose a usable publication time | No |

These checks are in `data/processed/news_timestamp_audit.csv`; hand-audited inputs live in `config/news_timestamp_validations.yaml`. A validated timestamp never overwrites the provider field. Instead, `validated_event_time_utc`, `timestamp_validation_status`, and `alpha_minus_source_seconds` are added. This correction also removed the Meta dividend from the CPI contamination window: it was actually published after the close, not before CPI.

## Contamination screen

Within the default ±120-minute windows, the FOMC statement/SEP bundle produced 34 raw ticker-mapped candidates, 12 direct-mention review candidates, and eight high-confidence articles affecting seven stocks. These remain manual-review candidates, not automatic exclusions. Examples include a Microsoft corporate announcement 69 seconds after 2:00 p.m. and a Broadcom partnership release about 70 minutes before it.

The same logic is applied to every event × stock pair in `data/processed/event_news_contamination.parquet`. Raw candidates, review candidates, and high-confidence candidates are all retained so threshold sensitivity can be measured.

The expanded file contains 946 event-stock rows over 43 calendar events and 79 high-confidence contamination flags. A descriptive 220-row FOMC stock-response model includes the contamination indicator and maximum absolute sentiment together with event, horizon, and theme effects. The news coefficients are not distinguishable from zero (`p=0.84` for contamination and `p=0.39` for sentiment). This check is useful for omitted-news screening, but the small, non-random pilot is not a causal test of sentiment.

## Main limitation

The feed is suitable for contamination screening, sentiment covariates, source/topic analysis, and generating candidate unscheduled events. It is not sufficient to assert that a headline first reached traders at the provider timestamp. A candidate becomes an exact intraday treatment only after an original publisher/company/SEC/wire page supplies a defensible time; the verified source time, not the Alpha Vantage time, becomes the event clock.

The NVIDIA–Intel story is now the first end-to-end unscheduled-news pilot. At the source-verified clock, NVDA's first valid Nasdaq quote did not move; the first trade and first nonzero quote change occurred 88.547 ms after release, and the midpoint was +30.64 bp at 30 seconds before reversing. See `reports/unscheduled_news_pilot.md`.

Source pages used for the spot check:

- https://www.prnewswire.com/news-releases/meta-announces-quarterly-cash-dividend-302554438.html
- https://blogs.microsoft.com/on-the-issues/2025/09/17/our-new-collaboration-with-maryland-will-accelerate-scalable-quantum-computing/
- https://www.broadcom.com/company/news/product-releases/63506
- https://www.googlecloudpresscorner.com/2025-09-08-Qualcomm-and-Google-Cloud-Deepen-Collaboration-to-Bring-Agentic-AI-Experiences-to-the-Auto-Industry
- https://www.globenewswire.com/news-release/2025/09/18/3152283/0/en/index.html

See Alpha Vantage's `NEWS_SENTIMENT` documentation: https://www.alphavantage.co/documentation/#news-sentiment
