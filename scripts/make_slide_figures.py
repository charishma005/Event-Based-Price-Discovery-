"""Slide figures for the 2015-2026 FOMC results (one PNG per slide).

Reads only committed processed files and the paper's 12-meeting control
numbers, so it runs without the raw DBN cache:

- data/processed/fomc_sample_2015_2026/timing_liquidity.csv   (H2, H4)
- data/processed/fomc_sample_2015_2026/response_horizons.csv  (H2)
- data/processed/fomc_sample_2015_2026/speed_metrics.parquet  (H5)
- tables/fomc_h5_surprise_speed*.csv, tables/fomc_h6_surprise_asymmetry*.csv

Writes figures/fomc_sample_2015_2026/slides/slide_1{6,7,8}_*.png. The H4, H5 and H6
slides that used to live here are superseded:
- H4 with matched controls: scripts/plot_h4_depth_controls.py
- H5 and H6 from 1 s to 40 min, ES, NQ and ZN separately: scripts/plot_fomc_price_paths.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.analyze_fomc_surprises import _meetings, _speed_panel
from src.events.surprises import build_surprise_panel
from src.utils.config import PROJECT_ROOT

ROOT = PROJECT_ROOT / "data" / "processed" / "fomc_sample_2015_2026"
OUT = PROJECT_ROOT / "figures" / "fomc_sample_2015_2026" / "slides"
TABLES = PROJECT_ROOT / "tables"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8f8e89"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_LIGHT = "#86b6ef"
INSTRUMENT_COLOR = {"ES.v.0": BLUE, "NQ.v.0": ORANGE, "ZN.v.0": AQUA}
INSTRUMENT_NAME = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 14,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
    }
)


HALO = [patheffects.withStroke(linewidth=4, foreground=SURFACE)]


def _figure(title: str, subtitle: str, ncols: int = 1, widths=None, left: float = 0.08):
    fig, axes = plt.subplots(
        1, ncols, figsize=(13.33, 7.5), gridspec_kw={"width_ratios": widths} if widths else None
    )
    fig.subplots_adjust(left=left, right=0.97, top=0.74, bottom=0.14, wspace=0.28)
    fig.text(0.04, 0.94, title, fontsize=22, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.875, subtitle, fontsize=14, color=INK_2, va="top")
    return fig, np.atleast_1d(axes)


def _grid(ax, axis="y") -> None:
    ax.grid(axis=axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _save(fig, name: str, source: str) -> None:
    fig.text(0.04, 0.035, source, fontsize=11, color=MUTED)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print(OUT / name)


def _timing() -> pd.DataFrame:
    timing = pd.read_csv(ROOT / "timing_liquidity.csv")
    return timing.loc[timing["dataset_condition"].eq("available")]


def slide_16_first_quote() -> None:
    timing = _timing()
    moves = pd.read_csv(ROOT / "response_horizons.csv")
    moves = moves.loc[moves["horizon_seconds"].eq(60), ["meeting", "subevent", "instrument", "log_return_bp"]]
    data = timing.merge(moves, on=["meeting", "subevent", "instrument"])
    data = data.loc[data["eligible_primary_q1"].astype(bool) & data["log_return_bp"].abs().gt(0.1)]
    share = data["first_quote_revision_bp"].abs() / data["log_return_bp"].abs()
    bins = pd.cut(share, [-np.inf, 0, 0.10, 0.40, np.inf], labels=["Exactly 0%", "0-10%", "10-40%", "Over 40%"])
    counts = pd.crosstab(bins, data["subevent"]).reindex(columns=["statement", "press_conference"])
    zero_share = share.eq(0).mean()

    fig, (ax,) = _figure(
        f"The first quote carries none of the move in {zero_share:.0%} of FOMC observations",
        "Share of the 60-second price move shown by the first valid quote after the announcement. H2 threshold: below 40%.",
        left=0.13,
    )
    y = np.arange(len(counts))[::-1]
    height = 0.36
    for offset, sub, color, name in ((height / 2, "statement", BLUE, "Statement"), (-height / 2, "press_conference", ORANGE, "Press conference")):
        values = counts[sub].to_numpy()
        ax.barh(y + offset, values, height=height - 0.04, color=color, label=f"{name} (n = {values.sum()})")
        for yy, v in zip(y + offset, values):
            ax.text(v + 2, yy, str(v), va="center", fontsize=13, color=INK)
    ax.set_yticks(y, counts.index.astype(str))
    ax.set_xlabel("Observations (meeting x instrument), 93 meetings 2015-2026")
    ax.set_xlim(0, counts.to_numpy().max() * 1.12)
    ax.axhline(0.5, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(ax.get_xlim()[1] * 0.99, 0.62, "40% threshold", ha="right", fontsize=12, color=INK_2)
    ax.legend(loc="center right", frameon=False, fontsize=13)
    _grid(ax, "x")
    _save(
        fig,
        "slide_16_h2_first_quote_share.png",
        "Eligible observations only (no trade before the first quote; |60s move| > 0.1 bp). Numeric macro releases (H1) show the same: median 0%.",
    )


def slide_17_surprise_speed() -> None:
    panel = build_surprise_panel(_meetings("fomc_sample_2015_2026.yaml"))
    surprises = panel.loc[panel["dataset_condition"].eq("available")].drop(
        columns=["meeting_date", "dataset_condition", "STMT_recomputed"], errors="ignore"
    )
    data = _speed_panel(surprises, pd.read_parquet(ROOT / "speed_metrics.parquet"))
    data = data.loc[data["subevent"].eq("statement") & data["metric"].eq("first_crossing_50_seconds")]
    table = pd.read_csv(TABLES / "fomc_h5_surprise_speed_2015_2026.csv")

    fig, axes = _figure(
        "Surprise size predicts pricing speed only in ZN",
        "FOMC statements, 2015-2026. Each dot is one meeting. Time for the price to cover 50% of its five-minute move.",
        ncols=2,
    )
    for ax, instrument, color, label, note in (
        (axes[0], "equity_average", BLUE, "ES + NQ average", "No relationship"),
        (axes[1], "ZN.v.0", AQUA, "ZN (10-year Treasury)", "Surprise and outcome share rate-futures inputs"),
    ):
        sample = data.loc[data["instrument"].eq(instrument)].dropna(subset=["STMT"])
        ax.scatter(sample["STMT"].abs(), sample["seconds"].clip(lower=0.5), s=60, zorder=3, color=color, alpha=0.8, edgecolor=SURFACE, linewidth=1.5)
        row = table.loc[
            table["subevent"].eq("statement")
            & table["metric"].eq("first_crossing_50_seconds")
            & table["instrument"].eq(instrument)
            & table["measure"].eq("STMT")
        ].iloc[0]
        ax.set_yscale("log")
        ax.set_yticks([0.5, 1, 3, 10, 30, 100, 300], ["0", "1", "3", "10", "30", "100", "300"])
        ax.set_ylim(0.4, 400)
        ax.set_xlabel("|Statement surprise| (USMPD, one-year yield units)")
        ax.set_title(label, loc="left", fontsize=16, pad=30, color=INK, fontweight="bold")
        ax.text(0, 1.025, note, transform=ax.transAxes, fontsize=12, color=INK_2)
        holm = "survives" if row["holm_p"] < 0.05 else "does not survive"
        ax.text(
            0.98, 0.96,
            f"Spearman rho = {row['spearman_rho_abs_surprise']:.2f}\np = {row['two_sided_p']:.2g}, n = {int(row['observations'])}\n{holm} Holm correction",
            transform=ax.transAxes, ha="right", va="top", fontsize=13, color=INK, linespacing=1.4,
            path_effects=HALO, zorder=4,
        )
        _grid(ax, "both")
    axes[0].set_ylabel("Seconds to 50% crossing (log scale)")
    _save(
        fig,
        "slide_17_h5_surprise_vs_speed.png",
        "Source: speed_metrics.parquet and tables/fomc_h5_surprise_speed_2015_2026.csv. H5 predicted a positive relationship (bigger surprise, slower).",
    )


def slide_18_multiple_testing() -> None:
    families = []
    for hyp, stem, column in (
        ("H5", "fomc_h5_surprise_speed", "two_sided_p"),
        ("H6", "fomc_h6_surprise_asymmetry", "mannwhitney_p_two_sided"),
    ):
        for sample, suffix in (("12 meetings", ""), ("93 meetings", "_2015_2026")):
            table = pd.read_csv(TABLES / f"{stem}{suffix}.csv")
            tested = table[column].notna()
            families.append(
                {
                    "label": f"{hyp}, {sample}",
                    "tests": int(tested.sum()),
                    "raw": int(table.loc[tested, column].lt(0.05).sum()),
                    "holm": int(table["holm_p"].lt(0.05).sum()),
                }
            )
    families = pd.DataFrame(families)

    fig, (ax,) = _figure(
        "Almost no surprise-speed test survives correction",
        "Each H5/H6 table runs 75-105 tests. At p < 0.05, about 1 in 20 look significant by chance alone (black tick).",
        left=0.17,
    )
    y = np.arange(len(families))[::-1]
    height = 0.36
    ax.barh(y + height / 2, families["raw"], height=height - 0.04, color=BLUE_LIGHT, label="Raw p < 0.05")
    ax.barh(y - height / 2, families["holm"], height=height - 0.04, color=BLUE, label="Still significant after Holm correction")
    for yy, row in zip(y, families.itertuples()):
        ax.text(row.raw + 0.3, yy + height / 2, str(row.raw), va="center", fontsize=13, color=INK)
        ax.text(row.holm + 0.3, yy - height / 2, str(row.holm), va="center", fontsize=13, color=INK)
        chance = 0.05 * row.tests
        ax.plot([chance, chance], [yy + 0.02, yy + height + 0.1], color=INK, linewidth=3, solid_capstyle="round", zorder=4)
    ax.set_yticks(y, [f"{r.label}\n({r.tests} tests)" for r in families.itertuples()])
    ax.set_xlabel("Number of tests")
    ax.set_xlim(0, families["raw"].max() * 1.25)
    ax.set_ylim(-0.7, len(families) - 0.2)
    ax.plot([], [], color=INK, linewidth=3, label="Expected by chance (5% of tests)")
    ax.legend(loc="lower right", frameon=False, fontsize=13)
    _grid(ax, "x")
    _save(
        fig,
        "slide_18_multiple_testing.png",
        "The 3 H5 tests that survive at 93 meetings are all ZN statement cells. Source: holm_p columns in tables/fomc_h5_*.csv and fomc_h6_*.csv.",
    )


TERCILE_COLOR = {"small": "#86b6ef", "medium": BLUE, "large": "#104281"}
TERCILE_NAME = {"small": "Small surprise", "medium": "Medium", "large": "Large surprise"}


def main() -> None:
    slide_16_first_quote()
    slide_17_surprise_speed()
    slide_18_multiple_testing()


if __name__ == "__main__":
    main()
