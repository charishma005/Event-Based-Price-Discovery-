from __future__ import annotations

import databento as db
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.utils.config import PROJECT_ROOT, load_yaml


RAW_DIR = PROJECT_ROOT / "data" / "raw" / "databento"


def _daily_file(dataset: str) -> object:
    """Return the newest cached daily-bar file for a Databento dataset."""
    candidates = sorted(
        RAW_DIR.glob(f"{dataset}-ohlcv-1d-*.dbn.zst"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(f"No cached {dataset} ohlcv-1d file in {RAW_DIR}")
    return candidates[-1]


def _daily_closes(path) -> pd.DataFrame:
    data = db.DBNStore.from_file(path).to_df().reset_index()
    timestamp_column = data.columns[0]
    data = data.rename(columns={timestamp_column: "timestamp_utc"})
    data["date"] = pd.to_datetime(data["timestamp_utc"], utc=True).dt.tz_localize(None).dt.normalize()
    return data.pivot(index="date", columns="symbol", values="close").sort_index()


def main() -> None:
    universe = pd.DataFrame(
        load_yaml(PROJECT_ROOT / "config" / "universe.yaml")["securities"]
    )
    stock_prices = _daily_closes(_daily_file("EQUS.MINI"))
    futures_prices = _daily_closes(_daily_file("GLBX.MDP3"))
    stock_returns = np.log(stock_prices).diff()
    futures_returns = np.log(futures_prices).diff()
    factors = pd.DataFrame(
        {
            "broad_market_return": stock_returns["SPY"],
            # A positive ZN return generally corresponds to a fall in intermediate yields.
            "treasury_price_return": futures_returns["ZN.v.0"],
        }
    )

    event_config = load_yaml(PROJECT_ROOT / "config" / "historical_event_dates.yaml")
    event_dates = {
        event_class: pd.DatetimeIndex(pd.to_datetime(details["dates"]))
        for event_class, details in event_config["event_classes"].items()
    }
    all_event_dates = pd.DatetimeIndex(
        sorted({date for dates in event_dates.values() for date in dates})
    )

    rows: list[dict[str, object]] = []
    residual_frames: list[pd.DataFrame] = []
    for security in universe.itertuples(index=False):
        sample = pd.concat(
            [stock_returns[security.ticker].rename("stock_return"), factors],
            axis=1,
            sort=False,
        ).dropna()
        estimation_sample = sample.loc[~sample.index.isin(all_event_dates)]
        model = sm.OLS(
            estimation_sample["stock_return"],
            sm.add_constant(estimation_sample[factors.columns]),
        ).fit(cov_type="HC3")
        predicted = model.predict(sm.add_constant(sample[factors.columns]))
        residual = sample["stock_return"] - predicted
        event_class = pd.Series("non_event", index=sample.index, dtype="object")
        for class_name, dates in event_dates.items():
            event_class.loc[event_class.index.isin(dates)] = class_name
        residual_frames.append(
            pd.DataFrame(
                {
                    "date": sample.index,
                    "ticker": security.ticker,
                    "sector": security.sector,
                    "theme": security.theme,
                    "event_class": event_class.to_numpy(),
                    "stock_return": sample["stock_return"].to_numpy(),
                    "predicted_return": predicted.to_numpy(),
                    "market_rate_residual": residual.to_numpy(),
                    "absolute_residual_bp": residual.abs().to_numpy() * 10_000,
                }
            )
        )
        rows.append(
            {
                "ticker": security.ticker,
                "sector": security.sector,
                "theme": security.theme,
                "nobs": int(model.nobs),
                "r_squared": float(model.rsquared),
                "beta_market": float(model.params["broad_market_return"]),
                "t_market_hc3": float(model.tvalues["broad_market_return"]),
                "beta_treasury_price": float(model.params["treasury_price_return"]),
                "t_treasury_price_hc3": float(model.tvalues["treasury_price_return"]),
                "rate_sign_interpretation": "positive=stock tends to rise when ZN rises/intermediate yields fall",
                "sample_start": estimation_sample.index.min(),
                "sample_end": estimation_sample.index.max(),
            }
        )
    estimates = pd.DataFrame(rows)
    estimates["market_beta_rank_desc"] = estimates["beta_market"].rank(
        ascending=False, method="min"
    ).astype(int)
    estimates["lower_yield_sensitivity_rank_desc"] = estimates[
        "beta_treasury_price"
    ].rank(ascending=False, method="min").astype(int)

    output_dir = PROJECT_ROOT / "data" / "processed" / "stock_cross_section"
    figure_dir = PROJECT_ROOT / "figures" / "stock_cross_section"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    estimates.to_csv(output_dir / "historical_sensitivities.csv", index=False)
    estimates.to_parquet(output_dir / "historical_sensitivities.parquet", index=False)
    residuals = pd.concat(residual_frames, ignore_index=True)
    residuals.to_parquet(output_dir / "historical_event_day_residuals.parquet", index=False)
    baseline = (
        residuals.loc[residuals["event_class"].eq("non_event")]
        .groupby("ticker")["absolute_residual_bp"]
        .mean()
        .rename("non_event_mean_abs_residual_bp")
    )
    event_sensitivity = (
        residuals.loc[~residuals["event_class"].eq("non_event")]
        .groupby(["ticker", "sector", "theme", "event_class"], as_index=False)
        .agg(
            event_days=("date", "nunique"),
            mean_abs_residual_bp=("absolute_residual_bp", "mean"),
            median_abs_residual_bp=("absolute_residual_bp", "median"),
            mean_signed_residual_bp=("market_rate_residual", lambda x: x.mean() * 10_000),
        )
        .join(baseline, on="ticker")
    )
    event_sensitivity["event_to_non_event_abs_ratio"] = (
        event_sensitivity["mean_abs_residual_bp"]
        / event_sensitivity["non_event_mean_abs_residual_bp"]
    )
    event_sensitivity.to_csv(output_dir / "historical_event_day_sensitivities.csv", index=False)
    event_sensitivity.to_parquet(
        output_dir / "historical_event_day_sensitivities.parquet", index=False
    )
    theme = (
        estimates.groupby("theme", as_index=False)
        .agg(
            mean_market_beta=("beta_market", "mean"),
            mean_treasury_price_beta=("beta_treasury_price", "mean"),
            median_r_squared=("r_squared", "median"),
            stock_count=("ticker", "size"),
        )
    )
    theme.to_csv(output_dir / "historical_theme_sensitivities.csv", index=False)
    event_theme = (
        event_sensitivity.groupby(["theme", "event_class"], as_index=False)
        .agg(
            mean_abs_residual_bp=("mean_abs_residual_bp", "mean"),
            median_event_to_non_event_ratio=("event_to_non_event_abs_ratio", "median"),
            stock_count=("ticker", "size"),
        )
    )
    event_theme.to_csv(
        output_dir / "historical_event_day_sensitivities_by_theme.csv", index=False
    )

    fig, ax = plt.subplots(figsize=(9, 6.5))
    theme_names = universe["theme"].drop_duplicates().tolist()
    colors = plt.cm.tab10(np.linspace(0, 1, len(theme_names)))
    for theme_name, color in zip(theme_names, colors):
        sample = estimates.loc[estimates["theme"].eq(theme_name)]
        ax.scatter(
            sample["beta_market"],
            sample["beta_treasury_price"],
            label=theme_name.replace("_", " "),
            color=color,
            s=42,
            alpha=0.85,
        )
        for row in sample.itertuples(index=False):
            ax.annotate(row.ticker, (row.beta_market, row.beta_treasury_price), xytext=(3, 3), textcoords="offset points", fontsize=8)
    ax.axhline(0, color="black", lw=0.7)
    ax.axvline(1, color="black", lw=0.7, ls="--")
    ax.set(
        xlabel="Market beta to SPY daily return",
        ylabel="ZN price-return beta (positive generally means lower-yield sensitivity)",
        title="Measured stock sensitivities, September 2024–September 2025",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()
    fig.savefig(figure_dir / "historical_market_rate_sensitivity.png", dpi=180)
    plt.close(fig)

    heatmap = event_sensitivity.pivot(
        index="ticker", columns="event_class", values="event_to_non_event_abs_ratio"
    ).reindex(universe["ticker"])
    fig, ax = plt.subplots(figsize=(7.5, 8.5))
    image = ax.imshow(heatmap.to_numpy(), cmap="RdBu_r", vmin=0.5, vmax=2.0, aspect="auto")
    ax.set_xticks(range(len(heatmap.columns)), [name.replace("_", " ") for name in heatmap.columns])
    ax.set_yticks(range(len(heatmap.index)), heatmap.index)
    for row_index in range(len(heatmap.index)):
        for column_index in range(len(heatmap.columns)):
            value = heatmap.iloc[row_index, column_index]
            ax.text(column_index, row_index, f"{value:.2f}", ha="center", va="center", fontsize=7)
    ax.set_title("Absolute abnormal return on event days / ordinary days")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.85)
    colorbar.set_label("ratio (daily market- and ZN-adjusted residual)")
    fig.tight_layout()
    fig.savefig(figure_dir / "historical_event_day_sensitivity.png", dpi=180)
    plt.close(fig)
    print(f"Wrote historical sensitivity estimates for {len(estimates)} stocks.")


if __name__ == "__main__":
    main()
