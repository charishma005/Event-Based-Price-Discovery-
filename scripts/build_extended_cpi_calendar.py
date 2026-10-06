"""Build an official BLS CPI release calendar for 2015 through the current year."""
from __future__ import annotations

import argparse
import html
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.utils.config import PROJECT_ROOT


ROW = re.compile(
    r'<tr[^>]*class="release-list-(?:odd|even)-row"[^>]*>\s*'
    r'<td[^>]*class="date-cell"[^>]*>.*?<p>(.*?)</p>.*?</td>\s*'
    r'<td[^>]*class="time-cell"[^>]*>.*?<p>(.*?)</p>.*?</td>\s*'
    r'<td[^>]*class="desc-cell"[^>]*>.*?<p>(.*?)</p>.*?</td>\s*</tr>',
    re.I | re.S,
)
TAG = re.compile(r'<[^>]+>')


def text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).replace("\xa0", " ").split())


def fetch_year(year: int, timeout: int = 45) -> list[dict[str, object]]:
    url = f"https://www.bls.gov/schedule/{year}/home.htm"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 research contact example@example.com", "Accept": "text/html"},
        timeout=timeout,
    )
    response.raise_for_status()
    rows: list[dict[str, object]] = []
    for date_html, time_html, description_html in ROW.findall(response.text):
        description = text(description_html)
        if not description.lower().startswith("consumer price index"):
            continue
        date_text, time_text = text(date_html), text(time_html)
        local = datetime.strptime(f"{date_text} {time_text}", "%A, %B %d, %Y %I:%M %p")
        local = local.replace(tzinfo=ZoneInfo("America/New_York"))
        reference = description.split(" for ", 1)[1] if " for " in description else None
        rows.append(
            {
                "event_id": f"cpi_{local:%Y%m%d}",
                "event_date": local.date().isoformat(),
                "scheduled_time_et": local.isoformat(),
                "scheduled_time_utc": local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
                "reference_period": reference,
                "source_agency": "BLS",
                "event_name": description,
                "representation_class": "scalar_numeric",
                "concurrent_release": "Real Earnings",
                "authoritative_source_url": url,
                "calendar_retrieved_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            }
        )
    if not rows:
        raise RuntimeError(f"No CPI rows parsed from {url}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()
    rows = []
    for year in range(args.start_year, args.end_year + 1):
        found = fetch_year(year)
        print(f"{year}: {len(found)} CPI releases")
        rows.extend(found)
    data = pd.DataFrame(rows).sort_values("scheduled_time_utc").drop_duplicates("event_id")
    data["release_status"] = pd.to_datetime(data.scheduled_time_utc, utc=True).le(pd.Timestamp.now(tz="UTC")).map(
        {True: "released", False: "scheduled_future"}
    )
    data["request_start_utc"] = (
        pd.to_datetime(data.scheduled_time_utc, utc=True) - pd.Timedelta(minutes=5)
    ).map(lambda value: value.isoformat())
    data["request_end_utc"] = (
        pd.to_datetime(data.scheduled_time_utc, utc=True) + pd.Timedelta(minutes=6)
    ).map(lambda value: value.isoformat())
    output = PROJECT_ROOT / "data/events/cpi_calendar_2015_2026.csv"
    data.to_csv(output, index=False)
    data.to_parquet(output.with_suffix(".parquet"), index=False)
    print(f"Wrote {len(data)} rows to {output}; released={data.release_status.eq('released').sum()}")


if __name__ == "__main__":
    main()
