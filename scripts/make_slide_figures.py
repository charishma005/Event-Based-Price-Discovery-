"""Slide figures for the 2015-2026 FOMC results (one PNG per slide).

Reads only committed processed files and the paper's 12-meeting control
numbers, so it runs without the raw DBN cache:

- data/processed/fomc_sample_2015_2026/timing_liquidity.csv   (H2, H4)
- data/processed/fomc_sample_2015_2026/response_horizons.csv  (H2)
- data/processed/fomc_sample_2015_2026/speed_metrics.parquet  (H5)
- tables/fomc_h5_surprise_speed*.csv, tables/fomc_h6_surprise_asymmetry*.csv

Writes figures/fomc_sample_2015_2026/slides/slide_1{5,6,7,8}_*.png.
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


def slide_15_depth() -> None:
    fig, (left, right) = _figure(
        "Market makers pull displayed depth before FOMC announcements",
        "Depth ratio = touch depth in the final minute / the prior four minutes. Below 1 = depth withdrawn.",
        ncols=2,
        widths=[1, 1.35],
    )
    # Left: 12 meetings against matched control days (paper section 4.6).
    rows = [("All three", 0.563, 1.026), ("ES", 0.567, 1.003), ("NQ", 0.951, 1.033), ("ZN", 0.171, 1.041)]
    for y, (label, event, control) in enumerate(reversed(rows)):
        left.plot([event, control], [y, y], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
        left.scatter(control, y, s=110, color=MUTED, edgecolor=SURFACE, linewidth=2, zorder=3)
        left.scatter(event, y, s=110, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        left.text(event - 0.04, y + 0.22, f"{event:.2f}", ha="center", color=INK, fontsize=12)
        left.text(control + 0.04, y + 0.22, f"{control:.2f}", ha="center", color=INK_2, fontsize=12)
    left.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
    left.set_ylim(-0.6, len(rows) - 0.3)
    left.set_xlim(0, 1.25)
    left.axvline(1, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    left.set_xlabel("Mean depth ratio")
    left.set_title("12 meetings vs matched control days", loc="left", fontsize=15, pad=14)
    left.text(0.17, len(rows) - 0.55, "FOMC day", color=BLUE, fontsize=12, fontweight="bold")
    left.text(1.05, len(rows) - 0.55, "Control day", color=INK_2, fontsize=12, fontweight="bold", ha="center")
    left.text(0.02, -0.5, "p = 0.00024, lower in 12 of 12 meetings", color=INK_2, fontsize=12)
    _grid(left, "x")

    # Right: 93 meetings, same-event comparison only.
    timing = _timing()
    rng = np.random.default_rng(7)
    groups = [(sub, inst) for sub in ("statement", "press_conference") for inst in INSTRUMENT_COLOR]
    for x, (sub, inst) in enumerate(groups):
        x = x + (0.6 if sub == "press_conference" else 0)
        values = timing.loc[timing["subevent"].eq(sub) & timing["instrument"].eq(inst), "pre60_to_baseline_depth_ratio"].dropna()
        right.scatter(
            x + rng.uniform(-0.22, 0.22, len(values)), values, s=16, color=INSTRUMENT_COLOR[inst], alpha=0.55, linewidth=0
        )
        median = values.median()
        right.plot([x - 0.3, x + 0.3], [median, median], color=INK, linewidth=2.5, solid_capstyle="round")
        right.text(x, median * 1.12 if median < 0.6 else median * 0.80, f"{median:.2f}", ha="center", fontsize=12, color=INK, fontweight="bold", path_effects=HALO)
    right.set_yscale("log")
    right.set_yticks([0.05, 0.1, 0.25, 0.5, 1, 2], ["0.05", "0.1", "0.25", "0.5", "1", "2"])
    right.set_ylim(0.03, 3)
    right.axhline(1, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    positions = [0, 1, 2, 3.6, 4.6, 5.6]
    right.set_xticks(positions, [INSTRUMENT_NAME[i] for _, i in groups])
    for label, tick in zip(right.get_xticklabels(), groups):
        label.set_color(INSTRUMENT_COLOR[tick[1]] if tick[1] != "ZN.v.0" else "#128a5f")
        label.set_fontweight("bold")
    right.text(1, 2.45, "Statement (92 meetings)", ha="center", fontsize=13, color=INK)
    right.text(4.6, 2.45, "Press conference (76)", ha="center", fontsize=13, color=INK)
    right.set_ylabel("Depth ratio (log scale); bar = median")
    right.set_title("93 meetings, 2015-2026: same-day comparison, no controls", loc="left", fontsize=15, pad=14)
    _grid(right)
    _save(
        fig,
        "slide_15_h4_depth_withdrawal.png",
        "Left: paper section 4.6 (2024-2025). Right: timing_liquidity.csv, fomc_sample_2015_2026. Controls for 2015-2023 not yet collected.",
    )


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


def h5_response_profile() -> None:
    """Median |R_h| by surprise tercile; a second figure for the share of the 30-minute move when present."""
    profile = pd.read_csv(TABLES / "fomc_h5_response_profile_2015_2026.csv")
    h5a = pd.read_csv(TABLES / "fomc_h5a_response_magnitude_2015_2026.csv")
    horizons = sorted(profile["horizon_seconds"].unique())
    labels = profile.drop_duplicates("horizon_seconds").set_index("horizon_seconds")["horizon"]
    headline = h5a.loc[h5a["measure"].eq("STMT") & h5a["instrument"].isin(["equity_average", "ZN.v.0"])]
    robust = bool(headline["spearman_rho"].gt(0).all() and headline["holm_p"].lt(0.05).all())
    span = f"{labels[horizons[0]]} to {labels[horizons[-1]]}"
    panels = (("equity_average", "ES + NQ average"), ("ZN.v.0", "ZN (10-year Treasury)"))

    def draw(column: str, ylabel: str, name: str, title: str, subtitle: str, source: str) -> None:
        fig, axes = _figure(title, subtitle, ncols=2)
        for ax, (instrument, label) in zip(axes, panels):
            rows = profile.loc[profile["instrument"].eq(instrument)]
            ends = []
            for group in ("small", "medium", "large"):
                line = rows.loc[rows["surprise_group"].eq(group)].set_index("horizon_seconds")[column].reindex(horizons)
                x = np.arange(len(horizons))
                ax.plot(x, line, color=TERCILE_COLOR[group], linewidth=2.5, marker="o", markersize=8,
                        markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
                last = line.last_valid_index()
                if last is not None:
                    ends.append([line[last], horizons.index(last), TERCILE_NAME[group]])
            # Direct labels at line ends, pushed apart so they never overlap.
            low, high = ax.get_ylim()
            gap = 0.06 * (high - low)
            ends.sort()
            for i in range(1, len(ends)):
                ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
            for y, x, text in ends:
                ax.text(x + 0.15, y, text, va="center", fontsize=12, color=INK, path_effects=HALO)
            ax.set_xticks(np.arange(len(horizons)), [labels[h] for h in horizons])
            ax.set_xlim(-0.3, len(horizons) + 0.9)
            ax.set_ylim(bottom=0)
            ax.set_xlabel("Time after the 2:00 p.m. statement")
            ax.set_title(label, loc="left", fontsize=16, pad=14, color=INK, fontweight="bold")
            _grid(ax)
        axes[0].set_ylabel(ylabel)
        _save(fig, name, source)

    draw(
        "median_abs_return_bp", "Median |return| (basis points)", "h5a_response_profile.png",
        "Larger statement surprises move prices more at every horizon" if robust else "Response size by statement surprise size",
        f"FOMC statements 2015-2026, meetings split into thirds by |USMPD statement surprise|. Horizons {span}.",
        "Source: tables/fomc_h5_response_profile_2015_2026.csv; tests in tables/fomc_h5a_response_magnitude_2015_2026.csv.",
    )
    if "median_fraction_of_30m" in profile and profile["median_fraction_of_30m"].notna().any():
        profile.loc[profile["horizon_seconds"].eq(1800), "median_fraction_of_30m"] = 1.0
        draw(
            "median_fraction_of_30m", "Median share of the 30-minute move", "h5b_fraction_profile.png",
            "How much of the 30-minute move is done early, by surprise size",
            "|R_h| / |R_30m|. Events with the smallest 30-minute moves (bottom quartile) are excluded.",
            "Source: tables/fomc_h5_response_profile_2015_2026.csv; tests in tables/fomc_h5b_response_fraction_2015_2026.csv.",
        )


def main() -> None:
    slide_15_depth()
    slide_16_first_quote()
    slide_17_surprise_speed()
    slide_18_multiple_testing()
    h5_response_profile()


if __name__ == "__main__":
    main()
