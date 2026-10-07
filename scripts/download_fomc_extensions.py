"""Extend statement-only FOMC windows to 40 minutes after the statement.

Meetings without a press conference (mostly 2015-2018) were downloaded only to
+15 minutes. This requests the same start to +40 minutes, matching the
press-conference meetings, as separate files; the original windows are untouched.

Run: python -m scripts.download_fomc_extensions --execute
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.data.databento_client import DatabentoRequest, download_request, estimate_request, print_summary
from src.utils.config import PROJECT_ROOT, load_yaml

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
EXTENDED_END = pd.Timedelta(minutes=40)


def extension_windows(config_name: str = "fomc_sample_2015_2026.yaml") -> list[dict]:
    """Statement-only meetings with request_end_utc moved to statement + 40 minutes."""
    windows = []
    for meeting in load_yaml(PROJECT_ROOT / "config" / config_name)["meetings"]:
        if "press_conference_time_utc" in meeting:
            continue
        end = pd.Timestamp(meeting["statement_time_utc"]) + EXTENDED_END
        windows.append({**meeting, "request_end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return windows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="Download; without it, only estimate")
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml")
    args = parser.parse_args()
    windows = extension_windows(args.config)
    total = 0.0
    for window in windows:
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema="mbp-1", symbols=INSTRUMENTS, stype_in="continuous",
            start=window["request_start_utc"], end=window["request_end_utc"],
        )
        estimate = estimate_request(request)
        total += estimate.cost_usd
        print(f"\n{window['label']} (extended)")
        print_summary(estimate)
        if args.execute:
            path = download_request(estimate, execute=True)
            print(f"{window['label']}: {path.name}")
    print(f"\n{len(windows)} extended windows, estimated ${total:,.2f}")


if __name__ == "__main__":
    main()
