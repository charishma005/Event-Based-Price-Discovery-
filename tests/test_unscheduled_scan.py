import numpy as np
import pandas as pd

import scripts.build_unscheduled_jump_sample as scan


def _bars(day: str, jump_minute: str | None = None, jump_bp: float = 40.0) -> pd.DataFrame:
    """One quiet trading day of minute bars for the three contracts, with an optional jump in ES."""
    rng = np.random.default_rng(int(day.replace("-", "")) % 10_000)
    times = pd.date_range(f"{day} 06:00", f"{day} 16:29", freq="1min", tz=scan.NEW_YORK)
    frames = []
    for number, (symbol, price) in enumerate((("ES.v.0", 5000.0), ("NQ.v.0", 18000.0), ("ZN.v.0", 110.0))):
        returns = rng.normal(0, 1.0e-4, len(times))
        if jump_minute and symbol == "ES.v.0":
            returns[times.strftime("%H:%M") == jump_minute] += jump_bp * 1e-4
        frames.append(pd.DataFrame({
            "instrument": symbol, "contract_id": np.int32(number + 1), "ts": times.tz_convert("UTC").asi8,
            "close": price * np.exp(np.cumsum(returns)), "volume": np.int32(1000),
            "minute_of_day": (times.hour * 60 + times.minute).astype("int16"),
            "day": (times.year * 10000 + times.month * 100 + times.day).astype("int32")}))
    bars = pd.concat(frames, ignore_index=True)
    bars["instrument"] = bars["instrument"].astype("category")
    return bars


def test_release_clocks_are_never_eligible():
    minutes = pd.Series(range(8 * 60, 16 * 60))
    allowed = set(minutes[scan.off_clock(minutes)] % 15)
    assert allowed == set(range(4, 12))                       # four to eleven minutes past each quarter hour


def test_jump_off_the_clock_is_found_and_on_the_clock_is_not(monkeypatch):
    monkeypatch.setattr(scan, "_blocked_days", lambda: (set(), set(), {}, set()))
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-03-04", periods=8)]
    quiet = [_bars(day) for day in days[:-2]]
    off_clock_day = _bars(days[-2], jump_minute="11:37")
    on_clock_day = _bars(days[-1], jump_minute="10:00")
    stats = scan.jump_statistics(pd.concat([*quiet, off_clock_day, on_clock_day], ignore_index=True))
    arrivals, wide = scan.find_arrivals(stats)
    found = set(arrivals["event_id"])
    assert f"jump_{days[-2].replace('-', '')}_1137" in found
    assert not any(days[-1].replace("-", "") in name for name in found)
    assert int(wide["candidate_any_time"].sum()) >= 2         # the 10:00 jump is seen, then screened out


def test_second_jump_within_the_hour_is_aftermath(monkeypatch):
    monkeypatch.setattr(scan, "_blocked_days", lambda: (set(), set(), {}, set()))
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-03-04", periods=7)]
    frames = [_bars(day) for day in days[:-1]]
    last = _bars(days[-1], jump_minute="11:37")
    es = last["instrument"].eq("ES.v.0")
    local = pd.to_datetime(last.loc[es, "ts"], utc=True).dt.tz_convert(scan.NEW_YORK).dt.strftime("%H:%M")
    bump = np.where(local.to_numpy() >= "12:08", np.exp(-60e-4), 1.0)        # second jump 31 minutes later
    last.loc[es, "close"] = last.loc[es, "close"].to_numpy() * bump
    stats = scan.jump_statistics(pd.concat([*frames, last], ignore_index=True))
    arrivals, _ = scan.find_arrivals(stats)
    same_day = [name for name in arrivals["event_id"] if days[-1].replace("-", "") in name]
    assert same_day == [f"jump_{days[-1].replace('-', '')}_1137"]


def test_same_clock_windows_leave_out_controls_across_a_daylight_saving_change():
    from scripts.analyze_unscheduled_arrivals import same_clock_windows
    from src.utils.config import PROJECT_ROOT

    windows = pd.read_csv(PROJECT_ROOT / "data" / "events" / "unscheduled_windows.csv")
    kept = same_clock_windows()
    dropped = windows.loc[~windows["event_id"].isin(kept)]
    assert dropped["is_control"].all()                      # every arrival is kept
    assert dropped["family"].value_counts().to_dict() == {"unscheduled_jump_control": 19, "unscheduled_fed_control": 2}
    # 27 October 2015, 11:54 a.m. EDT: the controls one and two weeks later are in EST, at 10:54 a.m.
    assert {"jump_20151027_1154_control_+7d", "jump_20151027_1154_control_+14d"} <= set(dropped["event_id"])
    assert "jump_20151027_1154_control_-7d" in kept
