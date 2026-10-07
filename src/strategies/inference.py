"""Inference with the FOMC event as the independent unit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

BOOTSTRAP_DRAWS = 10_000
SEED = 20261007


def ols_clustered(data: pd.DataFrame, y: str, xs: list[str], cluster: str = "event_id",
                  fixed_effects: str | None = None) -> pd.DataFrame:
    """OLS with standard errors clustered by event. One row per coefficient (constant included)."""
    columns = [y, *xs, cluster] + ([fixed_effects] if fixed_effects else [])
    sample = data[columns].replace([np.inf, -np.inf], np.nan).dropna()
    n_clusters = sample[cluster].nunique()
    if len(sample) < len(xs) + 3 or n_clusters < 5:
        return pd.DataFrame([{"term": "insufficient_data", "N": len(sample), "N_events": n_clusters}])
    constant = [x for x in xs if sample[x].astype(float).std() <= 1e-12]
    xs = [x for x in xs if x not in constant]      # no variation: not identified, reported as dropped
    if not xs:
        return pd.DataFrame([{"term": "insufficient_data", "N": len(sample), "N_events": n_clusters,
                              "dropped_constant": "|".join(constant)}])
    X = sample[xs].astype(float)
    if fixed_effects:
        X = pd.concat([X, pd.get_dummies(sample[fixed_effects], prefix="fe", drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X, has_constant="add")
    fit = sm.OLS(sample[y].astype(float), X).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(sample[cluster])[0]})
    ci = fit.conf_int()
    out = pd.DataFrame({
        "term": fit.params.index, "coef": fit.params.values, "se": fit.bse.values, "t_stat": fit.tvalues.values,
        "p_value": fit.pvalues.values, "ci_low": ci[0].values, "ci_high": ci[1].values,
    })
    out = out.loc[~out["term"].str.startswith("fe_")]
    out["r2"], out["N"], out["N_events"] = fit.rsquared, len(sample), n_clusters
    out["dropped_constant"] = "|".join(constant)
    return out.reset_index(drop=True)


def event_bootstrap_mean(values: pd.Series, groups: pd.Series | None = None, draws: int = BOOTSTRAP_DRAWS,
                         seed: int = SEED) -> tuple[float, float]:
    """95% CI of the mean, resampling events (values are first averaged within each event)."""
    series = pd.Series(np.asarray(values, float))
    if groups is not None:
        series = series.groupby(np.asarray(groups)).mean()
    series = series.dropna()
    if len(series) < 3:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    sample = rng.choice(series.to_numpy(), size=(draws, len(series)), replace=True).mean(axis=1)
    return float(np.percentile(sample, 2.5)), float(np.percentile(sample, 97.5))


def t_test(values: pd.Series) -> tuple[float, float]:
    values = pd.Series(values, dtype=float).dropna()
    if len(values) < 3 or values.std(ddof=1) == 0:
        return np.nan, np.nan
    result = stats.ttest_1samp(values, 0.0)
    return float(result.statistic), float(result.pvalue)


def holm(pvalues: pd.Series) -> pd.Series:
    from statsmodels.stats.multitest import multipletests

    p = pd.Series(pvalues, dtype=float)
    out = pd.Series(np.nan, index=p.index)
    ok = p.notna()
    if ok.any():
        out[ok] = multipletests(p[ok], method="holm")[1]
    return out
