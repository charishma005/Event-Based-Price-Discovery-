from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon

from src.analysis.event_summary import (
    mechanism_estimates,
    second_intervals,
    summarize_horizons,
    timing_and_liquidity_summary,
    valid_quotes,
)
from src.microstructure.mechanism import fit_order_flow_impact
from src.events.contamination import build_event_news_flags
from src.utils.config import PROJECT_ROOT, load_yaml


def _messages(label: str, instrument: str) -> pd.DataFrame:
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
    changed = quotes.loc[
        quotes["ts_event"].ge(event_time)
        & quotes["midpoint"].ne(pre.iloc[-1]["midpoint"])
    ]
    if changed.empty:
        return None
    return float((changed.iloc[0]["ts_event"] - event_time).total_seconds() * 1000)


def _session(timestamp: pd.Timestamp) -> str:
    local = timestamp.tz_convert("America/New_York")
    minute = local.hour * 60 + local.minute
    if minute < 9 * 60 + 30:
        return "pre_market"
    if minute <= 16 * 60:
        return "regular"
    return "after_hours"


def _figure(config: dict[str, object], output) -> None:
    events = config["events"]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True)
    for ax, event in zip(axes.flat, events):
        for label, time_field, name, color in (
            (event["label"], "event_time_utc", "news", "#d95f02"),
            (event["placebo_label"], "placebo_time_utc", "matched clock", "#4c78a8"),
        ):
            center = pd.Timestamp(event[time_field])
            quotes = valid_quotes(_messages(label, event["instrument"]))
            pre = quotes.loc[quotes["ts_event"].lt(center)]
            if pre.empty:
                continue
            reference = float(pre.iloc[-1]["midpoint"])
            sample = quotes.loc[
                quotes["ts_event"].between(
                    center - pd.Timedelta(seconds=30),
                    center + pd.Timedelta(seconds=300),
                )
            ].copy()
            sample["seconds"] = (sample["ts_event"] - center).dt.total_seconds()
            sample["return_bp"] = 1e4 * np.log(sample["midpoint"] / reference)
            sampled = (
                sample.set_index("ts_event")[["seconds", "return_bp"]]
                .resample("500ms")
                .last()
                .dropna()
            )
            ax.plot(sampled["seconds"], sampled["return_bp"], color=color, lw=1, label=name)
        ax.axvline(0, color="black", ls="--", lw=0.8)
        ax.axhline(0, color="#777777", lw=0.5)
        ax.set_title(event["label"].replace("_announcement", "").replace("_", " "))
        ax.grid(alpha=0.2)
    axes[0, 0].legend(frameon=False)
    for ax in axes[-1, :]:
        ax.set_xlabel("event time (seconds)")
    for ax in axes[:, 0]:
        ax.set_ylabel("midpoint return (bp)")
    fig.suptitle("Source-verified corporate news versus matched clocks")
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _depth_inference(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scheduled, sample in summary.groupby("scheduled_indicator"):
        difference = sample["event_minus_placebo_depth_ratio"].dropna().to_numpy(float)
        nonzero = difference[~np.isclose(difference, 0)]
        rows.append(
            {
                "scheduled_indicator": bool(scheduled),
                "event_pairs": len(difference),
                "mean_event_depth_ratio": sample["event_depth_ratio"].mean(),
                "mean_placebo_depth_ratio": sample["placebo_depth_ratio"].mean(),
                "event_lower_count": int((difference < 0).sum()),
                "one_sided_sign_p_event_lower": np.nan
                if not len(nonzero)
                else float(
                    binomtest((nonzero < 0).sum(), len(nonzero), 0.5, alternative="greater").pvalue
                ),
                "one_sided_wilcoxon_p_event_lower": np.nan
                if not len(nonzero)
                else float(wilcoxon(nonzero, alternative="less", method="auto").pvalue),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "unscheduled_news_sample.yaml")
    timing_rows: list[dict[str, object]] = []
    horizons: list[pd.DataFrame] = []
    mechanisms: list[pd.DataFrame] = []
    metadata_rows: list[dict[str, object]] = []
    for event in config["events"]:
        event_time = pd.Timestamp(event["event_time_utc"])
        placebo_time = pd.Timestamp(event["placebo_time_utc"])
        event_messages = _messages(event["label"], event["instrument"])
        placebo_messages = _messages(event["placebo_label"], event["instrument"])
        for label, center, messages, kind in (
            (event["label"], event_time, event_messages, "source_verified_news"),
            (event["placebo_label"], placebo_time, placebo_messages, "matched_clock_placebo"),
        ):
            row = timing_and_liquidity_summary(messages, center, event["instrument"], label)
            row["window_type"] = kind
            row["first_nonzero_quote_delay_ms"] = _first_nonzero_quote_delay_ms(messages, center)
            row["announcement_category"] = event["announcement_category"]
            row["representation_class"] = event["representation_class"]
            row["scheduled_indicator"] = bool(event["scheduled_indicator"])
            timing_rows.append(row)
            frame = summarize_horizons(messages, center, event["instrument"], label)
            frame["window_type"] = kind
            frame["announcement_category"] = event["announcement_category"]
            frame["representation_class"] = event["representation_class"]
            frame["scheduled_indicator"] = bool(event["scheduled_indicator"])
            horizons.append(frame)
        placebo_intervals = second_intervals(placebo_messages).dropna(subset=["return"])
        try:
            impact, _ = fit_order_flow_impact(placebo_intervals)
            mechanism = mechanism_estimates(
                event_messages, event_time, event["instrument"], event["label"], impact
            )
            mechanism["impact_training_source"] = "matched_clock_placebo_full_window"
            mechanism["scheduled_indicator"] = bool(event["scheduled_indicator"])
            mechanisms.append(mechanism)
        except (ValueError, np.linalg.LinAlgError) as exc:
            impact = {"error": str(exc)}
        metadata_rows.append(
            {
                "event": event["label"],
                "instrument": event["instrument"],
                "article_id": event["article_id"],
                "event_time_utc": event_time,
                "event_time_et": event_time.tz_convert("America/New_York"),
                "alpha_vantage_time_utc": pd.Timestamp(event["alpha_vantage_time_utc"]),
                "alpha_minus_source_seconds": (
                    pd.Timestamp(event["alpha_vantage_time_utc"]) - event_time
                ).total_seconds(),
                "source_url": event["source_url"],
                "announcement_category": event["announcement_category"],
                "representation_class": event["representation_class"],
                "scheduled_indicator": bool(event["scheduled_indicator"]),
                "session": _session(event_time),
                "placebo": event["placebo_label"],
                "placebo_time_utc": placebo_time,
                "impact_fit_json": json.dumps(impact),
            }
        )
    timing = pd.DataFrame(timing_rows)
    horizon_panel = pd.concat(horizons, ignore_index=True)
    mechanism_panel = pd.concat(mechanisms, ignore_index=True) if mechanisms else pd.DataFrame()
    metadata = pd.DataFrame(metadata_rows)
    news = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "alpha_vantage_news.parquet")
    aliases = load_yaml(PROJECT_ROOT / "config" / "news_aliases.yaml")["aliases"]
    screen_rows = []
    for event in config["events"]:
        screen_rows.extend(
            [
                {"event_id": event["label"], "scheduled_time_utc": event["event_time_utc"]},
                {
                    "event_id": event["placebo_label"],
                    "scheduled_time_utc": event["placebo_time_utc"],
                },
            ]
        )
    screen_events = pd.DataFrame(screen_rows)
    screen_tickers = sorted({event["instrument"] for event in config["events"]})
    news_screen = build_event_news_flags(
        news,
        screen_events,
        screen_tickers,
        pre_minutes=60,
        post_minutes=60,
        queried_tickers=set(news["query_ticker"].dropna().astype(str)),
        aliases=aliases,
        minimum_relevance=0.60,
        high_confidence_relevance=0.80,
    )
    event_timing = timing.loc[timing["window_type"].eq("source_verified_news")].set_index("event")
    placebo_timing = timing.loc[timing["window_type"].eq("matched_clock_placebo")].set_index("event")
    summary_rows = []
    for event in config["events"]:
        e = event_timing.loc[event["label"]]
        p = placebo_timing.loc[event["placebo_label"]]
        event_60 = horizon_panel.loc[
            horizon_panel["event"].eq(event["label"])
            & horizon_panel["horizon_seconds"].eq(60)
        ]
        placebo_60 = horizon_panel.loc[
            horizon_panel["event"].eq(event["placebo_label"])
            & horizon_panel["horizon_seconds"].eq(60)
        ]
        event_screen = news_screen.loc[
            news_screen["event_id"].eq(event["label"])
            & news_screen["instrument"].eq(event["instrument"])
        ].iloc[0]
        placebo_screen = news_screen.loc[
            news_screen["event_id"].eq(event["placebo_label"])
            & news_screen["instrument"].eq(event["instrument"])
        ].iloc[0]
        summary_rows.append(
            {
                "event": event["label"],
                "instrument": event["instrument"],
                "scheduled_indicator": bool(event["scheduled_indicator"]),
                "session": _session(pd.Timestamp(event["event_time_utc"])),
                "valid_mechanically": bool(e["valid_mechanically"]),
                "first_post_quote_delay_ms": e["first_post_quote_delay_ms"],
                "first_trade_delay_ms": e["first_trade_delay_ms"],
                "first_quote_revision_bp": e["first_quote_revision_bp"],
                "last_pretrade_quote_revision_bp": e["last_pretrade_quote_revision_bp"],
                "event_depth_ratio": e["pre60_to_baseline_depth_ratio"],
                "placebo_depth_ratio": p["pre60_to_baseline_depth_ratio"],
                "event_minus_placebo_depth_ratio": e["pre60_to_baseline_depth_ratio"]
                - p["pre60_to_baseline_depth_ratio"],
                "event_return_60s_bp": event_60["log_return_bp"].iloc[0]
                if len(event_60)
                else np.nan,
                "placebo_return_60s_bp": placebo_60["log_return_bp"].iloc[0]
                if len(placebo_60)
                else np.nan,
                "event_high_confidence_articles_pm60m": int(event_screen["article_count"]),
                "placebo_high_confidence_articles_pm60m": int(placebo_screen["article_count"]),
                "quality_flags": e["quality_flags"],
            }
        )
    summary = pd.DataFrame(summary_rows)
    inference = _depth_inference(summary)
    output = PROJECT_ROOT / "data" / "processed" / "unscheduled_news"
    figures = PROJECT_ROOT / "figures" / "unscheduled_news"
    tables = PROJECT_ROOT / "tables"
    output.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    for name, frame in (
        ("source_verified_metadata", metadata),
        ("source_verified_timing", timing),
        ("source_verified_response_horizons", horizon_panel),
        ("source_verified_mechanism", mechanism_panel),
        ("source_verified_summary", summary),
        ("source_verified_depth_inference", inference),
        ("source_verified_news_screen", news_screen),
    ):
        frame.to_csv(output / f"{name}.csv", index=False)
        frame.to_parquet(output / f"{name}.parquet", index=False)
    paper_summary = summary[
        [
            "event",
            "instrument",
            "scheduled_indicator",
            "valid_mechanically",
            "event_return_60s_bp",
            "placebo_return_60s_bp",
            "event_depth_ratio",
            "placebo_depth_ratio",
        ]
    ].copy()
    paper_summary.to_csv(tables / "corporate_news_summary.csv", index=False)
    (tables / "corporate_news_summary.tex").write_text(
        paper_summary.to_latex(index=False, float_format="%.3f"), encoding="utf-8"
    )
    _figure(config, figures / "source_verified_event_vs_placebo.png")
    print(summary.to_string(index=False))
    print("\nDepth inference")
    print(inference.to_string(index=False))


if __name__ == "__main__":
    main()
