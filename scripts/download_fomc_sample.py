from __future__ import annotations

import argparse

from src.data.databento_client import DatabentoRequest, download_request, estimate_request, human_size, print_summary
from src.utils.config import PROJECT_ROOT, load_yaml, settings


INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cost-estimate or retrieve FOMC meeting windows")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--meetings", nargs="*")
    parser.add_argument("--config", default="fomc_sample.yaml", help="File under config/")
    args = parser.parse_args()
    selected = set(args.meetings or [])
    config = load_yaml(PROJECT_ROOT / "config" / args.config)
    estimates = []
    for meeting in config["meetings"]:
        if selected and meeting["label"] not in selected:
            continue
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema="mbp-1", symbols=INSTRUMENTS,
            stype_in="continuous", start=meeting["request_start_utc"], end=meeting["request_end_utc"],
        )
        estimate = estimate_request(request)
        estimates.append((meeting, estimate))
        print(f"\n{meeting['label']}")
        print_summary(estimate)
    if not estimates:
        raise RuntimeError("No meeting requests selected")
    total_bytes = sum(value.billable_bytes for _, value in estimates)
    total_cost = sum(value.cost_usd for _, value in estimates)
    print(f"\nPortfolio estimate: {len(estimates)} windows, {human_size(total_bytes)}, ${total_cost:,.4f}; {sum(value.cached for _, value in estimates)} cached.")
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request.")
        return
    guards = settings()["cost_control"]
    rejected = [meeting["label"] for meeting, estimate in estimates if estimate.billable_bytes > int(guards["max_auto_billable_bytes"]) or estimate.cost_usd > float(guards["max_auto_cost_usd"])]
    if rejected:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(rejected)}")
    for meeting, estimate in estimates:
        path = download_request(estimate, execute=True)
        print(f"{meeting['label']}: {path.name}")


if __name__ == "__main__":
    main()
