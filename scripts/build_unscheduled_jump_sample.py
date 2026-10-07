"""Unscheduled arrivals found from the price record, with several control days each.

Professor's step 8: the unscheduled test rested on five hand-picked corporate
announcements with one control each. News-wire clocks are not reliable enough
to build a large sample (several vendor timestamps were hours off), so this
script identifies arrivals from prices instead and leaves out every time of day
at which news is scheduled.

1. One-minute bars for ES, NQ and ZN, 2015-2026 (``ohlcv-1m``).
2. Jump statistic per minute, in the spirit of Lee and Mykland (2008): the
   return divided by the local volatility of the previous 60 minutes, with
   returns first scaled by a minute-of-day factor (median absolute return for
   that minute in the same year). Local variance is the realized variance of
   that hour without its largest minute, so an earlier jump does not hide a
   later one; bipower variation is not used because ZN's coarse tick leaves
   many zero returns. At least 55 of the 60 minutes must have traded, which
   also removes reopenings after a trading halt.
3. A candidate needs |statistic| >= JUMP_THRESHOLD and a move of at least
   MIN_MOVE_BP in ES or ZN. Holiday and half-day sessions are dropped: ES
   volume from 9:30 to 4:00 must be at least half its trailing 20-day median.
4. Scheduled news is removed by construction:
   - only minutes that are not on a release clock (not within three minutes of
     :00, :15, :30 or :45);
   - not 8:30-9:00 or 10:00-10:30 (data releases and their aftermath), not
     9:25-9:45 (cash open), not 1:00-1:15 p.m. (auction results), not the last
     ten minutes of the session;
   - not from 2:00 p.m. on FOMC statement days or within 30 minutes of the
     minutes or the Beige Book; not within 45 minutes after a BLS release;
   - days the vendor flags as degraded are dropped.
   What cannot be screened: remarks inside a scheduled live speech or a foreign
   central bank press conference. Those arrive at times nobody knows in
   advance, which is the property the test needs, but the afternoon may be
   known to be eventful.
5. The first candidate in any 60 minutes is the arrival; later ones are its aftermath.
6. Controls: the same weekday one and two weeks before and after (up to
   four), at the arrival's UTC time, kept when the day traded normally, is not
   an FOMC afternoon and has no candidate of its own within 45 minutes. The
   same UTC time is the same New York clock except across a daylight-saving
   change, where the control is one hour off (19 of 373 windows, 2 of the 19
   for Federal Reserve announcements); scripts.analyze_unscheduled_arrivals
   repeats the test without those.

The thresholds were fixed from the number of candidates they produce, before
any depth data for these windows existed.

Also written: the six unscheduled Federal Reserve announcements since 2015 that
fall in trading hours (USMPD), with controls built the same way.
"""
from __future__ import annotations

import argparse
import json
import warnings

import numpy as np
import pandas as pd

from src.data.raw_index import build_raw_index
from src.utils.config import PROJECT_ROOT

warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", category=RuntimeWarning)
EVENTS = PROJECT_ROOT / "data" / "events"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
DETECTORS = ("ES.v.0", "ZN.v.0")
MIN_MOVE_BP = {"ES.v.0": 12.0, "NQ.v.0": 15.0, "ZN.v.0": 5.0}
JUMP_THRESHOLD = 8.0
VOLATILITY_MINUTES = 60
MIN_TRADED_MINUTES = 55
THIN_DAY_SHARE = 0.5
CLOCK_GUARD_MINUTES = 3
ARRIVAL_GAP_MINUTES = 60
PRE_MINUTES, POST_MINUTES = 30, 16
CONTROL_OFFSETS_DAYS = (-14, -7, 7, 14)
BLOCKED_WINDOWS_ET = (("08:30", "09:00"), ("09:25", "09:45"), ("10:00", "10:30"), ("13:00", "13:15"), ("15:50", "16:00"))
SESSION_ET = ("08:00", "16:00")
NEW_YORK = "America/New_York"


