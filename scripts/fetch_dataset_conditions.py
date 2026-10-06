"""Vendor data-quality condition for every GLBX.MDP3 date since 2015 (free metadata request).

Databento marks every dataset date as available, degraded, pending or missing.
``scripts.build_event_registry`` and ``scripts.build_unscheduled_jump_sample``
read this file to flag, and leave out, the days marked as degraded.

Output: ``reports/glbx_dataset_conditions_2015_2026.json``. The copy in the
repository was retrieved on 2026-10-05, before the Q1 freeze. The vendor can
revise a condition later, and a revised file would change the registry, so an
existing file is never replaced unless ``--force`` is given; use ``--output``
to write a second copy for comparison.
"""
from __future__ import annotations

import argparse
import json

from src.data.databento_client import historical_client
from src.utils.config import PROJECT_ROOT
from src.utils.io import utc_now_iso

DATASET = "GLBX.MDP3"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-date", default="2015-01-01")
    parser.add_argument("--end-date", default="2026-09-30")
    parser.add_argument("--output", default="glbx_dataset_conditions_2015_2026.json", help="File under reports/")
    parser.add_argument("--force", action="store_true", help="Replace an existing file")
    args = parser.parse_args()
    output = PROJECT_ROOT / "reports" / args.output
    if output.exists() and not args.force:
        raise SystemExit(f"{output.name} exists; pass --output for a second copy or --force to replace it.")
    conditions = historical_client().metadata.get_dataset_condition(
        dataset=DATASET, start_date=args.start_date, end_date=args.end_date)
    result = {"dataset": DATASET, "retrieved_utc": utc_now_iso(), "conditions": conditions}
    output.write_text(json.dumps(result, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in conditions:
        counts[row["condition"]] = counts.get(row["condition"], 0) + 1
    print(f"{len(conditions)} dates, {args.start_date} to {args.end_date}: {counts}")
    print(f"Saved {output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
