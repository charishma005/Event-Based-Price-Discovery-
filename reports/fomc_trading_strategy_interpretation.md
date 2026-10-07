## Interpretation (written after reviewing the tables; not used to change any rule)

**Bottom line.** None of the 21 registered strategies is SUPPORTED. No strategy makes money after
executable costs in both development (2015-2022) and the holdout (2023-2026) with a full-sample
95% CI above zero. The holdout was run once (lock hash unchanged, zero overrides).

**The momentum hypotheses fail, and in equities the sign is the opposite.**
- P1 (price-only momentum): a large first 5-minute move does not continue in ES or NQ. The mean
  executable return is negative in both samples (ES -9.0 / -5.6 bp, NQ -12.2 / -14.5 bp; full-sample
  CIs include 0). ZN is flat (+0.1 bp). In the regressions, the +5 to +20 return loads negatively on
  the first move in ES and NQ in both samples (NQ full sample -0.11, p = 0.08): a mild reversal, not
  continuation.
- P2 (large move + liquidity stress -> follow) is the worst primary rule. On NQ it loses
  -30.5 bp (development, 7 trades) and -37.2 bp (holdout, 2 trades); full sample -32.0 bp,
  95% CI [-53.2, -10.2]. S2-NQd and S2-NQs (NQ depth-only and spread-only stress) and S5C
  (ES/NQ confirmed + stress) lose for the same reason. The interaction |ret_0_5m| x stress in
  Model D is negative for every instrument and sample; for NQ it is -0.17 (full sample, p = 0.01;
  holdout p < 0.001, development p = 0.21).
- P3 (large move + recovered liquidity -> fade) has too few trades to judge (13 portfolio trades in
  92 meetings, 2 in the holdout). The only positive rows (P3 ES, P3-10m) rest on 1-3 trades.

**What the data suggest instead (a new hypothesis, not a result).** In NQ, large moves made while
the book is still stressed at +5 minutes tend to partly *reverse* by +20 minutes. The stressed-book
state looks like overshoot, not unresolved news. This is the opposite of the economic logic
registered for P2. Because the sign was learned from these same 92 meetings, a "stress -> fade"
rule cannot be called validated here. It has to be registered now and tested on meetings after
2026-09 (or on a different event set, such as CPI and NFP releases with the same one-second book)
before it counts as evidence. Its weaknesses:
- 4 of the 7 development NQ P2 trades are from 2022 (the hiking cycle);
- the holdout contributes only 2 trades;
- the per-instrument stress coefficient in Model C is not significant on its own.

**Liquidity alone carries no linear signal.** depth_ratio_5m, spread_ratio_5m, the 1-to-5-minute
recovery measures and the stress score are insignificant in Models B and C for all three markets
in both samples. Whatever information liquidity carries works only through its interaction with a
large move (Model D), and only for NQ.

**ZN.** Nothing works at the event level (P1 to P3, S9 fade and follow). The S9 regression flips
sign between development (-3.0, p = 0.07) and the holdout (+16.5, p = 0.06), the signature of noise.
ZN's depth does overshoot its baseline 10-30 minutes after the statement (figure 11). The
overshoot is larger after moves that continued, but the +10 level does not separate them in
advance.

**Second-level microstructure (S10).** The 5-second change in order-book imbalance predicts the
next 5-60 s mid return in all three markets (p < 0.001; ES +0.2, NQ +0.1, ZN +0.3 bp per unit).
The development coefficients predict the holdout out of sample in ZN (R2 4-8% at 5 s, about 1% at
30-60 s). In ES and NQ the out-of-sample R2 is about zero (at most 0.2%). This is the large-tick
queue-imbalance effect: the predicted mid moves are smaller than one tick and fall inside the
bid-ask spread. It is a microstructure regularity, not an executable FOMC strategy.

**Costs.** Fees are ignored. The median bid-ask cost per round trip is about 0.7 bp for ES and NQ
and 1.3 bp for ZN. One extra tick per side adds about 1.3 bp (ES), 0.4 bp (NQ) and 2.6 bp (ZN). The
losing rules lose 10-40 bp per trade, so the failures are failures of the signal, not of costs.

**Q17: strongest hypothesis for further research.** "In NQ, a large first 5-minute FOMC move made
with a stressed book (low depth, wide spread) partly reverses over the next 15 minutes." Register
it as a new pre-specified fade rule, with the P2 thresholds unchanged and only the direction
flipped. Test it only on data not yet seen: the next FOMC meetings, and other scheduled releases
with the same one-second book. The second candidate is the ZN queue-imbalance effect at 5-30 s,
which needs a tick-level execution model (queue position, passive fills) to say whether any of it
can be captured.
