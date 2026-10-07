"""Freeze ``config/h3_prereg.yaml``: record the input and code hashes and the time.

Run once, after the survey parser has been run and before the analysis. The
hashes let anyone check later that the survey workbook, the step 1 features,
the registry and both scripts are the ones that existed at the freeze.
"""
from __future__ import annotations

import pandas as pd

from scripts.analyze_h3_dispersion import HASHED_FILES, PREREGISTRATION, TABLES, sha256
from src.utils.config import PROJECT_ROOT


def main() -> None:
    path = PROJECT_ROOT / PREREGISTRATION
    text = path.read_text(encoding="utf-8")
    if "status: frozen" in text:
        raise SystemExit("Already frozen; a second freeze would overwrite the recorded hashes.")
    marker = "status: draft"
    if text.count(marker) != 1:
        raise SystemExit("Expected exactly one 'status: draft' line")
    if list(TABLES.glob("h3_*.csv")):
        raise SystemExit("H3 result tables already exist; the freeze must come before the analysis.")
    text = text.replace(marker, "status: frozen", 1).rstrip("\n") + "\n\nfreeze:\n"
    text += f"  frozen_at_utc: '{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')}'\n"
    for key, relative in HASHED_FILES.items():
        text += f"  {key}: {sha256(relative)}\n"
    path.write_text(text, encoding="utf-8")
    print(text[text.index("freeze:"):])


if __name__ == "__main__":
    main()
