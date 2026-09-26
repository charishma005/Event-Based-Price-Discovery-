import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml


def test_historical_event_dates_are_distinct_and_in_sample() -> None:
    config = load_yaml(PROJECT_ROOT / "config" / "historical_event_dates.yaml")
    start = pd.Timestamp(config["sample_start"])
    end = pd.Timestamp(config["sample_end"])
    classes = config["event_classes"]
    fomc = pd.DatetimeIndex(pd.to_datetime(classes["fomc_statement"]["dates"]))
    cpi = pd.DatetimeIndex(pd.to_datetime(classes["cpi_release"]["dates"]))

    assert len(fomc) == 9
    assert len(cpi) == 13
    assert not fomc.has_duplicates
    assert not cpi.has_duplicates
    assert fomc.intersection(cpi).empty
    assert min(fomc.min(), cpi.min()) >= start
    assert max(fomc.max(), cpi.max()) <= end
    assert classes["fomc_statement"]["source_url"].startswith("https://www.federalreserve.gov/")
    assert classes["cpi_release"]["source_url"].startswith("https://www.bls.gov/")
