# Research design extracted from the proposal

## Research object

The project asks how public information becomes a market price. Its central event-level object is the share of an announcement-related price adjustment attributable to (i) an immediate revision of displayed quotes before any trade and (ii) later adjustment associated with signed order flow. The project must not substitute a generic event-study return for this decomposition.

## Questions and hypotheses

- **Q1 — Mechanism.** What fraction of the total adjustment occurs in the initial, pre-trade quote revision, and what fraction accumulates with subsequent signed order flow? How does that fraction vary by announcement type?
- **Q2 — Speed.** How long does efficient-price discovery take, and how does that horizon vary with surprise magnitude and disagreement?
- **Q3 — Location.** Which instrument leads price discovery: rates instruments for rate-sensitive information, or index futures for broad risk information?
- **Q4 — Liquidity.** How do touch depth and spreads change around scheduled versus unscheduled information, and does pre-event liquidity withdrawal predict the mechanism?
- **Q5 — Asymmetry.** Conditional on surprise magnitude, are adverse surprises incorporated more slowly than favorable surprises?

- **H1.** Scalar numeric news is mostly incorporated by quote revision; the proposal's benchmark is more than 70% of the five-minute move.
- **H2.** Narrative or extemporaneous communication relies more on order flow; the proposal's benchmark is less than 40% in the pre-trade jump.
- **H3.** The order-flow share increases with ex-ante forecast dispersion.
- **H4.** Displayed depth falls during the 60 seconds before scheduled arrivals, but not before unscheduled news.
- **H5.** The price-discovery horizon increases with the absolute standardized surprise.
- **H6.** Bad news is incorporated more slowly than good news of comparable magnitude.

## Announcement taxonomy

The proposal specifies four independent dimensions:

1. **Scheduling:** scheduled to the second; scheduled only to a day/window; unscheduled.
2. **Representation class (primary):** `scalar_numeric`, `multi_dimensional_numeric`, `narrative_text`, or `extemporaneous_speech`.
3. **Ex-ante disagreement:** continuous cross-sectional forecast dispersion.
4. **Surprise magnitude:** standardized realized-minus-consensus deviation.

The pilot preserves simultaneous releases as separate event IDs. In particular, the September 17 FOMC statement, Summary of Economic Projections (SEP), press-conference opening, and later Q&A are not one event. A precise Q&A marker is deferred until official video/caption timing can be validated.

Separate IDs do not imply separate causal identification. The statement and SEP were both released at exactly 2:00 p.m. EDT, so the observed 2:00 market response is a **joint statement-plus-SEP treatment**. Their individual price effects cannot be disentangled from market timestamps alone. Identification of representation effects will require cross-meeting variation (meetings with versus without an SEP), textual/numeric content measures, or a design that treats the simultaneous bundle as its own event class.

## Mechanism definition

For event `i`, let `m_-` be the midpoint of the final valid quote before the official information-arrival time and `m_+` the midpoint of the first valid quote after arrival. The initial quote-revision component is

`QR_i = m_+ - m_-`,

but only when message sequencing shows that no trade intervened. Locked/crossed books, missing quotes, halts, auctions, and unresolved same-timestamp ordering are flagged rather than silently repaired.

The subsequent order-flow component is the cumulative fitted price change after the event from a short-interval return regression on contemporaneous signed order flow. The impact coefficient is Kyle-style and should be estimated from a defensible event or pooled sample, not chosen to make components add up. Signed flow is positive for buyer-initiated trades and negative for seller-initiated trades. When the source explicitly supplies aggressor side, it takes precedence over Lee–Ready inference.

Let `OF_i` denote that fitted component. The proposal's mechanism share is

`MS_i = QR_i / (QR_i + OF_i)`.

The residual is retained explicitly as `total adjustment - QR_i - OF_i`. A near-zero denominator, opposing component signs, reversal, or a share outside `[0, 1]` is an economically meaningful diagnostic, not a reason to winsorize or renormalize automatically.

## Required market data and timestamp semantics

### Required for primary Q1

