"""Bid-side and ask-side depth around FOMC statements, by rate action and surprise size.

Per event and instrument, best-bid size and best-ask size are each carried
forward on a one-second grid and summarized as the median of each minute, from
-5 to +39 minutes around the statement. Bid and ask (and their total) are divided
by their own mean over minutes -5 to -2, as in plot_fomc_depth_profile. Bid share
is bid / (bid + ask) per second, not normalized: 0.5 is a balanced book.

Groups: rate action (hike / hold / cut, from policy_change_bps) and surprise size
(small / medium / large thirds of |USMPD statement surprise|, cut over all
available meetings). Matched 2015-2023 control days (-5 to +9) are drawn in grey.

Figures per instrument, in figures/paper/:
  figure_depth_sides_<inst>_by_action.png          1x3  bid / ask / total ratio
  figure_depth_sides_<inst>_by_surprise.png        1x3  bid / ask / total ratio
  figure_depth_sides_<inst>_action_x_surprise.png  3x3  bid / ask ratio; cells with
                                                        fewer than 5 meetings show
                                                        each meeting's own lines
  figure_bid_share_<inst>.png                      2x3  bid share by action / surprise

Run: python -m scripts.plot_fomc_depth_sides --extend
(--extend first downloads the 16 statement-only meetings out to +40 minutes.)
"""

from __future__ import annotations

import argparse
import gc

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.plot_fomc_depth_profile import _normalize, minute_profile_from_depth
from scripts.process_fomc_placebos import _matching_raw_file as placebo_raw_file
from scripts.process_fomc_sample import _matching_raw_file as meeting_raw_file
from src.events.meeting_groups import ACTIONS, SURPRISES, meeting_groups
from src.utils.config import PROJECT_ROOT, load_yaml

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
LAST_MINUTE = 39
MIN_FOR_BAND = 5
METRICS = ("bid_rel", "ask_rel", "total_rel", "bid_share")
COLORS = {"bid_rel": "#1f5fa8", "ask_rel": "#c0392b", "total_rel": "#222222"}
LABELS = {"bid_rel": "Bid depth", "ask_rel": "Ask depth", "total_rel": "Total depth"}
CONTROL = "#8a8a8a"
OUT = PROJECT_ROOT / "data" / "processed" / "fomc_depth_sides"


# ---------------------------------------------------------------- reading

def read_sides(path, chunk_rows: int = 2_000_000) -> dict[str, pd.DataFrame]:
    """Stream a DBN file; per symbol, bid and ask size of valid quotes indexed by ts_event."""
    import databento as db

    keep = []
    for chunk in db.DBNStore.from_file(path).to_df(count=chunk_rows):
        if chunk.empty:
            continue
        chunk = chunk.reset_index()
        action = chunk["action"].astype(str).str.upper()
        valid = (
            ~action.eq("T")
            & chunk["bid_px_00"].gt(0)
            & chunk["ask_px_00"].gt(chunk["bid_px_00"])
        )
        slim = chunk.loc[valid, ["ts_event", "symbol", "bid_sz_00", "ask_sz_00"]]
        keep.append(slim.rename(columns={"bid_sz_00": "bid", "ask_sz_00": "ask"}))
        del chunk
    if not keep:
        return {}
    quotes = pd.concat(keep, ignore_index=True)
    quotes["ts_event"] = pd.to_datetime(quotes["ts_event"], utc=True)
    quotes[["bid", "ask"]] = quotes[["bid", "ask"]].astype(float)
    return {
        symbol: group.sort_values("ts_event", kind="stable").groupby("ts_event")[["bid", "ask"]].last()
        for symbol, group in quotes.groupby("symbol")
    }


def side_profiles(sides: pd.DataFrame, event: pd.Timestamp, first: int, last: int) -> pd.DataFrame | None:
    """Minute medians of bid, ask, total and bid share, plus baseline-relative ratios."""
    total = sides["bid"] + sides["ask"]
    share = (sides["bid"] / total).where(total > 0)
    out = pd.DataFrame(
        {
            "bid": minute_profile_from_depth(sides["bid"], event, first, last),
            "ask": minute_profile_from_depth(sides["ask"], event, first, last),
            "total": minute_profile_from_depth(total, event, first, last),
            "bid_share": minute_profile_from_depth(share, event, first, last),
        }
    )
    for side in ("bid", "ask", "total"):
        rel = _normalize(out[side])
        if rel is None:
            return None
        out[f"{side}_rel"] = rel
    return out


