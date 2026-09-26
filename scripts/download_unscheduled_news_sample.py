from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.data.databento_client import (
    DatabentoRequest,
    download_request,
    estimate_request,
    human_size,
    print_summary,
)
from src.utils.config import PROJECT_ROOT, load_yaml, settings


def _requests() -> list[tuple[str, DatabentoRequest]]:
    config = load_yaml(PROJECT_ROOT / "config" / "unscheduled_news_sample.yaml")
    request_config = config["request"]
    requests: list[tuple[str, DatabentoRequest]] = []
    for event in config["events"]:
        for label_field, time_field in (
            ("label", "event_time_utc"),
            ("placebo_label", "placebo_time_utc"),
        ):
            center = pd.Timestamp(event[time_field])
            requests.append(
                (
                    event[label_field],
                    DatabentoRequest.create(
                        dataset=request_config["dataset"],
                        schema=request_config["schema"],
                        symbols=[event["instrument"]],
                        stype_in=request_config["stype_in"],
                        start=center
                        - pd.Timedelta(
                            minutes=event.get("pre_minutes", request_config["pre_minutes"])
                        ),
                        end=center
                        + pd.Timedelta(
                            minutes=event.get("post_minutes", request_config["post_minutes"])
                        ),
                    ),
                )
            )
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cost-estimate or retrieve source-verified corporate-news windows"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--labels", nargs="*")
    args = parser.parse_args()
    selected = set(args.labels or [])
    requests = [item for item in _requests() if not selected or item[0] in selected]
    if not requests:
        raise RuntimeError("No corporate-news requests selected")
    with ThreadPoolExecutor(max_workers=min(3, len(requests))) as pool:
        estimates = list(pool.map(lambda item: estimate_request(item[1]), requests))
    for (label, _), estimate in zip(requests, estimates):
        print(f"\n{label}")
        print_summary(estimate)
    total_bytes = sum(value.billable_bytes for value in estimates)
    total_cost = sum(value.cost_usd for value in estimates)
    print(
        f"\nPortfolio estimate: {len(estimates)} windows, {human_size(total_bytes)}, "
        f"${total_cost:,.4f}; {sum(value.cached for value in estimates)} cached."
    )
    if not args.execute:
        print("Estimate only. Add --execute after reviewing every request.")
        return
    guards = settings()["cost_control"]
    rejected = [
        label
        for ((label, _), estimate) in zip(requests, estimates)
        if estimate.cost_usd > float(guards["max_auto_cost_usd"])
        or estimate.billable_bytes > int(guards["max_auto_billable_bytes"])
    ]
    if rejected:
        raise RuntimeError(f"Configured cost guard rejected: {', '.join(rejected)}")
    for (label, _), estimate in zip(requests, estimates):
        path = download_request(estimate, execute=True)
        print(f"{label}: {path.name}")


if __name__ == "__main__":
    main()
