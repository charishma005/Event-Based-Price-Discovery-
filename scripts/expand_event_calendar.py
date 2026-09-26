from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


NAMES = {
    "cpi": ("BLS", "Consumer Price Index", "macro_inflation"),
    "ppi": ("BLS", "Producer Price Index", "macro_inflation"),
    "employment_situation": ("BLS", "Employment Situation", "labor"),
    "retail_sales": ("U.S. Census Bureau", "Advance Retail Sales", "macro_activity"),
}


def main() -> None:
    path = PROJECT_ROOT / "data" / "events" / "event_calendar.csv"
    existing = pd.read_csv(path)
    config = load_yaml(PROJECT_ROOT / "config" / "macro_sample.yaml")
    rows = []
    for event in config["events"]:
        agency, name, category = NAMES[event["event_type"]]
        utc = pd.Timestamp(event["event_time_utc"])
        eastern = utc.tz_convert("America/New_York")
        source_key = "census_calendar" if event["event_type"] == "retail_sales" else "bls_calendar"
        notes = "Vintage consensus and forecast dispersion unavailable."
        if event.get("concurrent_release"):
            notes += f" Concurrent with {event['concurrent_release']}; treat as a bundled arrival."
        rows.append(
            {
                "event_id": event["event_id"],
                "event_date": event["event_date"],
                "scheduled_time_et": eastern.isoformat(),
                "scheduled_time_utc": utc.isoformat().replace("+00:00", "Z"),
                "source_agency": agency,
                "event_name": f"{name} - {event['reference_period']}",
                "event_category": category,
                "representation_class": event["representation_class"],
                "scheduled_indicator": 1,
                "numeric_or_narrative": "numeric",
                "expected_value": None,
                "realized_value": None,
                "prior_value": None,
                "forecast_dispersion": None,
                "standardized_surprise": None,
                "authoritative_source_url": config["source_urls"][source_key],
                "notes": notes,
            }
        )
    additions = pd.DataFrame(rows).reindex(columns=existing.columns)
    output = pd.concat(
        [existing.loc[~existing["event_id"].isin(additions["event_id"])], additions],
        ignore_index=True,
    ).sort_values(["scheduled_time_utc", "event_id"], kind="stable")
    output.to_csv(path, index=False)
    output.to_parquet(path.with_suffix(".parquet"), index=False)
    print(f"Wrote {len(output)} harmonized events ({len(additions)} macro additions).")


if __name__ == "__main__":
    main()
