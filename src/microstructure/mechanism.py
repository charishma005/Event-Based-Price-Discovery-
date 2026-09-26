from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class QuoteRevisionResult:
    pre_quote_ts: pd.Timestamp | None
    post_quote_ts: pd.Timestamp | None
    pre_midpoint: float | None
    post_midpoint: float | None
    quote_revision_component: float | None
    intervening_trade: bool
    sequencing_ambiguous: bool
    valid_for_primary_q1: bool
    quality_flags: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def add_quote_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["midpoint"] = (result["bid"] + result["ask"]) / 2
    result["spread"] = result["ask"] - result["bid"]
    total = result["bid_size"] + result["ask_size"]
    result["depth_total_touch"] = total
    result["depth_imbalance"] = np.where(
        total > 0, (result["bid_size"] - result["ask_size"]) / total, np.nan
    )
    return result


def identify_initial_quote_revision(
    messages: pd.DataFrame,
    event_time_utc: str | pd.Timestamp,
) -> QuoteRevisionResult:
    """Locate the pre/post BBO and enforce the no-intervening-trade rule."""
    required = {"ts_event", "record_type", "bid", "ask"}
    missing = required.difference(messages.columns)
    if missing:
        raise ValueError(f"messages missing columns: {sorted(missing)}")

    data = messages.copy().reset_index(drop=True)
    data["ts_event"] = pd.to_datetime(data["ts_event"], utc=True)
    event = pd.Timestamp(event_time_utc)
    if event.tzinfo is None:
        raise ValueError("event timestamp must be timezone-aware")
    event = event.tz_convert("UTC")
    data["_row_order"] = np.arange(len(data))
    has_sequence = "sequence" in data and data["sequence"].notna().all()
    if not has_sequence:
        data["sequence"] = 0
    data = data.sort_values(["ts_event", "sequence", "_row_order"], kind="stable")

    quote = data["record_type"].eq("quote")
    valid_quote = quote & data["bid"].gt(0) & data["ask"].gt(data["bid"])
    pre = data.loc[valid_quote & data["ts_event"].lt(event)].tail(1)
    post = data.loc[valid_quote & data["ts_event"].ge(event)].head(1)
    flags: list[str] = []
    status_near_event = pd.Series(False, index=data.index)
    if "status" in data.columns:
        status_near_event = (
            data["record_type"].eq("status")
            & data["status"].astype("string").str.lower().str.contains(
                "halt|pause|auction", na=False
            )
            & (data["ts_event"].sub(event).abs() <= pd.Timedelta(minutes=5))
        )
        if status_near_event.any():
            flags.append("halt_pause_or_auction_near_event")
    if pre.empty:
        flags.append("missing_pre_quote")
    if post.empty:
        flags.append("missing_post_quote")
    invalid_around_event = quote & (~valid_quote) & (
        data["ts_event"].sub(event).abs() <= pd.Timedelta(seconds=1)
    )
    if invalid_around_event.any():
        flags.append("locked_crossed_or_invalid_quote_near_event")
    if pre.empty or post.empty:
        return QuoteRevisionResult(
            None if pre.empty else pre.iloc[0]["ts_event"],
            None if post.empty else post.iloc[0]["ts_event"],
            None, None, None, False, False, False, tuple(flags),
        )

    pre_row = pre.iloc[0]
    post_row = post.iloc[0]
    post_position = data.index.get_loc(post.index[0])
    between = data.iloc[:post_position]
    between = between.loc[
        between["ts_event"].ge(event) & between["record_type"].eq("trade")
    ]
    intervening = not between.empty
    if intervening:
        flags.append("trade_before_first_post_event_quote")

    same_ts_types = data.loc[
        data["ts_event"].eq(post_row["ts_event"]), "record_type"
    ]
    ambiguous = bool(
        (not has_sequence or data.loc[data["ts_event"].eq(post_row["ts_event"]), "sequence"].eq(0).all())
        and {"quote", "trade"}.issubset(set(same_ts_types))
    )
    if ambiguous:
        flags.append("same_timestamp_quote_trade_order_unresolved")

    pre_mid = float((pre_row["bid"] + pre_row["ask"]) / 2)
    post_mid = float((post_row["bid"] + post_row["ask"]) / 2)
    return QuoteRevisionResult(
        pre_quote_ts=pre_row["ts_event"],
        post_quote_ts=post_row["ts_event"],
        pre_midpoint=pre_mid,
        post_midpoint=post_mid,
        quote_revision_component=post_mid - pre_mid,
        intervening_trade=intervening,
        sequencing_ambiguous=ambiguous,
        valid_for_primary_q1=(
            not intervening and not ambiguous and not status_near_event.any()
        ),
        quality_flags=tuple(flags),
    )


