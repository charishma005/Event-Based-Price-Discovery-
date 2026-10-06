"""Cost-estimate or retrieve every registry window that is not cached yet (resumable).

Without ``--execute`` nothing is downloaded: the script prints the portfolio
estimate. With it, each request is estimated first and must pass the guards in
``config/settings.yaml`` (per-request dollars and billable bytes) plus the
stricter options below before it is retrieved. Estimates are cached in
``reports/registry_download_estimates.csv`` so a rerun does not query them again.

Examples
    python -m scripts.download_registry_windows --families fomc
    python -m scripts.download_registry_windows --execute --require-zero-cost --max-seconds 110
"""
from __future__ import annotations

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from src.data.databento_client import DatabentoRequest, Estimate, download_request, estimate_request, human_size
from src.utils.config import PROJECT_ROOT, settings

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
ESTIMATES = PROJECT_ROOT / "reports" / "registry_download_estimates.csv"
_lock = threading.Lock()


def _requests(registry: pd.DataFrame, schema: str) -> list[tuple[str, DatabentoRequest]]:
    out = []
    ordered = registry.sort_values(["request_start_utc", "is_control", "event_time_utc"])
    windows = ordered.drop_duplicates(["request_start_utc", "request_end_utc"])
    for row in windows.itertuples(index=False):
        request = DatabentoRequest.create(
            dataset="GLBX.MDP3", schema=schema, symbols=INSTRUMENTS, stype_in="continuous",
            start=row.request_start_utc, end=row.request_end_utc,
        )
        out.append((row.event_id, request))
    return out


def _free_gb(path) -> float:
    """Space available to this user (not merely unallocated blocks) in GB."""
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize / 1e9


def repair_manifests(requests: list[tuple[str, DatabentoRequest]], cache: dict[str, dict]) -> int:
    """Write the manifest for a complete file whose download was interrupted before the manifest step.

    Files are renamed into place only after the transfer finished, so a file
    without a manifest is complete; it just was never counted and hashed.
    """
    import databento as db

    from dataclasses import asdict

    from src.utils.io import sha256_file, utc_now_iso, write_json_exclusive

    repaired = 0
    for _, request in requests:
        target = request.output_path
        manifest = target.with_suffix(target.suffix + ".metadata.json")
        if not target.exists() or manifest.exists():
            continue
        known = cache.get(request.request_id, {})
        write_json_exclusive(manifest, {
            "provider": "Databento", **asdict(request), "request_id": request.request_id,
            "download_time_utc": utc_now_iso(), "source_timezone": "UTC",
            "billable_bytes_estimate": known.get("billable_bytes"), "cost_usd_estimate": known.get("cost_usd"),
            "record_count": int(db.DBNStore.from_file(target).to_ndarray().shape[0]),
            "file_size_bytes": target.stat().st_size, "sha256": sha256_file(target),
            "library_version": getattr(db, "__version__", "unknown"), "manifest_rebuilt_after_interruption": True,
        })
        repaired += 1
    return repaired


def _load_estimates() -> dict[str, dict]:
    if not ESTIMATES.exists():
        return {}
    return pd.read_csv(ESTIMATES).drop_duplicates("request_id", keep="last").set_index("request_id").to_dict("index")