- Official information-arrival timestamp, with its source and precision.
- `ts_event`: exchange/matching-engine event time, timezone-aware and stored in UTC.
- Message ordering information such as venue `sequence`, plus publisher and instrument identifiers.
- Every best-bid/best-ask update needed to find the final pre-event and first post-event quote.
- Bid, ask, bid size, and ask size; midpoint is `(bid + ask) / 2`.
- Every trade in the event window, with trade price, quantity, and explicit aggressor side when the feed supplies it.
- Trading/status messages needed to identify halts and auction states.

### Useful but not strictly required for baseline Q1

- `ts_recv`, the Databento capture-server receipt time, for latency diagnostics only.
- Exchange send time reconstructed from `ts_recv - ts_in_delta`, where populated.
- Order IDs, add/cancel/modify actions, and full MBO for queue/deeper-book work.
- MBP-10 or reconstructed deeper depth for Q4 extensions.
- Venue attribution and consolidated-versus-single-venue comparisons.

### Distinctions that must remain explicit

- **Exchange event timestamp:** when the exchange matching engine received/recorded the event; primary ordering clock.
- **Vendor receipt timestamp:** when Databento captured the packet; useful for latency, not a substitute for exchange event time.
- **Trade timestamp:** `ts_event` on a trade record.
- **Quote timestamp:** `ts_event` on the message that changed the valid BBO.
- **BBO midpoint:** arithmetic mean of the best bid and best ask.
- **Aggressor side:** the side initiating the trade, not the resting-book side.
- **Signed flow:** aggressor sign times shares/contracts, notional, or trade count.
- **BBO depth:** displayed quantity at the best bid and offer.
- **Deeper-book depth:** displayed quantity beyond the touch; it requires MBP-10 or MBO reconstruction.

Databento historical requests with schemas containing `ts_recv` are filtered on the receive-time index. Event-window requests therefore need a small safety buffer, followed by filtering and ordering on `ts_event` inside the pipeline.

## Announcement metadata

For scheduled numeric releases, store scheduled timestamp, realized value, consensus, forecast dispersion, and revisions. The standardized surprise is `S_i = (A_i - F_i) / sigma_i`. Forecast dispersion is essential for H3 and cannot be replaced silently. The official agencies provide realized/prior data and timestamps, but generally not the real-time consensus or dispersion; those fields remain unavailable until a licensed forecast source is identified. Policy surprises should ultimately be measured from a narrow-window rate-futures instrument. Unscheduled news needs a first-publication timestamp and relevance/novelty fields.

## Placebos and robustness

- Matched non-announcement days at the same exact clock time, with the same weekday where possible.
- Exclude known competing macro releases from placebo windows.
- Compare unweighted and cell-balanced estimates.
- Use within-day contrasts when several representation classes arrive on one day.
- Inspect subperiod stability.
- For Q2, compare variance-ratio convergence with a state-space permanent/transitory decomposition.
- For Q3, report Hasbrouck bounds and a permanent/transitory decomposition rather than one arbitrary ordering.
- Repeat liquidity results with quoted/effective spreads, touch depth, and deeper depth where available.

## What survives without ticks?

| Analysis | Tick/ordered messages required? | What lower-frequency data can still do |
|---|---:|---|
| Q1 quote revision versus signed flow | **Yes** | Cannot be identified from 1-second or minute bars. |
| Q2 speed/horizon | Preferred, not absolute | One-second data can estimate coarse horizons; minute data is screening only. |
| Q3 price-discovery location | Preferred | Synchronized one-second futures can support a coarse lead/lag pilot. |
| Q4 liquidity withdrawal | **Top-of-book ticks required** for the main test | One-second BBO can provide a coarse spread/depth path if sizes are present. OHLCV cannot. |
| Q5 response asymmetry | No | One-second/minute returns can support an initial event-level analysis once surprises exist. |

## Practical narrow pilot

Start with the September 17, 2025 FOMC releases and ES, NQ, ZN, then SPY/NVDA/JPM where feed coverage is appropriate. Use 1-second data for screening; use MBP-1 for event-level BBO plus trades; escalate to MBO or MBP-10 only for selected windows and depth/order-lifecycle questions.
