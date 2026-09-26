# Proposal critique and implementable scope

## What is strong

The proposal asks a genuinely microstructural question rather than merely measuring returns around news. Its key distinction—public information moving quotes before a trade versus later movement associated with signed flow—is observable in high-quality message data, especially in liquid single-venue futures. The representation taxonomy also creates useful variation: scalar releases, multidimensional releases, written narrative, and speech plausibly impose different interpretation burdens.

The narrow-first strategy is essential. ES/NQ/ZN around a known FOMC timestamp offer high liquidity, exchange timestamps, explicit trade-side fields where the source supplies them, and no cash-market opening complication. Timestamp validation and matched clock-time placebos are correctly treated as research outputs rather than housekeeping.

## Identification and measurement risks

1. **Simultaneous information.** The September 17 statement and SEP both arrived at 2:00 p.m. They can have separate metadata records, but the market response is a joint treatment. Representation-specific identification needs cross-meeting variation or content measures.
2. **The order-flow component is fitted, not directly observed.** Signed volume is observed; the price change "caused by" it is a regression prediction. The result depends on interval length, impact-coefficient estimation sample, functional form, and endogeneity. Report those choices and cross-fit or estimate impact outside the focal observation where possible.
3. **No-intervening-trade eligibility is selective.** Fast or surprising events may produce a trade before the first quote change more often. The fraction of ineligible events is itself an outcome and must be reported by representation class.
4. **Mechanism-share instability.** `QR / (QR + OF)` can explode when the denominator is near zero or when components offset. The proposal's signed definition should remain primary, while the data should retain denominator, residual, opposing-sign flags, reversals, and out-of-range shares.
5. **Fragmented equity markets.** Nasdaq TotalView gives excellent sequencing but only one venue; aggregated equity BBO loses venue identity and, in `EQUS.MINI`, sequence information. Futures therefore support cleaner Q1 claims than individual stocks.
6. **Consensus and dispersion are separate licensed data problems.** Official releases identify actual and prior values but not the real-time survey distribution. H3 and standardized-surprise tests should not run until vintage consensus/dispersion is licensed.
7. **News timestamps can be epistemically late.** A headline timestamp can be an update or syndication time rather than first public availability. Unscheduled-news results require story-version and first-publication validation, plus novelty/deduplication.
8. **Signed flow is not automatically structural causality.** Trading and quote revisions jointly respond to information. The decomposition is a transparent statistical accounting object unless stronger instruments/structural assumptions are added.

## What this pilot can establish

- Whether the final pre-event and first post-event futures BBO can be located unambiguously.
- How often a trade intervenes and how often aggressor side is known.
- The signed immediate quote jump and additional movement over 100 ms through five minutes.
- Whether signed flow visually and statistically covaries with later price changes under several buckets.
- Pre-event spread/depth withdrawal versus matched placebo times.
- Relative reaction timing across ES, NQ, and ZN.
- A clean joint comparison of the 2:00 p.m. statement-plus-SEP bundle with the 2:30 p.m. press conference.

## What this pilot cannot yet establish

- A reliable representation-class coefficient from one FOMC day.
- Separate statement and SEP causal effects on September 17.
- H3 without forecast dispersion.
- H5/H6 without a larger set of signed, standardized surprises.
- A robust Q3 VECM/Hasbrouck comparison from one event.
- A valid 2025 unscheduled-news design from the WRDS RavenPack Trial, which ends in 2020.

## Recommended implementation path

Run one narrow `GLBX.MDP3 mbp-1` statement window after reviewing the authenticated cost estimate. Validate the exact sequence in ES, NQ, and ZN; then repeat for the press conference and matched placebos. Add MBO only if MBP-1 passes and deeper liquidity/order-lifecycle questions materially change Q4. Expand to other September releases next, and only then estimate pooled impact coefficients and event-level mechanism shares. Add the stock cross-section after the futures mechanics are stable.

