# Pilot equity-universe verification

All 22 proposed names were S&P 500 constituents during September 8–19, 2025. No replacement is required. Verification used a constituent-history reconstruction (current member plus an addition date before the pilot and no intervening removal) and a cross-check against S&P DJI's official September 5, 2025 rebalance announcement. That announcement's changes took effect September 22, after the pilot, and did not remove any proposed name.

| Ticker | Pilot listing venue | Proposed theme | S&P 500 in pilot? |
|---|---|---|---:|
| NVDA | NASDAQ | growth/duration/rates | Yes |
| MSFT | NASDAQ | growth/duration/rates | Yes |
| AAPL | NASDAQ | growth/duration/rates | Yes |
| AMZN | NASDAQ | growth/duration/rates | Yes |
| META | NASDAQ | growth/duration/rates | Yes |
| GOOGL | NASDAQ | growth/duration/rates | Yes |
| AVGO | NASDAQ | growth/duration/rates | Yes |
| AMD | NASDAQ | growth/duration/rates | Yes |
| TSLA | NASDAQ | high-beta/interpretation-heavy | Yes |
| NFLX | NASDAQ | high-beta/interpretation-heavy | Yes |
| JPM | NYSE | banks/rates | Yes |
| BAC | NYSE | banks/rates | Yes |
| GS | NYSE | banks/rates | Yes |
| COST | NASDAQ | consumer/macro | Yes |
| WMT | NYSE | consumer/macro | Yes |
| HD | NYSE | consumer/macro | Yes |
| XOM | NYSE | energy/inflation | Yes |
| CVX | NYSE | energy/inflation | Yes |
| PLD | NYSE | real estate/long duration | Yes |
| AMT | NYSE | real estate/long duration | Yes |
| CAT | NYSE | industrial/cyclical | Yes |
| BA | NYSE | industrial/cyclical | Yes |

The theme column is not validation of economic sensitivity. `src/analysis/sensitivity.py` estimates exposures to broad-market and rates factors and can add CPI/FOMC surprise factors once vintage consensus data exist.

Sources:

- S&P DJI September 2025 rebalance announcement: https://press.spglobal.com/2025-09-05-AppLovin%2C-Robinhood-Markets-and-Emcor-Group-Set-to-Join-S-P-500-Others-to-Join-S-P-100%2C-S-P-MidCap-400-and-S-P-SmallCap-600
- Constituent history used for reconstruction: https://github.com/datasets/s-and-p-500-companies/blob/main/data/constituents.csv

