"""Freeze ``config/q1_short_horizon_prereg.yaml``: record hashes and the freeze time.

Run once, after the development analysis and before any out-of-sample window is
processed. The hashes let anyone check later that the measure code, the
analysis script and the event registry are the ones that existed at the freeze.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from scripts.extract_tick_features import PREREGISTRATION, measure_code_hash
from src.utils.config import PROJECT_ROOT


def _sha256(relative: str) -> str:
    return hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()


def main() -> None:
    path = PROJECT_ROOT / PREREGISTRATION
    text = path.read_text(encoding="utf-8")
    if "status: frozen" in text:
        raise SystemExit("Already frozen; a second freeze would overwrite the recorded hashes.")
    marker = "status: draft"
    if text.count(marker) != 1:
        raise SystemExit("Expected exactly one 'status: draft' line")
    parts = (PROJECT_ROOT / "data" / "processed" / "tick_features" / "parts").glob("*.events.parquet")
    processed = pd.concat([pd.read_parquet(part, columns=["sample"]) for part in parts])
    if processed["sample"].ne("development").any():
        raise SystemExit("Out-of-sample parts already exist; the freeze must come first.")
    registry = pd.read_csv(PROJECT_ROOT / "data" / "events" / "event_registry.csv", keep_default_na=False)
    text = text.replace(marker, "status: frozen", 1).rstrip("\n") + "\n"
    text += (
        "\nfreeze:\n"
        f"  frozen_at_utc: '{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')}'\n"
        f"  measure_code_sha256: {measure_code_hash()}\n"
        f"  analysis_code_sha256: {_sha256('scripts/analyze_q1_short_horizon.py')}\n"
        f"  event_registry_sha256: {_sha256('data/events/event_registry.csv')}\n"
        f"  event_registry_rows: {len(registry)}\n"
        f"  development_rows_processed_before_freeze: {len(processed)}\n"
        "  out_of_sample_rows_processed_before_freeze: 0\n"
        f"measure_code_sha256: {measure_code_hash()}\n"
    )
    path.write_text(text, encoding="utf-8")
    print(text[text.index("freeze:"):])


if __name__ == "__main__":
    main()
