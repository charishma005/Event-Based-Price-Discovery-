from __future__ import annotations

import argparse

from src.data.databento_client import (
    DatabentoRequest,
    download_request,
    estimate_request,
    print_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate a Databento request; download only with --execute"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--stype-in", default="raw_symbol")
    parser.add_argument("--start", required=True, help="Timezone-aware ISO timestamp")
    parser.add_argument("--end", required=True, help="Timezone-aware ISO timestamp")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    request = DatabentoRequest.create(
        dataset=args.dataset,
        schema=args.schema,
        symbols=args.symbols,
        stype_in=args.stype_in,
        start=args.start,
        end=args.end,
    )
    estimate = estimate_request(request)
    if args.execute:
        path = download_request(estimate, execute=True)
        print(f"Saved immutable raw data to {path}")
    else:
        print_summary(estimate)
        print("Estimate only. Add --execute only after reviewing the summary.")


if __name__ == "__main__":
    main()

