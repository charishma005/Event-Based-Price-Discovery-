"""Frozen development-sample parameters and the registered trade rules.

``estimate_params`` accepts development rows only (it raises otherwise), so no
threshold, z-score, beta or cross-market relationship can see the holdout.
``apply_params`` turns features into signal variables with those frozen
numbers; the rule functions turn signal variables into trades. None of this
reads targets (future returns) or any USMPD surprise.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.strategies.fomc_features import INSTRUMENTS

Q_LARGE = 0.75          # large move and persistent stress: development 75th percentile
Q_LOW, Q_HIGH = 0.25, 0.75
ES, NQ, ZN = INSTRUMENTS


def _z(params: dict, name: str, values: pd.Series) -> pd.Series:
    mean, std = params[f"{name}_mean"], params[f"{name}_std"]
    if std and np.isfinite(std) and std > 0:
        return (values - mean) / std
    return values * 0.0      # no development variation: the part carries no information (NaN stays NaN)


# Raw ingredients of each score, all oriented so that "higher" has the stated meaning.
def _stress_parts(f: pd.DataFrame) -> dict[str, pd.Series]:
    return {"stress_depth": 1 - f["depth_ratio_5m"], "stress_spread": f["spread_ratio_5m"] - 1}


def _recovery_parts(f: pd.DataFrame) -> dict[str, pd.Series]:
    return {"rec_depth_level": f["depth_ratio_5m"], "rec_depth_change": f["depth_recovery_1_5"],
            "rec_spread_level": -f["spread_ratio_5m"], "rec_spread_change": f["spread_recovery_1_5"]}


def _speed_parts(f: pd.DataFrame) -> dict[str, pd.Series]:
    return {"speed_depth": f["depth_recovery_slope_1_5"], "speed_spread": f["spread_recovery_slope_1_5"]}


def _moments(values: pd.Series) -> tuple[float, float]:
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    return float(values.mean()), float(values.std(ddof=1))


def estimate_params(dev: pd.DataFrame) -> dict:
    """All frozen numbers, estimated on development rows only."""
    if not dev["sample"].eq("development").all():
        raise ValueError("estimate_params must only see development rows")
    params: dict = {"instruments": {}, "cross": {}}
    for instrument, f in dev.groupby("instrument"):
        p: dict = {"n_events": int(f["event_id"].nunique())}
        p["move_q75"] = float(f["abs_ret_0_5m"].quantile(Q_LARGE))
        p["ret_0_5m_mean"], p["ret_0_5m_std"] = _moments(f["ret_0_5m"])
        for parts in (_stress_parts(f), _recovery_parts(f), _speed_parts(f)):
            for name, values in parts.items():
                p[f"{name}_mean"], p[f"{name}_std"] = _moments(values)
        scored = apply_instrument(f, p)
        for score in ("stress", "stress_depth_only", "stress_spread_only", "recovery_score"):
            p[f"{score}_q75"] = float(scored[score].quantile(Q_LARGE))
        p["speed_score_q25"] = float(scored["speed_score"].quantile(Q_LOW))
        p["speed_score_q75"] = float(scored["speed_score"].quantile(Q_HIGH))
        if instrument == ZN and "depth_ratio_10m" in f:
            p["depth_ratio_10m_q25"] = float(f["depth_ratio_10m"].quantile(Q_LOW))
            p["depth_ratio_10m_q75"] = float(f["depth_ratio_10m"].quantile(Q_HIGH))
        params["instruments"][instrument] = p
    wide = dev.pivot_table(index="event_id", columns="instrument", values="ret_0_5m")
    pair = wide[[ES, NQ]].dropna() if {ES, NQ} <= set(wide) else pd.DataFrame()
    if len(pair) >= 10:
        beta, alpha = np.polyfit(pair[ES], pair[NQ], 1)
        resid = pair[NQ] - (alpha + beta * pair[ES])
        params["cross"].update({"es_nq_alpha": float(alpha), "es_nq_beta": float(beta),
                                "es_nq_abs_resid_q75": float(resid.abs().quantile(Q_LARGE)), "es_nq_n": len(pair)})
    trio = wide[[ES, ZN]].dropna() if {ES, ZN} <= set(wide) else pd.DataFrame()
    if len(trio) >= 10:
        corr = float(trio[ES].corr(trio[ZN]))
        params["cross"].update({"es_zn_corr": corr, "zn_expected_sign_vs_es": float(np.sign(corr) or 1.0)})
    scored = apply_params(dev, params)
    stress = scored.pivot_table(index="event_id", columns="instrument", values="stress")
    if {ES, NQ} <= set(stress):
        params["cross"]["es_nq_mean_stress_q75"] = float(stress[[ES, NQ]].mean(axis=1).quantile(Q_LARGE))
    if set(INSTRUMENTS) <= set(stress):
        params["cross"]["three_mean_stress_q75"] = float(stress[list(INSTRUMENTS)].mean(axis=1).quantile(Q_LARGE))
    nq_rec = scored.loc[scored["instrument"].eq(NQ), "recovery_score"]
    params["cross"]["nq_recovery_median"] = float(nq_rec.median())
    return params


def apply_instrument(f: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Signal variables for one instrument with frozen parameters ``p``."""
    out = f.copy()
    s = _stress_parts(f)
    z_depth, z_spread = _z(p, "stress_depth", s["stress_depth"]), _z(p, "stress_spread", s["stress_spread"])
    out["stress_depth_only"], out["stress_spread_only"] = z_depth, z_spread
    out["stress"] = z_depth + z_spread                              # liquidity_stress_5m
    out["recovery_score"] = sum(_z(p, k, v) for k, v in _recovery_parts(f).items())
    out["speed_score"] = sum(_z(p, k, v) for k, v in _speed_parts(f).items())
    out["move_z"] = _z(p, "ret_0_5m", f["ret_0_5m"])
    out["direction_5m"] = np.sign(f["ret_0_5m"])
    if "move_q75" in p:
        out["large_move"] = f["abs_ret_0_5m"] >= p["move_q75"]
    return out


