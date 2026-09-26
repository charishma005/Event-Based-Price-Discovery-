# Subsecond price-discovery results

## Design

The analysis uses exchange-time `GLBX.MDP3` MBP-1 quote messages for ES, NQ, and ZN around the written statement and press-conference opening in twelve available-quality FOMC meetings from January 2024 through July 2025. It measures the first post-event quote to cross 0.5, 1, and 2 basis points in absolute value within 30 seconds. It also samples quote returns every 100 milliseconds and searches pairwise correlations over leads and lags from -1 to +1 second.

This is a descriptive cross-asset timing test. It is not a Hasbrouck information-share estimate because the three futures are different claims, not multiple markets for the same security. Equal basis-point thresholds also represent different economic response scales.

## Results

- ES and NQ have their largest absolute 100 millisecond return correlation at zero lag in all twelve meetings after both the statement and press opening. Median absolute correlations are 0.844 and 0.822.
- Statement-period ES-ZN and NQ-ZN correlations peak at zero lag in eight of twelve meetings, but median absolute correlations are only 0.272 and 0.248.
- After statements, median 1 basis-point crossing delays are 129 ms for ES, 213 ms for NQ, and 1,006 ms for ZN.
- ES reaches 1 basis point before NQ in 10 of 12 statement windows (one-sided sign p=0.019; Wilcoxon p=0.065). ES reaches it before ZN in 9 of 12 (Wilcoxon p=0.026).
- The ordering is not universal. At press openings, median 1 basis-point delays are 630 ms for ES, 228 ms for NQ, and 2,938 ms for the 11 ZN meetings that cross. Only two ZN press observations cross 2 basis points within 30 seconds.

## Interpretation

ES may lead the first material equity-index adjustment to written statements by tens of milliseconds, but ES and NQ are effectively simultaneous on a 100 millisecond grid. There is no stable leader across sub-events, pairs, and thresholds. ZN's slower equal-basis-point crossing is partly a response-scale comparison and should not be read as a structural information share.

Reproducible CSV and Parquet outputs are in `data/processed/fomc_price_discovery/`; the publication figure is `figures/paper/fomc_subsecond_first_move.png`.
