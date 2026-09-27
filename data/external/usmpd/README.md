# USMPD monetary policy surprises

Source: U.S. Monetary Policy Event-Study Database (USMPD), Michael Bauer and
Caroline Foshee, Federal Reserve Bank of San Francisco.

| File | Contents |
| --- | --- |
| `mps.csv` | Published surprises per FOMC event: `STMT` (statement window), `PC` (press-conference window), `ME` (whole monetary event). Units: percentage points of the one-year yield; positive = hawkish. |
| `mps_minutes.csv` | Surprises around minutes releases (not used in the FOMC speed tests). |
| `USMPD.xlsx` | Full database: intraday futures, OIS, Treasury and asset-price changes per event (sheets: Statements, Press Conferences, Monetary Events, Minutes). |
| `y1.csv` | One-year GSW zero-coupon yield (`SVENY01`), used to scale the first principal component. |
| `source_scripts/mps.R`, `source_scripts/gss.R` | Original factor code. `src/events/surprises.py` ports both to Python. |

`USMPD.xlsx` adds the raw `MP1`
surprise, the GSS (2005) target/path factors, and the real-time `STMT`/`PC`
factors. The real-time factors re-estimate the PCA and the yield scaling using
only events up to each meeting, which removes the look-ahead in the
full-sample factors. `scripts/analyze_fomc_surprises.py`
checks that the recomputed `STMT` matches `mps.csv` before running the tests.

Run: `python -m scripts.analyze_fomc_surprises` (after `scripts/analyze_fomc_sample.py`).
