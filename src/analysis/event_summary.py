from __future__ import annotations

import numpy as np
import pandas as pd

from src.microstructure.mechanism import (
    fit_order_flow_impact,
    identify_initial_quote_revision,
    mechanism_components,
    sign_trades,
)


def valid_quotes(messages: pd.DataFrame) -> pd.DataFrame:
    quotes = messages.loc[
        messages["record_type"].eq("quote")
        & messages["bid"].gt(0)
        & messages["ask"].gt(messages["bid"])
    ].copy()
    quotes["midpoint"] = (quotes["bid"] + quotes["ask"]) / 2
    quotes["spread"] = quotes["ask"] - quotes["bid"]
    quotes["touch_depth"] = quotes["bid_size"] + quotes["ask_size"]
    return quotes.sort_values(["ts_event", "sequence"], kind="stable")


def _quote_at_or_before(quotes: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series | None:
    sample = quotes.loc[quotes["ts_event"].le(timestamp)]
    return None if sample.empty else sample.iloc[-1]


def summarize_horizons(
    messages: pd.DataFrame,
    event_time: pd.Timestamp,
    instrument: str,
    event_name: str,
    horizons_seconds: tuple[float, ...] = (0.1, 0.25, 0.5, 1, 5, 30, 60, 300),
) -> pd.DataFrame:
    """Measure midpoint, liquidity, and explicit signed flow at fixed event horizons."""
    event = pd.Timestamp(event_time).tz_convert("UTC")
    data = messages.sort_values(["ts_event", "sequence"], kind="stable")
    quotes = valid_quotes(data)
    pre = _quote_at_or_before(quotes.loc[quotes["ts_event"].lt(event)], event)
    if pre is None:
        raise ValueError(f"{instrument} has no valid pre-event quote")
    trades = sign_trades(data.loc[data["record_type"].eq("trade")])
    data_end = data["ts_event"].max()
    rows: list[dict[str, object]] = []
    for horizon in horizons_seconds:
        cutoff = event + pd.Timedelta(seconds=horizon)
        covered = data_end >= cutoff
        post = _quote_at_or_before(quotes, cutoff) if covered else None
        trade_sample = trades.loc[
            trades["ts_event"].ge(event) & trades["ts_event"].lt(cutoff)
        ] if covered else trades.iloc[0:0]
        rows.append(
            {
                "event": event_name,
                "instrument": instrument,
                "event_time_utc": event,
                "horizon_seconds": float(horizon),
                "full_horizon_covered": bool(covered),
                "pre_midpoint": float(pre["midpoint"]),
                "midpoint": None if post is None else float(post["midpoint"]),
                "midpoint_change": None
                if post is None
                else float(post["midpoint"] - pre["midpoint"]),
                "log_return_bp": None
                if post is None
                else float(1e4 * np.log(post["midpoint"] / pre["midpoint"])),
                "spread": None if post is None else float(post["spread"]),
                "touch_depth": None if post is None else float(post["touch_depth"]),
                "trade_count": int(len(trade_sample)) if covered else None,
                "signed_volume": trade_sample["signed_volume"].sum(min_count=1)
                if covered
                else None,
                "signed_notional": trade_sample["signed_notional"].sum(min_count=1)
                if covered
                else None,
                "known_side_fraction": trade_sample["aggressor_side_known"].mean()
                if covered and len(trade_sample)
                else None,
            }
        )
    return pd.DataFrame(rows)


def timing_and_liquidity_summary(
    messages: pd.DataFrame,
    event_time: pd.Timestamp,
    instrument: str,
    event_name: str,
) -> dict[str, object]:
    event = pd.Timestamp(event_time).tz_convert("UTC")
    data = messages.sort_values(["ts_event", "sequence"], kind="stable")
    quotes = valid_quotes(data)
    trades = data.loc[data["record_type"].eq("trade")]
    primary = identify_initial_quote_revision(data, event)
    first_trade = trades.loc[trades["ts_event"].ge(event)].head(1)
    first_trade_ts = None if first_trade.empty else first_trade.iloc[0]["ts_event"]
    pretrade = quotes.loc[quotes["ts_event"].ge(event)]
    if first_trade_ts is not None:
        pretrade = pretrade.loc[pretrade["ts_event"].lt(first_trade_ts)]
    else:
        pretrade = pretrade.iloc[0:0]
    pre_quote = quotes.loc[quotes["ts_event"].lt(event)].tail(1)
    last_pretrade_return_bp = None
    if not pretrade.empty and not pre_quote.empty:
        last_pretrade_return_bp = float(
            1e4
            * np.log(
                pretrade.iloc[-1]["midpoint"] / pre_quote.iloc[-1]["midpoint"]
            )
        )
    baseline = quotes.loc[
        quotes["ts_event"].ge(event - pd.Timedelta(minutes=10))
        & quotes["ts_event"].lt(event - pd.Timedelta(seconds=60))
    ]
    pre60 = quotes.loc[
        quotes["ts_event"].ge(event - pd.Timedelta(seconds=60))
        & quotes["ts_event"].lt(event)
    ]
    latency_us = None
    latency_p99_us = None
    if "ts_recv" in data:
        latency = (
            pd.to_datetime(data["ts_recv"], utc=True) - data["ts_event"]
        ).dt.total_seconds() * 1e6
        latency = latency.loc[latency.ge(0)]
        if not latency.empty:
            latency_us = float(latency.median())
            latency_p99_us = float(latency.quantile(0.99))
    return {
        "event": event_name,
        "instrument": instrument,
        "event_time_utc": event,
        "pre_quote_ts": primary.pre_quote_ts,
        "first_post_quote_ts": primary.post_quote_ts,
        "first_trade_ts": first_trade_ts,
        "first_post_quote_delay_ms": None
        if primary.post_quote_ts is None
        else float((primary.post_quote_ts - event).total_seconds() * 1000),
        "first_trade_delay_ms": None
        if first_trade_ts is None
        else float((first_trade_ts - event).total_seconds() * 1000),
        "first_quote_revision_price": primary.quote_revision_component,
        "first_quote_revision_bp": None
        if primary.pre_midpoint in (None, 0) or primary.post_midpoint is None
        else float(1e4 * np.log(primary.post_midpoint / primary.pre_midpoint)),
        "intervening_trade": primary.intervening_trade,
        "sequencing_ambiguous": primary.sequencing_ambiguous,
        "valid_mechanically": primary.valid_for_primary_q1,
        "quality_flags": "|".join(primary.quality_flags),
        "pretrade_quote_count": int(len(pretrade)),
        "last_pretrade_quote_revision_bp": last_pretrade_return_bp,
        "baseline_touch_depth_mean": baseline["touch_depth"].mean(),
        "pre60_touch_depth_mean": pre60["touch_depth"].mean(),
        "pre60_to_baseline_depth_ratio": None
        if baseline.empty or baseline["touch_depth"].mean() == 0
        else float(pre60["touch_depth"].mean() / baseline["touch_depth"].mean()),
        "median_capture_latency_us": latency_us,
        "p99_capture_latency_us": latency_p99_us,
    }


def flow_intervals(messages: pd.DataFrame, frequency: str = "1s") -> pd.DataFrame:
    """Construct fixed-clock midpoint returns, signed flow, and lagged liquidity."""
    quotes = valid_quotes(messages)
    quote_state = (
        quotes.set_index("ts_event")[["midpoint", "touch_depth", "spread"]]
        .resample(frequency)
        .last()
        .ffill()
    )
    midpoint = quote_state["midpoint"]
    returns = np.log(midpoint).diff().rename("return")
    trades = sign_trades(messages.loc[messages["record_type"].eq("trade")].copy())
    trades["bucket"] = trades["ts_event"].dt.floor(frequency)
    flow = trades.groupby("bucket").agg(
        signed_volume=("signed_volume", lambda values: values.sum(min_count=1)),
        trade_count=("size", "size"),
        known_side_fraction=("aggressor_side_known", "mean"),
    )
    intervals = pd.concat(
        [returns, quote_state[["touch_depth", "spread"]], flow], axis=1, sort=True
    )
    intervals["signed_volume"] = intervals["signed_volume"].fillna(0.0)
    intervals["trade_count"] = intervals["trade_count"].fillna(0).astype(int)
    intervals["lag_touch_depth"] = intervals["touch_depth"].shift(1)
    intervals["lag_spread"] = intervals["spread"].shift(1)
    return intervals


def second_intervals(messages: pd.DataFrame) -> pd.DataFrame:
    """Construct one-second intervals; retained as the baseline public API."""
    return flow_intervals(messages, "1s")


def estimate_pre_event_impact(
    messages: pd.DataFrame,
    event_time: pd.Timestamp,
    *,
    training_start_seconds: int = -540,
    training_end_seconds: int = -60,
) -> tuple[dict[str, float | int], pd.DataFrame]:
    event = pd.Timestamp(event_time).tz_convert("UTC")
    intervals = second_intervals(messages)
    sample = intervals.loc[
        (intervals.index >= event + pd.Timedelta(seconds=training_start_seconds))
        & (intervals.index < event + pd.Timedelta(seconds=training_end_seconds))
    ]
    return fit_order_flow_impact(sample)


def mechanism_estimates(
    messages: pd.DataFrame,
    event_time: pd.Timestamp,
    instrument: str,
    event_name: str,
    impact: dict[str, float | int],
    horizons_seconds: tuple[int, ...] = (5, 30, 60, 300),
) -> pd.DataFrame:
    event = pd.Timestamp(event_time).tz_convert("UTC")
    quotes = valid_quotes(messages)
    pre = quotes.loc[quotes["ts_event"].lt(event)].iloc[-1]
    primary = identify_initial_quote_revision(messages, event)
    quote_return = np.nan
    if primary.pre_midpoint and primary.post_midpoint:
        quote_return = float(np.log(primary.post_midpoint / primary.pre_midpoint))
    trades = sign_trades(messages.loc[messages["record_type"].eq("trade")])
    rows: list[dict[str, object]] = []
    data_end = messages["ts_event"].max()
    for horizon in horizons_seconds:
        cutoff = event + pd.Timedelta(seconds=horizon)
        if data_end < cutoff:
            continue
        post = _quote_at_or_before(quotes, cutoff)
        sample = trades.loc[
            trades["ts_event"].ge(event) & trades["ts_event"].lt(cutoff)
        ]
        signed_volume = sample["signed_volume"].sum(min_count=1)
        total = float(np.log(post["midpoint"] / pre["midpoint"]))
        components = mechanism_components(
            quote_revision=quote_return,
            cumulative_signed_flow=float(signed_volume),
            impact_coefficient=float(impact["impact_coefficient"]),
            total_adjustment=total,
        )
        component_sum = float(components["component_denominator"])
        coverage = np.nan if abs(total) <= 1e-12 else component_sum / total
        component_flags = list(components["quality_flags"])
        if np.isfinite(coverage) and abs(coverage) < 0.25:
            component_flags.append("low_component_coverage")
        rows.append(
            {
                "event": event_name,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "impact_training_nobs": impact["nobs"],
                "impact_coefficient": impact["impact_coefficient"],
                "impact_r_squared": impact["r_squared"],
                "signed_volume": signed_volume,
                "known_side_fraction": sample["aggressor_side_known"].mean()
                if len(sample)
                else np.nan,
                "total_adjustment_bp": total * 1e4,
                "quote_revision_bp": components["quote_revision_component"] * 1e4,
                "order_flow_component_bp": components["order_flow_component"] * 1e4,
                "residual_component_bp": components["residual_component"] * 1e4,
                "mechanism_share": components["mechanism_share"],
                "component_coverage_ratio": coverage,
                "component_flags": "|".join(component_flags),
                "valid_mechanically": primary.valid_for_primary_q1,
            }
        )
    return pd.DataFrame(rows)
