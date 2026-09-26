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


def _matching_raw_file(placebo: dict[str, object]) -> Path | None:
    raw_dir = PROJECT_ROOT / "data" / "raw" / "databento"
    start = pd.Timestamp(placebo["request_start_utc"])
    end = pd.Timestamp(placebo["request_end_utc"])
    for metadata_path in raw_dir.glob("GLBX.MDP3-mbp-1-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            pd.Timestamp(metadata["start"]) == start
            and pd.Timestamp(metadata["end"]) == end
            and set(metadata["symbols"]) == set(INSTRUMENTS)
        ):
            dbn_path = metadata_path.with_suffix("").with_suffix("")
            if dbn_path.exists():
                return dbn_path
    return None


def _inference(comparison: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for instrument, sample in comparison.groupby("instrument"):
        differences = sample["depth_ratio_difference"].dropna().to_numpy(float)
        nonzero = differences[~np.isclose(differences, 0)]
        wilcoxon_p = np.nan
        if len(nonzero) >= 3:
            wilcoxon_p = float(
                wilcoxon(nonzero, alternative="less", method="auto").pvalue
            )
        negative = int((nonzero < 0).sum())
        sign_p = (
            np.nan
            if len(nonzero) == 0
            else float(binomtest(negative, len(nonzero), 0.5, alternative="greater").pvalue)
        )
        rows.append(
            {
                "instrument": instrument,
                "meeting_pairs": len(differences),
                "mean_event_depth_ratio": sample["event_pre60_depth_ratio"].mean(),
                "mean_placebo_depth_ratio": sample["placebo_pre60_depth_ratio"].mean(),
                "mean_difference": np.mean(differences),
                "median_difference": np.median(differences),
                "event_lower_pair_count": negative,
                "one_sided_sign_test_p": sign_p,
                "one_sided_wilcoxon_p": wilcoxon_p,
            }
        )
    pooled = comparison.dropna(subset=["depth_ratio_difference"])
    meeting_level = (
        pooled.groupby("matched_meeting", as_index=False)
        .agg(
            event_pre60_depth_ratio=("event_pre60_depth_ratio", "mean"),
            placebo_pre60_depth_ratio=("placebo_pre60_depth_ratio", "mean"),
            depth_ratio_difference=("depth_ratio_difference", "mean"),
        )
    )
    differences = meeting_level["depth_ratio_difference"].to_numpy(float)
    negative = int((differences < 0).sum())
    rows.append(
        {
            "instrument": "meeting_cluster_average",
            "meeting_pairs": len(differences),
            "mean_event_depth_ratio": meeting_level["event_pre60_depth_ratio"].mean(),
            "mean_placebo_depth_ratio": meeting_level["placebo_pre60_depth_ratio"].mean(),
            "mean_difference": np.mean(differences),
            "median_difference": np.median(differences),
            "event_lower_pair_count": negative,
            "one_sided_sign_test_p": float(
                binomtest(negative, len(differences), 0.5, alternative="greater").pvalue
            ),
            "one_sided_wilcoxon_p": float(
                wilcoxon(differences, alternative="less", method="auto").pvalue
            ),
        }
    )
    return pd.DataFrame(rows)


def main() -> None:
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc

    config = load_yaml(PROJECT_ROOT / "config" / "fomc_placebos.yaml")
    timing_rows: list[dict[str, object]] = []
    horizon_frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []
    for placebo in config["placebos"]:
        path = _matching_raw_file(placebo)
        if path is None:
            print(f"Skipping {placebo['placebo_id']}: matching immutable DBN is not cached")
            continue
        frame = db.DBNStore.from_file(path).to_df()
        event_time = pd.Timestamp(placebo["placebo_time_utc"])
        for instrument in INSTRUMENTS:
            raw = frame.loc[frame["symbol"].eq(instrument)]
            if raw.empty:
                continue
            messages = normalize_mbp1(raw)
            timing = timing_and_liquidity_summary(
                messages, event_time, instrument, placebo["placebo_id"]
            )
            timing.update(
                {
                    "placebo_id": placebo["placebo_id"],
                    "matched_meeting": placebo["matched_meeting"],
                    "placebo_quality_flag": placebo["quality_flag"],
                }
            )
            timing_rows.append(timing)
            horizons = summarize_horizons(
                messages, event_time, instrument, placebo["placebo_id"]
            )
            horizons["placebo_id"] = placebo["placebo_id"]
            horizons["matched_meeting"] = placebo["matched_meeting"]
            horizons["placebo_quality_flag"] = placebo["quality_flag"]
            horizon_frames.append(horizons)
            coverage_rows.append(
                {
                    "placebo_id": placebo["placebo_id"],
                    "matched_meeting": placebo["matched_meeting"],
                    "instrument": instrument,
                    "raw_file": str(path.relative_to(PROJECT_ROOT)),
                    "message_count": len(messages),
                    "first_message_utc": messages["ts_event"].min(),
                    "last_message_utc": messages["ts_event"].max(),
                }
            )
        del frame

    if not timing_rows:
        raise RuntimeError("No configured FOMC placebo files were available")
    timing = pd.DataFrame(timing_rows)
    horizons = pd.concat(horizon_frames, ignore_index=True)
    controls = timing.loc[
        ~timing["placebo_quality_flag"].str.contains("secondary_control", na=False)
    ]
    control_means = (
        controls.groupby(["matched_meeting", "instrument"], as_index=False)
        .agg(
            placebo_count=("placebo_id", "nunique"),
            placebo_pre60_depth_ratio=("pre60_to_baseline_depth_ratio", "mean"),
            placebo_pre60_depth_ratio_sd=("pre60_to_baseline_depth_ratio", "std"),
        )
    )
    actual = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "fomc_sample" / "timing_liquidity.parquet"
    )
    actual = actual.loc[
        actual["subevent"].eq("statement")
        & actual["dataset_condition"].eq("available")
    ][["meeting", "instrument", "pre60_to_baseline_depth_ratio"]].rename(
        columns={
            "meeting": "matched_meeting",
            "pre60_to_baseline_depth_ratio": "event_pre60_depth_ratio",
        }
    )
    comparison = actual.merge(control_means, on=["matched_meeting", "instrument"], how="left")
    comparison["depth_ratio_difference"] = (
        comparison["event_pre60_depth_ratio"]
        - comparison["placebo_pre60_depth_ratio"]
    )
    inference = _inference(comparison)

    output = PROJECT_ROOT / "data" / "processed" / "fomc_placebos"
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "timing_liquidity": timing,
        "response_horizons": horizons,
        "raw_coverage": pd.DataFrame(coverage_rows),
        "matched_depth_comparison": comparison,
        "depth_inference": inference,
    }
    for name, product in products.items():
        product.to_parquet(output / f"{name}.parquet", index=False)
        product.to_csv(output / f"{name}.csv", index=False)
    print(
        f"Processed {timing['placebo_id'].nunique()} placebo windows and "
        f"{len(comparison)} meeting-instrument depth comparisons."
    )


if __name__ == "__main__":
    main()
