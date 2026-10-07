"""Liquidity stress (ELS), event-move size and execution cost around FOMC statements.

Implements ``config/liquidity_trading_prereg.yaml``; every window, horizon and
threshold is read from there. Parts:

  A  ELS regressions: |move| on pre-event ELS; continuation with an ELS interaction
  B  out-of-sample prediction of top-quartile moves (expanding window by year)
  C  execution: user schedule, TWAP, calendar blackout and ELS-adaptive, by implementation shortfall
  D  stressed-move fade (exploratory; confirmatory only after the freeze date)
  E  short momentum filtered by predicted move size (exploratory; same)

Input: the one-second FOMC session panel written by
``python -m scripts.extract_session_panels`` then ``--merge``
(``data/processed/fomc_sessions/panel.parquet`` and ``sessions.parquet``).

Typical use:
    python -m scripts.analyze_liquidity_trading --check-data      # coverage only, no outcomes
    python -m scripts.freeze_liquidity_trading_preregistration    # fix the spec and input hashes
    python -m scripts.analyze_liquidity_trading                    # the frozen run

``--unfrozen`` runs everything before the freeze and writes ``liq_unfrozen_*``
tables; a later freeze then records that such a run was made.
"""
from __future__ import annotations

import argparse
import hashlib
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.optimize import minimize
from scipy.stats import wilcoxon
from statsmodels.stats.multitest import multipletests

from src.microstructure import liquidity_stress as ls
from src.utils.config import PROJECT_ROOT, load_yaml

warnings.filterwarnings("ignore", category=FutureWarning)

PREREGISTRATION = "config/liquidity_trading_prereg.yaml"
HASHED_FILES = {
    "panel_sha256": "data/processed/fomc_sessions/panel.parquet",
    "sessions_sha256": "data/processed/fomc_sessions/sessions.parquet",
    "registry_sha256": "data/events/fomc_session_windows.csv",
    "measure_code_sha256": "src/microstructure/liquidity_stress.py",
    "analysis_code_sha256": "scripts/analyze_liquidity_trading.py",
}
IMPLIED_VOL = "data/external/implied_vol.csv"
TABLES = PROJECT_ROOT / "tables"
FIGURES = PROJECT_ROOT / "figures" / "liquidity_trading"
SHORT = {"ES.v.0": "ES", "NQ.v.0": "NQ", "ZN.v.0": "ZN"}


def sha256(relative: str) -> str:
    return hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()


def check_freeze(unfrozen: bool, allow_change: bool) -> dict:
    spec = load_yaml(PROJECT_ROOT / PREREGISTRATION)
    if spec.get("status") != "frozen":
        if unfrozen:
            print("WARNING: the pre-declaration is not frozen; tables are written as liq_unfrozen_*.")
            return spec
        raise SystemExit("Not frozen. Run scripts.freeze_liquidity_trading_preregistration first, "
                         "or --check-data, or --unfrozen for an explicitly labelled draft run.")
    freeze = spec.get("freeze", {})
    files = dict(HASHED_FILES)
    if "implied_vol_sha256" in freeze:
        files["implied_vol_sha256"] = IMPLIED_VOL
    changed = [f"{relative} changed since the freeze" for key, relative in files.items()
               if (PROJECT_ROOT / relative).exists() and freeze.get(key) != sha256(relative)]
    missing = [f"{relative} missing" for key, relative in files.items() if not (PROJECT_ROOT / relative).exists()]
    if missing or (changed and not allow_change):
        raise SystemExit("Freeze check failed:\n  " + "\n  ".join(missing + changed) +
                         ("\nLog the change in post_freeze_log and rerun with --allow-change." if changed else ""))
    for line in changed:
        print(f"WARNING (allowed): {line}")
    return spec


# ---------------------------------------------------------------- data

