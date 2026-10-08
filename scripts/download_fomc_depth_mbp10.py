"""Download full-book (MBP-10) windows around every FOMC statement.

For each meeting in the sample config, fetch 10-level depth for ES.v.0, NQ.v.0
and ZN.v.0 from 30 minutes before to 90 minutes after the statement. All three
instruments go in one request (stype_in=continuous), matching the existing
raw-file layout. MBP-10 contains levels 1-10, so the same files serve level-2,
level-5 and level-10 depth analyses.

Downloads are real and billable. Files are cached by request hash, so re-running
skips meetings already on disk. Requires --execute; run with the venv python and
DATABENTO_API_KEY set (e.g. via .env).

  set -a; . ./.env; set +a
  .venv/bin/python -m scripts.download_fomc_depth_mbp10 --execute
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.data.databento_client import (
    DatabentoRequest,
    download_request,
    estimate_request,
    human_size,
)
from src.utils.config import PROJECT_ROOT, load_yaml, settings

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
PRE_MINUTES = 30
POST_MINUTES = 90
SCHEMA = "mbp-10"


def meeting_window(meeting: dict[str, object]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Statement time minus 30 minutes to plus 90 minutes."""
    statement = pd.Timestamp(meeting["statement_time_utc"]).tz_convert("UTC")
    return (
        statement - pd.Timedelta(minutes=PRE_MINUTES),
        statement + pd.Timedelta(minutes=POST_MINUTES),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml", help="File under config/")
    parser.add_argument("--execute", action="store_true", help="Actually download (billable)")
    parser.add_argument("--meetings", nargs="*", help="Optional subset of meeting labels")
    args = parser.parse_args()

    meetings = load_yaml(PROJECT_ROOT / "config" / args.config)["meetings"]
    selected = set(args.meetings or [])
    if selected:
        meetings = [m for m in meetings if m["label"] in selected]

    guard_usd = float(settings()["cost_control"]["max_auto_cost_usd"])
    total = len(meetings)
    done = failed = 0
    total_bytes = 0
    for number, meeting in enumerate(meetings, start=1):
        label = meeting["label"]
        start, end = meeting_window(meeting)
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema=SCHEMA, symbols=INSTRUMENTS,
            stype_in="continuous", start=start, end=end,
        )
        print(f"[{number}/{total}] {label} {start} .. {end}", flush=True)
        try:
            estimate = estimate_request(request)
            if estimate.available:
                print(f"  cached; skipped", flush=True)
                done += 1
                continue
            if estimate.cost_usd > guard_usd:
                print(
                    f"  cost ${estimate.cost_usd:.4f} exceeds per-request guard "
                    f"${guard_usd:.2f}; skipped (raise max_auto_cost_usd to fetch)",
                    flush=True,
                )
                failed += 1
                continue
            print(f"  {human_size(estimate.billable_bytes)}  ${estimate.cost_usd:.4f}", flush=True)
            if args.execute:
                path = download_request(
                    estimate, execute=True, quiet=True, size_guard_bytes=8 * 1024 ** 3
                )
                print(f"  saved {path.name}", flush=True)
                total_bytes += estimate.billable_bytes
                done += 1
            else:
                done += 1
        except Exception as exc:  # keep going so one bad window doesn't stop the batch
            print(f"  ERROR: {exc}", flush=True)
            failed += 1

    verb = "downloaded" if args.execute else "estimated"
    print(
        f"\n{done} {verb}, {failed} failed/skipped"
        + (f", {human_size(total_bytes)} fetched" if args.execute else " (estimate only; add --execute)"),
        flush=True,
    )


if __name__ == "__main__":
    main()
