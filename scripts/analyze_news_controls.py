from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.utils.config import PROJECT_ROOT


def main() -> None:
    processed = PROJECT_ROOT / "data" / "processed"
    flags = pd.read_parquet(processed / "event_news_contamination.parquet")
    cross = pd.read_parquet(
        processed / "stock_cross_section" / "fomc_1s_cross_section.parquet"
    )
    controls = flags.rename(columns={"instrument": "ticker"})[
        [
            "event_id", "ticker", "alpha_vantage_query_coverage",
            "company_news_contamination", "article_count",
            "max_ticker_relevance", "max_abs_ticker_sentiment",
        ]
    ]
    panel = cross.merge(controls, on=["event_id", "ticker"], how="left", validate="many_to_one")
    panel["news_contamination"] = panel["company_news_contamination_y"].fillna(
        panel["company_news_contamination_x"]
    ).fillna(False).astype(bool)
    panel["news_sentiment_descriptor"] = panel["max_abs_ticker_sentiment"].fillna(0.0)
    panel["news_relevance_descriptor"] = panel["max_ticker_relevance"].fillna(0.0)
    panel["log_absolute_return"] = np.log1p(panel["absolute_return_bp"].clip(lower=0))

    summary = (
        panel.groupby(["event_id", "horizon_seconds"], as_index=False)
        .agg(
            instruments=("ticker", "nunique"),
            contaminated_instruments=("news_contamination", "sum"),
            mean_absolute_return_bp=("absolute_return_bp", "mean"),
            median_absolute_return_bp=("absolute_return_bp", "median"),
            max_news_relevance=("news_relevance_descriptor", "max"),
            max_abs_news_sentiment=("news_sentiment_descriptor", "max"),
        )
    )
    sample = panel.dropna(subset=["log_absolute_return", "theme", "event_id"]).copy()
    model = smf.ols(
        "log_absolute_return ~ news_contamination + news_sentiment_descriptor "
        "+ C(event_id) + C(horizon_seconds) + C(theme)",
        data=sample,
    ).fit(cov_type="HC1")
    coefficients = pd.DataFrame(
        {
            "term": model.params.index,
            "coefficient": model.params.values,
            "standard_error_hc1": model.bse.values,
            "p_value": model.pvalues.values,
            "confidence_interval_low": model.conf_int()[0].values,
            "confidence_interval_high": model.conf_int()[1].values,
            "nobs": int(model.nobs),
            "r_squared": model.rsquared,
        }
    )
    output = processed / "news_controls"
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "fomc_cross_section_with_news_controls": panel,
        "news_contamination_summary": summary,
        "news_control_regression": coefficients,
    }
    for name, frame in products.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
        frame.to_csv(output / f"{name}.csv", index=False)
    focus = coefficients.loc[
        coefficients["term"].isin(
            ["news_contamination[T.True]", "news_sentiment_descriptor"]
        )
    ]
    print(f"Fitted descriptive news-control model on {int(model.nobs)} observations.")
    print(focus[["term", "coefficient", "standard_error_hc1", "p_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
