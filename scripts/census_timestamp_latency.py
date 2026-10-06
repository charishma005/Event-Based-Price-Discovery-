"""Receive-minus-exchange clock gap in every cached tick, trade and one-second file (resumable).

The one-second BBO schema samples the book on the vendor's receive clock, so the
session panels need to know how that clock relates to the exchange clock. This
census reads every cached GLBX.MDP3 ``mbp-1``, ``trades`` and ``bbo-1s`` file and
records percentiles of ``ts_recv - ts_event`` in milliseconds. In the cached
history the low end of that gap is exactly one second higher in every file from
9 May to 3 August 2018 and in no other file; ``scripts.extract_session_panels``
detects the whole-second offset per file and removes it.

Output: ``reports/timestamp_latency_census.csv``, one row per file:
    n                     records in the file
    lat_p01 ... lat_max   percentiles of the gap, milliseconds
    bad_ts_recv_share     share of records the vendor flags as having an unreliable receive stamp
    tsin_*                percentiles of ``ts_in_delta`` (nanoseconds), where the schema has it
Files already in the output are skipped; rerun with ``--max-seconds`` to continue a scan.
"""
from __future__ import annotations

import argparse
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.raw_index import build_raw_index
from src.utils.config import PROJECT_ROOT

OUTPUT = PROJECT_ROOT / "reports" / "timestamp_latency_census.csv"
SCHEMAS = ("mbp-1", "trades", "bbo-1s")
BAD_TS_RECV = 8                     # DBN record flag: the receive timestamp is unreliable
COLUMNS = ["path", "schema", "start", "n", "lat_p01", "lat_p50", "lat_p99", "lat_min", "lat_max",
           "bad_ts_recv_share", "tsin_p50", "tsin_p01", "tsin_p99"]


def scan(task: tuple[str, str, str]) -> dict[str, object]:
    import databento as db

    path, schema, start = task
    row: dict[str, object] = {"path": Path(path).name, "schema": schema, "start": start, "n": 0}
    records = db.DBNStore.from_file(path).to_ndarray()
    if len(records) == 0:
        return row
    gap = (records["ts_recv"].astype(np.int64) - records["ts_event"].astype(np.int64)) / 1e6
    row.update(n=len(records), lat_p01=np.percentile(gap, 1), lat_p50=np.percentile(gap, 50),
               lat_p99=np.percentile(gap, 99), lat_min=gap.min(), lat_max=gap.max())
    if "ts_in_delta" in records.dtype.names:
        delta = records["ts_in_delta"].astype(np.int64)
        row.update(tsin_p50=float(np.percentile(delta, 50)), tsin_p01=float(np.percentile(delta, 1)),
                   tsin_p99=float(np.percentile(delta, 99)))
    if "flags" in records.dtype.names:
        row["bad_ts_recv_share"] = float(((records["flags"] & BAD_TS_RECV) > 0).mean())
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, default=0.0, help="Stop starting new files after this long")
    args = parser.parse_args()
    index = build_raw_index()
    index = index.loc[index["dataset"].eq("GLBX.MDP3") & index["schema"].isin(SCHEMAS)]
    census = pd.read_csv(OUTPUT, float_precision="round_trip") if OUTPUT.exists() else pd.DataFrame(columns=COLUMNS)
    done = set(census["path"])
    tasks = [(str(row.path), row.schema, str(row.start)) for row in index.itertuples(index=False)
             if Path(row.path).name not in done]
    print(f"{len(tasks)} files to scan, {len(done)} already in the census", flush=True)
    started, rows = time.time(), []
    if tasks:
        with Pool(max(1, args.workers)) as pool:
            for row in pool.imap_unordered(scan, tasks, chunksize=4):
                rows.append(row)
                if args.max_seconds and time.time() - started > args.max_seconds:
                    pool.terminate()
                    break
    census = pd.concat([census, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True) if rows else census
    census = census.sort_values(["schema", "start", "path"]).reset_index(drop=True)
    census[COLUMNS].to_csv(OUTPUT, index=False)
    left = len(tasks) - len(rows)
    print(f"scanned {len(rows)} files in {time.time() - started:.0f}s; {len(census)} in the census"
          + (f"; {left} left, run again" if left else ""))
    # Whole-second offset: the low end of the gap sits about one second above normal.
    shifted = census.loc[census["lat_p01"] > 900, "start"].astype(str).str[:10]
    if len(shifted):
        print(f"{len(shifted)} files with a gap of one second or more at the first percentile, "
              f"dated {shifted.min()} to {shifted.max()}")


if __name__ == "__main__":
    main()
