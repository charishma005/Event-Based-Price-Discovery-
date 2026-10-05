#!/usr/bin/env bash
# Download (no estimate step) and process all FOMC data into data/processed/.
# Requires DATABENTO_API_KEY in .env. Re-runnable: cached raw files are not re-downloaded.
set -euo pipefail
cd "$(dirname "$0")/.."
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
CFG=fomc_sample_2015_2026.yaml

# 1. Raw data -> data/raw/databento
python -m scripts.download_fomc_sample --config "$CFG" --execute
python -m scripts.build_fomc_placebo_config
python -m scripts.download_fomc_placebos --config fomc_placebos_2015_2023.yaml --execute

# 2. Processed data -> data/processed/fomc_sample_2015_2026 and fomc_placebos_2015_2023
python -m scripts.process_fomc_sample --config "$CFG" --output-name fomc_sample_2015_2026
python -m scripts.process_fomc_placebos --config fomc_placebos_2015_2023.yaml \
  --actual-name fomc_sample_2015_2026 --output-name fomc_placebos_2015_2023

# 3. Analysis tables -> tables/
python -m scripts.analyze_fomc_sample --config "$CFG"
python -m scripts.analyze_fomc_surprises --config "$CFG"
python -m scripts.analyze_fomc_h5_horizons --config "$CFG"
python -m scripts.analyze_fomc_h6_horizons --config "$CFG"
python -m scripts.analyze_fomc_h5_h6_extra --config "$CFG"
