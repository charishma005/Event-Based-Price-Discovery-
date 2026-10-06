"""Rule-based matched control days for the meetings and months that have none.

The 2024-2025 controls in ``fomc_placebos.yaml`` and ``macro_placebos.yaml`` were
chosen by hand and stay as they are. This script adds controls for every other
event using a rule that was fixed before any control-day market data existed:

FOMC (2:00 p.m. Eastern)
    One control a week before and one a week after the meeting, same weekday and
    clock. If a candidate is excluded, the same weekday two weeks away is tried
    once on that side. Excluded: FOMC statement days (scheduled or not), minutes
    and Beige Book days, the Monthly Treasury Statement day (eighth business day
    of the month, 2:00 p.m.), market holidays, shortened sessions and the last
    week of December.

Macro (8:30 a.m. Eastern)
    One control per calendar month, anchored on that month's CPI date: the same
    weekday one week later, else one week earlier, else two weeks later, else two
    weeks earlier. Excluded: every 8:30 a.m. release in the BLS calendar, every
    date in ``data/events/other_release_calendar_0830.csv`` when that file
    exists, Thursdays (weekly claims), holidays and shortened sessions.

The screen covers scheduled official releases only; unscheduled news cannot be
ruled out. ``quality_flag`` records which screen each control passed.
"""
from __future__ import annotations

import argparse

import pandas as pd
import yaml
from pandas.tseries.holiday import GoodFriday, USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

from src.utils.config import PROJECT_ROOT, load_yaml

EVENTS = PROJECT_ROOT / "data" / "events"
FIRST, LAST = "2014-12-01", "2027-01-31"


def market_closures() -> set[str]:
    """Full closures, shortened sessions and thin holiday sessions (dates as strings)."""
    federal = USFederalHolidayCalendar().holidays(FIRST, LAST)
    closed = {day.strftime("%Y-%m-%d") for day in federal}
    for year in range(2014, 2028):
        closed.add(GoodFriday.dates(f"{year}-01-01", f"{year}-12-31")[0].strftime("%Y-%m-%d"))
        thanksgiving = [d for d in pd.date_range(f"{year}-11-01", f"{year}-11-30") if d.dayofweek == 3][3]
        closed.add((thanksgiving - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))   # pre-holiday
        closed.add((thanksgiving + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))   # early close
        closed.add(f"{year}-07-03")
        for day in range(24, 32):
            closed.add(f"{year}-12-{day:02d}")
        closed.add(f"{year}-01-02")
    return closed


def treasury_statement_days() -> set[str]:
    """Monthly Treasury Statement: 2:00 p.m. on the eighth business day of each month."""
    business = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    days = set()
    for month in pd.date_range(FIRST, LAST, freq="MS"):
        first = month if (month + 0 * business) == month else month + business
        days.add((first + 7 * business).strftime("%Y-%m-%d"))
    return days


def _clock(day: pd.Timestamp, hour: int, minute: int) -> pd.Timestamp:
    local = pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=hour, minute=minute,
                         tz="America/New_York")
    return local.tz_convert("UTC")


def _entry(prefix: str, clock: pd.Timestamp, matched_key: str, matched: str, flag: str) -> dict[str, str]:
    local = clock.tz_convert("America/New_York")
    return {
        "placebo_id": f"{prefix}_{local:%Y%m%d_%H%M}",
        matched_key: matched,
        "placebo_time_utc": clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_start_utc": (clock - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_end_utc": (clock + pd.Timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quality_flag": flag,
    }


def fomc_controls() -> list[dict[str, str]]:
    fed = pd.read_csv(EVENTS / "fed_release_calendar_2015_2026.csv")
    excluded = set(fed["release_date"]) | treasury_statement_days() | market_closures()
    have = {item["matched_meeting"] for item in load_yaml(PROJECT_ROOT / "config" / "fomc_placebos.yaml")["placebos"]}
    meetings = load_yaml(PROJECT_ROOT / "config" / "fomc_sample_2015_2026.yaml")["meetings"]
    rows = []
    for meeting in meetings:
        if meeting["label"] in have:
            continue
        day = pd.Timestamp(meeting["meeting_date"])
        statement = pd.Timestamp(meeting["statement_time_utc"]).tz_convert("America/New_York")
        for direction in (-1, 1):
            for weeks in (1, 2):
                candidate = day + pd.Timedelta(days=7 * weeks * direction)
                if candidate.strftime("%Y-%m-%d") in excluded:
                    continue
                flag = "clean_rule_based_screen" if weeks == 1 else "clean_rule_based_screen_two_weeks"
                rows.append(_entry("placebo", _clock(candidate, statement.hour, statement.minute),
                                   "matched_meeting", meeting["label"], flag))
                break
    return rows


def macro_controls() -> list[dict[str, str]]:
    bls = pd.read_csv(EVENTS / "bls_release_calendar_2015_2026.csv")
    excluded = set(bls.loc[bls["release_time_et"].eq("08:30"), "release_date"]) | market_closures()
    other_path = EVENTS / "other_release_calendar_0830.csv"
    full_screen = other_path.exists()
    if full_screen:
        excluded |= set(pd.read_csv(other_path)["release_date"])
    flag = "no_scheduled_official_release_at_clock" if full_screen else "bls_and_claims_screen_only"
    have = {str(item["matched_month"]) for item in load_yaml(PROJECT_ROOT / "config" / "macro_placebos.yaml")["placebos"]}
    cpi = pd.read_csv(EVENTS / "cpi_calendar_2015_2026.csv")
    cpi = cpi.loc[cpi["release_status"].eq("released")]
    rows = []
    for item in cpi.itertuples(index=False):
        day = pd.Timestamp(item.event_date)
        month = day.strftime("%Y-%m")
        if month in have:
            continue
        for offset in (7, -7, 14, -14):
            candidate = day + pd.Timedelta(days=offset)
            if candidate.dayofweek == 3 or candidate.strftime("%Y-%m-%d") in excluded:
                continue
            if candidate.strftime("%Y-%m") != month and abs(offset) > 7:
                continue
            rows.append(_entry("macro_placebo", _clock(candidate, 8, 30), "matched_month", month, flag))
            break
    return rows


def _write(name: str, rows: list[dict[str, str]], rule: str) -> None:
    config = {"selection_rule": rule,
              "notes": "Generated by scripts/build_placebo_configs.py; see that module for the full rule.",
              "placebos": rows}
    (PROJECT_ROOT / "config" / name).write_text(yaml.safe_dump(config, sort_keys=False, width=1000), encoding="utf-8")
    flags = pd.Series([row["quality_flag"] for row in rows]).value_counts().to_dict()
    print(f"{name}: {len(rows)} controls {flags}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", choices=("fomc", "macro", "both"), default="both")
    args = parser.parse_args()
    if args.kind in ("fomc", "both"):
        _write("fomc_placebos_2015_2026.yaml", fomc_controls(),
               "Same weekday and 2:00 p.m. Eastern clock one week before and after each meeting; "
               "two weeks if excluded. Screened for FOMC statements, minutes, Beige Book, the Monthly "
               "Treasury Statement, holidays and shortened sessions.")
    if args.kind in ("macro", "both"):
        _write("macro_placebos_2015_2026.yaml", macro_controls(),
               "One 8:30 a.m. Eastern control per month anchored on the CPI date (plus or minus one "
               "week, then two). Screened for BLS releases at the clock, Thursday claims, holidays and "
               "shortened sessions; Census and BEA releases only when other_release_calendar_0830.csv exists.")


if __name__ == "__main__":
    main()
