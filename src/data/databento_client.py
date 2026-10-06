from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.utils.config import PROJECT_ROOT, raw_databento_dirs, settings
from src.utils.io import sha256_file, utc_now_iso, write_json_exclusive


@dataclass(frozen=True)
class DatabentoRequest:
    dataset: str
    schema: str
    symbols: tuple[str, ...]
    stype_in: str
    start: str
    end: str

    @classmethod
    def create(
        cls,
        *,
        dataset: str,
        schema: str,
        symbols: Iterable[str],
        stype_in: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
    ) -> "DatabentoRequest":
        start_ts = _utc_timestamp(start)
        end_ts = _utc_timestamp(end)
        if end_ts <= start_ts:
            raise ValueError("end must be later than start")
        clean_symbols = tuple(dict.fromkeys(str(s) for s in symbols))
        if not clean_symbols:
            raise ValueError("at least one symbol is required")
        return cls(
            dataset=dataset,
            schema=schema,
            symbols=clean_symbols,
            stype_in=stype_in,
            start=start_ts.isoformat(),
            end=end_ts.isoformat(),
        )

    @property
    def request_id(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(body).hexdigest()[:16]

    @property
    def file_name(self) -> str:
        return f"{self.dataset}-{self.schema}-{self.request_id}.dbn.zst"

    @property
    def output_path(self) -> Path:
        return PROJECT_ROOT / "data" / "raw" / "databento" / self.file_name

    @property
    def existing_path(self) -> Path | None:
        """The cached file in the project cache or any ``T3_EXTRA_RAW_DIRS`` cache."""
        for directory in raw_databento_dirs():
            candidate = directory / self.file_name
            if candidate.exists():
                return candidate
        return None


@dataclass(frozen=True)
class Estimate:
    request: DatabentoRequest
    billable_bytes: int
    cost_usd: float
    cached: bool

    @property
    def available(self) -> bool:
        """True when the file is in the project cache or in a ``T3_EXTRA_RAW_DIRS`` cache."""
        return self.cached or self.request.existing_path is not None


def _utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value!r}")
    return ts.tz_convert("UTC")


def historical_client() -> Any:
    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY is not set. Configure it in the process environment; "
            "do not place it in source code."
        )
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before using Databento") from exc
    return db.Historical(key)


def estimate_request(request: DatabentoRequest) -> Estimate:
    """Use free metadata endpoints to estimate bytes and dollars before retrieval."""
    client = historical_client()
    kwargs = asdict(request)
    kwargs["symbols"] = list(request.symbols)
    size = int(client.metadata.get_billable_size(**kwargs))
    cost = float(client.metadata.get_cost(**kwargs))
    return Estimate(request, size, cost, request.output_path.exists())


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def print_summary(estimate: Estimate) -> None:
    req = estimate.request
    print(f"Dataset: {req.dataset}")
    print(f"Schema: {req.schema}")
    print(f"Symbols: {', '.join(req.symbols)}")
    print(f"Window: {req.start} to {req.end}")
    print(f"Estimated size: {human_size(estimate.billable_bytes)}")
    print(f"Estimated cost: ${estimate.cost_usd:,.4f}")
    print(f"Cached: {'yes' if estimate.available else 'no'}")


def download_request(
    estimate: Estimate, *, execute: bool = False, size_guard_bytes: int | None = None,
    quiet: bool = False,
) -> Path:
    """Download an estimated request only after explicit opt-in and cost checks.

    ``size_guard_bytes`` replaces the configured billable-size tripwire for one
    call; the caller must have reviewed the estimate. The dollar guard always applies.
    """
    if not quiet:
        print_summary(estimate)
    if not execute:
        raise RuntimeError("Estimate only. Re-run with explicit execution enabled.")
    if estimate.available:
        return estimate.request.existing_path or estimate.request.output_path

    guards = settings()["cost_control"]
    if estimate.cost_usd > float(guards["max_auto_cost_usd"]):
        raise RuntimeError("Estimated monetary cost exceeds configured guard")
    size_guard = int(guards["max_auto_billable_bytes"]) if size_guard_bytes is None else int(size_guard_bytes)
    if estimate.billable_bytes > size_guard:
        raise RuntimeError("Estimated size exceeds configured guard")

    target = estimate.request.output_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)

    client = historical_client()
    req = estimate.request
    store = client.timeseries.get_range(
        dataset=req.dataset,
        schema=req.schema,
        symbols=list(req.symbols),
        stype_in=req.stype_in,
        start=req.start,
        end=req.end,
    )
    # Write under a temporary name first: an interrupted transfer must never
    # leave a truncated file that later looks like an immutable raw download.
    partial = target.with_name(target.name + ".part")
    store.to_file(partial, mode="w")
    if target.exists():
        raise FileExistsError(target)
    os.replace(partial, target)
    import databento as db

    record_count = int(db.DBNStore.from_file(target).to_ndarray().shape[0])
    manifest = {
        "provider": "Databento",
        **asdict(req),
        "request_id": req.request_id,
        "download_time_utc": utc_now_iso(),
        "source_timezone": "UTC",
        "billable_bytes_estimate": estimate.billable_bytes,
        "cost_usd_estimate": estimate.cost_usd,
        "record_count": record_count,
        "file_size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
    }
    manifest["library_version"] = getattr(db, "__version__", "unknown")
    write_json_exclusive(target.with_suffix(target.suffix + ".metadata.json"), manifest)
    return target
