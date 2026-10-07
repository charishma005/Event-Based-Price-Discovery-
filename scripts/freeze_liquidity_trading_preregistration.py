"""Freeze ``config/liquidity_trading_prereg.yaml``: record the input and code hashes and the time.

Run once, after ``python -m scripts.analyze_liquidity_trading --check-data`` and
before the analysis. If an ``--unfrozen`` run was already made, the freeze needs
``--acknowledge-unfrozen-run`` and records that fact in the YAML, because parts A
to C are then no longer blind.
"""
from __future__ import annotations

import argparse

import pandas as pd

from scripts.analyze_liquidity_trading import HASHED_FILES, IMPLIED_VOL, PREREGISTRATION, TABLES, sha256
from src.utils.config import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--acknowledge-unfrozen-run", action="store_true")
    args = parser.parse_args()
    path = PROJECT_ROOT / PREREGISTRATION
    text = path.read_text(encoding="utf-8")
    if "status: frozen" in text:
        raise SystemExit("Already frozen; a second freeze would overwrite the recorded hashes.")
    marker = "status: draft"
    if text.count(marker) != 1:
        raise SystemExit("Expected exactly one 'status: draft' line")
    frozen_tables = [p for p in TABLES.glob("liq_*.csv") if not p.name.startswith("liq_unfrozen_")]
    if frozen_tables:
        raise SystemExit("liq_* result tables already exist; the freeze must come before the analysis.")
    unfrozen = sorted(TABLES.glob("liq_unfrozen_*.csv"))
    if unfrozen and not args.acknowledge_unfrozen_run:
        raise SystemExit("An --unfrozen run exists (tables/liq_unfrozen_*.csv). Rerun with "
                         "--acknowledge-unfrozen-run; the freeze will record it.")
    missing = [relative for relative in HASHED_FILES.values() if not (PROJECT_ROOT / relative).exists()]
    if missing:
        raise SystemExit("Missing inputs: " + ", ".join(missing))
    text = text.replace(marker, "status: frozen", 1).rstrip("\n") + "\n\nfreeze:\n"
    text += f"  frozen_at_utc: '{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')}'\n"
    for key, relative in HASHED_FILES.items():
        text += f"  {key}: {sha256(relative)}\n"
    if (PROJECT_ROOT / IMPLIED_VOL).exists():
        text += f"  implied_vol_sha256: {sha256(IMPLIED_VOL)}\n"
    if unfrozen:
        modified = pd.Timestamp(max(p.stat().st_mtime for p in unfrozen), unit="s", tz="UTC")
        text += f"  unfrozen_run_before_freeze: '{modified.strftime('%Y-%m-%dT%H:%M:%SZ')}'\n"
    path.write_text(text, encoding="utf-8")
    print(text[text.index("freeze:"):])


if __name__ == "__main__":
    main()
