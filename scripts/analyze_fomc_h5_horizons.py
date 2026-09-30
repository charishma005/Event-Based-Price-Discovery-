"""Multi-horizon H5: FOMC statement surprise size vs response size and timing.

For every statement at t=0 and horizon h in 1s, 5s, 30s, 1m, 5m, 10m, 20m, 30m,
R_h = 10000 * [ln(mid_{t+h}) - ln(mid_{t-})] in basis points, from the last
valid pre-statement midpoint. The 30-minute endpoint is the press-conference
start (2:30 p.m. after a 2:00 p.m. statement), the last point before new
scheduled information.

H5a  |surprise| vs |R_h| at each horizon. Positive = larger surprises move
     prices more. Note: USMPD surprises are built from rate-futures moves around
     the statement, so for ZN in particular this is close to mechanical.
H5b  |surprise| vs |R_h| / |R_30m| at each horizon before 30m. H5 predicts a
     negative correlation: a larger surprise leaves a smaller share of the
     30-minute move done early. Events whose |R_30m| is in the bottom quartile
     of their instrument are dropped, because a ratio over a near-zero
     endpoint is noise.

Also writes a small/medium/large surprise-tercile response profile.
Horizons past 5 minutes need response_horizons rebuilt by
process_fomc_sample.py after the 10/20/30-minute horizons were added; until
then the script runs H5a on the horizons present and skips H5b.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from scripts.analyze_fomc_surprises import _adjust, _meetings, _write
from src.events.surprises import build_surprise_panel
from src.utils.config import PROJECT_ROOT

HORIZONS = (1, 5, 30, 60, 300, 600, 1200, 1800)
LABELS = {1: "1s", 5: "5s", 30: "30s", 60: "1m", 300: "5m", 600: "10m", 1200: "20m", 1800: "30m"}
ENDPOINT = 1800
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
EQUITY = ("ES.v.0", "NQ.v.0")
MEASURES = ("STMT", "STMT_real_time")
SMALL_ENDPOINT_QUANTILE = 0.25
MIN_OBS = 8
TERCILES = ("small", "medium", "large")


def absolute_returns(horizons: pd.DataFrame) -> pd.DataFrame:
    """Meeting x instrument x horizon |R_h| for covered statement horizons, plus an ES+NQ average."""
    data = horizons.loc[
        horizons["subevent"].eq("statement")
        & horizons["dataset_condition"].eq("available")
        & horizons["full_horizon_covered"].astype(bool)
        & horizons["horizon_seconds"].isin(HORIZONS)
        & horizons["instrument"].isin(INSTRUMENTS)
    ].dropna(subset=["log_return_bp"])
    data = data.assign(abs_return_bp=data["log_return_bp"].abs())[
        ["meeting", "instrument", "horizon_seconds", "abs_return_bp"]
    ]
    equity = (
        data.loc[data["instrument"].isin(EQUITY)]
        .groupby(["meeting", "horizon_seconds"])["abs_return_bp"]
        .agg(["mean", "count"])
        .reset_index()
    )
    equity = equity.loc[equity["count"].eq(len(EQUITY))].drop(columns="count")
    equity = equity.rename(columns={"mean": "abs_return_bp"}).assign(instrument="equity_average")
    return pd.concat([data, equity], ignore_index=True)


def response_fractions(returns: pd.DataFrame) -> pd.DataFrame:
    """|R_h| / |R_30m|, dropping events whose endpoint is zero or in the bottom quartile of its instrument."""
    endpoint = returns.loc[returns["horizon_seconds"].eq(ENDPOINT), ["meeting", "instrument", "abs_return_bp"]]
    endpoint = endpoint.rename(columns={"abs_return_bp": "endpoint_bp"})
    cutoff = endpoint.groupby("instrument")["endpoint_bp"].transform(
        lambda values: values.quantile(SMALL_ENDPOINT_QUANTILE)
    )
    endpoint = endpoint.loc[endpoint["endpoint_bp"].gt(cutoff) & endpoint["endpoint_bp"].gt(0)]
    data = returns.merge(endpoint, on=["meeting", "instrument"])
    return data.assign(fraction=data["abs_return_bp"] / data["endpoint_bp"])


def surprise_terciles(surprises: pd.DataFrame, measure: str = "STMT") -> pd.Series:
    """Meeting -> small/medium/large by |surprise| terciles."""
    magnitude = surprises.set_index("meeting")[measure].abs().dropna()
    return pd.qcut(magnitude.rank(method="first"), 3, labels=list(TERCILES)).astype(str)


def _spearman(x: pd.Series, y: pd.Series, alternative: str) -> tuple[float, float, float]:
    if len(x) < MIN_OBS or x.nunique() < 2 or y.nunique() < 2:
        return np.nan, np.nan, np.nan
    one = spearmanr(x, y, alternative=alternative)
    return float(one.statistic), float(one.pvalue), float(spearmanr(x, y).pvalue)


def _correlations(frame: pd.DataFrame, value: str, alternative: str, surprises: pd.DataFrame) -> pd.DataFrame:
    data = frame.merge(surprises, on="meeting")
    rows = []
    for (instrument, horizon), group in data.groupby(["instrument", "horizon_seconds"]):
        for measure in MEASURES:
            if measure not in group:
                continue
            sample = group.dropna(subset=[measure, value])
            rho, one_sided, two_sided = _spearman(sample[measure].abs(), sample[value], alternative)
            rows.append(
                {
                    "instrument": instrument,
                    "horizon": LABELS[int(horizon)],
                    "horizon_seconds": int(horizon),
                    "measure": measure,
                    "observations": len(sample),
                    f"median_{value}": float(sample[value].median()) if len(sample) else np.nan,
                    "spearman_rho": rho,
                    f"one_sided_p_{'positive' if alternative == 'greater' else 'negative'}": one_sided,
                    "two_sided_p": two_sided,
                }
            )
    table = pd.DataFrame(rows).sort_values(["instrument", "measure", "horizon_seconds"], ignore_index=True)
    return _adjust(table, "two_sided_p")


def response_profile(returns: pd.DataFrame, fractions: pd.DataFrame, terciles: pd.Series) -> pd.DataFrame:
    groups = terciles.rename("surprise_group").reset_index()
    data = returns.merge(groups, on="meeting")
    data = pd.concat([data, data.assign(surprise_group="all")], ignore_index=True)
    profile = (
        data.groupby(["instrument", "surprise_group", "horizon_seconds"])["abs_return_bp"]
        .agg(observations="count", mean_abs_return_bp="mean", median_abs_return_bp="median")
        .reset_index()
    )
    if not fractions.empty:
        shares = fractions.merge(groups, on="meeting")
        shares = pd.concat([shares, shares.assign(surprise_group="all")], ignore_index=True)
        shares = (
            shares.groupby(["instrument", "surprise_group", "horizon_seconds"])["fraction"]
            .agg(fraction_observations="count", median_fraction_of_30m="median")
            .reset_index()
        )
        profile = profile.merge(shares, on=["instrument", "surprise_group", "horizon_seconds"], how="left")
    profile.insert(2, "horizon", profile["horizon_seconds"].map(LABELS))
    order = {name: i for i, name in enumerate((*TERCILES, "all"))}
    return profile.sort_values(
        ["instrument", "surprise_group", "horizon_seconds"], key=lambda s: s.map(order) if s.name == "surprise_group" else s,
        ignore_index=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-horizon H5 on FOMC statements")
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml", help="File under config/")
    parser.add_argument("--root", help="Folder under data/processed/ (default: config name)")
    parser.add_argument("--suffix", help="Appended to table names (default: config name after fomc_sample)")
    args = parser.parse_args()
    stem = args.config.removesuffix(".yaml")
    root = PROJECT_ROOT / "data" / "processed" / (args.root or stem)
    suffix = args.suffix if args.suffix is not None else stem.removeprefix("fomc_sample")

    panel = build_surprise_panel(_meetings(args.config))
    surprises = panel.loc[panel["dataset_condition"].eq("available"), ["meeting", *MEASURES]]
    returns = absolute_returns(pd.read_csv(root / "response_horizons.csv"))
    present = sorted(returns["horizon_seconds"].unique())
    print("Horizons present: " + ", ".join(LABELS[int(h)] for h in present))

    h5a = _correlations(returns, "abs_return_bp", "greater", surprises)
    _write(h5a, f"fomc_h5a_response_magnitude{suffix}")
    has_endpoint = ENDPOINT in present
    fractions = response_fractions(returns) if has_endpoint else pd.DataFrame()
    if has_endpoint:
        h5b = _correlations(fractions.loc[fractions["horizon_seconds"].lt(ENDPOINT)], "fraction", "less", surprises)
        _write(h5b, f"fomc_h5b_response_fraction{suffix}")
    else:
        print("No 30-minute horizon: rerun process_fomc_sample.py to add 10/20/30 minutes; H5b skipped.")
    profile = response_profile(returns, fractions, surprise_terciles(surprises))
    _write(profile, f"fomc_h5_response_profile{suffix}")

    headline = ["instrument", "horizon", "observations", "spearman_rho", "two_sided_p", "holm_p"]
    stmt = h5a["measure"].eq("STMT")
    print("\nH5a |STMT| vs |R_h|:")
    print(h5a.loc[stmt, headline].round(4).to_string(index=False))
    if has_endpoint:
        print("\nH5b |STMT| vs |R_h|/|R_30m|:")
        print(h5b.loc[h5b["measure"].eq("STMT"), headline].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