def _window_rows(window: dict, path, kind: str) -> pd.DataFrame:
    frames = []
    for instrument, sides in read_sides(path).items():
        if instrument not in INSTRUMENTS or sides.empty:
            continue
        profile = side_profiles(sides, window["event"], window["first"], window["last"])
        if profile is None:
            continue
        frames.append(profile.reset_index().assign(kind=kind, id=window["id"], instrument=instrument))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _collect(windows: list[dict], kind: str) -> pd.DataFrame:
    """Per-window results are cached (keyed by coverage), so reruns resume."""
    cache = OUT / "cache" / kind
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, window in enumerate(windows, 1):
        tag = f"[{kind} {i}/{len(windows)}] {window['id']}"
        cached = cache / f"{window['id']}_to{window['last']}.parquet"
        if cached.exists():
            frames.append(pd.read_parquet(cached))
            print(f"{tag}: cached")
            continue
        rows = _window_rows(window, window["path"], kind)
        rows.to_parquet(cached, index=False)
        frames.append(rows)
        print(tag if not rows.empty else f"{tag}: no usable quotes")
        gc.collect()
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------- windows

def meeting_windows(config: str) -> list[dict]:
    from scripts.download_fomc_extensions import extension_windows

    extended = {w["label"]: w for w in extension_windows(config)}
    windows = []
    for m in load_yaml(PROJECT_ROOT / "config" / config)["meetings"]:
        if m.get("dataset_condition", "available") != "available":
            continue
        event = pd.Timestamp(m["statement_time_utc"])
        path = meeting_raw_file(extended[m["label"]]) if m["label"] in extended else None
        source = extended.get(m["label"]) if path is not None else m
        if path is None:
            path = meeting_raw_file(m)
        if path is None:
            print(f"{m['label']}: raw file not cached, skipped")
            continue
        end = (pd.Timestamp(source["request_end_utc"]) - event).total_seconds() / 60
        last = min(LAST_MINUTE, int(end) - 1)
        if last < LAST_MINUTE:
            print(f"{m['label']}: covers only to +{last + 1} min (run with --extend)")
        windows.append({"id": m["label"], "event": event, "first": -5, "last": last, "path": path})
    return windows


def control_windows(config: str) -> list[dict]:
    windows = []
    for p in load_yaml(PROJECT_ROOT / "config" / config)["placebos"]:
        path = placebo_raw_file(p)
        if path is None:
            continue
        event = pd.Timestamp(p["placebo_time_utc"])
        end = (pd.Timestamp(p["request_end_utc"]) - event).total_seconds() / 60
        windows.append({"id": p["placebo_id"], "event": event, "first": -5, "last": int(end) - 1, "path": path})
    return windows


# ---------------------------------------------------------------- summaries

def _quantiles(values: pd.Series) -> pd.Series:
    return pd.Series(
        {"n": values.notna().sum(), "median": values.median(),
         "q25": values.quantile(0.25), "q75": values.quantile(0.75)}
    )


