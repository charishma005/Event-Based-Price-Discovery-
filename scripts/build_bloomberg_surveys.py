"""Parse the Bloomberg economist-survey export into one tidy table.

The workbook ``data/raw/bloomberg/bbg_eco.xlsx`` holds one sheet per ECO ticker
in the BDH layout: a ticker in A1, then from row 3 one line per release with
period end, release date (yyyymmdd), an empty release-time column, survey
median, average, high, low, number of forecasters, actual as first released,
first revision and the revised series. The workbook is licensed data and stays
local; so does the parquet written here (``data/processed/`` is git-ignored).

Run: python -m scripts.build_bloomberg_surveys
"""
from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT

WORKBOOK = PROJECT_ROOT / "data" / "raw" / "bloomberg" / "bbg_eco.xlsx"
OUTPUT = PROJECT_ROOT / "data" / "processed" / "bloomberg_surveys.parquet"
COLUMNS = ["period_end", "release_date", "release_time", "survey_median", "survey_average",
           "survey_high", "survey_low", "survey_n", "actual_release", "first_revision", "revised_value"]
RELEASE_OF_TICKER = {
    "CPI CHNG Index": "cpi", "CPUPXCHG Index": "cpi", "CPI YOY Index": "cpi", "CPUPXYOY Index": "cpi",
    "FDIDFDMO Index": "ppi", "FDIDSGMO Index": "ppi", "FDIUFDYO Index": "ppi",
    "NFP TCH Index": "employment_situation", "NFP PCH Index": "employment_situation",
    "USURTOT Index": "employment_situation", "AHE MOM% Index": "employment_situation",
    "RSTAMOM Index": "retail_sales", "RSTAXMOM Index": "retail_sales",
    "INJCJC Index": "jobless_claims", "NHSPSTOT Index": "housing_starts",
}


def _excel_date(value):
    # Sheets store the period end either as a datetime or as an Excel serial number.
    if isinstance(value, (int, float)):
        return pd.Timestamp("1899-12-30") + pd.to_timedelta(float(value), unit="D")
    return pd.Timestamp(value)


def read_sheet(workbook: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    raw = workbook.parse(sheet, header=None)
    ticker = str(raw.iat[0, 0]).strip()
    frame = raw.iloc[2:, : len(COLUMNS)].copy()
    frame.columns = COLUMNS
    frame = frame.dropna(subset=["period_end"])
    frame["period_end"] = frame["period_end"].map(_excel_date)
    frame["release_date"] = pd.to_datetime(
        frame["release_date"].astype("Float64").astype("Int64").astype(str), format="%Y%m%d", errors="coerce"
    )
    for column in COLUMNS[3:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.insert(0, "release", RELEASE_OF_TICKER.get(ticker, "other"))
    frame.insert(0, "ticker", ticker)
    return frame.drop(columns="release_time")


def build() -> pd.DataFrame:
    workbook = pd.ExcelFile(WORKBOOK)
    table = pd.concat([read_sheet(workbook, sheet) for sheet in workbook.sheet_names], ignore_index=True)
    # The same ticker was exported twice; keep one copy per ticker and period.
    table = table.drop_duplicates(subset=["ticker", "period_end"]).sort_values(["ticker", "period_end"])
    table["survey_range"] = table["survey_high"] - table["survey_low"]
    table["surprise"] = table["actual_release"] - table["survey_median"]
    return table.reset_index(drop=True)


def main() -> None:
    table = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUTPUT, index=False)
    registry = pd.read_csv(PROJECT_ROOT / "data" / "events" / "event_registry.csv", keep_default_na=False)
    registry = registry.loc[registry["family"].eq("macro")]
    registry_dates = pd.to_datetime(registry["event_date"])
    usable = table.loc[table["survey_median"].notna() & table["actual_release"].notna()]
    summary = usable.groupby(["release", "ticker"]).agg(
        releases=("release_date", "size"), first=("release_date", "min"), last=("release_date", "max"),
        median_forecasters=("survey_n", "median"),
    )
    # Registry mornings of the same release type that have a usable survey row.
    summary["mornings_in_registry"] = [
        int(registry_dates[registry["event_types"].str.contains(release)]
            .isin(usable.loc[usable["ticker"].eq(ticker), "release_date"]).sum())
        for release, ticker in summary.index
    ]
    with pd.option_context("display.width", 200):
        print(summary.to_string())
    print(f"\nWrote {OUTPUT.relative_to(PROJECT_ROOT)}: {len(table)} rows, {table['ticker'].nunique()} tickers")


if __name__ == "__main__":
    main()
