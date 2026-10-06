"""Estimate or retrieve bounded CPI futures MBP-1 windows from a verified calendar."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from dataclasses import asdict

from src.data.databento_client import DatabentoRequest, Estimate, download_request, estimate_request, historical_client, human_size, print_summary
from src.utils.config import PROJECT_ROOT, settings


def _utc_timestamp(value: str) -> pd.Timestamp:
    """Parse a CLI boundary and normalize it to an aware UTC timestamp."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=pd.Timestamp.now(tz="UTC").isoformat())
    parser.add_argument("--instruments", nargs="+", default=["ES.v.0", "NQ.v.0", "ZN.v.0"])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--size-only", action="store_true", help="Use only the fast free billable-size endpoint; execution is disabled")
    parser.add_argument(
        "--confirmed-zero-cost",
        action="store_true",
        help=(
            "Use billable-size estimates with a zero-dollar cost already confirmed "
            "for the same account, dataset, schema, symbols, and window design."
        ),
    )
    parser.add_argument(
        "--conservative-billable-bytes",
        type=int,
        default=None,
        help=(
            "Skip an unresponsive size endpoint and apply this conservative "
            "per-window bound. Requires --confirmed-zero-cost."
        ),
    )
    args = parser.parse_args()
    calendar = pd.read_csv(PROJECT_ROOT / "data/events/cpi_calendar_2015_2026.csv")
    event_time = pd.to_datetime(calendar.scheduled_time_utc, utc=True)
    selected = calendar.loc[event_time.ge(_utc_timestamp(args.start)) & event_time.le(_utc_timestamp(args.end))]
    if args.execute and args.size_only:
        raise RuntimeError("--size-only cannot be combined with --execute")
    if args.conservative_billable_bytes is not None and not args.confirmed_zero_cost:
        raise RuntimeError("--conservative-billable-bytes requires --confirmed-zero-cost")
    estimates = []
    rows = []
    client = historical_client() if (args.size_only or args.confirmed_zero_cost) else None
    for row in selected.itertuples(index=False):
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema="mbp-1", symbols=args.instruments,
            stype_in="continuous", start=row.request_start_utc, end=row.request_end_utc,
        )
        if args.conservative_billable_bytes is not None:
            estimate = Estimate(
                request=request,
                billable_bytes=args.conservative_billable_bytes,
                cost_usd=0.0,
                cached=request.output_path.exists(),
            )
        elif args.size_only or args.confirmed_zero_cost:
            kwargs = asdict(request)
            kwargs["symbols"] = list(request.symbols)
            size = int(client.metadata.get_billable_size(**kwargs))
            cost = float("nan") if args.size_only else 0.0
            estimate = Estimate(request=request, billable_bytes=size, cost_usd=cost, cached=request.output_path.exists())
        else:
            estimate = estimate_request(request)
        estimates.append((row.event_id, estimate))
        rows.append({"event_id": row.event_id, "event_time_utc": row.scheduled_time_utc,
                     "request_id": request.request_id, "cached": estimate.cached,
                     "billable_bytes": estimate.billable_bytes,
                     "cost_usd": estimate.cost_usd})
        if args.verbose:
            print(f"\nEvent: {row.event_id}")
            print_summary(estimate)
        elif len(estimates) % 20 == 0:
            print(f"Estimated {len(estimates)}/{len(selected)} windows", flush=True)
    total_size = sum(item.billable_bytes for _, item in estimates if not item.cached)
    total_cost = sum(item.cost_usd for _, item in estimates if not item.cached)
    cost_text = "not requested (size-only)" if args.size_only else f"${total_cost:,.4f}"
    output = PROJECT_ROOT / "reports/cpi_extension_estimates.csv"
    pd.DataFrame(rows).to_csv(output, index=False)
    print(f"\nPortfolio: {len(estimates)} CPI windows; uncached {human_size(total_size)}; cost {cost_text}; cached {sum(x.cached for _, x in estimates)}")
    print(f"Wrote {output}")
    if not args.execute:
        print("Estimate only. Add --execute after reviewing the portfolio.")
        return
    guards = settings()["cost_control"]
    for event_id, estimate in estimates:
        if estimate.cost_usd > float(guards["max_auto_cost_usd"]) or estimate.billable_bytes > int(guards["max_auto_billable_bytes"]):
            raise RuntimeError(f"Configured per-request guard rejected {event_id}")
    def retrieve(item: tuple[str, Estimate]) -> tuple[str, str]:
        event_id, estimate = item
        return event_id, str(download_request(estimate, execute=True))

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 3))) as pool:
        for event_id, path in pool.map(retrieve, estimates):
            print(event_id, path, flush=True)


if __name__ == "__main__":
    main()
