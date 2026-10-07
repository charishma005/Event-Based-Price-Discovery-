"""Bid-ask spread and best bid / best ask around FOMC statements, by rate action and surprise size.

Reads the one-second books from extract_fomc_book_seconds. Per event and
instrument, at every second:
  spread_ticks = (ask - bid) / tick            ES 0.25, NQ 0.25, ZN 1/64
  one_tick     = spread is one tick
  bid_offset, ask_offset = (bid or ask - reference mid) / tick, where the
      reference mid is the book in force at the statement second (2:00:00.000),
      direction-aligned: multiplied by -sign(USMPD statement surprise), so a
      positive offset means the quote moved the way the news implied (a hawkish
      surprise should lower all three contracts). Meetings with zero surprise
      are left out of the aligned paths.
Minute values are means of the 60 seconds (spreads take a few whole-tick values,
so medians would step). Across meetings: mean with a 25-75% band.

Figures per instrument (figures/paper/):
  figure_spread_<inst>_all.png                1x2  spread in ticks; time at one tick
  figure_spread_<inst>_by_action.png          1x3  hike / hold / cut
  figure_spread_<inst>_by_surprise.png        1x3  small / medium / large
  figure_spread_<inst>_action_x_surprise.png  3x3  (each meeting drawn where n < 5)
  figure_quotes_<inst>_by_action.png          1x3  best bid and best ask paths, ticks
  figure_quotes_<inst>_by_surprise.png        1x3
  figure_spread_<inst>_zoom.png               1x3  second by second, -60 s to +120 s

Run: python -m scripts.plot_fomc_spread
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.extract_fomc_book_seconds import load
from src.events.meeting_groups import ACTIONS, SURPRISES, meeting_groups
from src.utils.config import PROJECT_ROOT

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
TICK = {"ES.v.0": 0.25, "NQ.v.0": 0.25, "ZN.v.0": 1 / 64}
BASELINE = (-5, -2)  # minutes, inclusive
MIN_FOR_BAND = 5
ZOOM = (-60, 120)  # seconds
FOMC_COLOR, CONTROL = "#1f5fa8", "#8a8a8a"
BID, ASK = "#1f5fa8", "#c0392b"
FIGURES = PROJECT_ROOT / "figures" / "paper"


# ---------------------------------------------------------------- measures

def check_ticks(book: pd.DataFrame) -> None:
    """Warn if the smallest spread seen differs from the configured tick."""
    for instrument, group in book.groupby("instrument"):
        spread = (group["ask"] - group["bid"]).dropna()
        smallest = spread.loc[spread > 0].min()
        if instrument in TICK and not np.isclose(smallest, TICK[instrument], rtol=1e-3):
            print(f"WARNING {instrument}: smallest spread {smallest} differs from tick {TICK[instrument]}")


def second_measures(book: pd.DataFrame, direction: pd.Series | None) -> pd.DataFrame:
    """Spread, one-tick flag and reference-relative bid/ask offsets per second."""
    data = book.dropna(subset=["bid", "ask"]).copy()
    tick = data["instrument"].map(TICK)
    data["spread_ticks"] = (data["ask"] - data["bid"]) / tick
    data["one_tick"] = np.isclose(data["spread_ticks"], 1.0, atol=0.01).astype(float)
    mid = (data["bid"] + data["ask"]) / 2
    reference = mid.where(data["second"].eq(0)).groupby([data["id"], data["instrument"]]).transform("max")
    sign = data["id"].map(direction) if direction is not None else np.nan
    data["bid_offset"] = (data["bid"] - reference) / tick * sign
    data["ask_offset"] = (data["ask"] - reference) / tick * sign
    data["minute"] = np.floor(data["second"] / 60).astype(int)
    return data


def minute_panel(seconds: pd.DataFrame) -> pd.DataFrame:
    metrics = ["spread_ticks", "one_tick", "bid_offset", "ask_offset"]
    panel = seconds.groupby(["kind", "id", "instrument", "minute"])[metrics].mean().reset_index()
    base = panel.loc[panel["minute"].between(*BASELINE)].groupby(["id", "instrument"])["spread_ticks"].mean()
    panel["spread_ratio"] = panel["spread_ticks"] / panel.set_index(["id", "instrument"]).index.map(base)
    return panel


def _stats(values: pd.Series) -> pd.Series:
    return pd.Series({"n": values.notna().sum(), "mean": values.mean(),
                      "q25": values.quantile(0.25), "q75": values.quantile(0.75)})


def summarize(panel: pd.DataFrame, groups: pd.DataFrame, x: str, metrics: list[str]) -> pd.DataFrame:
    """Mean and quartiles per instrument, grouping, group, metric and x (minute or second)."""
    long = panel.melt(id_vars=["kind", "id", "instrument", x], value_vars=metrics, var_name="metric")
    fomc = long.loc[long["kind"].eq("fomc")].merge(
        groups[["meeting", "action", "surprise"]], left_on="id", right_on="meeting"
    )
    fomc["action_x_surprise"] = fomc["action"] + "|" + fomc["surprise"].astype(str)
    parts = [fomc.assign(grouping="all", group="all")]
    parts += [fomc.assign(grouping=g, group=fomc[g]) for g in ("action", "surprise", "action_x_surprise")]
    parts.append(long.loc[long["kind"].eq("control")].assign(grouping="control", group="control"))
    data = pd.concat(parts, ignore_index=True)
    return (
        data.groupby(["instrument", "grouping", "group", "metric", x])["value"].apply(_stats).unstack().reset_index()
    )


# ---------------------------------------------------------------- plotting helpers (also used by plot_fomc_price_paths)

def series(summary, instrument, grouping, group, metric, x="minute"):
    return summary.loc[
        summary["instrument"].eq(instrument) & summary["grouping"].eq(grouping)
        & summary["group"].eq(group) & summary["metric"].eq(metric)
    ].sort_values(x)


def band(ax, data, color, label=None, x="minute", centre="mean", shift=0.5, lw=1.8, alpha=0.15):
    if data.empty:
        return
    xs = data[x] + shift
    ax.fill_between(xs, data["q25"], data["q75"], color=color, alpha=alpha, lw=0)
    ax.plot(xs, data[centre], color=color, lw=lw, label=label)


def mark_events(ax, reference=None, press=30, xmax=40):
    if reference is not None:
        ax.axhline(reference, color="black", lw=0.6, ls=":")
    ax.axvline(0, color="black", lw=0.9, ls="--")
    if press is not None:
        ax.axvline(press, color="black", lw=0.9, ls="-.")
    ax.set_xlim(-5, xmax)


def group_title(grouping: str, group: str, n: int) -> str:
    label = f"{group} surprise" if grouping == "surprise" else group
    return f"{label.capitalize()} (n={n})"


def _n(data) -> int:
    return 0 if data.empty else int(data["n"].max())


# ---------------------------------------------------------------- figures

def plot_all(summary, instrument, output):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, metric, ylabel in ((axes[0], "spread_ticks", "Mean spread (ticks)"),
                               (axes[1], "one_tick", "Share of time at one tick")):
        band(ax, series(summary, instrument, "control", "control", metric), CONTROL, "Normal days")
        data = series(summary, instrument, "all", "all", metric)
        band(ax, data, FOMC_COLOR, f"FOMC days (n={_n(data)})")
        mark_events(ax)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Minutes from FOMC statement")
    axes[1].set_ylim(0, 1.05)
    axes[0].legend(fontsize=9, frameon=False)
    fig.suptitle(f"{instrument[:2]}: bid-ask spread around FOMC statements (mean, 25-75% band)")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_one_by_three(summary, instrument, grouping, order, output, metric="spread_ticks",
                      ylabel="Mean spread (ticks)"):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    for ax, group in zip(axes, order):
        band(ax, series(summary, instrument, "control", "control", metric), CONTROL, "Normal days")
        data = series(summary, instrument, grouping, group, metric)
        band(ax, data, FOMC_COLOR, "FOMC days")
        mark_events(ax)
        ax.set_title(group_title(grouping, group, _n(data)))
        ax.set_xlabel("Minutes from FOMC statement")
    axes[0].set_ylabel(ylabel)
    axes[0].legend(fontsize=9, frameon=False)
    by = "rate action" if grouping == "action" else "statement-surprise size"
    fig.suptitle(f"{instrument[:2]}: bid-ask spread around FOMC statements, by {by}")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_three_by_three(summary, panel, groups, instrument, output, metric="spread_ticks"):
    fig, axes = plt.subplots(3, 3, figsize=(16, 11), sharex=True, sharey=True)
    members = groups.set_index("meeting")
    control = series(summary, instrument, "control", "control", metric)
    for r, action in enumerate(ACTIONS):
        for c, surprise in enumerate(SURPRISES):
            ax = axes[r, c]
            ids = members.index[members["action"].eq(action) & members["surprise"].eq(surprise)]
            events = panel.loc[panel["kind"].eq("fomc") & panel["instrument"].eq(instrument) & panel["id"].isin(ids)]
            n = events["id"].nunique()
            band(ax, control, CONTROL)
            if n >= MIN_FOR_BAND:
                band(ax, series(summary, instrument, "action_x_surprise", f"{action}|{surprise}", metric), FOMC_COLOR)
                note = ""
            else:
                for _, event in events.groupby("id"):
                    event = event.sort_values("minute")
                    ax.plot(event["minute"] + 0.5, event[metric], color=FOMC_COLOR, lw=0.9, alpha=0.6)
                note = ", each meeting shown"
            mark_events(ax)
            ax.set_title(f"{action.capitalize()} / {surprise} surprise (n={n}{note})", fontsize=10)
            if r == 2:
                ax.set_xlabel("Minutes from FOMC statement")
            if c == 0:
                ax.set_ylabel("Mean spread (ticks)")
    fig.suptitle(f"{instrument[:2]}: bid-ask spread, rate action x surprise size (grey = normal days)")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_quotes(summary, instrument, grouping, order, output):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    for ax, group in zip(axes, order):
        ask = series(summary, instrument, grouping, group, "ask_offset")
        bid = series(summary, instrument, grouping, group, "bid_offset")
        band(ax, ask, ASK, "Best ask")
        band(ax, bid, BID, "Best bid")
        mark_events(ax, reference=0)
        ax.set_title(group_title(grouping, group, _n(bid)))
        ax.set_xlabel("Minutes from FOMC statement")
    axes[0].set_ylabel("Ticks from the 2:00:00 mid,\nin the direction the news implies")
    axes[0].legend(fontsize=9, frameon=False)
    by = "rate action" if grouping == "action" else "statement-surprise size"
    fig.suptitle(f"{instrument[:2]}: where the best bid and best ask go after the statement, by {by}")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def plot_zoom(zoom, instrument, output):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    control = series(zoom, instrument, "control", "control", "spread_ticks", x="second")
    for ax, group in zip(axes, SURPRISES):
        band(ax, control, CONTROL, "Normal days", x="second", shift=0, lw=1.2)
        data = series(zoom, instrument, "surprise", group, "spread_ticks", x="second")
        band(ax, data, FOMC_COLOR, "FOMC days", x="second", shift=0, lw=1.2)
        ax.axvline(0, color="black", lw=0.9, ls="--")
        ax.set_xlim(*ZOOM)
        ax.set_title(group_title("surprise", group, _n(data)))
        ax.set_xlabel("Seconds from FOMC statement")
    axes[0].set_ylabel("Mean spread (ticks)")
    axes[0].legend(fontsize=9, frameon=False)
    fig.suptitle(f"{instrument[:2]}: spread second by second around the statement, by surprise size")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def print_summary(summary) -> None:
    print("\nMean spread in ticks: minutes -5..-2 | minute -1 | peak (minute) | back within 10% of -5..-2 by")
    for instrument in INSTRUMENTS:
        print(f"\n{instrument}")
        for grouping, order in (("all", ("all",)), ("control", ("control",)), ("action", ACTIONS), ("surprise", SURPRISES)):
            for group in order:
                s = series(summary, instrument, grouping, group, "spread_ticks").set_index("minute")["mean"]
                one = series(summary, instrument, grouping, group, "one_tick").set_index("minute")["mean"]
                if s.empty:
                    continue
                base = s.loc[BASELINE[0]:BASELINE[1]].mean()
                peak = s.idxmax()
                after = s.loc[peak:]
                back = after.loc[after.le(base * 1.1)]
                back_by = f"{int(back.index[0]):+d}" if not back.empty else f">{int(s.index.max()):+d}"
                print(f"  {group:>8}: {base:5.2f} | {s.get(-1, np.nan):5.2f} | {s.max():5.2f} ({int(peak):+d}) | {back_by:>5}"
                      f"   one tick {one.loc[BASELINE[0]:BASELINE[1]].mean():.0%} before, {one.get(0, np.nan):.0%} at minute 0")


def main() -> None:
    groups = meeting_groups()
    direction = -np.sign(groups.set_index("meeting")["surprise_value"]).replace(0, np.nan)
    fomc, control = load("fomc"), load("control")
    check_ticks(fomc)
    seconds = pd.concat([second_measures(fomc, direction), second_measures(control, None)], ignore_index=True)
    panel = minute_panel(seconds)
    metrics = ["spread_ticks", "spread_ratio", "one_tick", "bid_offset", "ask_offset"]
    summary = summarize(panel, groups, "minute", metrics)
    zoom = summarize(seconds.loc[seconds["second"].between(*ZOOM)], groups, "second", ["spread_ticks"])
    summary.to_csv(PROJECT_ROOT / "tables" / "fomc_spread_minute.csv", index=False)
    zoom.to_csv(PROJECT_ROOT / "tables" / "fomc_spread_seconds.csv", index=False)

    FIGURES.mkdir(parents=True, exist_ok=True)
    for instrument in INSTRUMENTS:
        name = instrument[:2]
        plot_all(summary, instrument, FIGURES / f"figure_spread_{name}_all.png")
        plot_one_by_three(summary, instrument, "action", ACTIONS, FIGURES / f"figure_spread_{name}_by_action.png")
        plot_one_by_three(summary, instrument, "surprise", SURPRISES, FIGURES / f"figure_spread_{name}_by_surprise.png")
        plot_three_by_three(summary, panel, groups, instrument, FIGURES / f"figure_spread_{name}_action_x_surprise.png")
        plot_quotes(summary, instrument, "action", ACTIONS, FIGURES / f"figure_quotes_{name}_by_action.png")
        plot_quotes(summary, instrument, "surprise", SURPRISES, FIGURES / f"figure_quotes_{name}_by_surprise.png")
        plot_zoom(zoom, instrument, FIGURES / f"figure_spread_{name}_zoom.png")
    print_summary(summary)
    print("\nWrote 21 figures to figures/paper/ and tables/fomc_spread_{minute,seconds}.csv")


if __name__ == "__main__":
    main()
