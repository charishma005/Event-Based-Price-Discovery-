from __future__ import annotations

import json

import databento as db
import pandas as pd

from scripts.build_fomc_pilot import normalize_mbp1
from scripts.download_unscheduled_news_sample import _requests
from src.microstructure.mechanism import aggregate_signed_flow, identify_initial_quote_revision
from src.utils.config import PROJECT_ROOT, load_yaml


def main() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "unscheduled_news_sample.yaml")
    event_lookup = {
        event[field]: (event, time_field)
        for event in config["events"]
        for field, time_field in (
            ("label", "event_time_utc"),
            ("placebo_label", "placebo_time_utc"),
        )
    }
    processed = 0
    for label, request in _requests():
        event, time_field = event_lookup[label]
        if not request.output_path.exists():
            raise FileNotFoundError(
                f"Missing raw window for {label}; run scripts.download_unscheduled_news_sample first"
            )
        frame = db.DBNStore.from_file(request.output_path).to_df()
        if "symbol" in frame.columns:
            frame = frame.loc[frame["symbol"].eq(event["instrument"])]
        messages = normalize_mbp1(frame)
        event_time = pd.Timestamp(event[time_field])
        output = PROJECT_ROOT / "data" / "processed" / "fomc_pilot" / label
        output.mkdir(parents=True, exist_ok=True)
        messages.to_parquet(output / f"{event['instrument']}_messages.parquet", index=False)
        trades = messages.loc[messages["record_type"].eq("trade")]
        aggregate_signed_flow(trades, event_time).to_csv(
            output / f"{event['instrument']}_signed_flow_buckets.csv", index=False
        )
        primary = identify_initial_quote_revision(messages, event_time)
        diagnostic = {
            "instrument": event["instrument"],
            "event": label,
            "official_event_time_utc": event_time.isoformat(),
            "quote_revision": primary.to_dict(),
            "source_timestamp_verified": label == event["label"],
            "raw_request_id": request.request_id,
            "raw_file": request.output_path.name,
        }
        (output / f"{event['instrument']}_timestamp_diagnostic.json").write_text(
            json.dumps(diagnostic, indent=2, default=str) + "\n", encoding="utf-8"
        )
        processed += 1
    print(f"Processed {processed} source-verified event/control windows.")


if __name__ == "__main__":
    main()