def load(spec: dict) -> tuple[pd.DataFrame, dict]:
    """Session metadata and one Book per (event_id, instrument)."""
    m = spec["measures"]
    first = min(m["realized_vol"]["window_seconds"][0], spec["part_c_execution"]["execution_baseline_seconds"][0])
    last = max(max(m["horizons_seconds"]), spec["part_c_execution"]["deadline_second"]) + 60
    columns = ["event_id", "instrument", "seconds", "valid", "bid", "ask", "bid_size", "ask_size"]
    for key in ("panel", "registry"):
        if not (PROJECT_ROOT / spec["data"][key]).exists():
            raise SystemExit(f"{spec['data'][key]} not found. Build the one-second FOMC panel first:\n"
                             "  python -m scripts.download_registry_windows --registry fomc_session_windows.csv "
                             "--schema bbo-1s --require-zero-cost   # if the bbo-1s files are not cached\n"
                             "  python -m scripts.extract_session_panels\n"
                             "  python -m scripts.extract_session_panels --merge")
    panel = pd.read_parquet(PROJECT_ROOT / spec["data"]["panel"], columns=columns,
                            filters=[("seconds", ">=", first), ("seconds", "<=", last)])
    panel["event_id"] = panel["event_id"].astype(str)
    panel["instrument"] = panel["instrument"].astype(str)
    registry = pd.read_csv(PROJECT_ROOT / spec["data"]["registry"], keep_default_na=False)
    registry = registry.loc[registry["family"].isin(["fomc", "fomc_control"])
                            & registry["dataset_condition"].eq("available")
                            & registry["event_id"].isin(panel["event_id"].unique())].copy()
    registry["event_date"] = pd.to_datetime(registry["event_date"])
    registry["year"] = registry["event_date"].dt.year
    registry["sep"] = registry["sep_release"].astype(str).str.lower().eq("true").astype(int)
    registry["press"] = registry["press_conference_time_utc"].astype(str).str.strip().ne("").astype(int)
    registry["is_event"] = registry["family"].eq("fomc")
    path = PROJECT_ROOT / IMPLIED_VOL
    # After the freeze the file counts only if it was hashed at the freeze.
    frozen_without_iv = spec.get("status") == "frozen" and "implied_vol_sha256" not in spec.get("freeze", {})
    use_iv = spec["data"].get("implied_vol_used", "auto") == "auto" and path.exists() and not frozen_without_iv
    if use_iv:
        iv = pd.read_csv(path, parse_dates=["date"])
        registry = registry.merge(iv.rename(columns={"date": "event_date"}), on="event_date", how="left")
        registry["log_iv"] = np.log(registry["implied_vol"])
    books = {}
    instruments = spec["sample"]["instruments"]
    for (event_id, instrument), frame in panel.loc[panel["event_id"].isin(registry["event_id"])].groupby(
            ["event_id", "instrument"], observed=True):
        if instrument in instruments and len(frame):
            books[(event_id, instrument)] = ls.Book.from_frame(frame, instrument, m["ffill_seconds"])
    registry = registry.reset_index(drop=True)
    registry.attrs["use_iv"] = use_iv
    return registry, books


def trailing(second: int, window: int) -> tuple[int, int]:
    """[start, end) of the trailing window ending at ``second`` inclusive, never before the clock."""
    return max(0, second - window + 1), second + 1


def half_spread_bp(book: ls.Book, second: int) -> float:
    return (book.at(book.ask, second) - book.at(book.bid, second)) / 2 / book.at(book.mid, second) * 1e4


