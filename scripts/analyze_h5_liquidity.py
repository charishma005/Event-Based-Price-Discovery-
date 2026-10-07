"""H5 without the surprise: does the order book explain the FOMC price response by horizon?

H5 regressed the size of the statement response on the USMPD surprise at 1s ... 30m. Here the
surprise is replaced by book variables measured before the news (and, for one model, in the first
five seconds), so everything on the right-hand side is observable in real time.

Book variables (H4 baseline = -240 to -60 s; all from data/processed/tick_features/events.parquet)
  pre60_depth_ratio        touch depth, -60..0 s, over baseline
  pre60_bid_ratio          bid size, -60..0 s, over baseline bid size
  pre60_ask_ratio          ask size, -60..0 s, over baseline ask size
  pre60_spread_change      quoted spread, -60..0 s, minus baseline (ticks)
  imbalance_pre10          (bid - ask) / (bid + ask), -10..0 s           (signed)
  side_asymmetry_pre60     ln(bid ratio) - ln(ask ratio), -60..0 s      (signed: ask pulled more = +)
  imbalance_post5          (bid - ask) / (bid + ask), 0..5 s            (signed, real time at +5 s)

Models, per instrument and horizon h (returns R_h in bp from the last pre-statement mid,
data/processed/fomc_sample_2015_2026/response_horizons.csv):
  M_surprise     |R_h| ~ |STMT surprise| (bp)                       H5a benchmark (not real time)
  M_book         |R_h| ~ depth ratio + spread change                 magnitude from the book
  M_sides        |R_h| ~ bid ratio + ask ratio                       which side's withdrawal matters
  M_both         |R_h| ~ |surprise| + depth ratio + spread change    does the book add to the surprise?
  D_book         R_h ~ imbalance_pre10 + side_asymmetry_pre60        direction from the pre-news book
  D_post5        R_h - R_5s ~ imbalance_post5  (h > 5 s)             direction from the first 5 s
  D_surprise     R_h ~ STMT surprise (signed)                         direction benchmark
OLS with heteroskedasticity-robust (event-clustered) errors; one observation per meeting.
The same book models are repeated on 8:30 macro releases up to +5 min as a replication.

Run: python -m scripts.analyze_h5_liquidity
Writes tables/h5_liquidity_regressions.csv and figures/h5_liquidity/*.png
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.analyze_fomc_surprises import _meetings
from src.events.surprises import build_surprise_panel
from src.strategies.inference import ols_clustered
from src.utils.config import PROJECT_ROOT

EVENTS = PROJECT_ROOT / "data" / "processed" / "tick_features" / "events.parquet"
HORIZONS_CSV = PROJECT_ROOT / "data" / "processed" / "fomc_sample_2015_2026" / "response_horizons.csv"
TABLE = PROJECT_ROOT / "tables" / "h5_liquidity_regressions.csv"
FIG = PROJECT_ROOT / "figures" / "h5_liquidity"
HORIZONS = (1, 5, 30, 60, 300, 600, 1200, 1800)
LABELS = {1: "1s", 5: "5s", 30: "30s", 60: "1m", 300: "5m", 600: "10m", 1200: "20m", 1800: "30m"}
MACRO_HORIZONS = {1: "w1s", 5: "w5s", 30: "w30s", 60: "w60s", 300: "w300s"}
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
NAMES = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}
COLORS = {"ES": "#2a78d6", "NQ": "#eb6834", "ZN": "#1baf7a"}
PP_TO_BP = 100


def book_variables(e: pd.DataFrame) -> pd.DataFrame:
    out = e.copy()
    out["pre60_bid_ratio"] = out["pre60_bid_size"] / out["baseline_bid_size"]
    out["pre60_ask_ratio"] = out["pre60_ask_size"] / out["baseline_ask_size"]
    out["pre60_spread_change"] = out["pre60_spread_change_ticks"]
    out["imbalance_pre10"] = (out["pre10_bid_size"] - out["pre10_ask_size"]) / (out["pre10_bid_size"] + out["pre10_ask_size"])
    out["side_asymmetry_pre60"] = np.log(out["pre60_bid_ratio"]) - np.log(out["pre60_ask_ratio"])
    out["imbalance_post5"] = (out["post5_bid_size"] - out["post5_ask_size"]) / (out["post5_bid_size"] + out["post5_ask_size"])
    return out


MODELS = {
    "M_surprise": ("abs", ["abs_surprise_bp"]),
    "M_book": ("abs", ["pre60_depth_ratio", "pre60_spread_change"]),
    "M_sides": ("abs", ["pre60_bid_ratio", "pre60_ask_ratio"]),
    "M_both": ("abs", ["abs_surprise_bp", "pre60_depth_ratio", "pre60_spread_change"]),
    "D_book": ("signed", ["imbalance_pre10", "side_asymmetry_pre60"]),
    "D_post5": ("after5", ["imbalance_post5"]),
    "D_surprise": ("signed", ["surprise_bp"]),
}


def _fit(frame: pd.DataFrame, events: str, models: dict) -> list[pd.DataFrame]:
    rows = []
    for (inst, h), g in frame.groupby(["instrument", "horizon_seconds"]):
        for name, (kind, xs) in models.items():
            if kind == "after5" and h <= 5:
                continue
            y = {"abs": "abs_ret", "signed": "ret", "after5": "ret_after5"}[kind]
            if not set(xs) <= set(g.columns) or g[xs].isna().all().any():
                continue
            rows.append(ols_clustered(g, y, xs, cluster="event_id").assign(
                events=events, instrument=NAMES[inst], horizon_s=h, horizon=LABELS[h], model=name, y=y))
    return rows


def fomc_frame(e: pd.DataFrame) -> pd.DataFrame:
    st = e.loc[e["family"].eq("fomc") & e["subevent"].eq("statement")]
    st = st.set_index(["matched_event", "instrument"])
    h = pd.read_csv(HORIZONS_CSV)
    h = h.loc[h["subevent"].eq("statement") & h["dataset_condition"].eq("available")
              & h["full_horizon_covered"].astype(bool) & h["horizon_seconds"].isin(HORIZONS)
              & h["instrument"].isin(INSTRUMENTS)].dropna(subset=["log_return_bp"])
    r5 = h.loc[h["horizon_seconds"].eq(5)].set_index(["meeting", "instrument"])["log_return_bp"]
    panel = build_surprise_panel(_meetings("fomc_sample_2015_2026.yaml")).set_index("meeting")
    d = h[["meeting", "instrument", "horizon_seconds", "log_return_bp"]].rename(columns={"meeting": "event_id",
                                                                                       "log_return_bp": "ret"})
    d["horizon_seconds"] = d["horizon_seconds"].astype(int)
    d["abs_ret"] = d["ret"].abs()
    d["ret_after5"] = d["ret"] - r5.reindex(list(zip(d["event_id"], d["instrument"]))).to_numpy()
    d["surprise_bp"] = d["event_id"].map(panel["STMT"]) * PP_TO_BP
    d["abs_surprise_bp"] = d["surprise_bp"].abs()
    cols = ["pre60_depth_ratio", "pre60_bid_ratio", "pre60_ask_ratio", "pre60_spread_change",
            "imbalance_pre10", "side_asymmetry_pre60", "imbalance_post5"]
    book = st[cols].reindex(list(zip(d["event_id"], d["instrument"])))
    return pd.concat([d.reset_index(drop=True), book.reset_index(drop=True)], axis=1)


def macro_frame(e: pd.DataFrame) -> pd.DataFrame:
    m = e.loc[e["family"].eq("macro")]
    frames = []
    for h, col in MACRO_HORIZONS.items():
        f = m[["event_id", "instrument", "pre60_depth_ratio", "pre60_bid_ratio", "pre60_ask_ratio",
               "pre60_spread_change", "imbalance_pre10", "side_asymmetry_pre60", "imbalance_post5"]].copy()
        f["horizon_seconds"] = h
        f["ret"] = m[col + "_total_bp"].to_numpy()
        f["ret_after5"] = f["ret"] - m["w5s_total_bp"].to_numpy()
        f["abs_ret"] = f["ret"].abs()
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def _coef(t: pd.DataFrame, events, model, term):
    return t.loc[t["events"].eq(events) & t["model"].eq(model) & t["term"].eq(term)]


def figures(t: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    order = [LABELS[h] for h in HORIZONS]
    panels = [("M_book", "pre60_spread_change", "|R_h| per +1 tick of pre-statement spread (bp)"),
              ("M_book", "pre60_depth_ratio", "|R_h| per +1.0 pre-statement depth ratio (bp)"),
              ("D_book", "imbalance_pre10", "R_h per +1 imbalance, -10..0 s (bp)"),
              ("D_post5", "imbalance_post5", "R_h - R_5s per +1 imbalance, 0..5 s (bp)")]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (model, term, label) in zip(axes.flat, panels):
        for k, inst in enumerate(("ES", "NQ")):
            d = _coef(t, "fomc_statement", model, term)
            d = d.loc[d["instrument"].eq(inst)].set_index("horizon").reindex(order).dropna(subset=["coef"])
            x = np.array([order.index(h) for h in d.index]) + (k - 0.5) * 0.18
            ax.errorbar(x, d["coef"], yerr=[d["coef"] - d["ci_low"], d["ci_high"] - d["coef"]], fmt="o-",
                        color=COLORS[inst], lw=1.6, ms=5, capsize=3, label=inst)
        ax.axhline(0, color="#888888", lw=0.8)
        ax.set_xticks(range(len(order)), order)
        ax.set_title(label, fontsize=10)
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("FOMC statements: price response on the order book instead of the surprise "
                 "(95% CI, robust SE; 92 meetings, 76 at 20-30 min)")
    fig.tight_layout()
    fig.savefig(FIG / "h5_book_slopes_by_horizon.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    styles = {"M_surprise": ("|surprise| only (H5a)", "-", "o"), "M_book": ("book only (depth + spread)", "--", "s"),
              "M_both": ("|surprise| + book", ":", "^")}
    for ax, inst in zip(axes, ("ES", "NQ")):
        for model, (label, ls, marker) in styles.items():
            d = t.loc[t["events"].eq("fomc_statement") & t["model"].eq(model) & t["instrument"].eq(inst)]
            d = d.drop_duplicates("horizon").set_index("horizon").reindex(order)
            ax.plot(range(len(order)), d["r2"], ls=ls, marker=marker, color=COLORS[inst], lw=1.6, label=label)
        ax.set_xticks(range(len(order)), order)
        ax.set_title(inst)
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("R2 of |R_h|")
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle("How much of the response size each set of variables explains, by horizon")
    fig.tight_layout()
    fig.savefig(FIG / "h5_book_vs_surprise_r2.png", dpi=160)
    plt.close(fig)


def main() -> None:
    e = pd.read_parquet(EVENTS)
    e = book_variables(e.loc[e["dataset_condition"].ne("degraded") & e["pre_state_valid"]])
    rows = _fit(fomc_frame(e), "fomc_statement", MODELS)
    macro_models = {k: v for k, v in MODELS.items() if "surprise" not in k and k != "M_both"}
    rows += _fit(macro_frame(e), "macro_release", macro_models)
    t = pd.concat(rows, ignore_index=True)
    t = t[["events", "instrument", "horizon", "horizon_s", "model", "y", "term", "coef", "se", "t_stat", "p_value",
           "ci_low", "ci_high", "r2", "N", "N_events"]]
    TABLE.parent.mkdir(exist_ok=True)
    t.to_csv(TABLE, index=False)
    figures(t)
    print(f"Wrote {TABLE.relative_to(PROJECT_ROOT)} ({len(t)} rows) and figures in {FIG.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
