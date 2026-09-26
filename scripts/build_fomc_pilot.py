from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis.plots import plot_fomc_diagnostics
from src.microstructure.mechanism import (
    aggregate_signed_flow,
    identify_initial_quote_revision,
)
from src.utils.config import PROJECT_ROOT


EVENTS = {
    "statement": pd.Timestamp("2025-09-17T18:00:00Z"),
    "press_conference": pd.Timestamp("2025-09-17T18:30:00Z"),
}


def _char(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def normalize_mbp1(frame: pd.DataFrame) -> pd.DataFrame:
    """Map Databento MBP-1 columns to the transparent pilot schema."""
    data = frame.reset_index().copy()
    if "ts_event" not in data:
        raise ValueError("input DBN does not contain ts_event")
    action = data["action"].map(_char).str.upper()
    data["record_type"] = np.where(action.eq("T"), "trade", "quote")
    renamed = data.rename(
        columns={
            "bid_px_00": "bid",
            "ask_px_00": "ask",
            "bid_sz_00": "bid_size",
            "ask_sz_00": "ask_size",
        }
    )
    required = {
        "ts_event", "record_type", "bid", "ask", "bid_size", "ask_size",
        "price", "size", "side",
    }
    missing = required.difference(renamed.columns)
    if missing:
        raise ValueError(f"MBP-1 input is missing columns: {sorted(missing)}")
    renamed["ts_event"] = pd.to_datetime(renamed["ts_event"], utc=True)
    if "ts_recv" in renamed:
        renamed["ts_recv"] = pd.to_datetime(renamed["ts_recv"], utc=True)
    return renamed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build mechanical FOMC MBP-1 diagnostics")
    parser.add_argument("--dbn", type=Path, required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--event", choices=EVENTS, default="statement")
    parser.add_argument(
        "--event-time",
        help="Optional timezone-aware timestamp for a custom event or placebo.",
    )
    parser.add_argument(
        "--event-label",
        help="Filesystem-safe label used with --event-time.",
    )
    args = parser.parse_args()
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before reading DBN") from exc

    frame = db.DBNStore.from_file(args.dbn).to_df()
    if "symbol" in frame.columns:
        frame = frame.loc[frame["symbol"].eq(args.instrument)]
    messages = normalize_mbp1(frame)
    if args.event_time:
        event_time = pd.Timestamp(args.event_time)
        if event_time.tzinfo is None:
            raise ValueError("--event-time must be timezone-aware")
        event_time = event_time.tz_convert("UTC")
        event_label = args.event_label or "custom_event"
    else:
        event_time = EVENTS[args.event]
        event_label = args.event
    quote_result = identify_initial_quote_revision(messages, event_time)
    trades = messages.loc[messages["record_type"].eq("trade")]
    flows = aggregate_signed_flow(trades, event_time)

    output = PROJECT_ROOT / "data" / "processed" / "fomc_pilot" / event_label
    output.mkdir(parents=True, exist_ok=True)
    messages.to_parquet(output / f"{args.instrument}_messages.parquet", index=False)
    flows.to_csv(output / f"{args.instrument}_signed_flow_buckets.csv", index=False)

    first_trade = trades.loc[trades["ts_event"].ge(event_time)].head(1)
    diagnostics = {
        "instrument": args.instrument,
        "event": event_label,
        "official_event_time_utc": event_time.isoformat(),
        "quote_revision": quote_result.to_dict(),
        "first_trade_after_event": first_trade.to_dict(orient="records"),
        "note": "Order-flow component/mechanism share awaits an estimated impact coefficient; it is not forced from one event.",
    }
    (output / f"{args.instrument}_timestamp_diagnostic.json").write_text(
        json.dumps(diagnostics, indent=2, default=str) + "\n", encoding="utf-8"
    )
    paths = plot_fomc_diagnostics(
        messages,
        event_time_utc=event_time,
        instrument=args.instrument,
        output_dir=PROJECT_ROOT / "figures" / "fomc_pilot" / event_label,
    )
    print(json.dumps(diagnostics, indent=2, default=str))
    print("Figures:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
