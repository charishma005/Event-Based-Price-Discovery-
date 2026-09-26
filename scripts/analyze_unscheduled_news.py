from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.event_summary import (
    mechanism_estimates,
    second_intervals,
    summarize_horizons,
    timing_and_liquidity_summary,
    valid_quotes,
)
from src.microstructure.mechanism import fit_order_flow_impact
from src.utils.config import PROJECT_ROOT


EVENT = {
    "label": "nvda_intel_announcement",
    "time": pd.Timestamp("2025-09-18T11:00:00Z"),
    "article_id": "b70af7031968fbae1c63a249",
    "source_url": "https://www.globenewswire.com/news-release/2025/09/18/3152283/0/en/index.html",
}
PLACEBO = {
    "label": "nvda_intel_placebo_20250917",
    "time": pd.Timestamp("2025-09-17T11:00:00Z"),
}
META_EVENT = {
    "label": "meta_dividend_announcement",
    "time": pd.Timestamp("2025-09-11T20:35:00Z"),
    "article_id": "519c54b1b33c2eef79d4f929",
    "source_url": "https://www.prnewswire.com/news-releases/meta-announces-quarterly-cash-dividend-302554438.html",
}
META_PLACEBO = {
    "label": "meta_dividend_placebo_20250904",
    "time": pd.Timestamp("2025-09-04T20:35:00Z"),
}


def _messages(label: str, instrument: str = "NVDA") -> pd.DataFrame:
    path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "fomc_pilot"
        / label
        / f"{instrument}_messages.parquet"
    )
    return pd.read_parquet(path)


def _first_nonzero_quote_delay_ms(
    messages: pd.DataFrame, event_time: pd.Timestamp
) -> float | None:
    quotes = valid_quotes(messages)
    pre = quotes.loc[quotes["ts_event"].lt(event_time)]
    if pre.empty:
        return None
    midpoint = pre.iloc[-1]["midpoint"]
    changed = quotes.loc[
        quotes["ts_event"].ge(event_time) & quotes["midpoint"].ne(midpoint)
    ]
    if changed.empty:
        return None
    return float((changed.iloc[0]["ts_event"] - event_time).total_seconds() * 1000)


