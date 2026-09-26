from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.data.databento_client import (
    DatabentoRequest,
    estimate_request,
    historical_client,
    print_summary,
)
from src.utils.config import PROJECT_ROOT


CANDIDATES = [
    ("GLBX.MDP3", "ohlcv-1s", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T17:30:00Z", "2025-09-17T19:30:00Z"),
    ("GLBX.MDP3", "bbo-1s", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T17:50:00Z", "2025-09-17T19:00:00Z"),
    ("GLBX.MDP3", "mbp-1", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T17:50:00Z", "2025-09-17T18:10:00Z"),
    ("GLBX.MDP3", "mbp-1", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T18:25:00Z", "2025-09-17T19:00:00Z"),
    ("GLBX.MDP3", "mbo", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T17:59:00Z", "2025-09-17T18:05:00Z"),
    ("GLBX.MDP3", "status", ("ES.v.0", "NQ.v.0", "ZN.v.0"), "continuous", "2025-09-17T17:50:00Z", "2025-09-17T19:00:00Z"),
    ("EQUS.MINI", "mbp-1", ("SPY", "JPM"), "raw_symbol", "2025-09-17T17:50:00Z", "2025-09-17T18:10:00Z"),
    ("XNAS.ITCH", "mbp-1", ("NVDA",), "raw_symbol", "2025-09-17T17:50:00Z", "2025-09-17T18:10:00Z"),
    ("XNAS.ITCH", "status", ("NVDA",), "raw_symbol", "2025-09-17T17:50:00Z", "2025-09-17T18:10:00Z"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Databento entitlements and estimate pilot requests; no downloads"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "databento_cost_estimates.json",
    )
    args = parser.parse_args()
    client = historical_client()
    target_datasets = ("GLBX.MDP3", "XNAS.ITCH", "EQUS.MINI")
    available = client.metadata.list_datasets(
        start_date="2025-09-08", end_date="2025-09-20"
    )
    datasets = {}
    for dataset in target_datasets:
        if dataset not in available:
            datasets[dataset] = {"available_to_account": False}
            continue
        schemas = client.metadata.list_schemas(dataset=dataset)
        datasets[dataset] = {
            "available_to_account": True,
            "schemas": schemas,
            "range": client.metadata.get_dataset_range(dataset=dataset),
            "pilot_conditions": client.metadata.get_dataset_condition(
                dataset=dataset,
                start_date="2025-09-08",
                end_date="2025-09-19",
            ),
            "unit_prices": client.metadata.list_unit_prices(dataset=dataset),
            "fields": {
                schema: client.metadata.list_fields(
                    dataset=dataset, schema=schema, encoding="dbn"
                )
                for schema in schemas
                if schema in {"mbo", "mbp-10", "mbp-1", "tbbo", "trades", "bbo-1s", "ohlcv-1s", "status"}
            },
        }

    continuous_ids = client.symbology.resolve(
        dataset="GLBX.MDP3",
        symbols=["ES.v.0", "NQ.v.0", "ZN.v.0"],
        stype_in="continuous",
        stype_out="instrument_id",
        start_date="2025-09-08",
        end_date="2025-09-20",
    )
    instrument_ids = sorted(
        {
            mapping["s"]
            for mappings in continuous_ids.get("result", {}).values()
            for mapping in mappings
        }
    )
    raw_symbols = client.symbology.resolve(
        dataset="GLBX.MDP3",
        symbols=instrument_ids,
        stype_in="instrument_id",
        stype_out="raw_symbol",
        start_date="2025-09-08",
        end_date="2025-09-20",
    )

    rows = []
    for candidate in CANDIDATES:
        request = DatabentoRequest.create(
            dataset=candidate[0], schema=candidate[1], symbols=candidate[2],
            stype_in=candidate[3], start=candidate[4], end=candidate[5],
        )
        estimate = estimate_request(request)
        print_summary(estimate)
        print()
        rows.append(
            {
                **asdict(request),
                "request_id": request.request_id,
                "billable_bytes": estimate.billable_bytes,
                "cost_usd": estimate.cost_usd,
                "cached": estimate.cached,
            }
        )
    result = {
        "pilot_range": ["2025-09-08", "2025-09-20"],
        "available_datasets": available,
        "datasets": datasets,
        "continuous_to_instrument_id": continuous_ids,
        "instrument_id_to_raw_symbol": raw_symbols,
        "request_estimates": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"Saved metadata and estimates to {args.output}")


if __name__ == "__main__":
    main()
