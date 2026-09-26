# Proposal implementation status

| Proposal item | Pilot status | What is available now | What is still needed |
|---|---|---|---|
| Q1 mechanism share | Implemented on macro and multi-meeting FOMC samples | 148 eligible macro instrument-bundles plus 23 statement and 33 press observations; exchange-time sequencing, explicit signed flow, leave-one-event-out impact, residual, and flags | Extend beyond twenty macro months; resolve degraded September dates |
| Q2 speed | Implemented across 12 clean FOMC meetings | 50% statement crossings are faster than press openings by paired Wilcoxon tests in ES, NQ, and ZN; stable-band differences are not significant | State-space/variance-ratio robustness and surprise magnitudes |
| Q3 price-discovery location | Implemented descriptively at subsecond frequency | First 0.5/1/2 bp crossings and 100 ms cross-correlations across 12 clean meetings; ES/NQ peak at zero lag in every statement and press window, with limited ES-leading threshold evidence after statements | A structural common-efficient-price model requires a defensible same-claim or permanent-transitory design; possibly SOFR/additional Treasuries |
| Q4 liquidity | Implemented at touch, selected deeper-book windows, and a small source-verified corporate sample | FOMC depth is lower in all 12 clean meetings; macro depth is lower in 19/20 months; level-5/10 depth is lower in 8/9 selected observations; all five nominally unscheduled cases also have lower depth than controls (p=0.031) | A larger randomly sampled corporate-news panel is needed before attributing withdrawal specifically to scheduled events |
| Q5 asymmetry | Not identified | Signed raw returns and daily event residuals are present | Vintage consensus, standardized surprises, and a larger event sample |
| H1 scalar numeric quote share >70% | Rejected in the twenty-month literal first-quote sample | Median five-minute absolute quote fraction is zero in ES/NQ/ZN; none exceeds 70%; opposite-direction p-values are 2.98e-8, 4.77e-7, and 4.66e-10 | A longer sample and alternative pre-trade-quote robustness remain useful |
| H2 narrative quote share <40% | Supported in the current FOMC sample | All 23 eligible statement and 28 eligible press observations are below 40%; one-sided Wilcoxon p=0.0000042 and p=0.00000035 | Cross-central-bank validation and a model that explains more of the residual |
| H3 dispersion raises flow share | Blocked by data | Event schema has dispersion and surprise fields | Licensed vintage survey source such as Bloomberg/Refinitiv/FactSet/Haver |
| H4 scheduled depth withdrawal | Scheduled withdrawal is supported, but scheduled-versus-unscheduled specificity is not | FOMC ratio is 0.563 versus 1.026; macro ratio is 0.623 versus 0.976. However, five nominally unscheduled corporate cases average 0.448 versus 1.568 and all five differences are negative (p=0.031) | More source-verified events and multiple controls per event are required to distinguish anticipation from day-specific liquidity |
| H5 larger surprise slows discovery | Blocked by data | Multi-horizon response panel exists | Standardized surprises from vintage expectations |
| H6 bad news slower than good news | Blocked by data/sample | Directional returns exist | Surprise signs, matched magnitudes, and many more releases |

## What the pilot establishes

The proposal's central object is measurable without full MBO: `GLBX.MDP3` MBP-1 supplies exchange timestamps, every top-of-book update, trades, touch depth, and explicit aggressor side. The code rejects a Q1 observation when a trade intervenes, ordering is ambiguous, or the provider condition is degraded. It also retains unexplained adjustment rather than forcing quote and flow components to sum to the observed move.

The literal “first valid quote” definition often produces a zero revision even when several pre-trade quote updates follow. That is not a coding failure; it is a definition sensitivity revealed by the pilot. The primary measure is preserved exactly, while the last pre-trade quote is recorded as a declared robustness measure.

The proposed stock labels are now checked against one year of daily data. The output estimates market and Treasury-price betas outside CPI/FOMC days, then ranks market-and-rate-adjusted absolute residuals on 9 FOMC and 13 CPI dates. It supports the high-beta designation for TSLA/AMD/NVDA and lower-yield sensitivity for AMT/PLD, but shows that the broader theme labels are not interchangeable with measured exposures. This is a universe-refinement diagnostic; without vintage surprises it is not a test of H5 or H6.

