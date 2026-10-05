"""Build matched 2:00 p.m.-style control windows for the 2015-2023 FOMC meetings.

Rule (same as config/fomc_placebos.yaml): same weekday and exact clock time as
the FOMC statement, one and two weeks before the meeting. A candidate is moved
one further week back if it is a US federal holiday or another FOMC meeting
date. Unlike the hand-screened 2024-2025 controls, other scheduled releases at
the clock time (Treasury statement, minutes, Beige Book) are NOT screened, so
every control carries the flag ``unscreened_for_other_scheduled_releases``.
"""

from __future__ import annotations

import argparse

import pandas as pd
import yaml
from pandas.tseries.holiday import USFederalHolidayCalendar

from src.utils.config import PROJECT_ROOT, load_yaml

PRE = pd.Timedelta(minutes=5)
POST = pd.Timedelta(minutes=10)


def build(source: str, end_date: str, offsets_weeks: tuple[int, ...]) -> list[dict]:
    meetings = load_yaml(PROJECT_ROOT / "config" / source)["meetings"]
    fomc_dates = {pd.Timestamp(m["meeting_date"]) for m in meetings}
    holidays = set(
        USFederalHolidayCalendar().holidays("2014-01-01", "2026-12-31")
    )
    placebos = []
    for meeting in meetings:
        if pd.Timestamp(meeting["meeting_date"]) > pd.Timestamp(end_date):
            continue
        statement = pd.Timestamp(meeting["statement_time_utc"]).tz_convert("America/New_York")
        used: set[pd.Timestamp] = set()
        for weeks in offsets_weeks:
            # Step in local wall-clock time so the Eastern clock survives DST changes.
            local = statement.tz_localize(None) - pd.Timedelta(weeks=weeks)
            while (
                local.normalize() in fomc_dates
                or local.normalize() in holidays
                or local in used
            ):
                local -= pd.Timedelta(weeks=1)
            used.add(local)
            candidate = local.tz_localize("America/New_York").tz_convert("UTC")
            placebos.append(
                {
                    "placebo_id": f"placebo_{candidate:%Y%m%d}_{meeting['label'][-8:]}",
                    "matched_meeting": meeting["label"],
                    "placebo_time_utc": candidate.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "request_start_utc": (candidate - PRE).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "request_end_utc": (candidate + POST).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "quality_flag": "unscreened_for_other_scheduled_releases",
                }
            )
    return placebos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="fomc_sample_2015_2026.yaml")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--weeks", type=int, nargs="+", default=[1, 2])
    parser.add_argument("--output", default="fomc_placebos_2015_2023.yaml")
    args = parser.parse_args()
    placebos = build(args.source, args.end, tuple(args.weeks))
    config = {
        "selection_rule": (
            "Same weekday and statement clock time, 1 and 2 weeks before each meeting; "
            "shifted a week earlier on federal holidays or FOMC dates. Other scheduled "
            "releases are not screened."
        ),
        "placebos": placebos,
    }
    out = PROJECT_ROOT / "config" / args.output
    out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(placebos)} placebo windows to {out}")


if __name__ == "__main__":
    main()
