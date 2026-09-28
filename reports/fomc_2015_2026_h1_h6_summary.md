# H1–H6 status, 2015–2026 FOMC sample

Source: `config/fomc_sample_2015_2026.yaml` (93 scheduled meetings, 77 with
press conferences), processed to `data/processed/fomc_sample_2015_2026/`.
Tables: `tables/fomc_h2_quote_fraction_2015_2026.csv`,
`fomc_h4_depth_withdrawal_2015_2026.csv`, `fomc_h5_surprise_speed_2015_2026.csv`,
`fomc_h6_surprise_asymmetry_2015_2026.csv`.

H1 and H3 are unaffected by this extension: H1 is tested on the numeric macro
cross-section, not the FOMC meeting count, and H3 remains blocked by the
absence of a vintage forecast-dispersion source regardless of sample size.
Both keep their prior status below.

## H1 — Rejected (unchanged)
Scalar macro releases do not place >70% of the five-minute move in the
literal first quote (ES/NQ/ZN opposite-direction p < 4.8e-7). Not re-tested
here; source is the macro cross-section, not FOMC meetings.

## H2 — Supported in sample (strengthened)
Narrative (statement/press) first-quote share stays below 40% at much larger
n: statement 155/155 eligible observations below 40% (median fraction 0.0,
one-sided Wilcoxon p = 2.40e-32, 84 meetings); press 173/174 below 40%
(median 0.0, p = 1.80e-34, 75 meetings). Previously: 23/23 statement,
28/28 press (p = 4.2e-6 / 3.5e-7). The result holds at roughly 7x the
observation count.

## H3 — Not identified (unchanged)
Still requires a licensed vintage consensus/dispersion source; Databento and
Alpha Vantage do not supply it.

## H4 — Partly supported (confirmed at scale)
Meeting-cluster-average pre-event depth ratio (final minute / prior four
minutes) stays below 1: statement mean 0.584, median 0.569, 92/92 events
below 1 (sign p = 2.02e-28, Wilcoxon p = 4.07e-17); press mean 0.923,
median 0.914, 59/76 below 1 (sign p = 6.98e-7, Wilcoxon p = 2.72e-8).
Withdrawal is much sharper around statements than press openings, consistent
with the original 12-meeting finding, now on 92/76 events instead of 12.

## H5 — Not supported for statements; press now marginal (direction unchanged, weaker)
Meeting-average Spearman rho between |surprise| and horizon-to-50%-crossing:
- Statement (STMT), 50s crossing: rho = -0.284, n = 92, two-sided p = 0.0061
  — still negative (larger surprises resolve *faster*), same direction as the
  12-meeting result (rho = -0.79, p = 0.002) but much weaker once averaged
  over 8x the meetings.
- Press (PC), 50s crossing: rho = +0.229, n = 76, two-sided p = 0.046 —
  borderline positive, in the hypothesized direction but weak.
- At 90s the statement effect is gone (rho = 0.061, p = 0.56) while press
  strengthens slightly (rho = 0.273, p = 0.017). At the stable-within-10%
  horizon neither is significant (statement p = 0.061, press p = 0.77).

Conclusion: H5 remains not supported for statements (surprises are absorbed
faster, not slower, as before), and the mixed/inconsistent press-conference
pattern persists rather than resolving with more meetings.

## H6 — No longer even weakly supported (reversal from the 12-meeting sample)
The 12-meeting result (hawkish press surprises slower in ES 50%-crossings,
p = 0.003; NQ, p = 0.012) does not replicate at 93 meetings:
- Press, 50s crossing: ES p = 0.75, NQ p = 0.52, ZN p = 0.32, meeting-average
  p = 0.45 — none significant.
- Statement, all crossings/instruments: none significant except ZN at the
  stable-within-10% horizon (hawkish median 287s vs dovish 270s,
  Mann-Whitney two-sided p = 0.0104), which was not the significant cell
  before (ES/NQ were, at 50s).

Conclusion: H6 should move from "inconclusive" to "not supported" — the
asymmetry that appeared in the original small sample does not survive a
~7x-larger sample and shows up (weakly) in a different instrument/horizon
than before, consistent with the paper's own caution that it was "a
hypothesis for a longer panel rather than evidence of asymmetric
absorption."
