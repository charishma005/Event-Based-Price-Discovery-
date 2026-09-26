# Timestamp validation — September 17, 2025 FOMC pilot

Status: official arrivals and market-message timestamps validated. FOMC futures results remain provisional because Databento labels `GLBX.MDP3` on 2025-09-17 as `degraded`.

## Official arrivals

| Event | Eastern time | UTC | Interpretation |
|---|---|---|---|
| FOMC statement | 2025-09-17 14:00:00 EDT | 2025-09-17 18:00:00Z | Jointly observed with the SEP |
| Summary of Economic Projections | 2025-09-17 14:00:00 EDT | 2025-09-17 18:00:00Z | Cannot be separated from the statement by market time |
| Powell press conference start | 2025-09-17 14:30:00 EDT | 2025-09-17 18:30:00Z | Opening validated; exact Q&A marker remains pending |

September is daylight-saving time in New York, so EDT is UTC-4. All raw and processed market timestamps are stored as timezone-aware UTC.

## Statement-window message sequence

| Instrument | Final quote before event | First valid quote after event | First trade after event | First-quote delay | First-trade delay | Immediate revision (bp) | Primary mechanical validity |
|---|---|---|---|---:|---:|---:|---|
| ES | 17:59:59.863374527 | 18:00:00.006870825 | 18:00:00.152201969 | 6.870 ms | 152.202 ms | 0.000 | Pass mechanically; dataset degraded |
| NQ | 17:59:59.689926423 | 18:00:00.208938007 | 18:00:00.208938007 | 208.938 ms | 208.938 ms | 0.206 | Fail: trade before/at first quote; dataset degraded |
| ZN | 17:59:59.742931883 | 18:00:00.003653549 | 18:00:00.004977713 | 3.654 ms | 4.978 ms | 0.000 | Pass mechanically; dataset degraded |
| SPY (`EQUS.MINI`) | 17:59:57.809833009 | 18:00:00.160671171 | 18:00:00.160671171 | 160.671 ms | 160.671 ms | 0.152 | Fail: intervening trade and `sequence=0` tie |
| JPM (`EQUS.MINI`) | 17:59:56.466629148 | 18:00:01.018274086 | 18:00:01.018274086 | 1018.274 ms | 1018.274 ms | 16.095 | Fail: intervening trade and `sequence=0` tie |
| NVDA (`XNAS.ITCH`) | 17:59:59.923082896 | 18:00:00.011579971 | 18:00:00.011579971 | 11.580 ms | 11.580 ms | 0.000 | Fail: trade before first clean quote |

The literal proposal definition uses the first valid post-arrival quote. A separately reported robustness measure uses the final quote before the first trade. For ES, four quote updates occurred before the first trade and that robustness revision was -0.188 bp; for ZN it remained zero. This distinction is important because the first post-event quote can be an unchanged book update.

## Timestamp and feed diagnostics

- Median `ts_recv - ts_event` was about 97 microseconds for ES, 129 microseconds for NQ, and 584 microseconds for ZN in the FOMC statement sample. The corresponding 99th percentiles were approximately 1.13 ms, 3.61 ms, and 9.88 ms.
- No status records were returned for the requested futures or NVDA windows. This does not override the dataset-level `degraded` condition.
- `EQUS.MINI` has `sequence=0`; a trade and quote at the same `ts_event` cannot be ordered reliably. Those cases are rejected for primary Q1.
- `XNAS.ITCH` supplies venue sequence numbers but represents the Nasdaq book, not consolidated NBBO.
- Databento explicitly defines `B` as buyer aggressor, `A` as seller aggressor, and `N` as unknown for trade actions. Unknown sides remain unsigned.

## Clean comparison event

The September 16 Retail Sales window is marked `available` by Databento. ES and NQ both pass the no-intervening-trade test: their first clean quotes arrived 47.233 ms and 46.145 ms after release, roughly 816 ms before their first trades. Both first-quote revisions were zero. ZN fails because its first post-release trade and first clean quote share the same event timestamp.

## Expanded scheduled-release validation

