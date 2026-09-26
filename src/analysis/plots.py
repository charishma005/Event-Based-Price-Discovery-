from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_fomc_diagnostics(
    messages: pd.DataFrame,
    *,
    event_time_utc: pd.Timestamp,
    instrument: str,
    output_dir: str | Path,
) -> list[Path]:
    """Create transparent mechanical diagnostics before any regression."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = messages.copy().sort_values("ts_event")
    event = pd.Timestamp(event_time_utc).tz_convert("UTC")
    data["event_time_seconds"] = (
        data["ts_event"] - event
    ).dt.total_seconds()
    quote = data.loc[data["record_type"].eq("quote")].copy()
    quote["midpoint"] = (quote["bid"] + quote["ask"]) / 2
    quote["spread"] = quote["ask"] - quote["bid"]
    quote["touch_depth"] = quote["bid_size"] + quote["ask_size"]
    paths: list[Path] = []

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.step(quote["event_time_seconds"], quote["midpoint"], where="post")
    ax.axvline(0, color="crimson", linestyle="--", linewidth=1)
    ax.set(title=f"{instrument}: midpoint around information arrival", xlabel="Event time (seconds)", ylabel="Midpoint")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    path = output / f"{instrument}_figure_a_midpoint.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    axes[0].step(quote["event_time_seconds"], quote["spread"], where="post")
    axes[0].set_ylabel("Spread")
    axes[1].step(quote["event_time_seconds"], quote["touch_depth"], where="post")
    axes[1].set(xlabel="Event time (seconds)", ylabel="Touch depth")
    for ax in axes:
        ax.axvline(0, color="crimson", linestyle="--", linewidth=1)
        ax.grid(alpha=0.2)
    fig.suptitle(f"{instrument}: spread and touch depth")
    fig.tight_layout()
    path = output / f"{instrument}_figure_b_liquidity.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    trade = data.loc[data["record_type"].eq("trade")].copy()
    if not trade.empty:
        sign = trade["side"].astype("string").str.upper().map({"B": 1, "BID": 1, "A": -1, "ASK": -1})
        trade["cumulative_signed_volume"] = (sign * trade["size"]).fillna(0).cumsum()
        pre_quotes = quote.loc[quote["ts_event"].lt(event)]
        reference = pre_quotes["midpoint"].iloc[-1] if not pre_quotes.empty else np.nan
        quote["cumulative_return"] = np.log(quote["midpoint"] / reference)
        fig, ax1 = plt.subplots(figsize=(9, 4.5))
        ax1.step(trade["event_time_seconds"], trade["cumulative_signed_volume"], where="post", color="#1f77b4")
        ax1.set(xlabel="Event time (seconds)", ylabel="Cumulative signed volume", title=f"{instrument}: signed flow and midpoint return")
        ax2 = ax1.twinx()
        ax2.step(quote["event_time_seconds"], quote["cumulative_return"], where="post", color="#d95f02")
        ax2.set_ylabel("Cumulative log midpoint return")
        ax1.axvline(0, color="crimson", linestyle="--", linewidth=1)
        ax1.grid(alpha=0.2)
        fig.tight_layout()
        path = output / f"{instrument}_figure_c_flow_return.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        paths.append(path)
    return paths

