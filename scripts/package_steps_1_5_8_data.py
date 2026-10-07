"""List the raw data files behind steps 1, 5 and 8, and optionally pack them into one archive.

Steps 1, 5 and 8 of the professor's next steps read four kinds of Databento
files (dataset GLBX.MDP3, continuous front contracts ES.v.0, NQ.v.0, ZN.v.0):

    mbp-1      one tick window per registry clock (data/events/event_registry.csv)
    bbo-1s     one-second books for the FOMC and control afternoons
               (fomc_session_windows.csv) and for the unscheduled arrivals and
               their control days (unscheduled_windows.csv)
    trades     FOMC afternoons only. They fill the trade-volume columns of the
               one-second FOMC panel, which no step 1, 5 or 8 table reads.
    ohlcv-1m   one-minute bars, 2015-2026, for the unscheduled scan and for the
               volume screen of the macro control mornings

Default: write reports/data_files_steps_1_5_8.csv, one row per file, with its
window, record count, size and the SHA-256 recorded when it was downloaded.

    --verify     check the local raw files against that list instead of rewriting
                 it: every listed file present, same size, same SHA-256
    --zip PATH   pack the raw files (with their request manifests) and the merged
                 feature files into one uncompressed archive that unpacks at the
                 repository root. Every raw file is checked against its SHA-256
                 as it is read. Resumable: rerun until nothing is left.

The archive holds licensed vendor data. It is for the project team and must not
be added to the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pandas as pd

from src.data.raw_index import build_raw_index, find_raw_file
from src.utils.config import PROJECT_ROOT, raw_databento_dirs

EVENTS = PROJECT_ROOT / "data" / "events"
MANIFEST = PROJECT_ROOT / "reports" / "data_files_steps_1_5_8.csv"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
RAW_ARCHIVE_DIR = "data/raw/databento"
README_NAME = "data/processed/README_steps_1_5_8_data.md"
LIST_NAME = "data/processed/steps_1_5_8_data_files.csv"
# Merged outputs of extract_tick_features and extract_session_panels.
PROCESSED_FILES = (
    "data/processed/tick_features/events.parquet",
    "data/processed/tick_features/fine.parquet",
    "data/processed/tick_features/seconds.parquet",
    "data/processed/fomc_sessions/panel.parquet",
    "data/processed/fomc_sessions/sessions.parquet",
    "data/processed/fomc_sessions/sessions.csv",
    "data/processed/unscheduled/panel.parquet",
    "data/processed/unscheduled/sessions.parquet",
    "data/processed/unscheduled/sessions.csv",
)
TICK_WINDOWS = {        # registry family -> (what the window is, steps that read it)
    "macro": ("8:30 a.m. release", "1, 5, 8"),
    "macro_control": ("8:30 a.m. control morning", "1, 5"),
    "fomc": ("FOMC statement and press conference", "1, 5"),
    "fomc_control": ("2:00 p.m. control afternoon", "1"),
}
SESSION_WINDOWS = {
    "fomc": "FOMC afternoon, 1:30-4:00 p.m.",
    "fomc_control": "control afternoon, 1:30-4:00 p.m.",
    "unscheduled_jump": "unscheduled arrival",
    "unscheduled_jump_control": "control day for an unscheduled arrival",
    "unscheduled_fed": "unscheduled Federal Reserve announcement",
    "unscheduled_fed_control": "control day for an unscheduled Federal Reserve announcement",
}
COLUMNS = ["file", "schema", "window_start_utc", "window_end_utc", "content", "steps", "records", "bytes", "sha256"]


def _registry(name: str) -> pd.DataFrame:
    return pd.read_csv(EVENTS / name, parse_dates=["request_start_utc", "request_end_utc"], keep_default_na=False)


def used_raw_files(index: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Every raw file the step 1, 5 and 8 scripts read, and the windows that have no file."""
    index = build_raw_index() if index is None else index
    found: dict[Path, tuple[str, str]] = {}
    missing: list[str] = []

    def add(row, schema: str, content: str, steps: str, required: bool = True) -> None:
        path = find_raw_file(schema=schema, start=row.request_start_utc, end=row.request_end_utc,
                             symbols=INSTRUMENTS, index=index)
        if path is None:
            if required:
                missing.append(f"{schema} {row.event_id}")
        else:
            found.setdefault(path, (content, steps))

    for row in _registry("event_registry.csv").itertuples(index=False):
        family = row.family.removesuffix("_pseudo")         # a pseudo clock shares its event's window
        add(row, "mbp-1", *TICK_WINDOWS[family])
    for name in ("fomc_session_windows.csv", "unscheduled_windows.csv"):
        for row in _registry(name).itertuples(index=False):
            add(row, "bbo-1s", SESSION_WINDOWS[row.family], "8")
            add(row, "trades", SESSION_WINDOWS[row.family] + " (trade-volume columns of the panel; optional)", "8",
                required=False)
    for path in index.loc[index["schema"].eq("ohlcv-1m"), "path"]:
        found.setdefault(Path(path), ("one-minute bars", "5, 8"))

    by_path = index.set_index("path")
    rows = []
    for path, (content, steps) in found.items():
        entry = by_path.loc[path]
        recorded = json.loads(Path(str(path) + ".metadata.json").read_text(encoding="utf-8"))
        rows.append({"path": path, "file": path.name, "schema": entry["schema"],
                     "window_start_utc": entry["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "window_end_utc": entry["end"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "content": content, "steps": steps, "records": int(recorded["record_count"]),
                     "bytes": path.stat().st_size, "sha256": recorded["sha256"]})
    frame = pd.DataFrame(rows, columns=["path", *COLUMNS])
    if frame["file"].duplicated().any():
        raise SystemExit("The same file name appears in two raw folders: " + ", ".join(frame.loc[frame["file"].duplicated(), "file"]))
    return frame.sort_values(["schema", "window_start_utc", "file"]).reset_index(drop=True), missing


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def check_against_list(listed: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Listed files found in no raw folder, and files whose size or SHA-256 differs from the list."""
    directories = raw_databento_dirs()
    missing, different = [], []
    for row in listed.itertuples(index=False):
        path = next((folder / row.file for folder in directories if (folder / row.file).exists()), None)
        if path is None:
            missing.append(row.file)
        elif path.stat().st_size != row.bytes or sha256_of(path) != row.sha256:
            different.append(row.file)
    return missing, different


def pack(archive_path: Path, entries: list[tuple[str, Path]], expected: dict[str, str], max_seconds: float = 0.0) -> int:
    """Append the entries the archive does not hold yet; return how many are still left.

    ``entries`` are (name inside the archive, source file). A source whose name is in
    ``expected`` must have that SHA-256.
    """
    started = time.time()
    with zipfile.ZipFile(archive_path, "a", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        have = set(archive.namelist())
        pending = [(name, source) for name, source in entries if name not in have]
        done = 0
        for name, source in pending:
            if max_seconds and time.time() - started > max_seconds:
                break
            data = source.read_bytes()
            if name in expected and hashlib.sha256(data).hexdigest() != expected[name]:
                raise SystemExit(f"{source} does not match its recorded SHA-256; nothing more was added.")
            info = zipfile.ZipInfo.from_file(source, name)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            done += 1
    return len(pending) - done


def readme_features_only(processed: list[str]) -> str:
    lines = [
        "# Feature files for steps 1, 5 and 8",
        "",
        "Merged feature files behind `reports/professor_steps_1_5_8.md` in the",
        "Event-Based-Price-Discovery- repository, without the raw Databento files.",
        "",
        "Unpack at the repository root, keeping files that are already there:",
        "",
        "    unzip -n steps_1_5_8_features_only.zip",
        "",
        "This is enough to run the four analysis scripts (`analyze_q1_short_horizon`,",
        "`analyze_macro_extension`, `analyze_unscheduled_arrivals`, `analyze_tick_constraint`).",
        "Rebuilding the features, the unscheduled scan and the volume screen of the control",
        "mornings need the raw files in the full archive, `steps_1_5_8_data.zip`.",
        "",
    ]
    lines += [f"- `{name}`" for name in processed]
    lines += ["", "Derived from licensed vendor data: keep it inside the project team and out of the repository.", ""]
    return "\n".join(lines)


def readme(frame: pd.DataFrame, processed: list[str]) -> str:
    counts = frame.groupby("schema")["bytes"].agg(["count", "sum"])
    lines = [
        "# Data for steps 1, 5 and 8",
        "",
        "Raw Databento files (GLBX.MDP3; ES.v.0, NQ.v.0, ZN.v.0) and merged feature files behind",
        "`reports/professor_steps_1_5_8.md` in the Event-Based-Price-Discovery- repository.",
        "",
        "Unpack at the repository root, keeping files that are already there:",
        "",
        "    unzip -n steps_1_5_8_data.zip",
        "",
        "The raw files land in `data/raw/databento/` and the feature files in `data/processed/`;",
        "git ignores both (only `tick_features/events.parquet` is tracked, and it is the same file).",
        "The four analysis scripts then run as they are; the run order is at the end of the report.",
        "",
        "| Schema | Files | Size |",
        "|---|---|---|",
    ]
    lines += [f"| {schema} | {int(row['count'])} | {row['sum'] / 1e9:.2f} GB |" for schema, row in counts.iterrows()]
    lines += [
        "",
        "Every raw file comes with its `.metadata.json` request manifest. `steps_1_5_8_data_files.csv`",
        "(next to this file, and `reports/data_files_steps_1_5_8.csv` in the repository) lists each file",
        "with its window, what it is, the steps that read it and its SHA-256.",
        "`python -m scripts.package_steps_1_5_8_data --verify` checks the unpacked files against that list.",
        "",
        "Feature files (written by `extract_tick_features --merge` and `extract_session_panels --merge`):",
        "",
    ]
    lines += [f"- `{name}`" for name in processed]
    lines += [
        "",
        "`tick_features/seconds.parquet` is not read by the step 1, 5 or 8 scripts; it comes out of the",
        "same extraction and holds the one-second book around every registry clock.",
        "",
        "Licensed vendor data: keep it inside the project team and out of the repository.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="Check local raw files against the list")
    parser.add_argument("--zip", dest="archive", help="Archive to create or continue")
    parser.add_argument("--without-raw", action="store_true", help="With --zip: feature files only")
    parser.add_argument("--max-seconds", type=float, default=0.0, help="With --zip: stop adding files after this long")
    args = parser.parse_args()
    if args.verify:
        listed = pd.read_csv(MANIFEST)
        absent, different = check_against_list(listed)
        print(f"{len(listed)} listed files: {len(absent)} missing, {len(different)} with a different size or SHA-256")
        for label, names in (("missing", absent), ("different", different)):
            if names:
                print(f"{label}: {', '.join(names[:10])}{' ...' if len(names) > 10 else ''}")
        return
    frame, missing = used_raw_files()
    if missing:
        print(f"{len(missing)} windows have no raw file, for example: {', '.join(missing[:5])}")
    frame[COLUMNS].to_csv(MANIFEST, index=False)
    summary = frame.groupby("schema")["bytes"].agg(files="count", gigabytes=lambda v: v.sum() / 1e9)
    print(summary.to_string(float_format=lambda v: f"{v:.2f}"))
    print(f"{len(frame)} files, {frame['bytes'].sum() / 1e9:.2f} GB -> {MANIFEST.relative_to(PROJECT_ROOT)}")
    if args.archive:
        processed = [name for name in PROCESSED_FILES if (PROJECT_ROOT / name).exists()]
        entries: list[tuple[str, Path]] = []
        expected: dict[str, str] = {}
        if not args.without_raw:
            for row in frame.itertuples(index=False):
                name = f"{RAW_ARCHIVE_DIR}/{row.file}"
                entries += [(name, row.path), (name + ".metadata.json", Path(str(row.path) + ".metadata.json"))]
                expected[name] = row.sha256
        entries += [(name, PROJECT_ROOT / name) for name in processed]
        archive_path = Path(args.archive).expanduser()
        left = pack(archive_path, entries, expected, args.max_seconds)
        if left:
            print(f"{left} files still to add; run the same command again.")
            return
        with zipfile.ZipFile(archive_path, "a", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            have = set(archive.namelist())
            if LIST_NAME not in have and not args.without_raw:
                buffer = io.StringIO()
                frame[COLUMNS].to_csv(buffer, index=False)
                archive.writestr(LIST_NAME, buffer.getvalue())
            if README_NAME not in have:
                archive.writestr(README_NAME, readme_features_only(processed) if args.without_raw else readme(frame, processed))
            total = sum(item.file_size for item in archive.infolist())
            print(f"{archive_path.name}: {len(archive.namelist())} entries, {total / 1e9:.2f} GB, complete")


if __name__ == "__main__":
    main()