def apply_params(features: pd.DataFrame, params: dict) -> pd.DataFrame:
    frames = [apply_instrument(f, params["instruments"][i]) for i, f in features.groupby("instrument")
              if i in params["instruments"]]
    return pd.concat(frames).sort_index()


def save_params(params: dict, path) -> None:
    path.write_text(json.dumps(params, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------- trade rules
# Each rule returns trades: event_id, instrument, direction (+1/-1), weight, plus timing keys.
# Rules read signal variables and +5m (or +10m) features only.

def _trades(rows: pd.DataFrame, direction: pd.Series, entry="entry5", exit_="exit20m", weight=1.0) -> pd.DataFrame:
    out = rows[["event_id", "instrument", "sample"]].copy()
    out["direction"] = direction.astype(float)
    out["weight"] = weight
    out["entry"], out["exit"] = entry, exit_
    return out.loc[out["direction"].abs() > 0]


def price_momentum(s: pd.DataFrame, instruments, **kw) -> pd.DataFrame:
    rows = s.loc[s["instrument"].isin(instruments) & s["large_move"]]
    return _trades(rows, rows["direction_5m"], **kw)


def liquidity_momentum(s: pd.DataFrame, instruments, params, score="stress", **kw) -> pd.DataFrame:
    q = s["instrument"].map(lambda i: params["instruments"][i][f"{score}_q75"])
    rows = s.loc[s["instrument"].isin(instruments) & s["large_move"] & (s[score] >= q)]
    return _trades(rows, rows["direction_5m"], **kw)


def recovery_reversal(s: pd.DataFrame, instruments, params, **kw) -> pd.DataFrame:
    q = s["instrument"].map(lambda i: params["instruments"][i]["recovery_score_q75"])
    rows = s.loc[s["instrument"].isin(instruments) & s["large_move"] & (s["recovery_score"] >= q)]
    return _trades(rows, -rows["direction_5m"], **kw)


def recovery_speed(s: pd.DataFrame, instruments, params, mode: str, **kw) -> pd.DataFrame:
    p = s["instrument"].map(lambda i: params["instruments"][i])
    fast = s["speed_score"] >= p.map(lambda x: x["speed_score_q75"])
    slow = s["speed_score"] <= p.map(lambda x: x["speed_score_q25"])
    keep = s["instrument"].isin(instruments) & s["large_move"] & (fast if mode == "fast_fade" else slow)
    rows = s.loc[keep]
    sign = -1 if mode == "fast_fade" else 1
    return _trades(rows, sign * rows["direction_5m"], **kw)


def _wide(s: pd.DataFrame, column: str) -> pd.DataFrame:
    return s.pivot_table(index="event_id", columns="instrument", values=column, aggfunc="first")


def es_nq_confirmed(s: pd.DataFrame, params, with_liquidity: bool, **kw) -> pd.DataFrame:
    large, sign, stress = _wide(s, "large_move"), _wide(s, "direction_5m"), _wide(s, "stress")
    ok = (large[ES].astype(bool) & large[NQ].astype(bool) & sign[ES].eq(sign[NQ]) & sign[ES].ne(0))
    if with_liquidity:
        ok &= stress[[ES, NQ]].mean(axis=1) >= params["cross"]["es_nq_mean_stress_q75"]
    events = ok.index[ok.fillna(False)]
    rows = s.loc[s["event_id"].isin(events) & s["instrument"].isin([ES, NQ])]
    return _trades(rows, rows["direction_5m"], weight=0.5, **kw)


def three_market(s: pd.DataFrame, params, with_liquidity: bool, **kw) -> pd.DataFrame:
    """Coherent ES/NQ/ZN reaction, using the development sign of the ES-ZN co-movement."""
    sign, move = _wide(s, "direction_5m"), _wide(s, "move_z")
    expected = params["cross"]["zn_expected_sign_vs_es"]
    agree = sign[ES].eq(sign[NQ]) & sign[ZN].eq(expected * sign[ES]) & sign[ES].ne(0)
    strong = move[list(INSTRUMENTS)].abs().min(axis=1) >= 1.0   # every market at least 1 development s.d.
    ok = agree & strong
    if with_liquidity:
        ok &= _wide(s, "stress")[list(INSTRUMENTS)].mean(axis=1) >= params["cross"]["three_mean_stress_q75"]
    events = ok.index[ok.fillna(False)]
    rows = s.loc[s["event_id"].isin(events)]
    return _trades(rows, rows["direction_5m"], weight=1 / 3, **kw)


def es_nq_relative_value(s: pd.DataFrame, params, with_recovery: bool, **kw) -> pd.DataFrame:
    """Beta-neutral ES/NQ convergence trade on a large +5m NQ residual (beta from development)."""
    c = params["cross"]
    ret = _wide(s, "ret_0_5m")
    resid = ret[NQ] - (c["es_nq_alpha"] + c["es_nq_beta"] * ret[ES])
    ok = resid.abs() >= c["es_nq_abs_resid_q75"]
    if with_recovery:
        rec = s.loc[s["instrument"].eq(NQ)].set_index("event_id")["recovery_score"]
        ok &= rec.reindex(resid.index) >= c["nq_recovery_median"]
    events = ok.index[ok.fillna(False)]
    rows = s.loc[s["event_id"].isin(events) & s["instrument"].isin([ES, NQ])].copy()
    side = -np.sign(resid.reindex(rows["event_id"]).to_numpy())   # NQ overshoot -> short NQ, long ES
    direction = np.where(rows["instrument"].eq(NQ), side, -side)
    weight = np.where(rows["instrument"].eq(NQ), 1.0, abs(c["es_nq_beta"]))
    out = _trades(rows, pd.Series(direction, index=rows.index), **kw)
    out["weight"] = pd.Series(weight, index=rows.index).reindex(out.index)
    return out


def zn_replenishment(s: pd.DataFrame, params, mode: str, **kw) -> pd.DataFrame:
    """ZN at +10m: strong replenishment -> fade; still thin -> follow. Entry +10:01, exit +20:00."""
    p = params["instruments"][ZN]
    rows = s.loc[s["instrument"].eq(ZN) & s["large_move"]]
    if mode == "replenished_fade":
        rows = rows.loc[rows["depth_ratio_10m"] >= p["depth_ratio_10m_q75"]]
        direction = -rows["direction_5m"]
    else:
        rows = rows.loc[rows["depth_ratio_10m"] <= p["depth_ratio_10m_q25"]]
        direction = rows["direction_5m"]
    return _trades(rows, direction, **kw)   # the registry sets entry="entry10" for these
