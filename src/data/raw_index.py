"""Index of immutable Databento files across the configured raw directories.

Every download writes ``<file>.metadata.json`` next to the DBN file. Reading all
of those manifests once is much cheaper than re-reading them for every event,
and it lets the project reuse a raw cache kept outside the repository (see
``src.utils.config.raw_databento_dirs``).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.utils.config import raw_databento_dirs


def _read_manifest(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    dbn_path = path.with_name(path.name[: -len(".metadata.json")])
    if not dbn_path.exists():
        return None
    return {
        "path": dbn_path,
        "dataset": payload.get("dataset"),
        "schema": payload.get("schema"),
        "stype_in": payload.get("stype_in"),
        "start": pd.Timestamp(payload["start"]),
        "end": pd.Timestamp(payload["end"]),
        "symbols": "|".join(sorted(payload.get("symbols", []))),
        "record_count": payload.get("record_count"),
        "file_size_bytes": payload.get("file_size_bytes"),
        "request_id": payload.get("request_id"),
    }


def build_raw_index(directories: Iterable[Path] | None = None) -> pd.DataFrame:
    """One row per cached DBN file with a readable manifest."""
    rows = []
    for directory in directories or raw_databento_dirs():
        for manifest in sorted(Path(directory).glob("*.metadata.json")):
            row = _read_manifest(manifest)
            if row is not None:
                rows.append(row)
    columns = [
        "path", "dataset", "schema", "stype_in", "start", "end", "symbols",
        "record_count", "file_size_bytes", "request_id",
    ]
    return pd.DataFrame(rows, columns=columns)


@lru_cache(maxsize=1)
def _cached_index() -> pd.DataFrame:
    return build_raw_index()


def refresh_raw_index() -> pd.DataFrame:
    _cached_index.cache_clear()
    return _cached_index()


def find_raw_file(
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    symbols: Iterable[str],
    schema: str = "mbp-1",
    dataset: str = "GLBX.MDP3",
    index: pd.DataFrame | None = None,
) -> Path | None:
    """Exact-window lookup, matching the existing per-script helpers."""
    table = _cached_index() if index is None else index
    if table.empty:
        return None
    wanted = "|".join(sorted(str(symbol) for symbol in symbols))
    match = table.loc[
        table["dataset"].eq(dataset)
        & table["schema"].eq(schema)
        & table["start"].eq(pd.Timestamp(start))
        & table["end"].eq(pd.Timestamp(end))
        & table["symbols"].eq(wanted)
    ]
    return None if match.empty else Path(match.iloc[0]["path"])


def find_covering_files(
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    symbols: Iterable[str],
    schema: str = "mbp-1",
    dataset: str = "GLBX.MDP3",
    index: pd.DataFrame | None = None,
) -> list[Path]:
    """Files whose window overlaps ``[start, end)`` and that contain every symbol."""
    table = _cached_index() if index is None else index
    if table.empty:
        return []
    wanted = {str(symbol) for symbol in symbols}
    overlap = table.loc[
        table["dataset"].eq(dataset)
        & table["schema"].eq(schema)
        & table["start"].lt(pd.Timestamp(end))
        & table["end"].gt(pd.Timestamp(start))
    ]
    keep = overlap["symbols"].map(lambda value: wanted.issubset(set(value.split("|"))))
    return [Path(value) for value in overlap.loc[keep].sort_values("start")["path"]]
