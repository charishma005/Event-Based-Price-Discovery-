"""Scheduled Federal Reserve 2:00 p.m. releases, used only to screen control days.

Sources
- FOMC statements and minutes: USMPD workbook already in data/external/usmpd.
- Beige Book: the Board's yearly Beige Book pages (publication dates; released 2:00 p.m. ET).
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date

import pandas as pd
import requests

from src.events.surprises import USMPD_DIR
from src.utils.config import PROJECT_ROOT

BEIGE_LINK = re.compile(r"beigebook(20\d{6})\.htm|BeigeBook_(20\d{6})\.pdf", re.I)


def beige_book_dates(start_year: int, end_year: int) -> list[str]:
    found: set[str] = set()
    headers = {"User-Agent": "Mozilla/5.0 research contact example@example.com", "Accept": "text/html"}
    urls = [f"https://www.federalreserve.gov/monetarypolicy/beigebook{year}.htm"
            for year in range(start_year, end_year + 1)]
    urls.append("https://www.federalreserve.gov/monetarypolicy/publications/beige-book-default.htm")
    for url in urls:
        response = requests.get(url, headers=headers, timeout=45)
        if response.status_code == 404:
            continue        # the current year lives on the default page only
        response.raise_for_status()
        for first, second in BEIGE_LINK.findall(response.text):
            stamp = first or second
            if start_year <= int(stamp[:4]) <= end_year:
                found.add(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}")
        time.sleep(0.5)
    return sorted(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()
    workbook = USMPD_DIR / "USMPD.xlsx"
    rows = []
    statements = pd.read_excel(workbook, "Statements", usecols=["Date", "date_time", "Unscheduled"])
    for item in statements.itertuples(index=False):
        rows.append({"release_date": item.Date.strftime("%Y-%m-%d"), "release_time_et": f"{item.date_time:%H:%M}",
                     "release": "fomc_statement_unscheduled" if item.Unscheduled else "fomc_statement",
                     "source": "USMPD"})
    minutes = pd.read_excel(workbook, "Minutes", usecols=["Date", "date_time"])
    for item in minutes.itertuples(index=False):
        rows.append({"release_date": item.Date.strftime("%Y-%m-%d"), "release_time_et": f"{item.date_time:%H:%M}",
                     "release": "fomc_minutes", "source": "USMPD"})
    for value in beige_book_dates(args.start_year, args.end_year):
        rows.append({"release_date": value, "release_time_et": "14:00", "release": "beige_book",
                     "source": "federalreserve.gov Beige Book pages"})
    data = pd.DataFrame(rows)
    data = data.loc[data["release_date"].between(f"{args.start_year}-01-01", f"{args.end_year}-12-31")]
    data = data.drop_duplicates().sort_values(["release_date", "release"]).reset_index(drop=True)
    output = PROJECT_ROOT / "data" / "events" / "fed_release_calendar_2015_2026.csv"
    data.to_csv(output, index=False)
    print(data.groupby([data["release_date"].str[:4], "release"]).size().unstack(fill_value=0).to_string())
    print(f"Wrote {len(data)} rows to {output}")


if __name__ == "__main__":
    main()
