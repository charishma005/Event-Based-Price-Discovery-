from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


def main() -> None:
    validation = load_yaml(PROJECT_ROOT / "config" / "news_timestamp_validations.yaml")
    rows: list[dict[str, object]] = []
    for article_id, metadata in validation.items():
        alpha_time = pd.Timestamp(metadata["alpha_vantage_time_utc"])
        source_value = metadata.get("source_time_utc")
        source_time = pd.NaT if source_value is None else pd.Timestamp(source_value)
        delta_seconds = (
            None
            if pd.isna(source_time)
            else float((alpha_time - source_time).total_seconds())
        )
        rows.append(
            {
                "article_id": article_id,
                "ticker": metadata["ticker"],
                "alpha_vantage_time_utc": alpha_time,
                "source_time_utc": source_time,
                "alpha_minus_source_seconds": delta_seconds,
                "validation_status": metadata["validation_status"],
                "source_url": metadata["source_url"],
                "notes": metadata["notes"],
                "eligible_as_exact_unscheduled_event": metadata["validation_status"]
                in {"verified_match", "source_time_verified_alpha_mismatch"},
            }
        )
    audit = pd.DataFrame(rows)
    output = PROJECT_ROOT / "data" / "processed" / "news_timestamp_audit.csv"
    audit.to_csv(output, index=False)
    print(f"Wrote {len(audit)} source-level news timestamp checks to {output}.")


if __name__ == "__main__":
    main()
