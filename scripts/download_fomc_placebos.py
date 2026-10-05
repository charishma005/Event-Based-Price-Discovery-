from __future__ import annotations

import argparse

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
        description="Cost-estimate or retrieve configured matched-clock FOMC placebos"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Retrieve only after every request passes the configured cost and size guards",
    )
    parser.add_argument("--placebos", nargs="*", help="Optional placebo IDs")
    parser.add_argument("--config", default="fomc_placebos.yaml", help="File under config/")
    args = parser.parse_args()
    selected = set(args.placebos or [])
    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    estimates = []
    for placebo in config["placebos"]:
        if selected and placebo["placebo_id"] not in selected:
            continue
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3",
            schema="mbp-1",
            symbols=INSTRUMENTS,
            stype_in="continuous",
            start=placebo["request_start_utc"],
            end=placebo["request_end_utc"],
        )
        estimate = estimate_request(request)
        estimates.append((placebo, estimate))
        print(f"\n{placebo['placebo_id']} -> {placebo['matched_meeting']}")
        print_summary(estimate)
        if args.execute:  # download as we go so a later failure keeps earlier files
            path = download_request(estimate, execute=True)
            print(f"{placebo['placebo_id']}: {path.name}")

    if not estimates:
        raise RuntimeError("No configured placebo requests were selected")
    total_bytes = sum(estimate.billable_bytes for _, estimate in estimates)
    total_cost = sum(estimate.cost_usd for _, estimate in estimates)
    print(
        f"\nPortfolio estimate: {len(estimates)} windows, "
        f"{human_size(total_bytes)}, ${total_cost:,.4f}; "
        f"{sum(estimate.cached for _, estimate in estimates)} already cached."
    )
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request above.")
        return

    guards = settings()["cost_control"]
    oversized = [
        placebo["placebo_id"]
        for placebo, estimate in estimates
        if estimate.billable_bytes > int(guards["max_auto_billable_bytes"])
        or estimate.cost_usd > float(guards["max_auto_cost_usd"])
    ]
    if oversized:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(oversized)}")


if __name__ == "__main__":
    main()
