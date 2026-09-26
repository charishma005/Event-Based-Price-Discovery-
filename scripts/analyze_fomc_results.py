from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.event_summary import (
    estimate_pre_event_impact,
    mechanism_estimates,
    summarize_horizons,
    timing_and_liquidity_summary,
    valid_quotes,
)
from src.events.registry import pilot_events
from src.utils.config import PROJECT_ROOT


EVENTS = pilot_events()
EVENT_TIMES = {label: metadata["time"] for label, metadata in EVENTS.items()}


def _messages(event: str) -> dict[str, pd.DataFrame]:
    root = PROJECT_ROOT / "data" / "processed" / "fomc_pilot" / event
    output: dict[str, pd.DataFrame] = {}
    for path in sorted(root.glob("*_messages.parquet")):
        instrument = path.name.removesuffix("_messages.parquet")
        output[instrument] = pd.read_parquet(path)
    return output


def _make_cross_instrument_figure(
    all_messages: dict[str, pd.DataFrame], event: str, output: Path
) -> None:
    event_time = EVENT_TIMES[event]
    fig, ax = plt.subplots(figsize=(9, 5))
    for instrument, messages in all_messages.items():
        quotes = valid_quotes(messages)
        quotes = quotes.loc[
            quotes["ts_event"].between(
                event_time - pd.Timedelta(seconds=60),
                event_time + pd.Timedelta(seconds=300),
            )
        ].copy()
        if quotes.empty:
            continue
        pre = quotes.loc[quotes["ts_event"].lt(event_time), "midpoint"]
        if pre.empty:
            continue
        quotes["event_seconds"] = (quotes["ts_event"] - event_time).dt.total_seconds()
        quotes["return_bp"] = 1e4 * np.log(quotes["midpoint"] / pre.iloc[-1])
        sampled = (
            quotes.set_index("ts_event")[["event_seconds", "return_bp"]]
            .resample("250ms")
            .last()
            .dropna()
        )
        ax.plot(sampled["event_seconds"], sampled["return_bp"], label=instrument, lw=1.2)
    ax.axvline(0, color="black", ls="--", lw=1)
    ax.set(xlabel="Event time (seconds)", ylabel="Log midpoint return (bp)", title=f"Cross-instrument response: {event.replace('_', ' ')}")
    ax.grid(alpha=0.2)
    ax.legend(ncol=3)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _make_statement_press_figure(
    statement: dict[str, pd.DataFrame], press: dict[str, pd.DataFrame], output: Path
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharex=True)
    for ax, instrument in zip(axes, ["ES.v.0", "NQ.v.0", "ZN.v.0"]):
        for event, collection, color in (
            ("statement", statement, "#1f77b4"),
            ("press conference", press, "#d95f02"),
        ):
            if instrument not in collection:
                continue
            event_time = EVENT_TIMES["statement" if event == "statement" else "press_conference"]
            quotes = valid_quotes(collection[instrument])
            pre = quotes.loc[quotes["ts_event"].lt(event_time), "midpoint"].iloc[-1]
            quotes = quotes.loc[
                quotes["ts_event"].between(
                    event_time - pd.Timedelta(seconds=30),
                    event_time + pd.Timedelta(seconds=90),
                )
            ].copy()
            quotes["event_seconds"] = (quotes["ts_event"] - event_time).dt.total_seconds()
            quotes["return_bp"] = 1e4 * np.log(quotes["midpoint"] / pre)
            sampled = quotes.set_index("ts_event")[["event_seconds", "return_bp"]].resample("250ms").last().dropna()
            ax.plot(sampled.event_seconds, sampled.return_bp, label=event, color=color, lw=1.1)
        ax.axvline(0, color="black", ls="--", lw=1)
        ax.set_title(instrument)
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Log midpoint return (bp)")
    axes[1].set_xlabel("Event time (seconds)")
    axes[-1].legend()
    fig.suptitle("Statement bundle versus press-conference opening")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _make_depth_placebo_figure(timing: pd.DataFrame, output: Path) -> None:
    subset = timing.loc[
        timing["event"].isin(["statement", "placebo_20250910_1400"])
        & timing["instrument"].isin(["ES.v.0", "NQ.v.0", "ZN.v.0"])
    ].copy()
    table = subset.pivot(
        index="instrument", columns="event", values="pre60_to_baseline_depth_ratio"
    ).reindex(["ES.v.0", "NQ.v.0", "ZN.v.0"])
    ax = table.rename(
        columns={
            "statement": "FOMC statement",
            "placebo_20250910_1400": "Matched placebo",
        }
    ).plot(kind="bar", figsize=(8, 4.5), color=["#d95f02", "#1f77b4"])
    ax.axhline(1, color="black", lw=1, ls="--")
    ax.set(
        ylabel="Final-minute depth / earlier baseline",
        xlabel="Instrument",
        title="Pre-event touch-depth withdrawal versus placebo",
    )
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.2)
    ax.figure.tight_layout()
    ax.figure.savefig(output, dpi=180)
    plt.close(ax.figure)