def build_features(meta: pd.DataFrame, books: dict, spec: dict) -> pd.DataFrame:
    m = spec["measures"]
    base, pre, anchor = tuple(m["baseline_seconds"]), tuple(m["pre_window_seconds"]), m["anchor_second"]
    ends = sorted(set(m["horizons_seconds"]) | {t for pair in m["continuation_pairs_seconds"] for t in pair})
    rows = []
    for row in meta.itertuples(index=False):
        for instrument in spec["sample"]["instruments"]:
            book = books.get((row.event_id, instrument))
            if book is None:
                continue
            out = {"event_id": row.event_id, "instrument": instrument, "is_event": row.is_event,
                   "sample": row.sample, "event_date": row.event_date, "year": row.year,
                   "sep": row.sep, "press": row.press}
            if meta.attrs.get("use_iv"):
                out["log_iv"] = row.log_iv
            parts = ls.els(book, pre[0], pre[1], base)
            out.update({"els_pre": parts["els"], "log_depth_pre": parts["log_depth_ratio"],
                        "log_spread_pre": parts["log_spread_ratio"]})
            rv = ls.realized_vol_bp(book, *m["realized_vol"]["window_seconds"], m["realized_vol"]["step_seconds"])
            out["log_rv"] = np.log(rv) if rv > 0 else np.nan
            for t in ends:
                out[f"r_{t}"] = ls.log_return_bp(book, anchor, t)
            for t1, t2 in m["continuation_pairs_seconds"]:
                out[f"r_{t1}_{t2}"] = ls.log_return_bp(book, t1, t2)
                out[f"els_{t1}"] = ls.els(book, *trailing(t1, m["continuation_els_window_seconds"]), base)["els"]
            rows.append(out)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- part A

def _ols(formula: str, data: pd.DataFrame, cluster: str | None = None):
    model = smf.ols(formula, data=data)
    if cluster:
        return model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(data[cluster])[0]})
    return model.fit(cov_type="HC1")


def part_a(features: pd.DataFrame, spec: dict) -> pd.DataFrame:
    m = spec["measures"]
    events = features.loc[features["is_event"]].copy()
    rows = []
    for h in m["horizons_seconds"]:
        events[f"y_{h}"] = np.log1p(events[f"r_{h}"].abs())
        rhs = "els_pre + log_rv + sep + press"
        for instrument in [*spec["sample"]["instruments"], "pooled"]:
            data = events if instrument == "pooled" else events.loc[events["instrument"].eq(instrument)]
            data = data.dropna(subset=[f"y_{h}", "els_pre", "log_rv"])
            formula = f"y_{h} ~ {rhs}" + (" + C(instrument)" if instrument == "pooled" else "")
            fit = _ols(formula, data, cluster="event_id" if instrument == "pooled" else None)
            rows.append(_coef_row("move_size", instrument, f"0-{h}s", "els_pre", fit, len(data)))
    for t1, t2 in m["continuation_pairs_seconds"]:
        for instrument in spec["sample"]["instruments"]:
            data = events.loc[events["instrument"].eq(instrument)].rename(
                columns={f"r_{t1}_{t2}": "y", f"r_{t1}": "r1", f"els_{t1}": "els1"})
            data = data.dropna(subset=["y", "r1", "els1"])
            fit = _ols("y ~ r1 + els1 + r1:els1", data)
            rows.append(_coef_row("continuation", instrument, f"{t1}-{t2}s", "r1:els1", fit, len(data)))
            rows.append(_coef_row("continuation_slope", instrument, f"{t1}-{t2}s", "r1", fit, len(data)))
    table = pd.DataFrame(rows)
    for test in ("move_size", "continuation"):
        family = table["test"].eq(test) & table["instrument"].ne("pooled")
        table.loc[family, "holm_p"] = multipletests(table.loc[family, "p"], method="holm")[1]
    return table


def _coef_row(test, instrument, horizon, term, fit, n) -> dict:
    low, high = fit.conf_int().loc[term]
    return {"test": test, "instrument": instrument, "horizon": horizon, "term": term,
            "coef": fit.params[term], "se": fit.bse[term], "p": fit.pvalues[term],
            "ci_low": low, "ci_high": high, "r2": fit.rsquared, "n": n}


# ---------------------------------------------------------------- part B

