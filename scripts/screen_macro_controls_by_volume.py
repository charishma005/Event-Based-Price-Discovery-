"""Volume check on the macro control mornings (professor's step 5).

The 92 rule-based control mornings in ``config/macro_placebos_2015_2026.yaml``
are screened for BLS releases and Thursday jobless claims only; Census and BEA
release dates for 2015-2023 were not available when the rule was written. A
scheduled 8:30 a.m. release shows up in volume, so this script measures, for
every control morning, the volume of the 8:30 one-minute bar over the mean
volume of the ten bars before it (8:20-8:29), for ES, NQ and ZN.

``scripts.analyze_macro_extension`` reports the depth test twice: with all
control mornings, and without those where the ratio is at least
``VOLUME_SPIKE`` in ES or ZN.

Input: the one-minute bars (``ohlcv-1m``) used by the unscheduled scan.
Output: ``data/events/macro_control_volume_screen.csv``.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT

EVENTS = PROJECT_ROOT / "data" / "events"
OUTPUT = EVENTS / "macro_control_volume_screen.csv"
RELEASE_MINUTE = 8 * 60 + 30        # New York time
BASELINE_MINUTES = 10
VOLUME_SPIKE = 3.0                  # 8:30 bar over the mean of 8:20-8:29, ES or ZN
COLUMNS = {"ES.v.0": "es_volume_ratio_0830", "NQ.v.0": "nq_volume_ratio_0830", "ZN.v.0": "zn_volume_ratio_0830"}


def volume_ratios(bars: pd.DataFrame, days: list[int]) -> pd.DataFrame:
    """Volume at 8:30 over the mean of the ten minutes before, by day (yyyymmdd) and instrument.

    A minute without a bar counts as zero volume.
    """
    first = RELEASE_MINUTE - BASELINE_MINUTES
    part = bars.loc[bars["minute_of_day"].between(first, RELEASE_MINUTE) & bars["day"].isin(days)]
    volume = part.pivot_table(index=["day", "minute_of_day"], columns="instrument", values="volume",
                              aggfunc="sum", observed=True)
    grid = pd.MultiIndex.from_product([sorted(set(days)), range(first, RELEASE_MINUTE + 1)], names=["day", "minute_of_day"])
    volume = volume.reindex(grid).fillna(0.0)
    minute = volume.index.get_level_values("minute_of_day")
    at_release = volume.loc[minute == RELEASE_MINUTE].droplevel("minute_of_day")
    before = volume.loc[minute < RELEASE_MINUTE].groupby(level="day").mean()
    return (at_release / before).replace([np.inf, -np.inf], np.nan)


def flagged(screen: pd.DataFrame) -> pd.Series:
    """Control mornings with a volume spike at 8:30 in ES or ZN."""
    return screen[["es_volume_ratio_0830", "zn_volume_ratio_0830"]].max(axis=1) >= VOLUME_SPIKE


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    from scripts.build_unscheduled_jump_sample import load_minute_bars

    registry = pd.read_csv(EVENTS / "event_registry.csv")
    controls = registry.loc[registry["family"].eq("macro_control"), ["event_id", "event_date", "quality_flag"]].copy()
    days = pd.to_datetime(controls["event_date"]).dt.strftime("%Y%m%d").astype(int)
    ratios = volume_ratios(load_minute_bars(), days.tolist()).reindex(columns=list(COLUMNS))
    for instrument, column in COLUMNS.items():
        controls[column] = ratios[instrument].reindex(days.to_numpy()).to_numpy()
    controls.to_csv(OUTPUT, index=False)
    spike = flagged(controls)
    print(f"{len(controls)} control mornings, {int(spike.sum())} with 8:30 volume at least {VOLUME_SPIKE:g} times "
          f"the ten minutes before in ES or ZN")
    print(controls.loc[spike].groupby("quality_flag").size().to_string())
    print(f"written: {OUTPUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