def _save_estimates(cache: dict[str, dict]) -> None:
    frame = pd.DataFrame([{"request_id": key, **value} for key, value in cache.items()])
    frame.sort_values(["start", "request_id"]).to_csv(ESTIMATES, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default="event_registry.csv")
    parser.add_argument("--schema", default="mbp-1")
    parser.add_argument("--samples", nargs="*")
    parser.add_argument("--families", nargs="*")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--require-zero-cost", action="store_true", help="Stop at the first non-zero cost quote")
    parser.add_argument("--min-free-gb", type=float, default=8.0, help="Stop when the raw disk has less free space")
    parser.add_argument("--size-guard-mb", type=float,
                        help="Explicit per-run override of the billable-size guard in settings.yaml")
    parser.add_argument("--cost-only-estimate", action="store_true",
                        help="Query only the cost endpoint per request; size is bounded by --assumed-max-mb")
    parser.add_argument("--assumed-max-mb", type=float, default=200.0,
                        help="Conservative billable-size bound recorded with --cost-only-estimate")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, help="Stop starting new requests after this long")
    parser.add_argument("--shard", default="0/1", help="i/n: handle only requests whose order index mod n equals i")
    args = parser.parse_args()

    registry = pd.read_csv(
        PROJECT_ROOT / "data" / "events" / args.registry,
        parse_dates=["event_time_utc", "request_start_utc", "request_end_utc"], keep_default_na=False,
    )
    if args.samples:
        registry = registry.loc[registry["sample"].isin(args.samples)]
    if args.families:
        registry = registry.loc[registry["family"].isin(args.families)]
    shard, shards = (int(value) for value in args.shard.split("/"))
    every = _requests(registry, args.schema)
    repaired = repair_manifests(every, _load_estimates())
    if repaired:
        print(f"Rebuilt {repaired} manifests for files whose download was interrupted", flush=True)
    pending = [(label, request) for label, request in every if request.existing_path is None]
    pending = [item for number, item in enumerate(pending) if number % shards == shard]
    cache = _load_estimates()
    known = [cache[request.request_id] for _, request in pending if request.request_id in cache]
    print(f"{len(pending)} uncached windows in this shard; {len(known)} already estimated "
          f"({human_size(int(sum(item['billable_bytes'] for item in known)))}, "
          f"${sum(item['cost_usd'] for item in known):,.4f})", flush=True)
    if not pending:
        return

    guards = settings()["cost_control"]
    size_guard = int(guards["max_auto_billable_bytes"])
    if args.size_guard_mb:
        size_guard = int(args.size_guard_mb * 1e6)
        print(f"Size guard overridden for this run: {human_size(size_guard)} per request", flush=True)
    started = time.time()
    stop = threading.Event()
    raw_dir = pending[0][1].output_path.parent
    raw_dir.mkdir(parents=True, exist_ok=True)

    def handle(item: tuple[str, DatabentoRequest]) -> tuple[str, str]:
        label, request = item
        if stop.is_set() or (args.max_seconds and time.time() - started > args.max_seconds):
            return label, "deferred"
        cached = cache.get(request.request_id)
        if cached is None and args.cost_only_estimate:
            # One metadata call instead of two. The dollar guard is still enforced per request;
            # the billable size is recorded as unknown and bounded by --assumed-max-mb.
            from dataclasses import asdict

            from src.data.databento_client import historical_client

            kwargs = asdict(request)
            kwargs["symbols"] = list(request.symbols)
            cost = float(historical_client().metadata.get_cost(**kwargs))
            estimate = Estimate(request, int(args.assumed_max_mb * 1e6), cost, False)
            with _lock:
                cache[request.request_id] = {
                    "label": label, "schema": request.schema, "start": request.start, "end": request.end,
                    "billable_bytes": estimate.billable_bytes, "cost_usd": cost, "size_is_assumed_bound": True,
                }
                if len(cache) % 10 == 0:
                    _save_estimates(cache)
        elif cached is None:
            estimate = estimate_request(request)
            with _lock:
                cache[request.request_id] = {
                    "label": label, "schema": request.schema, "start": request.start, "end": request.end,
                    "billable_bytes": estimate.billable_bytes, "cost_usd": estimate.cost_usd,
                }
                if len(cache) % 10 == 0:
                    _save_estimates(cache)
        else:
            estimate = Estimate(request, int(cached["billable_bytes"]), float(cached["cost_usd"]),
                                request.existing_path is not None)
        if not args.execute:
            return label, "estimated"
        if args.require_zero_cost and estimate.cost_usd > 0:
            stop.set()
            return label, f"STOP: non-zero cost quote ${estimate.cost_usd:.4f}"
        if estimate.cost_usd > float(guards["max_auto_cost_usd"]):
            return label, f"rejected: cost ${estimate.cost_usd:.4f} exceeds guard"
        if estimate.billable_bytes > size_guard:
            return label, f"rejected: {human_size(estimate.billable_bytes)} exceeds size guard"
        if _free_gb(raw_dir) < args.min_free_gb:
            stop.set()
            return label, "STOP: free disk space below --min-free-gb"
        if stop.is_set() or (args.max_seconds and time.time() - started > args.max_seconds):
            return label, "deferred"
        path = download_request(estimate, execute=True, size_guard_bytes=size_guard, quiet=True)
        return label, f"ok {path.stat().st_size / 1e6:.1f} MB"

    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(handle, item): item[0] for item in pending}
        for future in as_completed(futures):
            try:
                label, status = future.result()
            except Exception as error:      # keep going; the window stays uncached for the next run
                label, status = futures[future], f"error: {type(error).__name__}: {str(error)[:160]}"
            kind = status.split()[0].rstrip(":")
            counts[kind] = counts.get(kind, 0) + 1
            if kind not in {"ok", "deferred", "estimated"}:
                print(f"{label}: {status}", flush=True)
    with _lock:
        _save_estimates(cache)
    estimated = [cache[request.request_id] for _, request in pending if request.request_id in cache]
    free = _free_gb(raw_dir)
    print(f"Status {counts}; estimated so far in shard: {len(estimated)} windows, "
          f"{human_size(int(sum(item['billable_bytes'] for item in estimated)))} billable, "
          f"${sum(item['cost_usd'] for item in estimated):,.4f}; free disk {free:.1f} GB; "
          f"{time.time() - started:.0f}s")
    if not args.execute:
        print("Estimate only. Add --execute after reviewing the portfolio.")


if __name__ == "__main__":
    main()
