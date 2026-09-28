from __future__ import annotations

import argparse
import json

from src.data.databento_client import historical_client
from src.utils.config import PROJECT_ROOT, load_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Databento conditions for a macro config")
    parser.add_argument("--config", default="macro_sample.yaml", help="File under config/")
    parser.add_argument("--output", default="macro_dataset_conditions.json", help="File under reports/")
    args = parser.parse_args()
    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    # Macro configs list "events"; FOMC configs list "meetings".
    items = config.get("events") or config.get("meetings") or []
    dates = sorted({item.get("event_date") or item["meeting_date"] for item in items})
    conditions = historical_client().metadata.get_dataset_condition(
        dataset="GLBX.MDP3",
        start_date=dates[0],
        end_date=dates[-1],
    )
    event_dates = set(dates)
    relevant = [row for row in conditions if row["date"] in event_dates]
    missing = sorted(event_dates - {row["date"] for row in relevant})
    result = {
        "dataset": "GLBX.MDP3",
        "configured_event_dates": dates,
        "conditions": relevant,
        "missing_dates": missing,
    }
    output = PROJECT_ROOT / "reports" / args.output
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in relevant:
        counts[row["condition"]] = counts.get(row["condition"], 0) + 1
    print(f"Condition counts on {len(relevant)} configured dates: {counts}")
    if missing:
        print(f"Dates without a returned condition: {', '.join(missing)}")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
