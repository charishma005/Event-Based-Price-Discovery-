from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from scripts.build_fomc_pilot import normalize_mbp1
from src.analysis.event_summary import summarize_horizons, timing_and_liquidity_summary
from src.utils.config import PROJECT_ROOT, load_yaml


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def _raw_file(placebo: dict[str, object]) -> Path | None:
    raw_dir = PROJECT_ROOT / "data" / "raw" / "databento"
    for metadata_path in raw_dir.glob("GLBX.MDP3-mbp-1-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == pd.Timestamp(placebo["request_start_utc"])
            and pd.Timestamp(metadata["end"]) == pd.Timestamp(placebo["request_end_utc"])
            and set(metadata["symbols"]) == set(INSTRUMENTS)
        ):
            path = metadata_path.with_suffix("").with_suffix("")
            if path.exists():
                return path
    return None


def _inference(comparison: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for instrument, sample in comparison.groupby("instrument"):
        # One control is reused by all announcements in a month. Aggregate first
        # so paired tests use independent month clusters, not pseudo-replicated
        # event/control rows.
        clustered = (
            sample.groupby("matched_month", as_index=False)
            .agg(
                event_pre60_depth_ratio=("event_pre60_depth_ratio", "mean"),
                control_pre60_depth_ratio=("control_pre60_depth_ratio", "first"),
            )
            .dropna()
        )
        differences = (
            clustered["event_pre60_depth_ratio"]
            - clustered["control_pre60_depth_ratio"]
        ).to_numpy(float)
        nonzero = differences[~np.isclose(differences, 0)]
        rows.append(
            {
                "instrument": instrument,
                "event_control_pairs": len(differences),
                "mean_event_depth_ratio": clustered["event_pre60_depth_ratio"].mean(),
                "mean_control_depth_ratio": clustered["control_pre60_depth_ratio"].mean(),
                "mean_difference": np.mean(differences),
                "median_difference": np.median(differences),
                "event_lower_pair_count": int((nonzero < 0).sum()),
                "one_sided_sign_test_p": float(
                    binomtest((nonzero < 0).sum(), len(nonzero), 0.5, alternative="greater").pvalue
                ),
                "one_sided_wilcoxon_p": float(wilcoxon(nonzero, alternative="less", method="auto").pvalue),
            }
        )
    month_instrument = (
        comparison.groupby(["matched_month", "instrument"], as_index=False)
        .agg(
            event_pre60_depth_ratio=("event_pre60_depth_ratio", "mean"),
            control_pre60_depth_ratio=("control_pre60_depth_ratio", "first"),
        )
        .dropna()
    )
    month_level = month_instrument.groupby("matched_month", as_index=False).agg(
        event_pre60_depth_ratio=("event_pre60_depth_ratio", "mean"),
        control_pre60_depth_ratio=("control_pre60_depth_ratio", "mean"),
    )
    differences = (
        month_level["event_pre60_depth_ratio"]
        - month_level["control_pre60_depth_ratio"]
    ).to_numpy(float)
    rows.append(
        {
            "instrument": "month_cluster_average",
            "event_control_pairs": len(differences),
            "mean_event_depth_ratio": month_level["event_pre60_depth_ratio"].mean(),
            "mean_control_depth_ratio": month_level["control_pre60_depth_ratio"].mean(),
            "mean_difference": differences.mean(),
            "median_difference": np.median(differences),
            "event_lower_pair_count": int((differences < 0).sum()),
            "one_sided_sign_test_p": float(
                binomtest((differences < 0).sum(), len(differences), 0.5, alternative="greater").pvalue
            ),
            "one_sided_wilcoxon_p": float(wilcoxon(differences, alternative="less", method="auto").pvalue),
        }
    )
    return pd.DataFrame(rows)


def main() -> None:
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc
    config = load_yaml(PROJECT_ROOT / "config" / "macro_placebos.yaml")
    timing_rows: list[dict[str, object]] = []
    horizon_frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []
    for placebo in config["placebos"]:
        path = _raw_file(placebo)
        if path is None:
            print(f"Skipping {placebo['placebo_id']}: immutable DBN is not cached")
            continue
        frame = db.DBNStore.from_file(path).to_df()
        event_time = pd.Timestamp(placebo["placebo_time_utc"])
        for instrument in INSTRUMENTS:
            raw = frame.loc[frame["symbol"].eq(instrument)]
            if raw.empty:
                continue
            messages = normalize_mbp1(raw)
            timing = timing_and_liquidity_summary(messages, event_time, instrument, placebo["placebo_id"])
            timing.update({"placebo_id": placebo["placebo_id"], "matched_month": placebo["matched_month"], "quality_flag": placebo["quality_flag"]})
            timing_rows.append(timing)
            horizons = summarize_horizons(messages, event_time, instrument, placebo["placebo_id"])
            horizons["placebo_id"] = placebo["placebo_id"]
            horizons["matched_month"] = placebo["matched_month"]
            horizon_frames.append(horizons)
            coverage_rows.append(
                {
                    "placebo_id": placebo["placebo_id"], "matched_month": placebo["matched_month"],
                    "instrument": instrument, "raw_file": str(path.relative_to(PROJECT_ROOT)),
                    "message_count": len(messages), "first_message_utc": messages["ts_event"].min(),
                    "last_message_utc": messages["ts_event"].max(),
                }
            )
        del frame
    if not timing_rows:
        raise RuntimeError("No macro placebo files were available")
    timing = pd.DataFrame(timing_rows)
    horizons = pd.concat(horizon_frames, ignore_index=True)
    controls = timing[["matched_month", "instrument", "pre60_to_baseline_depth_ratio"]].rename(
        columns={"pre60_to_baseline_depth_ratio": "control_pre60_depth_ratio"}
    )
    actual_paths = (
        PROJECT_ROOT / "data" / "processed" / "macro_sample_2024" / "timing_liquidity.parquet",
        PROJECT_ROOT / "data" / "processed" / "macro_sample" / "timing_liquidity.parquet",
    )
    actual = pd.concat(
        [pd.read_parquet(path) for path in actual_paths if path.exists()],
        ignore_index=True,
    )
    actual = actual.loc[actual["dataset_condition"].eq("available")].copy()
    actual["matched_month"] = pd.to_datetime(actual["event_time_utc"], utc=True).dt.strftime("%Y-%m")
    comparison = actual[["bundle_id", "event_types", "matched_month", "instrument", "pre60_to_baseline_depth_ratio"]].rename(
        columns={"pre60_to_baseline_depth_ratio": "event_pre60_depth_ratio"}
    )
    comparison = comparison.merge(controls, on=["matched_month", "instrument"], how="left")
    comparison["depth_ratio_difference"] = comparison["event_pre60_depth_ratio"] - comparison["control_pre60_depth_ratio"]
    products = {
        "timing_liquidity": timing, "response_horizons": horizons,
        "raw_coverage": pd.DataFrame(coverage_rows), "matched_depth_comparison": comparison,
        "depth_inference": _inference(comparison),
    }
    output = PROJECT_ROOT / "data" / "processed" / "macro_placebos"
    output.mkdir(parents=True, exist_ok=True)
    for name, product in products.items():
        product.to_parquet(output / f"{name}.parquet", index=False)
        product.to_csv(output / f"{name}.csv", index=False)
    print(f"Processed {timing['placebo_id'].nunique()} macro controls and {len(comparison)} event-instrument comparisons.")


if __name__ == "__main__":
    main()