def _make_quote_subsequent_figure(
    timing: pd.DataFrame, horizons: pd.DataFrame, output: Path
) -> None:
    immediate = timing.loc[timing["event"].eq("statement")].set_index("instrument")
    five = horizons.loc[
        horizons["event"].eq("statement") & horizons["horizon_seconds"].eq(5)
    ].set_index("instrument")
    order = ["ES.v.0", "NQ.v.0", "ZN.v.0", "SPY", "NVDA", "JPM"]
    primary = immediate["first_quote_revision_bp"].reindex(order)
    later = five["log_return_bp"].reindex(order) - primary
    frame = pd.DataFrame(
        {"First valid quote": primary, "Later midpoint change through 5s": later}
    )
    ax = frame.plot(kind="bar", stacked=True, figsize=(9, 4.8), color=["#4c78a8", "#f58518"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set(
        xlabel="Instrument",
        ylabel="Log midpoint change (bp)",
        title="First-quote revision versus subsequent five-second adjustment",
    )
    validity = immediate["valid_mechanically"].reindex(order).fillna(False)
    ax.set_xticklabels(
        [instrument if validity.loc[instrument] else f"{instrument}*" for instrument in order]
    )
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    ax.figure.text(
        0.01,
        0.01,
        "* Fails primary quote/trade sequencing rule. FOMC futures also carry a degraded dataset flag.",
        fontsize=8,
    )
    ax.figure.tight_layout(rect=(0, 0.04, 1, 1))
    ax.figure.savefig(output, dpi=180)
    plt.close(ax.figure)


def main() -> None:
    processed = PROJECT_ROOT / "data" / "processed" / "fomc_pilot"
    figures = PROJECT_ROOT / "figures" / "fomc_pilot"
    figures.mkdir(parents=True, exist_ok=True)
    statement = _messages("statement")
    press = _messages("press_conference")
    # Source-verified corporate-news cases use a separate placebo-trained workflow.
    collections = {
        event: _messages(event)
        for event, metadata in EVENTS.items()
        if metadata.get("analysis_group") != "unscheduled_news"
    }
    timing_rows: list[dict[str, object]] = []
    horizon_frames: list[pd.DataFrame] = []
    mechanism_frames: list[pd.DataFrame] = []
    impacts: dict[tuple[str, str], dict[str, float | int]] = {}
    for event, collection in collections.items():
        for instrument, messages in collection.items():
            timing = timing_and_liquidity_summary(
                messages, EVENT_TIMES[event], instrument, event
            )
            asset_group = "futures" if instrument.endswith(".v.0") else "equities"
            condition = EVENTS[event]["dataset_condition"][asset_group]
            timing["dataset_condition"] = condition
            timing["eligible_primary_q1"] = bool(
                timing["valid_mechanically"] and condition == "available"
            )
            timing_rows.append(timing)
            horizon_frames.append(
                summarize_horizons(messages, EVENT_TIMES[event], instrument, event)
            )
            if event != "press_conference":
                impact, _ = estimate_pre_event_impact(messages, EVENT_TIMES[event])
                impacts[(event, instrument)] = impact
            impact_key = (
                ("statement", instrument)
                if event == "press_conference"
                else (event, instrument)
            )
            if event != "placebo_20250910_1400" and impact_key in impacts:
                estimate = mechanism_estimates(
                    messages,
                    EVENT_TIMES[event],
                    instrument,
                    event,
                    impacts[impact_key],
                )
                estimate["dataset_condition"] = condition
                estimate["eligible_primary_q1"] = (
                    estimate["valid_mechanically"] & (condition == "available")
                )
                mechanism_frames.append(estimate)
    timing = pd.DataFrame(timing_rows)
    horizons = pd.concat(horizon_frames, ignore_index=True)
    mechanisms = pd.concat(mechanism_frames, ignore_index=True)
    for name, frame in (
        ("timing_liquidity_summary", timing),
        ("event_response_horizons", horizons),
        ("mechanism_estimates", mechanisms),
    ):
        frame.to_parquet(processed / f"{name}.parquet", index=False)
        frame.to_csv(processed / f"{name}.csv", index=False)
    _make_cross_instrument_figure(
        statement, "statement", figures / "figure_f_cross_instrument_statement.png"
    )
    _make_statement_press_figure(
        statement, press, figures / "figure_e_statement_vs_press.png"
    )
    _make_cross_instrument_figure(
        collections["retail_sales_20250916"],
        "retail_sales_20250916",
        figures / "figure_f_cross_instrument_retail_sales.png",
    )
    for event, collection in collections.items():
        if collection and event not in {
            "statement",
            "press_conference",
            "retail_sales_20250916",
            "placebo_20250910_1400",
        }:
            _make_cross_instrument_figure(
                collection,
                event,
                figures / f"cross_instrument_{event}.png",
            )
    _make_depth_placebo_figure(
        timing, figures / "figure_placebo_depth_withdrawal.png"
    )
    _make_quote_subsequent_figure(
        timing, horizons, figures / "figure_d_quote_vs_subsequent.png"
    )
    print(
        f"Wrote {len(timing)} timing rows, {len(horizons)} horizon rows, and "
        f"{len(mechanisms)} exploratory mechanism rows."
    )


if __name__ == "__main__":
    main()
