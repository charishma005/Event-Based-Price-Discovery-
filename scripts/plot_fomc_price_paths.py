"""H5 and H6 price paths from 1 second to 40 minutes, by surprise size and rate action.

Reads the one-second books from extract_fomc_book_seconds. The return to second
h is R_h = 10,000 x ln(mid_h / mid_0) in bp, where mid_0 is the book in force at
the statement second (2:00:00.000). ES, NQ and ZN are plotted separately; the
tables also carry "equity_average", the mean of the ES and NQ returns. Minute 30 is the press-conference start; later points mix in the
press conference.

H5, "with mod" (size only):   |R_h| = a + b |S| + e
H6, "without mod" (direction): R_h = a + b_hawk S+ + b_dove S- + e, on meetings
    without the smallest 25% of |S| (their sign is close to arbitrary), as in
    analyze_fomc_h6_horizons. Slopes are shown as bp per bp of surprise in the
    direction the news implies (hawkish should lower all three contracts).
S = USMPD statement surprise, converted from percentage points to bp. HC1 standard errors; Holm across horizons per
instrument for H5; Wald test of b_hawk = b_dove for H6.

Figures (figures/paper/):
  figure_h5_paths_overlay_{surprise,action}.png   1x3  ES, NQ, ZN; a line per group
  figure_h5_paths_{surprise,action}.png            1x3  one panel per group
  figure_h5_paths_action_x_surprise.png            3x3
  figure_h5_slopes.png                                  slope per horizon, 95% CI
  figure_h6_paths_hawk_dove.png                    1x3  ES, NQ, ZN; signed paths
  figure_h6_paths_{surprise,action}.png            1x3  aligned move per group
  figure_h6_paths_action_x_surprise.png            3x3
  figure_h6_slopes.png                             1x3  hawkish vs dovish slopes

Run: python -m scripts.plot_fomc_price_paths
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from scripts.extract_fomc_book_seconds import load
from src.events.meeting_groups import ACTIONS, SURPRISES, meeting_groups
from src.utils.config import PROJECT_ROOT

HORIZONS = (1, 5, 30, 60, 300, 600, 1200, 1800)
LABEL = {1: "1s", 5: "5s", 30: "30s", 60: "1m", 300: "5m", 600: "10m", 1200: "20m", 1800: "30m"}
LAST_SECOND = 40 * 60 - 1
SMALL_SURPRISE_QUANTILE = 0.25
MIN_FOR_BAND = 5
# Plotted separately; the ES+NQ average ("equity_average") is kept in the tables only.
UNITS = {"ES.v.0": ("ES (S&P 500)", "#2a78d6"), "NQ.v.0": ("NQ (Nasdaq-100)", "#eb6834"),
         "ZN.v.0": ("ZN (10-year Treasury)", "#1baf7a")}
ALL_UNITS = ("ES.v.0", "NQ.v.0", "ZN.v.0", "equity_average")
PP_TO_BP = 100  # USMPD surprises are in percentage points; slopes are reported per bp, as on the slides
GROUP_SHADES = {"small": "#9cc3f0", "medium": "#4a8fdc", "large": "#123e75",
                "hike": "#c0392b", "hold": "#7f8c8d", "cut": "#1f5fa8"}
HAWK, DOVE = "#d64545", "#2a78d6"
FIGURES = PROJECT_ROOT / "figures" / "paper"
TABLES = PROJECT_ROOT / "tables"


# ---------------------------------------------------------------- returns

def path_seconds() -> np.ndarray:
    grid = np.unique(np.round(np.logspace(0, np.log10(LAST_SECOND), 60)).astype(int))
    return np.union1d(grid, HORIZONS)


def returns(book: pd.DataFrame) -> pd.DataFrame:
    """R_h in bp for each meeting, unit and second in path_seconds()."""
    data = book.dropna(subset=["bid", "ask"])
    data = data.assign(mid=(data["bid"] + data["ask"]) / 2)
    ref = data.loc[data["second"].eq(0)].set_index(["id", "instrument"])["mid"]
    data = data.loc[data["second"].isin(path_seconds())]
    base = data.set_index(["id", "instrument"]).index.map(ref)
    data = data.assign(R=1e4 * np.log(data["mid"].to_numpy() / np.asarray(base, float)))
    data = data.dropna(subset=["R"])[["id", "instrument", "second", "R"]]
    equity = (
        data.loc[data["instrument"].isin(["ES.v.0", "NQ.v.0"])]
        .groupby(["id", "second"])["R"].agg(["mean", "count"]).reset_index()
    )
    equity = equity.loc[equity["count"].eq(2)].rename(columns={"mean": "R"}).drop(columns="count")
    return pd.concat([data, equity.assign(instrument="equity_average")], ignore_index=True)


def attach(paths: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    data = paths.merge(groups[["meeting", "action", "surprise", "surprise_value"]], left_on="id", right_on="meeting")
    data["absR"] = data["R"].abs()
    data["aligned"] = data["R"] * -np.sign(data["surprise_value"]).replace(0, np.nan)
    data["action_x_surprise"] = data["action"] + "|" + data["surprise"].astype(str)
    return data


def _stats(values: pd.Series) -> pd.Series:
    return pd.Series({"n": values.notna().sum(), "median": values.median(),
                      "q25": values.quantile(0.25), "q75": values.quantile(0.75)})


def profile(data: pd.DataFrame, value: str) -> pd.DataFrame:
    parts = [data.assign(grouping="all", group="all")]
    parts += [data.assign(grouping=g, group=data[g]) for g in ("action", "surprise", "action_x_surprise")]
    if "side" in data:
        parts.append(data.dropna(subset=["side"]).assign(grouping="side", group=lambda d: d["side"]))
    stacked = pd.concat(parts, ignore_index=True)
    return (
        stacked.groupby(["instrument", "grouping", "group", "second"])[value].apply(_stats).unstack().reset_index()
        .assign(value=value)
    )


# ---------------------------------------------------------------- regressions

def h5_slopes(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for unit in ALL_UNITS:
        for h in HORIZONS:
            sample = data.loc[data["instrument"].eq(unit) & data["second"].eq(h)].dropna(subset=["absR", "surprise_value"])
            if len(sample) < 10:
                continue
            x = sample["surprise_value"].abs() * PP_TO_BP
            fit = sm.OLS(sample["absR"], sm.add_constant(x)).fit(cov_type="HC1")
            beta, se = fit.params.iloc[1], fit.bse.iloc[1]
            rows.append({"instrument": unit, "horizon_seconds": h, "horizon": LABEL[h], "n": len(sample),
                         "alpha_bp": fit.params.iloc[0], "beta": beta, "se": se,
                         "ci_low": beta - 1.96 * se, "ci_high": beta + 1.96 * se,
                         "p": fit.pvalues.iloc[1]})
    out = pd.DataFrame(rows)
    out["holm_p"] = out.groupby("instrument")["p"].transform(lambda p: multipletests(p, method="holm")[1])
    return out


def h6_sample(data: pd.DataFrame) -> pd.DataFrame:
    magnitude = data.drop_duplicates("id").set_index("id")["surprise_value"].abs()
    keep = magnitude.index[magnitude.gt(magnitude.quantile(SMALL_SURPRISE_QUANTILE)) & magnitude.gt(0)]
    sample = data.loc[data["id"].isin(keep)].copy()
    sample["side"] = np.where(sample["surprise_value"] > 0, "hawkish", "dovish")
    return sample


def h6_slopes(sample: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for unit in ALL_UNITS:
        for h in HORIZONS:
            data = sample.loc[sample["instrument"].eq(unit) & sample["second"].eq(h)].dropna(subset=["R"])
            if len(data) < 10:
                continue
            s = data["surprise_value"] * PP_TO_BP
            X = sm.add_constant(pd.DataFrame({"hawk": s.clip(lower=0), "dove": s.clip(upper=0)}))
            fit = sm.OLS(data["R"], X).fit(cov_type="HC1")
            equal = fit.wald_test("hawk = dove", scalar=True)
            row = {"instrument": unit, "horizon_seconds": h, "horizon": LABEL[h], "n": len(data),
                   "n_hawkish": int((s > 0).sum()), "n_dovish": int((s < 0).sum()),
                   "p_equal": float(equal.pvalue)}
            for side in ("hawk", "dove"):
                # Implied direction: a positive surprise should lower prices, so report -beta.
                beta, se = -fit.params[side], fit.bse[side]
                row.update({f"{side}_move_per_bp": beta, f"{side}_ci_low": beta - 1.96 * se,
                            f"{side}_ci_high": beta + 1.96 * se})
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- plotting

def _axis(ax, zero=False):
    ax.set_xscale("log")
    ax.set_xlim(1, LAST_SECOND)
    ticks = [h for h in HORIZONS if h != 1200]  # 20m crowds 30m on a log axis
    ax.set_xticks(ticks, [LABEL[h] for h in ticks])
    ax.minorticks_off()
    ax.axvline(1800, color="black", lw=0.8, ls="-.")
    if zero:
        ax.axhline(0, color="black", lw=0.6)
    ax.grid(axis="y", color="#e4e3df")
    ax.set_xlabel("Time after 2:00 p.m. (log scale; dash-dot = press conference)")


def _series(prof, unit, grouping, group):
    return prof.loc[prof["instrument"].eq(unit) & prof["grouping"].eq(grouping) & prof["group"].eq(group)].sort_values("second")


def _line(ax, data, color, label, band=True):
    if data.empty:
        return
    if band:
        ax.fill_between(data["second"], data["q25"], data["q75"], color=color, alpha=0.13, lw=0)
    ax.plot(data["second"], data["median"], color=color, lw=2, label=label)


def plot_overlay(prof, grouping, order, title, ylabel, output, zero=False, units=UNITS):
    """Slide style: one panel per unit, a line per group."""
    fig, axes = plt.subplots(1, len(units), figsize=(6.5 * len(units), 5), sharey=True)
    for ax, (unit, (name, _)) in zip(axes, units.items()):
        for group in order:
            data = _series(prof, unit, grouping, group)
            n = 0 if data.empty else int(data["n"].max())
            _line(ax, data, GROUP_SHADES.get(group, HAWK if group == "hawkish" else DOVE),
                  f"{group} (n={n})", band=False)
        _axis(ax, zero)
        ax.set_title(name, loc="left", fontweight="bold")
    axes[0].set_ylabel(ylabel)
    axes[0].legend(frameon=False, fontsize=10)
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_panels(prof, grouping, order, title, ylabel, output, zero=False, units=UNITS):
    """One panel per group, a line per unit with its 25-75% band."""
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8), sharey=True)
    for ax, group in zip(axes, order):
        n = 0
        for unit, (name, color) in units.items():
            data = _series(prof, unit, grouping, group)
            n = max(n, 0 if data.empty else int(data["n"].max()))
            _line(ax, data, color, name)
        _axis(ax, zero)
        label = f"{group} surprise" if grouping == "surprise" else group
        ax.set_title(f"{label.capitalize()} (n={n})")
    axes[0].set_ylabel(ylabel)
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_grid(prof, data, value, title, ylabel, output, zero=False, units=UNITS):
    fig, axes = plt.subplots(3, 3, figsize=(17, 11), sharex=True, sharey=True)
    for r, action in enumerate(ACTIONS):
        for c, surprise in enumerate(SURPRISES):
            ax = axes[r, c]
            cell = f"{action}|{surprise}"
            members = data.loc[data["action_x_surprise"].eq(cell)]
            n = members["id"].nunique()
            for unit, (name, color) in units.items():
                if n >= MIN_FOR_BAND:
                    _line(ax, _series(prof, unit, "action_x_surprise", cell), color, name)
                else:
                    for _, event in members.loc[members["instrument"].eq(unit)].groupby("id"):
                        event = event.sort_values("second")
                        ax.plot(event["second"], event[value], color=color, lw=0.9, alpha=0.6)
            _axis(ax, zero)
            note = "" if n >= MIN_FOR_BAND else ", each meeting shown"
            ax.set_title(f"{action.capitalize()} / {surprise} surprise (n={n}{note})", fontsize=10)
            if r < 2:
                ax.set_xlabel("")
            if c == 0:
                ax.set_ylabel(ylabel)
    handles = [plt.Line2D([], [], color=color, lw=2, label=name) for name, color in units.values()]
    fig.legend(handles=handles, loc="upper right", frameon=False)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def plot_h5_slopes(slopes, output, units=UNITS):
    fig, ax = plt.subplots(figsize=(13, 5))
    width = 0.8 / len(units)
    for k, (unit, (name, color)) in enumerate(units.items()):
        data = slopes.loc[slopes["instrument"].eq(unit)]
        x = np.arange(len(data)) + (k - (len(units) - 1) / 2) * width
        ax.vlines(x, data["ci_low"], data["ci_high"], color=color, lw=2.5)
        for xi, (_, row) in zip(x, data.iterrows()):
            filled = row["holm_p"] < 0.05
            ax.scatter(xi, row["beta"], s=55, color=color if filled else "white", edgecolor=color, lw=2, zorder=3)
        ax.plot([], [], color=color, lw=2.5, label=name)
    ax.axhline(0, color="black", lw=0.8)
    labels = slopes.drop_duplicates("horizon_seconds").sort_values("horizon_seconds")["horizon"]
    ax.set_xticks(range(len(labels)), labels)
    ax.set_xlabel("Time after the 2:00 p.m. statement")
    ax.set_ylabel("bp of price move per 1 bp of surprise")
    ax.legend(frameon=False)
    ax.grid(axis="y", color="#e4e3df")
    ax.set_title("H5: |price move| on |USMPD surprise|, 1 s to 30 min. Bars = 95% CI; filled = significant after Holm",
                 loc="left")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_h6_slopes(slopes, output, units=UNITS):
    fig, axes = plt.subplots(1, len(units), figsize=(7.5 * len(units), 5))
    for ax, (unit, (name, _)) in zip(axes, units.items()):
        data = slopes.loc[slopes["instrument"].eq(unit)].reset_index(drop=True)
        for side, color, shift in (("hawk", HAWK, -0.12), ("dove", DOVE, 0.12)):
            x = np.arange(len(data)) + shift
            ax.vlines(x, data[f"{side}_ci_low"], data[f"{side}_ci_high"], color=color, lw=2.2)
            ax.scatter(x, data[f"{side}_move_per_bp"], color=color, s=40, zorder=3,
                       label="Hawkish" if side == "hawk" else "Dovish")
        top = ax.get_ylim()[1]
        for i, p in enumerate(data["p_equal"]):
            ax.text(i, top, f"p={p:.2f}", ha="center", va="bottom", fontsize=8, color="#52514e")
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(range(len(data)), data["horizon"])
        ax.set_title(name, loc="left", fontweight="bold", pad=18)
        ax.grid(axis="y", color="#e4e3df")
    axes[0].set_ylabel("bp move per 1 bp of surprise,\nin the direction the news implies")
    axes[0].legend(frameon=False)
    fig.suptitle("H6: hawkish vs dovish slopes, 1 s to 30 min (p = test that the two slopes are equal, HC1)")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main() -> None:
    groups = meeting_groups()
    data = attach(returns(load("fomc")), groups)
    FIGURES.mkdir(parents=True, exist_ok=True)

    # H5, with mod: |R|
    h5 = profile(data, "absR")
    slopes5 = h5_slopes(data)
    h5.to_csv(TABLES / "fomc_h5_paths_groups.csv", index=False)
    slopes5.to_csv(TABLES / "fomc_h5_slopes_paths.csv", index=False)
    plot_overlay(h5, "surprise", SURPRISES, "H5: larger surprises move prices more (median |return|)",
                 "Median |return| (bp)", FIGURES / "figure_h5_paths_overlay_surprise.png")
    plot_overlay(h5, "action", ACTIONS, "H5: median |return| by rate action",
                 "Median |return| (bp)", FIGURES / "figure_h5_paths_overlay_action.png")
    for grouping, order in (("surprise", SURPRISES), ("action", ACTIONS)):
        plot_panels(h5, grouping, order, f"H5: median |return| by {grouping} (25-75% band)",
                    "Median |return| (bp)", FIGURES / f"figure_h5_paths_{grouping}.png")
    plot_grid(h5, data, "absR", "H5: median |return|, rate action x surprise size", "Median |return| (bp)",
              FIGURES / "figure_h5_paths_action_x_surprise.png")
    plot_h5_slopes(slopes5, FIGURES / "figure_h5_slopes.png")

    # H6, without mod: signed R
    sample = h6_sample(data)
    h6_signed = profile(sample, "R")
    h6_aligned = profile(data, "aligned")
    slopes6 = h6_slopes(sample)
    pd.concat([h6_signed, h6_aligned]).to_csv(TABLES / "fomc_h6_paths_groups.csv", index=False)
    slopes6.to_csv(TABLES / "fomc_h6_slopes_paths.csv", index=False)
    n_hawk, n_dove = sample.drop_duplicates("id")["side"].value_counts().reindex(["hawkish", "dovish"]).fillna(0).astype(int)
    plot_overlay(h6_signed, "side", ("dovish", "hawkish"),
                 f"H6: hawkish surprises push prices down, dovish up ({n_hawk} hawkish, {n_dove} dovish; median return)",
                 "Median return (bp)", FIGURES / "figure_h6_paths_hawk_dove.png", zero=True)
    for grouping, order in (("surprise", SURPRISES), ("action", ACTIONS)):
        plot_panels(h6_aligned, grouping, order,
                    f"H6: move in the direction the news implies, by {grouping} (median, 25-75% band)",
                    "Median aligned return (bp)", FIGURES / f"figure_h6_paths_{grouping}.png", zero=True)
    plot_grid(h6_aligned, data, "aligned", "H6: move in the direction the news implies, rate action x surprise size",
              "Median aligned return (bp)", FIGURES / "figure_h6_paths_action_x_surprise.png", zero=True)
    plot_h6_slopes(slopes6, FIGURES / "figure_h6_slopes.png")

    cols5 = ["instrument", "horizon", "n", "beta", "ci_low", "ci_high", "holm_p"]
    print("\nH5 slopes (bp of |move| per bp of |surprise|):")
    print(slopes5.loc[slopes5["instrument"].isin(UNITS), cols5].round(3).to_string(index=False))
    cols6 = ["instrument", "horizon", "n_hawkish", "n_dovish", "hawk_move_per_bp", "dove_move_per_bp", "p_equal"]
    print("\nH6 slopes (bp per bp of surprise, in the implied direction):")
    print(slopes6.loc[slopes6["instrument"].isin(UNITS), cols6].round(3).to_string(index=False))
    print("\nWrote 11 figures to figures/paper/ and 4 tables to tables/")


if __name__ == "__main__":
    main()
