# Data feasibility and cost gate

Status: authenticated discovery and the bounded research downloads are complete. All three target datasets are available to the account. The immutable cache contains 166 requests, 66,364,205 records, and 1.48 GB of compressed files; all were estimated at an account cost of $0.00. Request metadata sit next to each raw file and the initial estimate matrix is saved in `reports/databento_cost_estimates.json`.

## Decision matrix

| Dataset | Instrument | Schema | Q1 usable? | Q2? | Q3? | Q4? | Aggressor side? | Depth? | Exchange timestamp? | Approx. cost/size |
|---|---|---|---|---|---|---|---|---|---|---|
| `GLBX.MDP3` | ES/NQ/ZN | `mbo` | **Yes; strongest** | Yes | Yes | **Yes** | Explicit when CME defines it; retain unknowns | Full order book | `ts_event`, ns | Six-minute statement estimate: 85.91 MiB, $0.00; deliberately not downloaded yet |
| `GLBX.MDP3` | ES/NQ/ZN | `mbp-10` | Yes | Yes | Yes | Yes | Trade records retain normalized side | Top 10 levels | `ts_event`, ns | Nine selected event-instrument windows downloaded; 1.09 GiB estimated, $0.00; split by instrument to satisfy the 250 MiB request guard |
| `GLBX.MDP3` | ES/NQ/ZN | `mbp-1` | **Yes, baseline** | Yes | Yes | Touch only | Trade records retain normalized side | BBO/touch | `ts_event`, ns | 20-minute statement estimate: 64.38 MiB, $0.00; downloaded |
| `GLBX.MDP3` | ES/NQ/ZN | `tbbo` | **No alone**: misses quote-only changes | Yes | Limited | Trade-time touch only | Yes/unknown as supplied | BBO immediately before trades | `ts_event`, ns | Cheaper but insufficient for initial jump |
| `GLBX.MDP3` | ES/NQ/ZN | `trades` | No | Coarse | Coarse | No | Yes/unknown as supplied | None | `ts_event`, ns | Cheap diagnostic |
| `GLBX.MDP3` | ES/NQ/ZN | `bbo-1s` | No | Yes, coarse | Yes, coarse | Coarse touch | Not a complete trade sequence | 1-second BBO | `ts_event`, ns | Tier A candidate |
| `GLBX.MDP3` | ES/NQ/ZN | `ohlcv-1s` | No | Yes, coarse | Yes, coarse | No | No | None | Bar event time | Cheapest Tier A screen |
| `XNAS.ITCH` | NVDA and other Nasdaq-listed stocks | `mbo` | Yes, **Nasdaq venue only** | Yes | Limited | Yes | Explicit for displayed executions; some non-displayed trades can be unknown | Full Nasdaq book | `ts_event`, ns, venue sequence | Pending; selected stocks/windows only |
| `XNAS.ITCH` | Nasdaq-listed stocks | `mbp-10` | Yes, Nasdaq venue only | Yes | Limited | Yes | Trade records retain normalized side where supplied | Top 10 Nasdaq levels | `ts_event`, ns | Pending; use only if deeper depth adds value |
| `XNAS.ITCH` | Nasdaq-listed stocks | `mbp-1` | Yes, Nasdaq venue only | Yes | Limited | Touch only | Normalized trade side when source defines it | Nasdaq BBO | `ts_event`, ns | NVDA 20-minute estimate: 16.43 MiB, $0.00; downloaded |
| `XNAS.ITCH` | Nasdaq-listed stocks | `tbbo`/`trades` | No alone | Yes/coarse | Limited | No/very limited | Side field can be unknown | Trade-time BBO/none | `ts_event`, ns | Diagnostic only |
| `XNAS.ITCH` | Nasdaq-listed stocks | `bbo-1s`/`ohlcv-1s` | No | Yes, coarse | Limited | BBO only / no | No complete signed flow | Sampled touch / none | `ts_event`, ns | Tier A |
| `EQUS.MINI` | SPY and broad stock basket | `mbp-1` | **Conditionally**: quote/trade stream exists, but `sequence=0` complicates ties | Yes | Limited | Touch only | Normalized side where available; verify empirically | Aggregated BBO incl. odd lots; venue anonymized | `ts_event`, ns | SPY/JPM 20-minute estimate: 9.72 MiB, $0.00; downloaded |
| `EQUS.MINI` | Broad stock basket | `tbbo`/`trades` | No alone | Yes/coarse | Limited | No/very limited | Verify non-null rate | Trade-time BBO/none | `ts_event`, ns | Diagnostic |
| `EQUS.MINI` | Broad stock basket | `bbo-1s`/`ohlcv-1s` | No | Yes, coarse; prefer OHLCV return | Limited | BBO diagnostic only / no | No complete signed flow | Sampled touch / none | Snapshot/bar time; underlying BBO event may be stale | 22 stocks, 90 minutes: 6.36 MiB estimated, $0.00; downloaded |
| `EQUS.MINI` / `GLBX.MDP3` | 22 stocks + SPY / ES-NQ-ZN | `ohlcv-1d` | No | Daily sensitivity only | No | No | No | None | Daily bar event time | Sep. 2024–Sep. 2025, 384.8 KiB estimated, $0.00; downloaded |
| Alpha Vantage | Stocks | 1-minute intraday | No | Screening only | No | No | No | None | Provider bar timestamp | Premium historical endpoint; no request made |
| Alpha Vantage | News | `NEWS_SENTIMENT` | Event metadata only, after timestamp validation | No | No | No | N/A | N/A | Returned second-resolution publication fields | 47 cached queries including 22 extended ticker histories; 10,005 unique articles; four ticker histories hit the 1,000-row ceiling |

