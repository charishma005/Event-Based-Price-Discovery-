from __future__ import annotations

import pandas as pd
import statsmodels.api as sm


def build_daily_factor_panel(
    *,
    market_returns: pd.Series,
    rate_changes: pd.Series,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Create daily market/rates and announcement factors for universe validation."""
    panel = pd.concat(
        [
            market_returns.rename("broad_market_return"),
            rate_changes.rename("rate_change"),
        ],
        axis=1,
    ).sort_index()
    panel.index = pd.to_datetime(panel.index).normalize()
    calendar = events.copy()
    calendar["event_date"] = pd.to_datetime(calendar["event_date"]).dt.normalize()
    macro_dates = set(calendar["event_date"])
    fomc_dates = set(
        calendar.loc[calendar["event_category"].eq("monetary_policy"), "event_date"]
    )
    cpi_rows = calendar.loc[
        calendar["event_name"].astype("string").str.contains(
            "Consumer Price Index", case=False, na=False
        )
    ].copy()
    cpi_dates = set(cpi_rows["event_date"])
    panel["major_macro_day"] = panel.index.isin(macro_dates).astype(int)
    panel["fomc_day"] = panel.index.isin(fomc_dates).astype(int)
    panel["cpi_day"] = panel.index.isin(cpi_dates).astype(int)
    panel["cpi_standardized_surprise"] = pd.NA
    if "standardized_surprise" in cpi_rows:
        surprise = pd.to_numeric(cpi_rows["standardized_surprise"], errors="coerce")
        surprise_by_date = pd.Series(surprise.to_numpy(), index=cpi_rows["event_date"])
        panel["cpi_standardized_surprise"] = panel.index.map(surprise_by_date)
    return panel


def estimate_historical_sensitivities(
    stock_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate stock exposures instead of assuming the YAML themes are correct.

    Inputs are date-indexed returns. Factor columns can include broad market and
    rate changes; additional event/surprise columns can be added after consensus
    data are licensed.
    """
    rows: list[dict] = []
    aligned = stock_returns.join(factor_returns, how="inner")
    factors = list(factor_returns.columns)
    for ticker in stock_returns.columns:
        sample = aligned[[ticker, *factors]].dropna()
        if len(sample) <= len(factors) + 5:
            continue
        model = sm.OLS(sample[ticker], sm.add_constant(sample[factors])).fit()
        row = {"ticker": ticker, "nobs": int(model.nobs), "r_squared": model.rsquared}
        row.update({f"beta_{name}": model.params[name] for name in factors})
        rows.append(row)
    return pd.DataFrame(rows)