def summarize(panel: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    long = panel.melt(
        id_vars=["kind", "id", "instrument", "minute"], value_vars=list(METRICS), var_name="metric"
    )
    fomc = long.loc[long["kind"].eq("fomc")].merge(
        groups[["meeting", "action", "surprise"]], left_on="id", right_on="meeting"
    )
    fomc["action_x_surprise"] = fomc["action"] + "|" + fomc["surprise"].astype(str)
    parts = [fomc.assign(grouping=g, group=fomc[g]) for g in ("action", "surprise", "action_x_surprise")]
    control = long.loc[long["kind"].eq("control")]
    parts.append(control.assign(grouping="control", group="control"))
    data = pd.concat(parts, ignore_index=True)
    return (
        data.groupby(["instrument", "grouping", "group", "metric", "minute"])["value"]
        .apply(_quantiles)
        .unstack()
        .reset_index()
    )


def _recovery(series: pd.Series) -> str:
    trough = series.idxmin()
    after = series.loc[trough:]
    back = after.loc[after.ge(1)]
    return f"+{int(back.index[0])}" if not back.empty else f">+{int(series.index.max())}"


def print_summary(summary: pd.DataFrame) -> None:
    for instrument in INSTRUMENTS:
        print(f"\n{instrument}: median ratio to minutes -5..-2 (min -1 | low, at | back to 1 by)")
        for grouping, order in (("action", ACTIONS), ("surprise", SURPRISES)):
            for group in order:
                cells = []
                for metric in ("bid_rel", "ask_rel"):
                    s = summary.loc[
                        summary["instrument"].eq(instrument) & summary["grouping"].eq(grouping)
                        & summary["group"].eq(group) & summary["metric"].eq(metric)
                    ].set_index("minute")
                    if s.empty:
                        continue
                    med = s["median"]
                    cells.append(
                        f"{metric[:3]} {med.get(-1, np.nan):.2f} | {med.min():.2f} at {int(med.idxmin()):+d} | {_recovery(med)}"
                    )
                n = summary.loc[
                    summary["instrument"].eq(instrument) & summary["grouping"].eq(grouping)
                    & summary["group"].eq(group) & summary["minute"].eq(0), "n"
                ].max()
                print(f"  {group:>6} (n={0 if pd.isna(n) else int(n):>2}): " + "   ".join(cells))


# ---------------------------------------------------------------- plots

def _series(summary, instrument, grouping, group, metric):
    return summary.loc[
        summary["instrument"].eq(instrument) & summary["grouping"].eq(grouping)
        & summary["group"].eq(group) & summary["metric"].eq(metric)
    ].sort_values("minute")


def _band(ax, data, color, label=None, lw=1.8, alpha=0.15):
    x = data["minute"] + 0.5
    ax.fill_between(x, data["q25"], data["q75"], color=color, alpha=alpha, lw=0)
    ax.plot(x, data["median"], color=color, lw=lw, label=label)


def _decorate(ax, reference: float, press: float = 30) -> None:
    ax.axhline(reference, color="black", lw=0.6, ls=":")
    ax.axvline(0, color="black", lw=0.9, ls="--")
    ax.axvline(press, color="black", lw=0.9, ls="-.")
    ax.set_xlim(-5, LAST_MINUTE + 1)


def _ratio_panel(ax, summary, instrument, grouping, group, metrics=("bid_rel", "ask_rel", "total_rel")):
    control = _series(summary, instrument, "control", "control", "total_rel")
    if not control.empty:
        _band(ax, control, CONTROL, "Normal days (total)", lw=1.4, alpha=0.2)
    n = 0
    for metric in metrics:
        data = _series(summary, instrument, grouping, group, metric)
        if data.empty:
            continue
        n = max(n, int(data["n"].max()))
        lw = 1.0 if metric == "total_rel" else 1.8
        alpha = 0.0 if metric == "total_rel" else 0.15
        _band(ax, data, COLORS[metric], LABELS[metric], lw=lw, alpha=alpha)
    _decorate(ax, 1)
    ax.set_ylim(0, 2.5)
    return n


def plot_one_by_three(summary, instrument, grouping, order, output) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    for ax, group in zip(axes, order):
        n = _ratio_panel(ax, summary, instrument, grouping, group)
        ax.set_title(f"{group.capitalize()} (n={n})")
        ax.set_xlabel("Minutes from FOMC statement")
    axes[0].set_ylabel("Median depth relative to minutes -5 to -1")
    axes[0].legend(loc="upper right", fontsize=8, frameon=False)
    name = instrument.split(".")[0]
    by = "rate action" if grouping == "action" else "statement-surprise size (USMPD thirds)"
    fig.suptitle(f"{name}: bid and ask depth around FOMC statements, by {by} (median, 25-75% band)")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_three_by_three(summary, panel, groups, instrument, output) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(16, 11), sharex=True, sharey=True)
    members = groups.set_index("meeting")
    for r, action in enumerate(ACTIONS):
        for c, surprise in enumerate(SURPRISES):
            ax = axes[r, c]
            ids = members.index[members["action"].eq(action) & members["surprise"].eq(surprise)]
            events = panel.loc[
                panel["kind"].eq("fomc") & panel["instrument"].eq(instrument) & panel["id"].isin(ids)
            ]
            n = events["id"].nunique()
            control = _series(summary, instrument, "control", "control", "total_rel")
            if not control.empty:
                _band(ax, control, CONTROL, lw=1.2, alpha=0.2)
            if n >= MIN_FOR_BAND:
                _ratio_panel(ax, summary, instrument, "action_x_surprise", f"{action}|{surprise}",
                             metrics=("bid_rel", "ask_rel"))
                note = ""
            else:
                for _, event in events.groupby("id"):
                    event = event.sort_values("minute")
                    for metric in ("bid_rel", "ask_rel"):
                        ax.plot(event["minute"] + 0.5, event[metric], color=COLORS[metric], lw=0.9, alpha=0.6)
                _decorate(ax, 1)
                ax.set_ylim(0, 2.5)
                note = ", each meeting shown"
            ax.set_title(f"{action.capitalize()} / {surprise} surprise (n={n}{note})", fontsize=10)
            if r == 2:
                ax.set_xlabel("Minutes from FOMC statement")
            if c == 0:
                ax.set_ylabel("Depth relative to min -5 to -1")
    handles = [plt.Line2D([], [], color=COLORS[m], lw=2, label=LABELS[m]) for m in ("bid_rel", "ask_rel")]
    handles.append(plt.Line2D([], [], color=CONTROL, lw=2, label="Normal days (total)"))
    fig.legend(handles=handles, loc="upper right", fontsize=9, frameon=False)
    fig.suptitle(f"{instrument.split('.')[0]}: bid and ask depth, rate action x surprise size")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_bid_share(summary, instrument, output) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), sharex=True, sharey=True)
    for r, (grouping, order) in enumerate((("action", ACTIONS), ("surprise", SURPRISES))):
        for c, group in enumerate(order):
            ax = axes[r, c]
            control = _series(summary, instrument, "control", "control", "bid_share")
            if not control.empty:
                _band(ax, control, CONTROL, "Normal days", lw=1.2, alpha=0.2)
            data = _series(summary, instrument, grouping, group, "bid_share")
            n = int(data["n"].max()) if not data.empty else 0
            if not data.empty:
                _band(ax, data, "#6a3d9a", "FOMC days")
            _decorate(ax, 0.5)
            label = f"{group} surprise" if grouping == "surprise" else group
            ax.set_title(f"{label.capitalize()} (n={n})")
            if r == 1:
                ax.set_xlabel("Minutes from FOMC statement")
            if c == 0:
                ax.set_ylabel("Bid share = bid / (bid + ask)")
    axes[0, 0].legend(loc="upper right", fontsize=8, frameon=False)
    fig.suptitle(f"{instrument.split('.')[0]}: bid share of touch depth (above 0.5 = more resting buyers)")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output, dpi=170)
    plt.close(fig)