## What each feed can and cannot identify

### `GLBX.MDP3`

This is the main futures dataset. It covers CME, CBOT, NYMEX, and COMEX; MDP 3.0 MBO is available for the 2025 pilot. `mbo` contains every order event. `mbp-1` contains every BBO update plus trades and is the cheapest plausible schema for Q1. `tbbo` samples the BBO only at trades, so it cannot show a public-signal quote jump that occurs before the first trade.

For ES and NQ, the customary roll date was September 15, 2025 and September expiry was September 19. The December contracts (`ESZ5`, `NQZ5`) are therefore the expected liquid contracts on September 17, but the pipeline deliberately resolves the actual `*.v.0` mapping and volume before hard-coding them. The corresponding raw ZN contract is also resolved from definitions rather than assumed.

### `XNAS.ITCH`

This is full-depth Nasdaq TotalView, not a consolidated national book. It is suitable for a transparent NVDA deep-book case study and supplies exchange sequence numbers, but quote revision estimates are venue-specific. For interlisted/cross-venue stock claims, compare with `EQUS.MINI` rather than calling Nasdaq BBO the NBBO.

### `EQUS.MINI`

This derived dataset aggregates the best prices and sizes across its component Reg NMS/ATS venues. It supplies MBP-1, TBBO, trades, BBO, OHLCV, and definitions, but no MBP-10/MBO. Original venue identity is anonymized, order counts are zero, and sequence is always zero. Identical-nanosecond quote/trade ordering can remain unresolved.

The empirical 22-stock check revealed an additional limitation: one-second BBO snapshots can carry stale and extremely wide books for less-active names, creating false midpoint jumps. Broad-stock event returns therefore use one-second OHLCV trade closes. BBO spread and touch depth are retained only as diagnostics, with a `wide_or_stale_eq_us_mini_bbo` flag above 50 bp. This does not disqualify narrowly inspected MBP-1 cases, but it prevents treating `bbo-1s` as a clean consolidated cross-sectional return series.

## Aggressor-side interpretation

Across Databento MBO/MBP/trades records, `side` denotes the initiating side: bid means buyer-initiated and ask means seller-initiated. Some native trade messages do not reveal an aggressor; those records remain unknown. The pipeline reports the known-side share before estimating order-flow regressions and never silently signs unknowns with Lee–Ready.

## Timestamp implications

`ts_event` is the exchange/matching-engine event timestamp and is the canonical research clock. `ts_recv` is Databento capture time and is retained for feed-latency diagnostics. Because historical requests are indexed by `ts_recv` when present, request windows include a small buffer and are then restricted in `ts_event`.

## Alpha Vantage feasibility

- Historical intraday supports 1/5/15/30/60-minute bars, not one-second bars, and the historical intraday endpoint is premium.
- `NEWS_SENTIMENT` supports ticker/topic filters, `time_from`/`time_to` at minute precision, sorting, and up to 1,000 rows. The authenticated corpus returned second-resolution publication fields and broad coverage, but the 44-candidate audit found a median 8.4-hour absolute discrepancy among machine-extractable source clocks. Source-specific first-publication semantics still require validation; URL canonicalization and alias/relevance filters are necessary.
- Earnings calendar is forward-looking (3/6/12 months), so it is not a historical September 2025 event master.
- Economic-indicator endpoints are low-frequency series, not release-time vintages or consensus data.

Therefore Alpha Vantage is the primary pilot source for news selection, sentiment, and contamination screening, while Databento supplies Q1 market mechanics. Alpha Vantage cannot supply the exchange quote/trade sequence or forecast dispersion.

Databento's separate Reference API can later contribute security-master and corporate-action checks (splits, symbol changes, dividends). It is not a news feed and does not replace Historical market data for Q1. Normal SDK authentication uses the API key; account name and user ID are not needed.

## Deferred futures

`RTY.v.0`, `YM.v.0`, SOFR (`SR3` family), and additional Treasury maturities are technically available through `GLBX.MDP3` parent/continuous symbology. They are deferred until ES/NQ/ZN pass timestamp validation. Expanding now would add cost and multiple-testing burden without improving the first mechanical test.

## Cost-controlled request ladder

1. Estimate `ohlcv-1s` and `bbo-1s` for ES/NQ/ZN over 17:30–19:30 UTC on September 17.
2. Estimate `mbp-1` over 17:50–18:10 and 18:25–19:00 UTC.
3. Estimate `mbo` only for 17:59–18:05 UTC and only after MBP-1 mechanics validate.
4. Retrieve the small `status` schema alongside selected MBP/MBO windows to identify halts, pauses, and auctions.
5. For equities, estimate `EQUS.MINI mbp-1` for SPY/JPM and `XNAS.ITCH mbp-1` for NVDA over the same narrow windows.
6. Every download requires both an estimate under configured limits and an explicit `--execute`; existing raw files are never overwritten.

## Sources

- Databento schema guide: https://databento.com/docs/knowledge-base
- `GLBX.MDP3`: https://databento.com/docs/venues-and-datasets/glbx-mdp3
- `XNAS.ITCH`: https://databento.com/docs/venues-and-datasets/xnas-itch
- `EQUS.MINI`: https://databento.com/docs/venues-and-datasets/equs-mini
- Timestamp semantics: https://databento.com/docs/standards-and-conventions/common-fields-enums-types
- Historical cost/size API: https://databento.com/docs/reference-historical/basics/
- Continuous futures: https://databento.com/docs/examples/symbology/continuous
- Alpha Vantage documentation: https://www.alphavantage.co/documentation/
