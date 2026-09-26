# News, announcements, sentiment, and expectations

## Bottom line

The current WRDS `ravenpack_trial` product does **not** cover the September 2025 pilot. WRDS lists its date range as 1582-01-11 through 2020-12-31, with no ongoing updates. It can be used to prototype entity joins, relevance filters, deduplication, and sentiment/event-taxonomy code on an older sample, but it cannot identify 2025 contamination or unscheduled events.

For the actual pilot, use a layered approach in which Alpha Vantage is the designated news provider:

1. official agencies for scheduled arrival times and realized values;
2. Alpha Vantage `NEWS_SENTIMENT` for company news, ticker relevance/sentiment, contamination flags, and candidate unscheduled events;
3. SEC/company IR pages only to validate timestamps for important direct corporate announcements;
4. a separate vintage-consensus source only if standardized macro surprises and forecast dispersion are later required. That expectations problem is distinct from the choice of news feed.

## Source assessment

| Source | Best use | Timestamp fit | Sentiment/event fields | September 2025? | Main limitation |
|---|---|---|---|---:|---|
| Official BLS/Census/BEA/Fed | Scheduled timestamp, actual, prior, revisions | Exact scheduled/release time | No market sentiment | Yes | No analyst consensus distribution |
| Databento | Quotes, trades, book, reference/corporate actions | Exchange nanoseconds | No news/sentiment | Yes | It is not a news feed |
| Alpha Vantage `NEWS_SENTIMENT` | **Primary pilot discovery/sentiment feed** | Returned fields have second precision, but audited errors range from 4 to 11 hours | Ticker relevance, ticker sentiment, overall sentiment, and topics | Yes; authenticated pilot complete | Provider publication time cannot be used as an event clock without source validation |
| WRDS `ravenpack_trial` | Prototype RavenPack processing | Point-in-time news analytics in the sample | Trial-dependent RavenPack fields | **No; ends 2020-12-31** | Cannot support the 2025 pilot |
| Current RavenPack on WRDS | Main structured company/global-macro news candidate | Designed as point-in-time analytics | Event, sentiment, relevance, attention/novelty-style analytics depending on edition | Yes if institution subscribes | Large licensed dataset; exact accessible schema/edition must be checked |
| WRDS SEC Sentiment | Filing tone and filing contamination | Filing acceptance/publication time | Filing text sentiment | Yes | SEC filings are not a general breaking-news feed |
| WRDS LexisNexis Text Analytics | Broad text/news research if subscribed | Must validate publication/update fields | Product-specific | Likely | Access, timestamp semantics, and redistribution constraints vary |
| Bloomberg Terminal/Desktop API | Manual event research, ECO/survey expectations, cross-checks | Strong for scheduled calendars and timestamped headlines | Bloomberg-specific analytics/metadata | Yes | Terminal access is not automatically a reproducible bulk historical-news license |
| Bloomberg Data License/B-PIPE | Scalable licensed news/reference/estimates workflow | Enterprise delivery | Product-dependent | Yes | Separate entitlement, cost, and licensing review |

## Required news table

Do not write provider-specific names into the research design. Normalize any source to these concepts and retain the original raw fields:

- `news_id` and provider story/event ID;
- `source_name` and provider;
- `headline` (and body only if licensed);
- `first_publication_time_utc`;
- `update_time_utc` and version/update flag;
- `retrieval_time_utc`;
- `timestamp_precision` and `timestamp_semantics`;
- ticker plus stable entity identifier;
- entity/ticker `relevance`;
- event category/topic and representation class;
- sentiment score and sentiment model/version;
- novelty/similarity score and lookback, if supplied;
- source URL or document identifier;
- `is_first_story`, `is_update`, and duplicate-cluster ID;
- contamination category (earnings, guidance, analyst event, product, M&A, litigation/regulation, split/dividend, other);
- raw-source table/file and a quality flag.

The precise RavenPack Trial column names are intentionally not asserted until the WRDS schema is queried. The same rule applies to Alpha Vantage publication fields: parse a real response, measure actual resolution, and distinguish first publication from subsequent updates.

## Expectations are a separate data problem

Alpha Vantage replaces RavenPack/Bloomberg for the news and sentiment arm. It does not, however, provide the vintage cross-section of economist forecasts needed to calculate forecast dispersion or a true ex-ante standardized macro surprise. If those proposal variables are implemented later, they require a survey/expectations source; this is not a reason to replace Alpha Vantage as the news provider.

## Pilot decision

- Keep scheduled macro/FOMC as the confirmatory pilot because official timestamps are strong.
- Use Alpha Vantage as the primary source for news selection, sentiment, relevance, and contamination flags.
- Treat each Alpha Vantage story as a candidate unscheduled event until its first-publication timing passes an authenticated/source audit.
- Do not run a September 2025 unscheduled-news regression with `ravenpack_trial`.
- Do not require RavenPack or Bloomberg for the pilot news dataset.

## Implemented retrieval and outputs

- `scripts/download_alpha_vantage_news.py` makes one cached request per ticker plus separate monetary-policy, macro, and financial-market topic requests over the pilot period. This avoids the API's comma-separated AND semantics.
- `scripts/build_news_panel.py` produces one normalized row per article-ticker pair, a query-coverage audit, and an event-by-stock contamination table.
- Raw responses are immutable and Git-ignored. Derived tables retain publication precision, query ticker, provider sentiment/relevance, repeated-title grouping, and a conservative timestamp-quality flag.
- No article is automatically labeled a valid unscheduled event. `eligible_as_unscheduled_event` remains false until timestamp validation is completed. Three stories now have defensible source clocks; NVIDIA–Intel and Meta's dividend declaration have completed tick-data cases, but the after-hours Meta sequence fails primary Q1 eligibility.
- `scripts/build_news_timestamp_audit.py` materializes source checks. Verified source times are stored beside, never over, Alpha Vantage times and are used for event matching.
- `scripts/analyze_unscheduled_news.py` compares the source-timed NVIDIA–Intel release with a prior-day same-clock NVDA window and the source-timed Meta dividend release with a prior-week same-clock META window. It estimates quote/flow/residual components only for the mechanically eligible NVIDIA case.

## Sources

- WRDS RavenPack catalog and Trial date range: https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/ravenpack/
- WRDS RavenPack feature overview: https://wrds-www.wharton.upenn.edu/documents/1395/RavenPack.pdf
- WRDS intraday event-study description: https://wrds-www.wharton.upenn.edu/pages/grid-items/intraday-second-second-event-study-upload-your-own-events/
- Bloomberg enterprise data: https://professional.bloomberg.com/products/data/
- Bloomberg Data License: https://professional.bloomberg.com/products/data/data-license/
- Alpha Vantage documentation: https://www.alphavantage.co/documentation/