def load_minute_bars() -> pd.DataFrame:
    """Minute closes from 6:00 a.m. to 4:30 p.m. New York time (the hours the scan needs)."""
    import databento as db

    index = build_raw_index()
    files = index.loc[index["schema"].eq("ohlcv-1m"), "path"]
    frames = []
    for path in files:
        store = db.DBNStore.from_file(path)
        records = store.to_ndarray()
        stamp = records["ts_event"].astype("int64")
        local = pd.DatetimeIndex(stamp, tz="UTC").tz_convert(NEW_YORK)
        minute = (local.hour * 60 + local.minute).to_numpy()
        day = (local.year * 10000 + local.month * 100 + local.day).to_numpy()
        wanted = (minute >= 6 * 60) & (minute < 16 * 60 + 30)
        for symbol, intervals in store.metadata.mappings.items():
            for interval in intervals:
                first = pd.Timestamp(interval["start_date"], tz="UTC").value
                last = pd.Timestamp(interval["end_date"], tz="UTC").value
                keep = wanted & (records["instrument_id"] == int(interval["symbol"])) & (stamp >= first) & (stamp < last)
                if keep.any():
                    frames.append(pd.DataFrame({
                        "instrument": symbol, "contract_id": np.int32(int(interval["symbol"])), "ts": stamp[keep],
                        "close": records["close"][keep] * 1e-9, "volume": records["volume"][keep].astype("int32"),
                        "minute_of_day": minute[keep].astype("int16"), "day": day[keep].astype("int32")}))
        del records, stamp, local
    bars = pd.concat(frames, ignore_index=True)
    bars["instrument"] = bars["instrument"].astype("category")
    return bars.drop_duplicates(["instrument", "ts"]).sort_values(["instrument", "ts"]).reset_index(drop=True)


