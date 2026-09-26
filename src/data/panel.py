from __future__ import annotations

from pathlib import Path

import pandas as pd


EVENT_TIME_COLUMNS = [
    "event_id", "instrument", "asset_class", "event_type",
    "representation_class", "source_dataset", "dataset_condition",
    "timestamp_utc", "timestamp_et", "timestamp_recv_utc", "capture_latency_us",
    "sequence", "event_time_ms", "bid", "ask",
    "midpoint", "spread", "relative_spread", "bid_size", "ask_size",
    "depth_total_touch", "depth_imbalance", "depth_bid_10", "depth_ask_10",
    "message_intensity", "trade_price", "trade_size", "aggressor_side",
    "signed_volume", "signed_notional", "return", "cumulative_return",
    "quote_revision_component", "order_flow_component", "residual_component",
    "mechanism_share", "contamination_flag", "contamination_notes", "quality_flags",
]


def write_event_time_panel(
    frame: pd.DataFrame, path: str | Path, *, overwrite: bool = False
) -> None:
    """Validate the canonical processed-panel columns and write Parquet."""
    missing = [column for column in EVENT_TIME_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"event-time panel is missing columns: {missing}")
    output = frame.loc[:, EVENT_TIME_COLUMNS].copy()
    output["timestamp_utc"] = pd.to_datetime(output["timestamp_utc"], utc=True)
    output["timestamp_recv_utc"] = pd.to_datetime(
        output["timestamp_recv_utc"], utc=True, errors="coerce"
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    if overwrite:
        temporary = target.with_suffix(target.suffix + ".tmp")
        output.to_parquet(temporary, index=False)
        temporary.replace(target)
    else:
        output.to_parquet(target, index=False)
