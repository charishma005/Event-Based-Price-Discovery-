from __future__ import annotations

import argparse
from collections import defaultdict

from src.data.databento_client import (
    DatabentoRequest,
    download_request,
    estimate_request,
    human_size,
    print_summary,
)
from src.utils.config import PROJECT_ROOT, load_yaml, settings


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cost-estimate or retrieve the official-calendar macro sample"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--event-types", nargs="*", help="Optional event types")
    parser.add_argument("--config", default="macro_sample.yaml", help="File under config/")
    args = parser.parse_args()
    selected = set(args.event_types or [])
    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    requests: dict[str, DatabentoRequest] = {}
    labels: dict[str, list[str]] = defaultdict(list)
    for event in config["events"]:
        if selected and event["event_type"] not in selected:
            continue
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3",
            schema="mbp-1",
            symbols=INSTRUMENTS,
            stype_in="continuous",
            start=event["request_start_utc"],
            end=event["request_end_utc"],
        )
        requests[request.request_id] = request
        labels[request.request_id].append(event["event_id"])

    estimates = []
    for request_id, request in requests.items():
        estimate = estimate_request(request)
        estimates.append(estimate)
        print(f"\nEvents: {', '.join(labels[request_id])}")
        print_summary(estimate)
    if not estimates:
        raise RuntimeError("No macro requests were selected")
    total_bytes = sum(value.billable_bytes for value in estimates)
    total_cost = sum(value.cost_usd for value in estimates)
    print(
        f"\nPortfolio estimate: {len(estimates)} unique windows for "
        f"{sum(len(value) for value in labels.values())} events, "
        f"{human_size(total_bytes)}, ${total_cost:,.4f}; "
        f"{sum(value.cached for value in estimates)} cached."
    )
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request.")
        return
    guards = settings()["cost_control"]
    rejected = [
        estimate.request.request_id
        for estimate in estimates
        if estimate.cost_usd > float(guards["max_auto_cost_usd"])
        or estimate.billable_bytes > int(guards["max_auto_billable_bytes"])
    ]
    if rejected:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(rejected)}")
    for estimate in estimates:
        path = download_request(estimate, execute=True)
        print(f"{', '.join(labels[estimate.request.request_id])}: {path.name}")


if __name__ == "__main__":
    main()
