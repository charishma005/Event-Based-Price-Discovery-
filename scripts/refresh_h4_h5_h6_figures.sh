#!/usr/bin/env bash
# Regenerate the current H4, H5 and H6 figures (they replace the old slide images).
# Needs the processed control windows and the one-second books on this machine:
#   data/processed/fomc_placebos_2015_2023/   (process_fomc_placebos)
#   data/processed/fomc_book_seconds/         (extract_fomc_book_seconds)
set -euo pipefail
cd "$(dirname "$0")/.."
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
python -m scripts.plot_h4_depth_controls      # H4 vs matched controls -> figures/fomc_sample_2015_2026/slides/slide_15b_*
python -m scripts.plot_fomc_price_paths       # H5 and H6, ES / NQ / ZN separately -> figures/paper/figure_h5_*, figure_h6_*
python -m scripts.make_slide_figures          # remaining slides 16-18
git add -f figures/fomc_sample_2015_2026/slides/slide_15b_h4_depth_vs_controls.png \
  figures/paper/figure_h5_*.png figures/paper/figure_h6_*.png \
  tables/fomc_h5_paths_groups.csv tables/fomc_h5_slopes_paths.csv \
  tables/fomc_h6_paths_groups.csv tables/fomc_h6_slopes_paths.csv
echo "Staged. Commit and push with:"
echo "  git commit -m 'Refresh H4, H5 and H6 figures' && git push origin claude/beautiful-ramanujan-98pgti"
