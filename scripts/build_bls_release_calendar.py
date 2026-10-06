"""Official BLS release clocks for every scheduled release, 2015 to the current year.

Generalizes ``build_extended_cpi_calendar.py`` (which keeps only CPI rows): the
yearly BLS schedule pages list every release with its date and Eastern time.
The output is used to add Employment Situation and PPI windows to the macro arm
and to screen 8:30 a.m. control days. It contains no market data.
"""
from __future__ import annotations

import argparse
import html
import re
import time
from datetime import date, datetime
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
TAG = re.compile(r"<[^>]+>")
FAMILIES = (
    ("Employment Situation", "employment_situation"),
    ("Consumer Price Index", "cpi"),
    ("Producer Price Index", "ppi"),
    ("Real Earnings", "real_earnings"),
    ("U.S. Import and Export Price Indexes", "import_export_prices"),
    ("Productivity and Costs", "productivity_costs"),
    ("Employment Cost Index", "employment_cost_index"),
    ("Job Openings and Labor Turnover", "jolts"),
)


def _text(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).replace("\xa0", " ").split())


def release_family(name: str) -> str:
    lowered = name.lower()
    for prefix, label in FAMILIES:
        if lowered.startswith(prefix.lower()):
            return label
    return "other_bls"


def fetch_year(year: int, timeout: int = 45) -> list[dict[str, object]]:
    url = f"https://www.bls.gov/schedule/{year}/home.htm"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 research contact example@example.com", "Accept": "text/html"},
        timeout=timeout,
    )
    response.raise_for_status()
    rows = []
    for date_html, time_html, description_html in ROW.findall(response.text):
        name, date_text, time_text = _text(description_html), _text(date_html), _text(time_html)
        try:
            local = datetime.strptime(f"{date_text} {time_text}", "%A, %B %d, %Y %I:%M %p")
        except ValueError:
            continue      # rows without a clock time are not scheduled releases
        local = local.replace(tzinfo=ZoneInfo("America/New_York"))
        rows.append({
            "release_date": local.date().isoformat(),
            "release_time_et": local.strftime("%H:%M"),
            "scheduled_time_utc": local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "release_name": name,
            "release_family": release_family(name),
            "reference_period": name.split(" for ", 1)[1] if " for " in name else "",
            "authoritative_source_url": url,
        })
    if not rows:
        raise RuntimeError(f"No release rows parsed from {url}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()
    rows = []
    for year in range(args.start_year, args.end_year + 1):
        found = fetch_year(year)
        print(f"{year}: {len(found)} scheduled releases", flush=True)
        rows.extend(found)
        time.sleep(1.0)
    data = pd.DataFrame(rows).drop_duplicates(["scheduled_time_utc", "release_name"])
    data = data.sort_values(["scheduled_time_utc", "release_name"]).reset_index(drop=True)
    data["calendar_retrieved_utc"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    output = PROJECT_ROOT / "data" / "events" / "bls_release_calendar_2015_2026.csv"
    data.to_csv(output, index=False)
    print(data.groupby("release_family").size().to_string())
    print(f"Wrote {len(data)} rows to {output}")


if __name__ == "__main__":
    main()