| Event | Instrument | First quote delay (ms) | First trade delay (ms) | First quote (bp) | Trade intervenes? | Dataset | Primary Q1 eligible? |
|---|---|---:|---:|---:|---|---|---|
| PPI | ES | 66.809 | 66.809 | -1.911 | yes | available | no |
| PPI | NQ | 67.614 | 192.731 | 0.000 | no | available | yes |
| PPI | ZN | 64.486 | 648.581 | 0.000 | no | available | yes |
| CPI bundle | ES | 25.489 | 206.813 | 0.000 | no | available | yes |
| CPI bundle | NQ | 24.452 | 24.452 | 0.104 | yes | available | no |
| CPI bundle | ZN | 1.271 | 1.271 | 0.000 | yes | available | no |
| Retail Sales bundle | ES | 47.233 | 863.036 | 0.000 | no | available | yes |
| Retail Sales bundle | NQ | 46.144 | 862.651 | 0.000 | no | available | yes |
| Retail Sales bundle | ZN | 11.153 | 11.153 | 0.000 | yes | available | no |
| Industrial Production | ES | 213.757 | 1307.437 | 0.000 | no | available | yes |
| Industrial Production | NQ | 335.537 | 2781.421 | 0.000 | no | available | yes |
| Industrial Production | ZN | 32.402 | 3080.814 | 0.000 | no | available | yes |
| Housing | ES | 2.874 | 485.827 | 0.000 | no | degraded | no |
| Housing | NQ | 81.934 | 5025.197 | 0.000 | no | degraded | no |
| Housing | ZN | 34.786 | 690.427 | 0.000 | no | degraded | no |

This produces seven usable event-instrument observations on available-quality days. A key empirical fact is that a zero literal first-quote revision is common even when a clean quote precedes the first trade. The final pre-trade quote remains a declared robustness measure; it does not replace the proposal's literal primary definition.

## Conclusion

The timestamp pipeline works and rejects ambiguous cases rather than silently assigning them. However, FOMC and housing futures observations should not enter a definitive primary regression until Databento clarifies the September 17 `degraded` designation or the results are replicated with an independent feed. PPI, CPI, Retail Sales, and industrial production now provide the technically eligible Q1 pilot cases.

## Source-verified unscheduled-news clock

The NVIDIA–Intel release provides the first complete non-agency timestamp test. Alpha Vantage records 2025-09-18 00:00:00 UTC, but the originating GlobeNewswire distribution is stamped 07:00 ET / 11:00:00 UTC. The eleven-hour-early provider value is retained for audit; all market alignment uses the source clock.

Meta's September 11 dividend declaration provides a second source-clock test. Alpha Vantage records 10:57:28 UTC, while the originating PR Newswire page is stamped 16:35 ET / 20:35 UTC. No market message arrives for 28.799 seconds after that source clock, and a trade intervenes before the first post-event quote. The exact clock is verified, but the after-hours observation fails the proposal's primary quote-sequencing condition and is retained with that failure rather than repaired.

For NVDA on `XNAS.ITCH`, the last valid pre-event quote was at 10:59:57.973744709 UTC. The first valid post-event quote was at 11:00:00.011886743 and was unchanged. The first trade was at 11:00:00.088546998; the first nonzero BBO change has that same exchange timestamp and sequence. This is not an unresolved tie: the Nasdaq sequence identifies the trade/book update, and there were three unchanged post-event quotes before it. The literal primary quote component is therefore zero, with the first price change associated with trading 88.547 ms after the verified wire time.

The source-verified corporate sample now contains six events:

| Event | Source clock (UTC) | First quote delay | First trade delay | First quote (bp) | Primary Q1 eligible? |
|---|---|---:|---:|---:|---|
| NVIDIA-Intel | 2025-09-18 11:00:00 | 11.886 ms | 88.546 ms | 0.000 | yes |
| Meta dividend | 2025-09-11 20:35:00 | 28.799 s | 28.799 s | -1.463 | no: trade intervenes |
| Google-Qualcomm | 2025-09-08 12:30:00 | 6.867 s | 12.442 s | 0.000 | yes |
| NVIDIA Q4 FY2025 earnings | 2025-02-26 21:20:00 | 280.114 ms | 276.717 ms | -0.759 | no: trade intervenes |
| AMD buyback | 2025-05-14 13:00:00 | 463.291 ms | 6.183 ms | 0.000 | no: trade intervenes |
| AMD-Absci | 2025-09-11 12:00:00 | 634.248 ms | 93.245 s | 1.902 | yes |

Each clock comes from an originating company or wire page. The matched control for every case has Alpha Vantage ticker coverage and zero direct high-relevance company articles within one hour. These checks do not prove the absence of all news, but they prevent a known provider-clock error or a known same-ticker headline from defining the comparison.

Official sources:

- https://www.federalreserve.gov/newsevents/pressreleases/monetary20250917a.htm
- https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20250917.htm
- https://www.federalreserve.gov/monetarypolicy/fomcpresconf20250917.htm
