# Source-verified corporate-news sample

## Event and clock

The first unscheduled-news case is NVIDIA's September 18, 2025 announcement that it would partner with Intel and invest $5 billion in Intel. Alpha Vantage identifies the story, maps it to NVDA with relevance 1.00, and labels both overall and ticker sentiment bullish (0.447 and 0.429). Its provider timestamp is 00:00:00 UTC, which is not the release time. The originating GlobeNewswire distribution is stamped 07:00 ET, or **11:00:00 UTC**. The source clock is therefore used; the Alpha Vantage value is 39,600 seconds early and remains stored for audit.

The market file is a cost-gated 15-minute `XNAS.ITCH` MBP-1 window for NVDA. This is Nasdaq TotalView, not the consolidated NBBO. A same-clock September 17 window is the matched control; the cached Alpha Vantage panel contains no direct, high-relevance NVDA article within one hour of that control.

## Mechanical result

The last valid pre-event midpoint was $174.32 at 10:59:57.973744709 UTC. The first valid post-event quote arrived 11.886 ms after the release and did not move. The first trade arrived 88.547 ms after release; the first nonzero quote change shares that exchange timestamp and sequence, so it is associated with the trade/book update rather than a clean pre-trade public-signal quote revision. The primary no-intervening-trade first-quote observation is mechanically valid and its literal quote-revision component is zero.

| Horizon | News return (bp) | Placebo return (bp) | News signed volume | Known aggressor side |
|---:|---:|---:|---:|---:|
| 100 ms | -2.87 | 0.29 | -3 | 100.0% |
| 500 ms | -6.31 | 7.83 | 9 | 88.8% |
| 5 sec | -4.88 | 6.67 | 664 | 84.6% |
| 30 sec | 30.64 | 6.38 | 36,230 | 79.1% |
| 60 sec | 15.76 | 4.06 | 37,236 | 75.0% |
| 5 min | -3.44 | 11.60 | 40,538 | 74.0% |

This is a sharp but non-monotonic discovery path: an initial decline, a roughly 31 bp positive response by 30 seconds, partial reversal by one minute, and full reversal by five minutes. One prior-day placebo is not a sampling distribution, but it shows that the 30-second news response is much larger than the same-clock control.

## Quote versus flow

A one-second impact coefficient estimated only on 898 seconds in the prior-day placebo has R-squared 0.148. Applied to the news event, positive signed flow predicts +58.32 bp at 30 seconds against an observed +30.64 bp, leaving a -27.68 bp residual. At five seconds the model predicts +1.07 bp while the observed move is -4.88 bp. The literal quote share is zero because the first valid quote did not move. These results support the proposal's insistence on retaining the residual and show that a single-window linear flow calibration is not stable enough for a substantive mechanism claim.

Touch depth in the final pre-event minute was 0.49 of the earlier-window mean, versus 1.38 at the placebo clock. Because this was unscheduled and there is only one control, that difference is diagnostic rather than evidence of anticipatory withdrawal.

## Second case: Meta dividend announcement

Alpha Vantage also identified Meta's September 11, 2025 quarterly dividend declaration, but its 10:57:28 UTC provider clock is 9 hours 37 minutes earlier than the originating PR Newswire distribution at **16:35 ET / 20:35 UTC**. Two zero-cost `XNAS.ITCH` MBP-1 windows compare the announcement with the same weekday and clock one week earlier.

This after-hours case is deliberately retained as a low-information counterexample. No quote or trade arrived for 28.799 seconds after the source clock; the first post-event quote coincided with an intervening sell trade, so the primary quote-revision observation is mechanically ineligible. The midpoint was unchanged through five seconds, -1.46 bp at 30 and 60 seconds, and +1.60 bp at five minutes. The matched clock was unchanged through one minute and -4.34 bp at five minutes. The announcement therefore does not produce a response distinguishable by inspection from ordinary sparse after-hours movement, and the data do not support a quote-versus-flow mechanism estimate.

This negative case is informative: a source-verified timestamp is necessary but not sufficient. Exact event studies also need enough quote and trade activity immediately around the clock. It is stored rather than excluded after observing the weak response, with the sequencing failure and after-hours session stated explicitly.

## Four additional source-verified cases

The sample now contains six event/control pairs. Alpha Vantage discovered every event, but each clock was independently replaced by an originating company or wire timestamp where the provider field was wrong. The four additions are Google Cloud's Qualcomm collaboration (GOOGL), NVIDIA's fourth-quarter results, AMD's $6 billion buyback authorization, and an Absci/Oracle/AMD collaboration. Each matched clock has Alpha Vantage ticker coverage and zero direct high-relevance company articles within plus or minus one hour.

Three of six news events pass the literal no-intervening-trade requirement: NVIDIA-Intel, Google-Qualcomm, and AMD-Absci. The Google case has an unchanged first quote, a 6.87-second first-quote delay, and a +1.06 bp one-minute response versus -0.24 bp at its control. AMD-Absci has a +1.90 bp first quote and +8.87 bp last-pretrade quote, then +6.02 bp at one minute versus -14.68 bp at its control. The scheduled NVIDIA earnings release and unscheduled AMD buyback are economically large - +331.53 bp and +143.80 bp at one minute - but both have a trade before the first post-release quote and therefore cannot enter the primary Q1 quote-share sample. Economic materiality and mechanical eligibility are recorded separately.

The depth comparison produces an important counter-result. All five nominally unscheduled cases have a lower final-minute/prior-window touch-depth ratio than their matched clocks. Their mean ratio is 0.448 versus 1.568, and paired one-sided sign and Wilcoxon tests both give p=0.03125. With only five selected releases and one control each, this is not a population estimate. It nevertheless means the current data do not support a claim that pre-event withdrawal is unique to scheduled public announcements. Possible explanations include routine wire-release conventions, information leakage or anticipation, and unobserved day-specific liquidity conditions.

## Interpretation

Together the six cases show both sides of feasibility. Alpha Vantage can discover and score candidates; source-level audits can replace unusable provider clocks; and Databento can supply exchange-sequenced quotes, trades, and aggressor side. Only three cases satisfy the proposal's literal Q1 sequence, while two of the largest responses fail because trading precedes the first quote. The sample is still too selected and small for a definitive scheduled-versus-unscheduled regression, but it now supplies a transparent countercheck against interpreting scheduled-event liquidity withdrawal too broadly.

Outputs are in `data/processed/unscheduled_news/`; comparison charts are under `figures/unscheduled_news/`. All six events and controls are included in the canonical event-time panel, with quality flags preserving every sequencing failure.

Source release: https://www.globenewswire.com/news-release/2025/09/18/3152283/0/en/index.html

Meta source release: https://www.prnewswire.com/news-releases/meta-announces-quarterly-cash-dividend-302554438.html