## Multi-meeting FOMC expansion completed

The repository now contains thirteen cached 45-minute `GLBX.MDP3` MBP-1 meeting windows and twenty-four 15-minute matched controls. Twelve FOMC meetings from January 2024 through July 2025 have available-quality data; September 2024 is preserved but excluded because the provider marks it degraded. The sample has 36 statement-instrument and 36 press-instrument observations, of which 23 and 33 respectively pass the literal no-intervening-trade rule.

Across clean meetings, median first crossings of 50% of the five-minute response are 9, 7.5, and 4.5 seconds after the statement for ES, NQ, and ZN, versus 97, 95.5, and 63.5 seconds after the press-conference opening. These are descriptive crossing statistics, not a state-space efficient-price estimate.

The subsecond Q3 extension reaches a similarly disciplined conclusion. ES and NQ 100 millisecond return correlations peak at zero lag in all twelve clean meetings for both sub-events. ES crosses 1 basis point before NQ after the statement in 10 of 12 meetings (sign p=0.019; Wilcoxon p=0.065), but that ranking reverses at the press opening and changes with the threshold. ZN crosses equal basis-point thresholds more slowly, but its response scale differs. These are cross-asset timing diagnostics, not Hasbrouck shares for multiple markets trading one claim.

The liquidity result is the strongest inferential finding. Matched same-weekday controls were screened against Federal Reserve and Treasury calendars; primary means exclude controls with uncertain same-day Fed announcement timing and the pre-holiday session. The final-minute/prior-four-minute depth ratio averages 0.563 on FOMC days and 1.026 on controls. Every meeting-cluster difference is negative (one-sided sign and Wilcoxon p=0.00024). ZN is strongest; NQ alone is not statistically distinguishable from its controls.

Paper-facing CSV/LaTeX tables are under `tables/`, four publication figures are under `figures/paper/`, and the current manuscript draft is at `paper/research_paper.md`.

## Twenty-month macro expansion completed

The main numeric sample now covers 77 unique 8:30 a.m. bundles from January 2024 through August 2025: twenty CPI, twenty PPI, twenty Employment Situation, and twenty retail-sales releases, with simultaneous clocks treated as bundles. ES, NQ, and ZN MBP-1 windows yield 231 instrument-bundle observations; 148 pass the primary no-intervening-trade rule.

The literal first post-event quote is unchanged in 144 of 231 observations. For mechanically eligible scalar releases, the median absolute first-quote fraction of the five-minute response is zero in every instrument and no observation exceeds 70%. This rejects H1 as operationalized, while the last-pretrade-quote robustness definition confirms that the result is not solely a missing-message artifact.

Twenty independently screened exact-clock controls provide one control per month from January 2024 through August 2025. Because controls are reused within month, formal matched inference remains aggregated to twenty month clusters. The mean all-instrument depth ratio is 0.623 on release mornings and 0.976 on controls; nineteen month differences are negative (sign p=0.000020, Wilcoxon p=0.0000019). ZN and ES drive the effect, while NQ does not withdraw.

## Source-verified corporate-news expansion completed

The corporate sample now contains six source-verified event/control pairs and twelve sequenced `XNAS.ITCH` windows. Three news events pass the literal no-intervening-trade requirement. NVIDIA earnings and AMD's buyback produce the largest one-minute responses, +331.5 and +143.8 basis points, but fail Q1 mechanically because a trade precedes the first quote. Google-Qualcomm and NVIDIA-Intel have unchanged first quotes; AMD-Absci has a +1.90 bp first quote and +8.87 bp last-pretrade revision.

All matched clocks have Alpha Vantage ticker coverage and zero direct high-relevance company articles within one hour. The five nominally unscheduled cases all have lower final-minute depth ratios than their controls. That result is too selected and small for population inference, but it directly prevents an overclaim that pre-event depth withdrawal is unique to scheduled announcements.

## Best next expansion

The highest-value next expenditure is a vintage forecast source for H3, H5, and H6, followed by a broader randomly sampled corporate-news and MBP-10 panel. The 44-candidate audit confirms that Alpha Vantage clocks are often hours away from source-page metadata; exact-event expansion must continue to use the original wire/company clock rather than the provider field.
