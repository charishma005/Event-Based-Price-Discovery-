"""Minute-by-minute median touch depth around FOMC statements, versus matched controls.

Touch depth is best-bid size plus best-ask size. For each event and instrument it
is carried forward on a one-second grid (so it is time-weighted, not
quote-weighted), and each minute gets the median of its 60 seconds. Each event is
then divided by its own mean over minutes -5 to -2, the same baseline as the H4
ratio, so years with very different depth levels are comparable. The plot shows
the cross-event median and interquartile band per minute.

Coverage comes from the cached windows: press-conference meetings run from -5 to
+40 minutes around the statement, and the 2015-2023 controls from -5 to +10.

Run: python -m scripts.plot_fomc_depth_profile
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.build_fomc_pilot import normalize_mbp1
from scripts.process_fomc_placebos import _matching_raw_file as placebo_raw_file
from scripts.process_fomc_sample import _matching_raw_file as meeting_raw_file
from src.analysis.event_summary import valid_quotes
from src.utils.config import PROJECT_ROOT, load_yaml

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
BASELINE_MINUTES = (-5, -2)  # inclusive minute labels, i.e. -5:00 to -1:00


def minute_profile(
    messages: pd.DataFrame, event: pd.Timestamp, first: int, last: int
) -> pd.Series:
    """Median one-second touch depth per minute; minute m covers [event+m, event+m+1)."""
    quotes = valid_quotes(messages)
    if quotes.empty:
        return pd.Series(dtype=float)
    depth = quotes.groupby("ts_event")["touch_depth"].last()
    grid = pd.date_range(
        event + pd.Timedelta(minutes=first),
        event + pd.Timedelta(minutes=last + 1),
        freq="1s",
        inclusive="left",
    )
    # Depth in force at each second: the last quote at or before it.
    on_grid = depth.reindex(depth.index.union(grid)).ffill().reindex(grid)
    minutes = np.floor((grid - event).total_seconds() / 60).astype(int)
    return on_grid.groupby(minutes).median().rename_axis("minute")


def _normalize(profile: pd.Series) -> pd.Series | None:
    base = profile.loc[BASELINE_MINUTES[0] : BASELINE_MINUTES[1]].mean()
    if not np.isfinite(base) or base <= 0:
        return None
    return profile / base


def _collect(windows: list[dict], raw_file, kind: str) -> pd.DataFrame:
    import databento as db

    rows = []
    for i, window in enumerate(windows, 1):
        path = raw_file(window)
        if path is None:
            print(f"[{kind} {i}/{len(windows)}] {window['id']}: raw file not cached, skipped")
            continue
        frame = db.DBNStore.from_file(path).to_df()
        if frame.empty:
            print(f"[{kind} {i}/{len(windows)}] {window['id']}: empty file, skipped")
            continue
        for instrument in INSTRUMENTS:
            raw = frame.loc[frame["symbol"].eq(instrument)]
            if raw.empty:
                continue
            profile = minute_profile(
                normalize_mbp1(raw), window["event"], window["first"], window["last"]
            )
            normalized = _normalize(profile)
            if normalized is None:
                continue
            for minute, value in profile.items():
                rows.append(
                    {
                        "kind": kind,
                        "id": window["id"],
                        "instrument": instrument,
                        "minute": int(minute),
                        "depth_contracts": float(value),
                        "depth_relative": float(normalized.loc[minute]),
                    }
                )
        print(f"[{kind} {i}/{len(windows)}] {window['id']}")
        del frame
    return pd.DataFrame(rows)


def _summary(panel: pd.DataFrame) -> pd.DataFrame:
    return (
        panel.groupby(["kind", "instrument", "minute"])
        .agg(
            events=("id", "nunique"),
            median_relative=("depth_relative", "median"),
            q25_relative=("depth_relative", lambda s: s.quantile(0.25)),
            q75_relative=("depth_relative", lambda s: s.quantile(0.75)),
            median_contracts=("depth_contracts", "median"),
        )
        .reset_index()
    )


def _plot(summary: pd.DataFrame, press_offset: float, output) -> None:
    fig, axes = plt.subplots(1, len(INSTRUMENTS), figsize=(15, 4.5), sharey=True)
    styles = {"fomc": ("#1f5fa8", "FOMC days (press-conference meetings)"),
              "control": ("#8a8a8a", "Matched normal days, 2015-2023")}
    for ax, instrument in zip(axes, INSTRUMENTS):
        for kind, (color, label) in styles.items():
            data = summary.loc[summary["kind"].eq(kind) & summary["instrument"].eq(instrument)]
            if data.empty:
                continue
            x = data["minute"] + 0.5  # plot each minute at its midpoint
            ax.fill_between(x, data["q25_relative"], data["q75_relative"], color=color, alpha=0.18, lw=0)
            ax.plot(x, data["median_relative"], color=color, lw=2, label=label)
        ax.axhline(1, color="black", lw=0.6, ls=":")
        ax.axvline(0, color="black", lw=1, ls="--")
        ax.axvline(press_offset, color="black", lw=1, ls="-.")
        ax.text(0.3, 0.02, "statement", transform=ax.get_xaxis_transform(), fontsize=8)
        ax.text(press_offset + 0.3, 0.02, "press conf.", transform=ax.get_xaxis_transform(), fontsize=8)
        ax.set_title(instrument.split(".")[0])
        ax.set_xlabel("Minutes from FOMC statement")
    axes[0].set_ylabel("Median touch depth\n(relative to minutes -5 to -1)")
    axes[0].legend(loc="lower right", fontsize=8, frameon=False)
    fig.suptitle("Touch depth around FOMC statements, minute by minute (median and 25-75% band)")
    fig.tight_layout()
    fig.savefig(output, dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="fomc_sample_2015_2026.yaml")
    parser.add_argument("--placebos", default="fomc_placebos_2015_2023.yaml")
    parser.add_argument("--no-controls", action="store_true")
    args = parser.parse_args()

    meetings = [
        m
        for m in load_yaml(PROJECT_ROOT / "config" / args.config)["meetings"]
        if "press_conference_time_utc" in m
        and m.get("dataset_condition", "available") == "available"
    ]
    offsets = []
    windows = []
    for m in meetings:
        event = pd.Timestamp(m["statement_time_utc"])
        offsets.append((pd.Timestamp(m["press_conference_time_utc"]) - event).total_seconds() / 60)
        end = (pd.Timestamp(m["request_end_utc"]) - event).total_seconds() / 60
        windows.append({**m, "id": m["label"], "event": event, "first": -5, "last": int(end) - 1})
    panel = _collect(windows, meeting_raw_file, "fomc")

    if not args.no_controls:
        placebos = load_yaml(PROJECT_ROOT / "config" / args.placebos)["placebos"]
        control_windows = []
        for p in placebos:
            event = pd.Timestamp(p["placebo_time_utc"])
            end = (pd.Timestamp(p["request_end_utc"]) - event).total_seconds() / 60
            control_windows.append(
                {**p, "id": p["placebo_id"], "event": event, "first": -5, "last": int(end) - 1}
            )
        panel = pd.concat([panel, _collect(control_windows, placebo_raw_file, "control")])

    if panel.empty:
        raise RuntimeError("No cached raw windows found; run scripts/run_fomc_pipeline.sh first")
    summary = _summary(panel)

    processed = PROJECT_ROOT / "data" / "processed" / "fomc_depth_profile"
    processed.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(processed / "minute_depth_by_event.parquet", index=False)
    summary.to_csv(PROJECT_ROOT / "tables" / "fomc_depth_profile_minute.csv", index=False)

    figures = PROJECT_ROOT / "figures" / "paper"
    figures.mkdir(parents=True, exist_ok=True)
    output = figures / "figure_fomc_depth_profile_minute.png"
    _plot(summary, float(np.median(offsets)), output)

    fomc = summary.loc[summary["kind"].eq("fomc")]
    print(f"\nEvents per instrument: {fomc.groupby('instrument')['events'].max().to_dict()}")
    print(
        fomc.pivot(index="minute", columns="instrument", values="median_relative")
        .round(3)
        .to_string()
    )
    print(f"\nWrote {output.relative_to(PROJECT_ROOT)} and tables/fomc_depth_profile_minute.csv")


if __name__ == "__main__":
    main()
