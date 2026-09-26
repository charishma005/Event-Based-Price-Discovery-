from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

from src.data.databento_client import DatabentoRequest, download_request, estimate_request, human_size, print_summary
from src.utils.config import PROJECT_ROOT, load_yaml, settings


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cost-estimate or retrieve matched-clock macro controls")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--placebos", nargs="*", help="Optional placebo IDs")
    args = parser.parse_args()
    selected = set(args.placebos or [])
    config = load_yaml(PROJECT_ROOT / "config" / "macro_placebos.yaml")
    requests = []
    for placebo in config["placebos"]:
        if selected and placebo["placebo_id"] not in selected:
            continue
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema="mbp-1", symbols=INSTRUMENTS,
            stype_in="continuous", start=placebo["request_start_utc"], end=placebo["request_end_utc"],
        )
        requests.append((placebo, request))
    if not requests:
        raise RuntimeError("No macro placebo requests were selected")
    # Metadata calls are independent and can be slow; modest parallelism keeps a
    # full calendar expansion practical without increasing the requested data.
    with ThreadPoolExecutor(max_workers=min(4, len(requests))) as pool:
        values = list(pool.map(lambda item: estimate_request(item[1]), requests))
    estimates = list(zip((item[0] for item in requests), values))
    for placebo, estimate in estimates:
        print(f"\n{placebo['placebo_id']} -> {placebo['matched_month']}")
        print_summary(estimate)
    total_bytes = sum(value.billable_bytes for _, value in estimates)
    total_cost = sum(value.cost_usd for _, value in estimates)
    print(f"\nPortfolio estimate: {len(estimates)} windows, {human_size(total_bytes)}, ${total_cost:,.4f}; {sum(value.cached for _, value in estimates)} cached.")
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request.")
        return
    guards = settings()["cost_control"]
    rejected = [p["placebo_id"] for p, e in estimates if e.cost_usd > float(guards["max_auto_cost_usd"]) or e.billable_bytes > int(guards["max_auto_billable_bytes"])]
    if rejected:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(rejected)}")
    with ThreadPoolExecutor(max_workers=min(3, len(estimates))) as pool:
        paths = list(pool.map(lambda item: download_request(item[1], execute=True), estimates))
    for (placebo, _), path in zip(estimates, paths):
        print(f"{placebo['placebo_id']}: {path.name}")


if __name__ == "__main__":
    main()