def jump_statistics(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per instrument: minute return and its jump statistic, indexed by bar time (ns)."""
    out = {}
    for instrument in INSTRUMENTS:
        part = bars.loc[bars["instrument"].eq(instrument)]
        consecutive = (part["ts"].diff() == 60 * 1_000_000_000) & (part["contract_id"].diff() == 0)
        returns = (1e4 * np.log(part["close"]).diff()).where(consecutive)
        absolute = returns.abs()
        year = part["day"] // 10000
        scale = absolute.groupby([year, part["minute_of_day"]]).transform("median")
        floor = absolute.groupby(year).transform("median")
        standardized = returns / np.maximum(scale, 0.5 * floor)
        # Realized variance of the previous hour without its largest minute; the current minute is excluded.
        squared = (standardized ** 2).shift(1)
        window = squared.rolling(VOLATILITY_MINUTES, min_periods=MIN_TRADED_MINUTES)
        local_variance = (window.sum() - window.max()) / (window.count() - 1)
        # The hour must be an unbroken run of minutes on the same contract.
        span = part["ts"] - part["ts"].shift(MIN_TRADED_MINUTES)
        unbroken = span <= VOLATILITY_MINUTES * 60 * 1_000_000_000
        statistic = (standardized / np.sqrt(local_variance)).where(unbroken & (local_variance > 0))
        root = instrument.split(".")[0]
        out[instrument] = pd.DataFrame({
            f"return_bp_{root}": returns.astype("float32").to_numpy(),
            f"jump_statistic_{root}": statistic.astype("float32").to_numpy(),
            f"volume_{root}": part["volume"].to_numpy(),
            "minute_of_day": part["minute_of_day"].to_numpy(), "day": part["day"].to_numpy()}, index=part["ts"].to_numpy())
    return out


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _day(text: str) -> int:
    return int(text.replace("-", ""))


def _blocked_days() -> tuple[set[int], set[int], dict[int, int], set[int]]:
    fed = pd.read_csv(EVENTS / "fed_release_calendar_2015_2026.csv")
    fomc_days = {_day(text) for text in fed.loc[fed["release"].eq("fomc_statement"), "release_date"]}
    other_fed = {_day(row.release_date): _minutes(row.release_time_et) for row in fed.itertuples() if row.release != "fomc_statement"}
    bls = pd.read_csv(EVENTS / "bls_release_calendar_2015_2026.csv")
    bls_clocks = {_day(row.release_date) * 10000 + _minutes(row.release_time_et) for row in bls.itertuples()}
    conditions = json.loads((PROJECT_ROOT / "reports" / "glbx_dataset_conditions_2015_2026.json").read_text())["conditions"]
    degraded = {_day(item["date"]) for item in conditions if item.get("condition") != "available"}
    return fomc_days, degraded, other_fed, bls_clocks


def off_clock(minute_of_day: pd.Series) -> pd.Series:
    within = minute_of_day % 15
    return (within > CLOCK_GUARD_MINUTES) & (within < 15 - CLOCK_GUARD_MINUTES)


def eligible_minutes(wide: pd.DataFrame) -> pd.Series:
    """Minutes at which nothing is scheduled (see the module docstring)."""
    fomc_days, degraded, other_fed, bls_clocks = _blocked_days()
    minute, day = wide["minute_of_day"].astype("int64"), wide["day"].astype("int64")
    ok = off_clock(minute)
    for first, last in BLOCKED_WINDOWS_ET:
        ok &= ~minute.between(_minutes(first), _minutes(last) - 1)
    ok &= ~(day.isin(fomc_days) & minute.ge(_minutes("14:00")))
    ok &= ~day.isin(degraded)
    released = day.map(other_fed)
    ok &= ~(released.notna() & (minute - released).between(0, 30))
    for offset in range(0, 46):
        ok &= ~(day * 10000 + minute - offset).isin(bls_clocks)
    return ok


def find_arrivals(stats: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    session = (_minutes(SESSION_ET[0]), _minutes(SESSION_ET[1]) - 1)
    pieces = []
    for instrument, frame in stats.items():
        inside = frame.loc[frame["minute_of_day"].between(*session)]
        pieces.append(inside if not pieces else inside.drop(columns=["minute_of_day", "day"]))
    wide = pd.concat(pieces, axis=1, join="outer")
    wide = wide.loc[wide["day"].notna()]
    # Holiday and half-day sessions: ES volume from 9:30 to 4:00 against its trailing 20-day median.
    cash = wide.loc[wide["minute_of_day"].between(_minutes("09:30"), _minutes("16:00") - 1)]
    daily = cash.groupby("day")["volume_ES"].sum().sort_index()
    normal = daily.shift(1).rolling(20, min_periods=5).median()
    thin = set(daily.index[daily < THIN_DAY_SHARE * normal])
    wide["thin_day"] = wide["day"].isin(thin)
    wide["eligible"] = eligible_minutes(wide) & ~wide["thin_day"]
    flags = []
    for instrument in DETECTORS:
        root = instrument.split(".")[0]
        flags.append((wide[f"jump_statistic_{root}"].abs() >= JUMP_THRESHOLD) & (wide[f"return_bp_{root}"].abs() >= MIN_MOVE_BP[instrument]))
    wide["candidate_any_time"] = np.logical_or.reduce(flags)
    wide["candidate"] = wide["candidate_any_time"] & wide["eligible"]
    wide["detected_in"] = np.select([flags[0] & flags[1], flags[0], flags[1]], ["ES and ZN", "ES", "ZN"], default="")
    candidates = wide.loc[wide["candidate"]]
    # First candidate in any hour; a large move in the previous hour at any clock also disqualifies.
    every = wide.index[wide["candidate_any_time"]].to_numpy()
    gap = ARRIVAL_GAP_MINUTES * 60 * 1_000_000_000
    keep = [not np.any((every < stamp) & (every >= stamp - gap)) for stamp in candidates.index.to_numpy()]
    arrivals = candidates.loc[keep].copy()
    arrivals.insert(0, "time_utc", pd.to_datetime(arrivals.index, utc=True))
    arrivals = arrivals.reset_index(drop=True)
    arrivals["event_id"] = "jump_" + arrivals["time_utc"].dt.tz_convert(NEW_YORK).dt.strftime("%Y%m%d_%H%M")
    arrivals["date_et"] = arrivals["time_utc"].dt.tz_convert(NEW_YORK).dt.strftime("%Y-%m-%d")
    return arrivals, wide


def controls_for(arrivals: pd.DataFrame, wide: pd.DataFrame, family: str) -> pd.DataFrame:
    fomc_days, degraded, _, _ = _blocked_days()
    candidate_times = wide.index[wide["candidate_any_time"]].to_numpy()
    thin_days = set(wide.loc[wide["thin_day"], "day"].astype(int))
    traded = wide.index.to_numpy()
    minute_ns = 60 * 1_000_000_000
    rows = []
    for event in arrivals.itertuples(index=False):
        local = event.time_utc.tz_convert(NEW_YORK)
        for offset in CONTROL_OFFSETS_DAYS:
            naive = (local + pd.Timedelta(days=offset)).tz_localize(None)
            try:
                control_local = pd.Timestamp(naive).tz_localize(NEW_YORK)
            except Exception:                      # clock that does not exist or is ambiguous on a DST change
                continue
            control = control_local.tz_convert("UTC")
            day = control_local.year * 10000 + control_local.month * 100 + control_local.day
            first, last = control.value - PRE_MINUTES * minute_ns, control.value + (POST_MINUTES - 1) * minute_ns
            inside = traded[(traded >= max(first, pd.Timestamp(f"{control_local:%Y-%m-%d} 08:00", tz=NEW_YORK).value)) & (traded <= last)]
            expected = (last - max(first, pd.Timestamp(f"{control_local:%Y-%m-%d} 08:00", tz=NEW_YORK).value)) // minute_ns + 1
            near = candidate_times[(candidate_times >= control.value - 45 * minute_ns) & (candidate_times <= control.value + 45 * minute_ns)]
            if len(inside) < 0.95 * expected or len(near) or day in degraded or day in thin_days:
                continue
            if day in fomc_days and control_local.hour >= 14:
                continue
            rows.append({"event_id": f"{event.event_id}_control_{offset:+d}d", "family": f"{family}_control",
                         "matched_event": event.event_id, "cluster": event.event_id, "event_time_utc": control,
                         "is_control": True, "control_offset_days": offset})
    return pd.DataFrame(rows)


def unscheduled_fed() -> pd.DataFrame:
    """Unscheduled Federal Reserve announcements in trading hours since 2015 (USMPD monetary events)."""
    path = PROJECT_ROOT / "data" / "external" / "usmpd" / "USMPD.xlsx"
    events = pd.read_excel(path, sheet_name="Monetary Events")
    events = events.loc[(events["Unscheduled"] == 1) & (pd.to_datetime(events["date_time"]) >= "2015-01-01")]
    local = pd.to_datetime(events["date_time"]).dt.tz_localize(NEW_YORK)
    open_hours = local.dt.dayofweek.lt(5) & local.dt.hour.between(8, 15)
    local = local.loc[open_hours]
    return pd.DataFrame({"time_utc": local.dt.tz_convert("UTC"),
                         "event_id": "fed_unscheduled_" + local.dt.strftime("%Y%m%d_%H%M")}).reset_index(drop=True)


def registry_rows(arrivals: pd.DataFrame, controls: pd.DataFrame, family: str) -> pd.DataFrame:
    events = pd.DataFrame({"event_id": arrivals["event_id"], "family": family, "matched_event": arrivals["event_id"],
                           "cluster": arrivals["event_id"], "event_time_utc": arrivals["time_utc"], "is_control": False,
                           "control_offset_days": 0})
    rows = pd.concat([events, controls], ignore_index=True)
    rows["request_start_utc"] = rows["event_time_utc"] - pd.Timedelta(minutes=PRE_MINUTES)
    rows["request_end_utc"] = rows["event_time_utc"] + pd.Timedelta(minutes=POST_MINUTES)
    rows["sample"] = "unscheduled"
    rows["dataset_condition"] = "available"
    rows["quality_flag"] = ""
    rows["event_date"] = rows["event_time_utc"].dt.tz_convert(NEW_YORK).dt.strftime("%Y-%m-%d")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--counts-only", action="store_true", help="Print candidate counts and stop")
    args = parser.parse_args()
    bars = load_minute_bars()
    stats = jump_statistics(bars)
    arrivals, wide = find_arrivals(stats)
    by_year = arrivals.groupby(arrivals["time_utc"].dt.year).size()
    print(f"{len(bars):,} minute bars (6:00 a.m. to 4:30 p.m.); {int(wide['candidate_any_time'].sum())} candidate minutes at any clock, "
          f"{int(wide['candidate'].sum())} off the release clocks, {len(arrivals)} arrivals")
    print("arrivals by year:", by_year.to_dict())
    print("detected in:", arrivals["detected_in"].value_counts().to_dict())
    if args.counts_only:
        return
    controls = controls_for(arrivals, wide, "unscheduled_jump")
    fed = unscheduled_fed()
    fed_controls = controls_for(fed, wide, "unscheduled_fed")
    registry = pd.concat([registry_rows(arrivals, controls, "unscheduled_jump"), registry_rows(fed, fed_controls, "unscheduled_fed")],
                         ignore_index=True)
    registry = registry.sort_values(["event_time_utc", "event_id"]).reset_index(drop=True)
    registry.to_csv(EVENTS / "unscheduled_windows.csv", index=False)
    columns = ["event_id", "time_utc", "date_et", "minute_of_day", "detected_in", "return_bp_ES", "return_bp_NQ", "return_bp_ZN",
               "jump_statistic_ES", "jump_statistic_NQ", "jump_statistic_ZN", "volume_ES", "volume_ZN"]
    detail = arrivals[columns].copy()
    detail["clock_et"] = detail["time_utc"].dt.tz_convert(NEW_YORK).dt.strftime("%H:%M")
    detail["controls"] = detail["event_id"].map(controls.groupby("matched_event").size()).fillna(0).astype(int)
    detail.to_csv(EVENTS / "unscheduled_jump_events.csv", index=False)
    print(f"controls per arrival: {detail['controls'].value_counts().sort_index().to_dict()}; "
          f"unscheduled Fed announcements: {len(fed)} with {len(fed_controls)} controls")
    print(f"registry rows: {len(registry)} -> data/events/unscheduled_windows.csv")
    with pd.option_context("display.width", 220, "display.max_rows", 300, "display.float_format", lambda v: f"{v:.1f}"):
        print(detail[["event_id", "clock_et", "detected_in", "return_bp_ES", "return_bp_NQ", "return_bp_ZN", "jump_statistic_ES",
                      "jump_statistic_ZN", "controls"]].to_string(index=False))


if __name__ == "__main__":
    main()