def _comparison_figure(
    event_messages: pd.DataFrame,
    placebo_messages: pd.DataFrame,
    *,
    event: dict[str, object],
    placebo: dict[str, object],
    instrument: str,
    event_name: str,
    output,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for label, messages, event_time, color in (
        (event_name, event_messages, event["time"], "#d95f02"),
        ("Matched same clock", placebo_messages, placebo["time"], "#4c78a8"),
    ):
        quotes = valid_quotes(messages)
        pre = quotes.loc[quotes["ts_event"].lt(event_time), "midpoint"].iloc[-1]
        sample = quotes.loc[
            quotes["ts_event"].between(
                event_time - pd.Timedelta(seconds=60),
                event_time + pd.Timedelta(seconds=300),
            )
        ].copy()
        sample["event_seconds"] = (sample["ts_event"] - event_time).dt.total_seconds()
        sample["return_bp"] = 1e4 * np.log(sample["midpoint"] / pre)
        sampled = (
            sample.set_index("ts_event")[["event_seconds", "return_bp"]]
            .resample("100ms")
            .last()
            .dropna()
        )
        ax.plot(sampled["event_seconds"], sampled["return_bp"], label=label, color=color, lw=1.1)
    ax.axvline(0, color="black", ls="--", lw=1)
    ax.set(
        xlabel="Event time (seconds)",
        ylabel="Nasdaq midpoint return (bp)",
        title=f"{instrument} response to source-verified corporate announcement",
    )
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    event_messages = _messages(EVENT["label"])
    placebo_messages = _messages(PLACEBO["label"])
    output_dir = PROJECT_ROOT / "data" / "processed" / "unscheduled_news"
    figure_dir = PROJECT_ROOT / "figures" / "unscheduled_news"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    timing_rows = []
    horizon_frames = []
    for metadata, messages, kind in (
        (EVENT, event_messages, "source_verified_news"),
        (PLACEBO, placebo_messages, "matched_clock_placebo"),
    ):
        timing = timing_and_liquidity_summary(
            messages, metadata["time"], "NVDA", metadata["label"]
        )
        timing["window_type"] = kind
        timing["first_nonzero_quote_delay_ms"] = _first_nonzero_quote_delay_ms(
            messages, metadata["time"]
        )
        timing_rows.append(timing)
        horizons = summarize_horizons(
            messages, metadata["time"], "NVDA", metadata["label"]
        )
        horizons["window_type"] = kind
        horizon_frames.append(horizons)

    # Estimate impact only on the prior-day ordinary window, leaving the news day out.
    placebo_intervals = second_intervals(placebo_messages).dropna(subset=["return"])
    impact, _ = fit_order_flow_impact(placebo_intervals)
    mechanism = mechanism_estimates(
        event_messages,
        EVENT["time"],
        "NVDA",
        EVENT["label"],
        impact,
    )
    mechanism["impact_training_source"] = "prior_day_same_clock_full_window"
    mechanism["source_timestamp_verified"] = True

    timing = pd.DataFrame(timing_rows)
    horizons = pd.concat(horizon_frames, ignore_index=True)
    for name, frame in (
        ("nvda_intel_timing", timing),
        ("nvda_intel_response_horizons", horizons),
        ("nvda_intel_mechanism", mechanism),
    ):
        frame.to_csv(output_dir / f"{name}.csv", index=False)
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)

    metadata = {
        "article_id": EVENT["article_id"],
        "instrument": "NVDA",
        "event_time_utc": EVENT["time"].isoformat(),
        "event_time_et": EVENT["time"].tz_convert("America/New_York").isoformat(),
        "source_url": EVENT["source_url"],
        "alpha_vantage_time_utc": "2025-09-18T00:00:00+00:00",
        "alpha_minus_source_seconds": -39600,
        "placebo_time_utc": PLACEBO["time"].isoformat(),
        "placebo_news_screen": "No direct high-relevance NVDA article within +/-60 minutes in the cached Alpha Vantage panel.",
        "impact_fit": impact,
        "venue_scope": "Nasdaq TotalView only; not consolidated NBBO.",
    }
    (output_dir / "nvda_intel_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    _comparison_figure(
        event_messages, placebo_messages,
        event=EVENT, placebo=PLACEBO, instrument="NVDA",
        event_name="NVIDIA–Intel release",
        output=figure_dir / "nvda_intel_event_vs_placebo.png",
    )

    meta_event_messages = _messages(META_EVENT["label"], "META").copy()
    meta_placebo_messages = _messages(META_PLACEBO["label"], "META").copy()
    meta_timing_rows = []
    meta_horizon_frames = []
    for metadata, messages, kind in (
        (META_EVENT, meta_event_messages, "source_verified_news"),
        (META_PLACEBO, meta_placebo_messages, "matched_clock_placebo"),
    ):
        timing_row = timing_and_liquidity_summary(
            messages, metadata["time"], "META", metadata["label"]
        )
        timing_row["window_type"] = kind
        timing_row["first_nonzero_quote_delay_ms"] = _first_nonzero_quote_delay_ms(
            messages, metadata["time"]
        )
        meta_timing_rows.append(timing_row)
        frame = summarize_horizons(messages, metadata["time"], "META", metadata["label"])
        frame["window_type"] = kind
        meta_horizon_frames.append(frame)
    meta_timing = pd.DataFrame(meta_timing_rows)
    meta_horizons = pd.concat(meta_horizon_frames, ignore_index=True)
    for name, frame in (
        ("meta_dividend_timing", meta_timing),
        ("meta_dividend_response_horizons", meta_horizons),
    ):
        frame.to_csv(output_dir / f"{name}.csv", index=False)
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    meta_metadata = {
        "article_id": META_EVENT["article_id"],
        "instrument": "META",
        "event_time_utc": META_EVENT["time"].isoformat(),
        "event_time_et": META_EVENT["time"].tz_convert("America/New_York").isoformat(),
        "source_url": META_EVENT["source_url"],
        "alpha_vantage_time_utc": "2025-09-11T10:57:28+00:00",
        "alpha_minus_source_seconds": -34652,
        "placebo_time_utc": META_PLACEBO["time"].isoformat(),
        "placebo_news_screen": "No direct high-relevance META article within +/-60 minutes in the cached Alpha Vantage panel.",
        "venue_scope": "Nasdaq TotalView only; not consolidated NBBO.",
        "session_note": "After-hours window; sparse messages make the literal Q1 sequence ineligible.",
    }
    (output_dir / "meta_dividend_metadata.json").write_text(
        json.dumps(meta_metadata, indent=2) + "\n", encoding="utf-8"
    )
    _comparison_figure(
        meta_event_messages, meta_placebo_messages,
        event=META_EVENT, placebo=META_PLACEBO, instrument="META",
        event_name="Meta dividend release",
        output=figure_dir / "meta_dividend_event_vs_placebo.png",
    )
    print(
        f"Wrote two source-verified cases: {len(timing) + len(meta_timing)} timing rows, "
        f"{len(horizons) + len(meta_horizons)} horizon rows, and {len(mechanism)} "
        "mechanism rows (NVDA only; META is sequence-ineligible)."
    )


if __name__ == "__main__":
    main()
