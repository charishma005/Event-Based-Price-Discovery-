# H1–H6 status, 2015–2026 FOMC sample

> **Update, October 2026.** `reports/professor_steps_1_5_8.md` adds to this
> page. H1 and H2 were re-tested with a pre-declared short-horizon share, which
> does vary across event types (step 1). For H4, the macro arm now reaches back
> to 2015 with matched control mornings (step 5), and there is a larger
> unscheduled sample with no withdrawal before the arrival, plus an account of
> why NQ depth does not fall (step 8). Steps 2, 3, 4, 6 and 7 (H3, the H4
> control tests for FOMC, H5 and H6, statement versus press conference) are
> done separately. The text below is the status before that work.

Sample: `config/fomc_sample_2015_2026.yaml`, 93 scheduled meetings (77 with
press conferences), processed to `data/processed/fomc_sample_2015_2026/`. The
sample includes the original twelve 2024–2025 meetings, so it is a larger
sample, not an independent replication.

Tables: `tables/fomc_h2_quote_fraction_2015_2026.csv`,
`fomc_h4_depth_withdrawal_2015_2026.csv`, `fomc_h5_surprise_speed_2015_2026.csv`,
`fomc_h6_surprise_asymmetry_2015_2026.csv`, plus `_large_moves_2015_2026`
robustness versions of the H5/H6 tables. H5/H6 tables carry `holm_p` and
`bh_q` columns adjusted across every cell of the table.

| Hypothesis | Status | Main reason |
|---|---|---|
| H1 | Rejected | First quote carries ~0% of scalar macro moves (macro sample; not re-tested here) |
| H2 | Supported in sample | Below-40% share in 155/155 statement and 173/174 press obs.; but the measure is ~0 for every event type |
| H3 | Not identified | No vintage forecast-dispersion source |
| H4 | Partly supported | Matched-control evidence for 2024–2025; 93-meeting test is within-event only |
| H5 | Not supported | No equity cell survives Holm; surviving ZN cells share inputs with the surprise |
| H6 | Not supported | No cell survives Holm in either sample |

## H1 — Rejected (unchanged)
Tested on the numeric macro cross-section, not FOMC meetings.

## H2 — Supported in sample, but a weak test
Per-instrument tests (one observation per meeting) all give one-sided Wilcoxon
p < 1e-12. The pooled rows combine three instruments per meeting and overstate
the effective sample. The median first-quote fraction is exactly zero for
numeric releases (H1) and FOMC communication (H2) alike, so the result does not
test the proposal's scalar-versus-narrative contrast.

## H3 — Not identified (unchanged)
Needs a licensed vintage consensus/dispersion source.

## H4 — Partly supported; the extension adds limited evidence
Placebo windows exist only for 2024–2025, so the 93-meeting test compares the
final minute with the prior four minutes of the same event, with no control
days. The ratio is below 1 in 92/92 statements (mean 0.584, p = 4.1e-17) and
59/76 press openings (mean 0.923, p = 2.7e-8). This cannot rule out a routine
2:00 p.m. depth pattern. Controls for 2015–2023 are needed.

## H5 — Not supported
- 105 cells; 18 raw p < 0.05; 3 survive Holm. All three are ZN statement 50%
  crossings (rho ≈ -0.46). USMPD surprises are built from rate-futures moves in
  the same window, so ZN is not independent evidence.
- ES+NQ average, statement: rho = -0.12, p = 0.28.
- Press meeting average: rho = 0.229, p = 0.046, Holm p = 1.0; drops to 0.105
  (p = 0.38) after removing near-zero and bottom-quartile moves.
- The crossing horizon is a fraction of the 5-minute move, so small moves give
  noisy horizons and can create a mechanical negative relation.
- The twelve-meeting headline (rho = -0.79, p = 0.002) has Holm p = 0.22.

## H6 — Not supported
105 cells; 3 raw p < 0.05; none survives Holm or BH. The twelve-meeting ES/NQ
press asymmetry (raw p = 0.003/0.012; smallest Holm p in that table 0.33) is
absent at 93 meetings (ES p = 0.75, NQ p = 0.52). Hawkish and dovish groups are
unbalanced (63 vs 27 statements under STMT).

## Other limitations
- 2015–2026 spans the zero lower bound, the 2020 response and the 2022–2023
  hikes; before 2019 press conferences followed only quarterly projection
  meetings.
- The stable-within-10% measure sits near the 300-second window end (medians
  ~290 s) and is effectively censored.
