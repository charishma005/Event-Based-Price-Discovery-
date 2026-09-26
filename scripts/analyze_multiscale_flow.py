from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
HORIZONS = (5.0, 60.0, 300.0)


def _fit(sample: pd.DataFrame, liquidity_conditioned: bool) -> dict[str, float | int]:
    columns = ["return", "signed_volume", "lag_touch_depth"]
    data = sample[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    data = data.loc[data["lag_touch_depth"].gt(0)]
    if len(data) < 100:
        raise ValueError("at least 100 finite intervals are required")
    median_depth = float(data["lag_touch_depth"].median())
    inverse_depth_state = median_depth / data["lag_touch_depth"] - 1.0
    interaction = data["signed_volume"] * inverse_depth_state
    regressors = [np.ones(len(data)), data["signed_volume"].to_numpy(float)]
    if liquidity_conditioned:
        regressors.append(interaction.to_numpy(float))
    x = np.column_stack(regressors)
    y = data["return"].to_numpy(float)
    coefficients, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ coefficients
    total_ss = float(np.square(y - y.mean()).sum())
    residual_ss = float(np.square(y - fitted).sum())
    return {
        "intercept": float(coefficients[0]),
        "flow_coefficient": float(coefficients[1]),
        "liquidity_interaction_coefficient": (
            float(coefficients[2]) if liquidity_conditioned else 0.0
        ),
        "training_median_depth": median_depth,
        "nobs": len(data),
        "r_squared": np.nan if total_ss == 0 else 1 - residual_ss / total_ss,
    }


def _predict_component(sample: pd.DataFrame, fit: dict[str, float | int]) -> float:
    depth = sample["lag_touch_depth"].replace(0, np.nan)
    state = float(fit["training_median_depth"]) / depth - 1.0
    flow = sample["signed_volume"].fillna(0.0)
    return float(
        (
            float(fit["flow_coefficient"]) * flow
            + float(fit["liquidity_interaction_coefficient"]) * flow * state
        ).sum(min_count=1)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare sub-second and liquidity-conditioned signed-flow models"
    )
    parser.add_argument(
        "--samples", nargs="+", default=["macro_sample", "macro_sample_2024"],
        help="Processed macro directories to pool",
    )
    parser.add_argument("--output", default="macro_multiyear")
    args = parser.parse_args()
    frames = []
    for sample_name in args.samples:
        path = PROJECT_ROOT / "data" / "processed" / sample_name / "subsecond_intervals.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            frame["sample_name"] = sample_name
            frames.append(frame)
    if not frames:
        raise RuntimeError("No subsecond interval products were found")
    intervals = pd.concat(frames, ignore_index=True)
    intervals = intervals.loc[intervals["dataset_condition"].eq("available")]
    fits: list[dict[str, object]] = []
    estimates: list[dict[str, object]] = []
    bundles = sorted(intervals["bundle_id"].unique())
    for focal_bundle in bundles:
        for instrument in INSTRUMENTS:
            for frequency in sorted(intervals["frequency"].unique()):
                training = intervals.loc[
                    intervals["bundle_id"].ne(focal_bundle)
                    & intervals["instrument"].eq(instrument)
                    & intervals["frequency"].eq(frequency)
                    & intervals["event_seconds"].ge(-240)
                    & intervals["event_seconds"].lt(-60)
                ]
                focal = intervals.loc[
                    intervals["bundle_id"].eq(focal_bundle)
                    & intervals["instrument"].eq(instrument)
                    & intervals["frequency"].eq(frequency)
                ]
                if training.empty or focal.empty:
                    continue
                for model_name, conditioned in (
                    ("linear_flow", False),
                    ("liquidity_conditioned", True),
                ):
                    fit = _fit(training, conditioned)
                    fits.append(
                        {
                            "focal_bundle": focal_bundle,
                            "instrument": instrument,
                            "frequency": frequency,
                            "model": model_name,
                            "training_bundle_count": training["bundle_id"].nunique(),
                            **fit,
                        }
                    )
                    for horizon in HORIZONS:
                        event_sample = focal.loc[
                            focal["event_seconds"].ge(0)
                            & focal["event_seconds"].lt(horizon)
                        ]
                        total = float(event_sample["return"].sum(min_count=1))
                        predicted = _predict_component(event_sample, fit)
                        estimates.append(
                            {
                                "bundle_id": focal_bundle,
                                "event_types": focal["event_types"].iloc[0],
                                "representation_class": focal["representation_class"].iloc[0],
                                "instrument": instrument,
                                "frequency": frequency,
                                "model": model_name,
                                "horizon_seconds": horizon,
                                "observed_return_bp": total * 1e4,
                                "flow_component_bp": predicted * 1e4,
                                "residual_bp": (total - predicted) * 1e4,
                                "absolute_error_bp": abs(total - predicted) * 1e4,
                                "training_r_squared": fit["r_squared"],
                            }
                        )
    fit_frame = pd.DataFrame(fits)
    estimate_frame = pd.DataFrame(estimates)
    comparison = (
        estimate_frame.groupby(
            ["frequency", "model", "instrument", "horizon_seconds"], as_index=False
        )
        .agg(
            events=("bundle_id", "nunique"),
            median_training_r_squared=("training_r_squared", "median"),
            median_absolute_error_bp=("absolute_error_bp", "median"),
            median_absolute_flow_component_bp=("flow_component_bp", lambda value: value.abs().median()),
            median_absolute_observed_bp=("observed_return_bp", lambda value: value.abs().median()),
        )
    )
    output = PROJECT_ROOT / "data" / "processed" / args.output
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "multiscale_flow_fits": fit_frame,
        "multiscale_mechanism_estimates": estimate_frame,
        "multiscale_model_comparison": comparison,
    }
    for name, frame in products.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
        frame.to_csv(output / f"{name}.csv", index=False)
    print(
        f"Wrote {len(fit_frame)} leave-one-bundle-out fits and "
        f"{len(estimate_frame)} event-horizon estimates across {len(bundles)} bundles."
    )


if __name__ == "__main__":
    main()