def sign_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Sign volume/notional only where the feed supplies aggressor side."""
    required = {"side", "size", "price"}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    result = trades.copy()
    side = result["side"].astype("string").str.upper()
    sign = side.map({"B": 1.0, "BID": 1.0, "A": -1.0, "ASK": -1.0})
    result["aggressor_sign"] = sign
    result["aggressor_side_known"] = sign.notna()
    result["signed_volume"] = sign * result["size"]
    result["signed_notional"] = sign * result["size"] * result["price"]
    result["signed_trade_count"] = sign
    return result


def aggregate_signed_flow(
    trades: pd.DataFrame,
    event_time_utc: str | pd.Timestamp,
    buckets_ms: Iterable[int] = (100, 250, 500, 1000, 5000),
) -> pd.DataFrame:
    data = sign_trades(trades)
    data["ts_event"] = pd.to_datetime(data["ts_event"], utc=True)
    event = pd.Timestamp(event_time_utc)
    if event.tzinfo is None:
        raise ValueError("event timestamp must be timezone-aware")
    event = event.tz_convert("UTC")
    rows = []
    for horizon in buckets_ms:
        sample = data.loc[
            data["ts_event"].ge(event)
            & data["ts_event"].lt(event + pd.Timedelta(milliseconds=horizon))
        ]
        rows.append(
            {
                "horizon_ms": int(horizon),
                "signed_volume": sample["signed_volume"].sum(min_count=1),
                "signed_notional": sample["signed_notional"].sum(min_count=1),
                "signed_trade_count": sample["signed_trade_count"].sum(min_count=1),
                "trade_count": len(sample),
                "known_side_fraction": sample["aggressor_side_known"].mean()
                if len(sample)
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def fit_order_flow_impact(
    intervals: pd.DataFrame,
    *,
    return_col: str = "return",
    flow_col: str = "signed_volume",
) -> tuple[dict[str, float | int], pd.DataFrame]:
    """Fit the proposal's linear short-interval return/flow relationship.

    The caller chooses the estimation sample. For focal-event estimates, prefer a
    pooled or leave-one-event-out sample so one observation does not mechanically
    determine its own order-flow component.
    """
    missing = {return_col, flow_col}.difference(intervals.columns)
    if missing:
        raise ValueError(f"interval panel missing columns: {sorted(missing)}")
    sample = intervals[[return_col, flow_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sample) < 3:
        raise ValueError("at least three finite intervals are required")
    x = np.column_stack([np.ones(len(sample)), sample[flow_col].to_numpy(float)])
    y = sample[return_col].to_numpy(float)
    coefficients, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ coefficients
    residual = y - fitted
    total_ss = float(np.square(y - y.mean()).sum())
    residual_ss = float(np.square(residual).sum())
    r_squared = np.nan if total_ss == 0 else 1 - residual_ss / total_ss
    output = intervals.copy()
    output["fitted_order_flow_return"] = np.nan
    output["order_flow_regression_residual"] = np.nan
    output.loc[sample.index, "fitted_order_flow_return"] = fitted
    output.loc[sample.index, "order_flow_regression_residual"] = residual
    diagnostics: dict[str, float | int] = {
        "intercept": float(coefficients[0]),
        "impact_coefficient": float(coefficients[1]),
        "nobs": int(len(sample)),
        "r_squared": float(r_squared),
    }
    return diagnostics, output


def mechanism_components(
    *,
    quote_revision: float,
    cumulative_signed_flow: float,
    impact_coefficient: float,
    total_adjustment: float,
    near_zero_tolerance: float = 1e-12,
) -> dict[str, float | bool | list[str]]:
    """Compute the proposal's signed components without forced normalization."""
    order_flow = impact_coefficient * cumulative_signed_flow
    denominator = quote_revision + order_flow
    residual = total_adjustment - denominator
    flags: list[str] = []
    if abs(denominator) <= near_zero_tolerance:
        share = np.nan
        flags.append("near_zero_component_denominator")
    else:
        share = quote_revision / denominator
    if quote_revision * order_flow < 0:
        flags.append("opposing_component_signs")
    if np.isfinite(share) and not 0 <= share <= 1:
        flags.append("mechanism_share_outside_unit_interval")
    if total_adjustment * denominator < 0:
        flags.append("component_sum_opposes_total_adjustment")
    return {
        "quote_revision_component": quote_revision,
        "order_flow_component": order_flow,
        "residual_component": residual,
        "component_denominator": denominator,
        "mechanism_share": share,
        "quality_flags": flags,
    }
