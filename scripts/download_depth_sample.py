from __future__ import annotations

import argparse

from src.data.databento_client import DatabentoRequest, download_request, estimate_request, human_size, print_summary
from src.utils.config import PROJECT_ROOT, load_yaml, settings


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cost-estimate or retrieve selected MBP-10 windows")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--events", nargs="*")
    args = parser.parse_args()
    selected = set(args.events or [])
    config = load_yaml(PROJECT_ROOT / "config" / "depth_sample.yaml")
    estimates = []
    for event in config["events"]:
        if selected and event["event_id"] not in selected:
            continue
        for instrument in INSTRUMENTS:
            request = DatabentoRequest.create(
                dataset="GLBX.MDP3", schema="mbp-10", symbols=(instrument,),
                stype_in="continuous", start=event["request_start_utc"], end=event["request_end_utc"],
            )
            estimate = estimate_request(request)
            estimates.append((event, instrument, estimate))
            print(f"\n{event['event_id']} / {instrument}: {event['reason']}")
            print_summary(estimate)
    if not estimates:
        raise RuntimeError("No depth requests selected")
    total_bytes = sum(value.billable_bytes for _, _, value in estimates)
    total_cost = sum(value.cost_usd for _, _, value in estimates)
    print(f"\nPortfolio estimate: {len(estimates)} event-instrument windows, {human_size(total_bytes)}, ${total_cost:,.4f}; {sum(value.cached for _, _, value in estimates)} cached.")
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request.")
        return
    guards = settings()["cost_control"]
    rejected = [f"{event['event_id']}/{instrument}" for event, instrument, estimate in estimates if estimate.billable_bytes > int(guards["max_auto_billable_bytes"]) or estimate.cost_usd > float(guards["max_auto_cost_usd"])]
    if rejected:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(rejected)}")
    for event, instrument, estimate in estimates:
        path = download_request(estimate, execute=True)
        print(f"{event['event_id']}/{instrument}: {path.name}")


if __name__ == "__main__":
    main()