def ridge_logit(x: np.ndarray, y: np.ndarray, penalty: float) -> np.ndarray:
    """L2-penalized logistic regression; first column of x is the unpenalized intercept."""
    def loss(beta):
        z = x @ beta
        nll = np.sum(np.logaddexp(0, z) - y * z)
        return nll + 0.5 * penalty * np.sum(beta[1:] ** 2)

    def grad(beta):
        p = 1 / (1 + np.exp(-(x @ beta)))
        g = x.T @ (p - y)
        g[1:] += penalty * beta[1:]
        return g

    return minimize(loss, np.zeros(x.shape[1]), jac=grad, method="L-BFGS-B").x


def _design(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> tuple[np.ndarray, np.ndarray]:
    mean, sd = train[columns].mean(), train[columns].std(ddof=0).replace(0, 1)
    def scale(frame):
        return np.column_stack([np.ones(len(frame)), ((frame[columns] - mean) / sd).to_numpy(float)])
    return scale(train), scale(test)


def part_b(features: pd.DataFrame, spec: dict, use_iv: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = spec["part_b_move_size_prediction"]
    first_test = 2018
    events = features.loc[features["is_event"]].copy()
    wide = events.pivot_table(index="event_id", columns="instrument", values="els_pre")
    wide.columns = [f"els_pre_{SHORT[c]}" for c in wide.columns]
    stress = list(wide.columns)
    events = events.merge(wide, left_on="event_id", right_index=True)
    base = ["log_rv", "sep", "press"] + (["log_iv"] if use_iv else [])
    full = base + stress
    predictions, summary = [], []
    rng = np.random.default_rng(20261007)
    for instrument in spec["sample"]["instruments"]:
        data = events.loc[events["instrument"].eq(instrument)].dropna(subset=["r_300", *full]).copy()
        data["abs_r"] = data["r_300"].abs()
        data["top"] = (data["abs_r"] > data["abs_r"].quantile(0.75)).astype(int)
        data["y_log"] = np.log1p(data["abs_r"])
        for year in sorted(y for y in data["year"].unique() if y >= first_test):
            train, test = data.loc[data["year"] < year], data.loc[data["year"].eq(year)]
            if len(train) < 10 or train["top"].nunique() < 2:
                continue
            out = test[["event_id", "instrument", "year", "sample", "event_date", "top", "y_log"]].copy()
            for name, columns in (("base", base), ("full", full)):
                xtr, xte = _design(train, test, columns)
                beta = ridge_logit(xtr, train["top"].to_numpy(float), penalty=1.0)
                out[f"p_{name}"] = 1 / (1 + np.exp(-(xte @ beta)))
                coef, *_ = np.linalg.lstsq(xtr, train["y_log"].to_numpy(float), rcond=None)
                out[f"yhat_{name}"] = xte @ coef
                out[f"ymean_{name}"] = train["y_log"].mean()
            predictions.append(out)
        if not predictions or predictions[-1]["instrument"].iloc[0] != instrument:
            continue
        oos = pd.concat([p for p in predictions if p["instrument"].iloc[0] == instrument])
        auc_full, auc_base = ls.auc(oos["p_full"], oos["top"]), ls.auc(oos["p_base"], oos["top"])
        draws = []
        ids = oos["event_id"].to_numpy()
        for _ in range(2000):
            pick = rng.integers(0, len(ids), len(ids))
            s = oos.iloc[pick]
            draws.append(ls.auc(s["p_full"], s["top"]) - ls.auc(s["p_base"], s["top"]))
        draws = np.array(draws)
        draws = draws[np.isfinite(draws)]
        sse = lambda col: np.sum((oos["y_log"] - oos[col]) ** 2)
        summary.append({
            "instrument": instrument, "test_events": len(oos), "test_years": f"{oos['year'].min()}-{oos['year'].max()}",
            "positives": int(oos["top"].sum()), "auc_base": auc_base, "auc_full": auc_full,
            "auc_difference": auc_full - auc_base, "ci_low": np.quantile(draws, 0.025),
            "ci_high": np.quantile(draws, 0.975), "oos_r2_base": 1 - sse("yhat_base") / sse("ymean_base"),
            "oos_r2_full": 1 - sse("yhat_full") / sse("ymean_full"),
            "base_features": " + ".join(base), "implied_vol_used": use_iv,
        })
    summary = pd.DataFrame(summary)
    if len(summary):
        supported = int((summary["ci_low"] > 0).sum())
        summary["verdict"] = ("supported" if supported >= 2 else "not supported") + \
            f": interval above zero in {supported} of {len(summary)} instruments"
    return summary, (pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame())


# ---------------------------------------------------------------- part C

def part_c(meta: pd.DataFrame, books: dict, spec: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    c = spec["part_c_execution"]
    total, decision = 100.0, c["twap"]["start_second"]
    twap = ls.schedule_twap(c["twap"]["start_second"], c["twap"]["end_second"], c["twap"]["step_seconds"], total)
    schedules = {
        "user_schedule": ls.schedule_fixed({int(k): float(v) for k, v in c["strategies"]["user_schedule"].items()}, total),
        "twap": twap,
        "calendar": ls.schedule_twap(c["twap"]["start_second"], c["twap"]["end_second"], c["twap"]["step_seconds"],
                                     total, blackout=tuple(c["calendar_blackout_seconds"])),
    }
    rows = []
    for row in meta.itertuples(index=False):
        for instrument in spec["sample"]["instruments"]:
            book = books.get((row.event_id, instrument))
            if book is None:
                continue
            live = ls.trailing_els(book, spec["measures"]["live_window_seconds"], tuple(c["execution_baseline_seconds"]))
            arrival = book.at(book.mid, decision)
            for side in (1, -1):
                runs = {name: ls.run_schedule(book, plan, side) for name, plan in schedules.items()}
                runs["adaptive"] = ls.run_adaptive(book, live, twap, c["adaptive_threshold_els"],
                                                   c["deadline_second"], c["twap"]["step_seconds"], side)
                for name, fills in runs.items():
                    rows.append({"event_id": row.event_id, "is_event": row.is_event, "sample": row.sample,
                                 "instrument": instrument, "side": "buy" if side > 0 else "sell", "strategy": name,
                                 "fills": len(fills), **ls.shortfall(fills, arrival, side)})
    sessions = pd.DataFrame(rows)
    per = (sessions.groupby(["event_id", "is_event", "instrument", "strategy"])
           .agg(spread_cost_bp=("spread_cost_bp", "mean"), complete=("is_bp", lambda v: v.notna().all()))
           .reset_index())
    summary = (sessions.assign(day=np.where(sessions["is_event"], "event", "control"))
               .groupby(["day", "instrument", "strategy", "side"])
               .agg(sessions=("is_bp", "count"), is_mean_bp=("is_bp", "mean"), spread_cost_mean_bp=("spread_cost_bp", "mean"),
                    spread_cost_median_bp=("spread_cost_bp", "median"), timing_sd_bp=("timing_bp", "std"),
                    completion_mean_s=("completion_second", "mean"))
               .reset_index())
    tests = []
    comparisons = [("adaptive", "calendar", True), ("adaptive", "twap", False), ("calendar", "twap", False),
                   ("user_schedule", "calendar", False)]
    for is_event in (True, False):
        for instrument in spec["sample"]["instruments"]:
            wide = per.loc[per["is_event"].eq(is_event) & per["instrument"].eq(instrument) & per["complete"]].pivot(
                index="event_id", columns="strategy", values="spread_cost_bp")
            for left, right, primary in comparisons:
                if left not in wide or right not in wide:
                    continue
                # Rounded to 1e-6 bp: identical fills differ only by float noise, which Wilcoxon would rank.
                diff = (wide[left] - wide[right]).dropna().round(6)
                p = wilcoxon(diff).pvalue if len(diff) > 5 and diff.abs().sum() > 0 else np.nan
                tests.append({"day": "event" if is_event else "control", "instrument": instrument,
                              "comparison": f"{left} minus {right}", "primary": primary and is_event,
                              "n": len(diff), "mean_difference_bp": diff.mean(), "median_difference_bp": diff.median(),
                              "share_negative": (diff < 0).mean(), "wilcoxon_p": p})
    tests = pd.DataFrame(tests)
    primary = tests["primary"] & tests["wilcoxon_p"].notna()
    tests.loc[primary, "holm_p"] = multipletests(tests.loc[primary, "wilcoxon_p"], method="holm")[1]
    return sessions, summary, tests


# ---------------------------------------------------------------- parts D and E (exploratory)

def _split(frame: pd.DataFrame, freeze_date: pd.Timestamp | None) -> pd.Series:
    after = frame["event_date"] > freeze_date if freeze_date is not None else pd.Series(False, index=frame.index)
    return np.where(after, "after_freeze", frame["sample"])


def _summarize_trades(trades: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    def stats(g):
        n = len(g)
        sd = g["net_bp"].std(ddof=1) if n > 1 else np.nan
        return pd.Series({"trades": n, "gross_mean_bp": g["gross_bp"].mean(), "net_mean_bp": g["net_bp"].mean(),
                          "net_median_bp": g["net_bp"].median(), "hit_rate": (g["net_bp"] > 0).mean(),
                          "net_t": g["net_bp"].mean() / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan})
    return trades.groupby(keys).apply(stats, include_groups=False).reset_index()


def part_d(features: pd.DataFrame, books: dict, spec: dict, freeze_date) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = spec["measures"]
    base = tuple(m["baseline_seconds"])
    events = features.loc[features["is_event"]].copy()
    events["split"] = _split(events, freeze_date)
    trades = []
    for instrument in spec["sample"]["instruments"]:
        data = events.loc[events["instrument"].eq(instrument)].dropna(subset=["r_300", "els_300"])
        fit = data.loc[data["split"].ne("after_freeze")]
        q75, q25, q50 = fit["r_300"].abs().quantile(0.75), fit["els_300"].quantile(0.25), fit["els_300"].quantile(0.5)
        for row in data.loc[(data["r_300"].abs() > q75) & (data["els_300"] < q25)].itertuples(index=False):
            book = books[(row.event_id, instrument)]
            live = ls.trailing_els(book, m["live_window_seconds"], base)
            exit_second = 1200
            for s in range(301, 1201):
                value = book.at(live, s)
                if np.isfinite(value) and value > q50:
                    exit_second = s
                    break
            position = -np.sign(row.r_300)
            gross = position * ls.log_return_bp(book, 300, exit_second)
            cost = half_spread_bp(book, 300) + half_spread_bp(book, exit_second)
            trades.append({"event_id": row.event_id, "instrument": instrument, "split": row.split,
                           "r_300": row.r_300, "els_300": row.els_300, "exit_second": exit_second,
                           "position": position, "gross_bp": gross, "cost_bp": cost, "net_bp": gross - cost,
                           "q75_abs_r": q75, "q25_els": q25, "q50_els": q50})
    trades = pd.DataFrame(trades)
    return trades, _summarize_trades(trades, ["instrument", "split"]) if len(trades) else pd.DataFrame()


def part_e(features: pd.DataFrame, predictions: pd.DataFrame, books: dict, freeze_date) -> tuple[pd.DataFrame, pd.DataFrame]:
    if predictions.empty:
        return pd.DataFrame(), pd.DataFrame()
    pred = predictions.loc[predictions["instrument"].isin(["ES.v.0", "NQ.v.0"])].pivot_table(
        index="event_id", columns="instrument", values="p_full").mean(axis=1).rename("p_equity")
    events = features.loc[features["is_event"] & features["instrument"].isin(["ES.v.0", "NQ.v.0"])].copy()
    events["split"] = _split(events, freeze_date)
    events = events.merge(pred, left_on="event_id", right_index=True)
    fit = events.loc[events["split"].ne("after_freeze")]
    p75 = fit.drop_duplicates("event_id")["p_equity"].quantile(0.75)
    signs = events.pivot_table(index="event_id", columns="instrument", values="r_30")
    agree = set(signs.index[np.sign(signs["ES.v.0"]) == np.sign(signs["NQ.v.0"])])
    trades = []
    for instrument in ("ES.v.0", "NQ.v.0"):
        data = events.loc[events["instrument"].eq(instrument)].dropna(subset=["r_30"])
        q75 = fit.loc[fit["instrument"].eq(instrument), "r_30"].abs().quantile(0.75)
        chosen = data.loc[(data["p_equity"] > p75) & (data["r_30"].abs() > q75) & data["event_id"].isin(agree)]
        for row in chosen.itertuples(index=False):
            book = books[(row.event_id, instrument)]
            position = np.sign(row.r_30)
            gross = position * ls.log_return_bp(book, 30, 120)
            cost = half_spread_bp(book, 30) + half_spread_bp(book, 120)
            trades.append({"event_id": row.event_id, "instrument": instrument, "split": row.split, "r_30": row.r_30,
                           "p_equity": row.p_equity, "position": position, "gross_bp": gross, "cost_bp": cost,
                           "net_bp": gross - cost})
    trades = pd.DataFrame(trades)
    return trades, _summarize_trades(trades, ["instrument", "split"]) if len(trades) else pd.DataFrame()


# ---------------------------------------------------------------- outputs

def els_paths(meta: pd.DataFrame, books: dict, spec: dict) -> pd.DataFrame:
    """Median live ELS by second, events against controls (descriptive)."""
    m = spec["measures"]
    seconds = np.arange(-300, 1201)
    rows = []
    for row in meta.itertuples(index=False):
        for instrument in spec["sample"]["instruments"]:
            book = books.get((row.event_id, instrument))
            if book is None:
                continue
            live = ls.trailing_els(book, m["live_window_seconds"], tuple(m["baseline_seconds"]))
            rows.append(pd.DataFrame({"instrument": instrument, "day": "event" if row.is_event else "control",
                                      "second": seconds, "els": [book.at(live, s) for s in seconds]}))
    data = pd.concat(rows, ignore_index=True)
    return (data.groupby(["instrument", "day", "second"])["els"]
            .agg(median="median", q25=lambda v: v.quantile(0.25), q75=lambda v: v.quantile(0.75), n="count")
            .reset_index())


def plot_paths(paths: pd.DataFrame, prefix: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    instruments = list(paths["instrument"].unique())
    fig, axes = plt.subplots(1, len(instruments), figsize=(4.2 * len(instruments), 3.4), sharey=True)
    for ax, instrument in zip(np.atleast_1d(axes), instruments):
        for day, color in (("control", "#8a8a8a"), ("event", "#2B5C9E")):
            d = paths.loc[paths["instrument"].eq(instrument) & paths["day"].eq(day)]
            ax.plot(d["second"] / 60, d["median"], color=color, lw=1.6, label=f"{day} days")
            ax.fill_between(d["second"] / 60, d["q25"], d["q75"], color=color, alpha=0.15, lw=0)
        ax.axvline(0, color="black", lw=0.8)
        ax.axhline(0, color="black", lw=0.5, ls=":")
        ax.set_title(SHORT.get(instrument, instrument))
        ax.set_xlabel("minutes from 2:00 p.m.")
    np.atleast_1d(axes)[0].set_ylabel("ELS, trailing 30 s (0 = baseline)")
    np.atleast_1d(axes)[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / f"{prefix}els_paths.png", dpi=160)
    plt.close(fig)


def check_data(meta: pd.DataFrame, books: dict, spec: dict) -> None:
    """Coverage only: no returns, no costs."""
    m = spec["measures"]
    rows = []
    for row in meta.itertuples(index=False):
        for instrument in spec["sample"]["instruments"]:
            book = books.get((row.event_id, instrument))
            rows.append({"day": "event" if row.is_event else "control", "sample": row.sample, "instrument": instrument,
                         "has_book": book is not None,
                         "els_pre_defined": book is not None and np.isfinite(
                             ls.els(book, *m["pre_window_seconds"], tuple(m["baseline_seconds"]))["els"]),
                         "covers_deadline": book is not None and book.index(spec["part_c_execution"]["deadline_second"]) is not None})
    table = pd.DataFrame(rows).groupby(["day", "sample", "instrument"])[["has_book", "els_pre_defined", "covers_deadline"]].sum()
    print(table.to_string())
    print(f"\nimplied vol file used: {meta.attrs.get('use_iv')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-data", action="store_true", help="Coverage only; computes no outcome")
    parser.add_argument("--unfrozen", action="store_true", help="Run before the freeze; tables named liq_unfrozen_*")
    parser.add_argument("--allow-change", action="store_true", help="Run although a hashed file changed (log it)")
    args = parser.parse_args()
    spec = load_yaml(PROJECT_ROOT / PREREGISTRATION) if args.check_data else check_freeze(args.unfrozen, args.allow_change)
    meta, books = load(spec)
    print(f"{meta['is_event'].sum()} FOMC events and {(~meta['is_event']).sum()} control afternoons; "
          f"{len(books)} session-instrument books")
    if args.check_data:
        check_data(meta, books, spec)
        return
    frozen = spec.get("status") == "frozen"
    prefix = "liq_" if frozen else "liq_unfrozen_"
    freeze_date = pd.Timestamp(spec["freeze"]["frozen_at_utc"]).tz_localize(None).normalize() if frozen else None
    TABLES.mkdir(exist_ok=True)

    def write(name: str, table: pd.DataFrame) -> None:
        table.to_csv(TABLES / f"{prefix}{name}.csv", index=False)
        print(f"  tables/{prefix}{name}.csv ({len(table)} rows)")

    features = build_features(meta, books, spec)
    write("features", features)
    a = part_a(features, spec)
    write("a_els_regressions", a)
    b_summary, predictions = part_b(features, spec, meta.attrs.get("use_iv", False))
    write("b_move_size_prediction", b_summary)
    write("b_predictions", predictions)
    sessions, c_summary, c_tests = part_c(meta, books, spec)
    write("c_execution_sessions", sessions)
    write("c_execution_summary", c_summary)
    write("c_execution_tests", c_tests)
    d_trades, d_summary = part_d(features, books, spec, freeze_date)
    write("d_fade_trades", d_trades)
    write("d_fade_summary", d_summary)
    e_trades, e_summary = part_e(features, predictions, books, freeze_date)
    write("e_momentum_trades", e_trades)
    write("e_momentum_summary", e_summary)
    paths = els_paths(meta, books, spec)
    write("els_paths", paths)
    plot_paths(paths, prefix)

    pd.set_option("display.width", 200)
    print("\nA. ELS coefficient on log(1+|move|), per instrument (prediction: negative)")
    print(a.loc[a["test"].eq("move_size"), ["instrument", "horizon", "coef", "se", "p", "holm_p", "n"]].round(4).to_string(index=False))
    print("\nB. Out-of-sample AUC, full minus base")
    print(b_summary.round(3).to_string(index=False) if len(b_summary) else "  (no test years)")
    print("\nC. Execution, primary: adaptive minus calendar spread cost on event days")
    print(c_tests.loc[c_tests["day"].eq("event")].round(4).to_string(index=False))
    print("\nD and E are exploratory; see the summaries above.")


if __name__ == "__main__":
    main()