# ---------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml")
    parser.add_argument("--placebos", default="fomc_placebos_2015_2023.yaml")
    parser.add_argument("--extend", action="store_true",
                        help="First download statement-only meetings out to +40 minutes")
    args = parser.parse_args()

    if args.extend:
        from scripts.download_fomc_extensions import extension_windows
        from src.data.databento_client import DatabentoRequest, download_request, estimate_request

        for window in extension_windows(args.config):
            request = DatabentoRequest.create(
                dataset="GLBX.MDP3", schema="mbp-1", symbols=INSTRUMENTS, stype_in="continuous",
                start=window["request_start_utc"], end=window["request_end_utc"],
            )
            path = download_request(estimate_request(request), execute=True)
            print(f"{window['label']} extended: {path.name}")

    groups = meeting_groups(args.config)
    panel = pd.concat(
        [_collect(meeting_windows(args.config), "fomc"), _collect(control_windows(args.placebos), "control")],
        ignore_index=True,
    )
    if panel.empty:
        raise RuntimeError("No cached raw windows found; run scripts/run_fomc_pipeline.sh first")
    panel.to_parquet(OUT / "minute_depth_sides_by_event.parquet", index=False)
    summary = summarize(panel, groups)
    summary.to_csv(PROJECT_ROOT / "tables" / "fomc_depth_sides_minute.csv", index=False)

    figures = PROJECT_ROOT / "figures" / "paper"
    figures.mkdir(parents=True, exist_ok=True)
    for instrument in INSTRUMENTS:
        name = instrument.split(".")[0]
        plot_one_by_three(summary, instrument, "action", ACTIONS, figures / f"figure_depth_sides_{name}_by_action.png")
        plot_one_by_three(summary, instrument, "surprise", SURPRISES, figures / f"figure_depth_sides_{name}_by_surprise.png")
        plot_three_by_three(summary, panel, groups, instrument, figures / f"figure_depth_sides_{name}_action_x_surprise.png")
        plot_bid_share(summary, instrument, figures / f"figure_bid_share_{name}.png")
    print_summary(summary)
    print("\nWrote 12 figures to figures/paper/ and tables/fomc_depth_sides_minute.csv")


if __name__ == "__main__":
    main()
