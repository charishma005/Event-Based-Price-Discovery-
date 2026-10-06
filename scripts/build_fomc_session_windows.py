"""Long afternoon windows around every FOMC statement and every matched 2:00 p.m. control.

The tick windows stop ten minutes into the press conference (or fifteen minutes
after a statement without one). Thirty-minute outcomes, the full press
conference and the depth-withdrawal strategy tests need the rest of the
afternoon. One-second BBO records are small enough to take 1:30 to 4:00 p.m.
Eastern for every meeting and control day; the trades schema adds signed flow
on meeting days.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.utils.config import PROJECT_ROOT

BEFORE, AFTER = pd.Timedelta(minutes=30), pd.Timedelta(minutes=120)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default="fomc_session_windows.csv")
    args = parser.parse_args()
    registry = pd.read_csv(
        PROJECT_ROOT / "data" / "events" / "event_registry.csv",
        parse_dates=["event_time_utc", "request_start_utc", "request_end_utc"], keep_default_na=False,
    )
    statements = registry.loc[registry["family"].eq("fomc") & registry["subevent"].eq("statement")]
    controls = registry.loc[registry["family"].eq("fomc_control")]
    press = registry.loc[registry["family"].eq("fomc") & registry["subevent"].eq("press_conference")]
    press_clock = press.set_index("cluster")["event_time_utc"]
    rows = pd.concat([statements, controls], ignore_index=True).copy()
    rows["press_conference_time_utc"] = rows["cluster"].map(press_clock).where(rows["family"].eq("fomc"))
    rows["request_start_utc"] = rows["event_time_utc"] - BEFORE
    rows["request_end_utc"] = rows["event_time_utc"] + AFTER
    rows = rows.sort_values("event_time_utc").reset_index(drop=True)
    output = PROJECT_ROOT / "data" / "events" / args.output
    rows.to_csv(output, index=False)
    print(rows.groupby(["sample", "family"]).size().unstack(fill_value=0).to_string())
    print(f"Wrote {len(rows)} session windows to {output}")


if __name__ == "__main__":
    main()
