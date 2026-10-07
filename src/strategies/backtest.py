"""Strategy registry, trade evaluation and event-level summary statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from src.strategies import fomc_signals as sig
from src.strategies.execution import trade_returns
from src.strategies.fomc_features import INSTRUMENTS
from src.strategies.inference import event_bootstrap_mean, t_test

ES, NQ, ZN = INSTRUMENTS
ALL = list(INSTRUMENTS)


@dataclass
class Strategy:
    strategy_id: str
    name: str
    instruments: list[str]
    role: str                      # primary / secondary / robustness / alias
    hypothesis: str
    logic: str
    features: str
    threshold_definition: str
    direction_rule: str
    rule: Callable = field(repr=False)
    entry: str = "entry5"
    exit: str = "exit20m"

    @property
    def entry_time(self) -> str:
        return "+10:01" if self.entry == "entry10" else "+5:01"

    @property
    def exit_time(self) -> str:
        return {"exit10m": "+10:00", "exit20m": "+20:00", "exit30m": "+30:00"}[self.exit]


def registry() -> list[Strategy]:
    """Every strategy, registered before any evaluation. Order is the report order."""
    large = "abs(ret_0_5m) >= development 75th percentile (per instrument)"
    out = [
        Strategy("P1", "Price-only momentum", ALL, "primary",
                 "A large first-5-minute move continues.", "Slow absorption of the news (H5: the move doubles from 1 to 5 min).",
                 "ret_0_5m", large, "follow sign(ret_0_5m)",
                 lambda s, p, **kw: sig.price_momentum(s, ALL, **kw)),
        Strategy("P2", "Large move + liquidity stress -> momentum", ALL, "primary",
                 "A large move with persistent liquidity stress continues.",
                 "Dealers still withdrawn = disagreement/uncertainty not yet resolved; price keeps adjusting.",
                 "ret_0_5m, depth_ratio_5m, spread_ratio_5m",
                 large + " AND liquidity_stress_5m >= development 75th percentile",
                 "follow sign(ret_0_5m)",
                 lambda s, p, **kw: sig.liquidity_momentum(s, ALL, p, **kw)),
        Strategy("P3", "Large move + liquidity recovery -> reversal", ALL, "primary",
                 "A large move with recovered liquidity stabilizes or reverses.",
                 "Liquidity providers back = news absorbed; the initial move overshot.",
                 "ret_0_5m, depth_ratio_5m, depth_recovery_1_5, spread_ratio_5m, spread_recovery_1_5",
                 large + " AND recovery_score (equal-weight z-sum) >= development 75th percentile",
                 "fade: -sign(ret_0_5m)",
                 lambda s, p, **kw: sig.recovery_reversal(s, ALL, p, **kw)),
        Strategy("S2-NQd", "NQ: large move + depth-only stress", [NQ], "secondary",
                 "Displayed depth alone identifies stress in NQ.", "NQ withdraws mostly through the spread, so depth may miss it.",
                 "ret_0_5m, depth_ratio_5m", large + " AND z(1 - depth_ratio_5m) >= dev 75th pct", "follow",
                 lambda s, p, **kw: sig.liquidity_momentum(s, [NQ], p, score="stress_depth_only", **kw)),
        Strategy("S2-NQs", "NQ: large move + spread-only stress", [NQ], "secondary",
                 "The NQ spread carries the stress signal.", "NQ is not tick-constrained; fear shows as a wider quote.",
                 "ret_0_5m, spread_ratio_5m", large + " AND z(spread_ratio_5m - 1) >= dev 75th pct", "follow",
                 lambda s, p, **kw: sig.liquidity_momentum(s, [NQ], p, score="stress_spread_only", **kw)),
        Strategy("S4-fast", "Large move + fast liquidity recovery -> fade", ALL, "secondary",
                 "Fast +1->+5 recovery marks absorbed news; the move reverses.", "Path of recovery, not only its level.",
                 "ret_0_5m, depth_recovery_slope_1_5, spread_recovery_slope_1_5",
                 large + " AND speed_score >= development 75th percentile", "fade",
                 lambda s, p, **kw: sig.recovery_speed(s, ALL, p, "fast_fade", **kw)),
        Strategy("S4-slow", "Large move + slow/failed recovery -> follow", ALL, "secondary",
                 "Slow or failed recovery marks unresolved news; the move continues.", "Path of recovery.",
                 "ret_0_5m, depth_recovery_slope_1_5, spread_recovery_slope_1_5",
                 large + " AND speed_score <= development 25th percentile", "follow",
                 lambda s, p, **kw: sig.recovery_speed(s, ALL, p, "slow_follow", **kw)),
        Strategy("S5B", "ES/NQ price-confirmed momentum", [ES, NQ], "secondary",
                 "Agreement of two large equity moves makes continuation more likely.", "Cross-market confirmation filters noise.",
                 "ret_0_5m (ES, NQ)", "ES and NQ both large (own dev 75th pct), same sign", "follow, both legs",
                 lambda s, p, **kw: sig.es_nq_confirmed(s, p, with_liquidity=False, **kw)),
        Strategy("S5C", "ES/NQ price + liquidity-confirmed momentum", [ES, NQ], "secondary",
                 "Confirmed moves with stressed books continue most.", "Confirmation plus unresolved liquidity.",
                 "ret_0_5m, liquidity_stress_5m (ES, NQ)",
                 "S5B AND mean(ES, NQ stress) >= dev 75th pct", "follow, both legs",
                 lambda s, p, **kw: sig.es_nq_confirmed(s, p, with_liquidity=True, **kw)),
        Strategy("S6", "Three-market agreement momentum", ALL, "secondary",
                 "A coherent ES/NQ/ZN reaction continues.", "All markets read the news the same way.",
                 "ret_0_5m (ES, NQ, ZN)",
                 "ES, NQ same sign; ZN sign = dev sign(corr(ES, ZN)) x ES sign; every |move| >= 1 dev s.d.",
                 "follow, all legs", lambda s, p, **kw: sig.three_market(s, p, with_liquidity=False, **kw)),
        Strategy("S6L", "Three-market agreement + liquidity stress", ALL, "secondary",
                 "Coherent reaction with stressed books continues most.", "Agreement plus unresolved liquidity.",
                 "ret_0_5m, liquidity_stress_5m (ES, NQ, ZN)", "S6 AND mean stress >= dev 75th pct",
                 "follow, all legs", lambda s, p, **kw: sig.three_market(s, p, with_liquidity=True, **kw)),
        Strategy("S7", "ES/NQ relative-value convergence", [ES, NQ], "secondary",
                 "A large NQ residual vs beta x ES converges.", "Temporary relative mispricing during the reaction.",
                 "ret_0_5m (ES, NQ); dev alpha, beta", "|NQ - (a + b ES)| >= dev 75th pct of |residual|",
                 "short the overshooting leg, long the other x beta",
                 lambda s, p, **kw: sig.es_nq_relative_value(s, p, with_recovery=False, **kw)),
        Strategy("S7R", "ES/NQ relative value + NQ liquidity recovery", [ES, NQ], "secondary",
                 "Residual converges faster when NQ liquidity has recovered.", "Recovered book lets the dislocation close.",
                 "S7 + NQ recovery_score", "S7 AND NQ recovery_score >= dev median", "as S7",
                 lambda s, p, **kw: sig.es_nq_relative_value(s, p, with_recovery=True, **kw)),
        Strategy("S9-fade", "ZN: large move + strong replenishment at +10m -> fade", [ZN], "secondary",
                 "Strong ZN depth replenishment marks overshoot; the move reverses.", "ZN depth overshoots after the news.",
                 "ret_0_5m, depth_ratio_10m (ZN)", large + " AND depth_ratio_10m >= ZN dev 75th pct", "fade",
                 lambda s, p, **kw: sig.zn_replenishment(s, p, "replenished_fade", **kw), entry="entry10"),
        Strategy("S9-follow", "ZN: large move + still-thin book at +10m -> follow", [ZN], "secondary",
                 "Thin ZN book at +10m marks unresolved news; the move continues.", "Liquidity has not returned.",
                 "ret_0_5m, depth_ratio_10m (ZN)", large + " AND depth_ratio_10m <= ZN dev 25th pct", "follow",
                 lambda s, p, **kw: sig.zn_replenishment(s, p, "thin_follow", **kw), entry="entry10"),
    ]
    for base in out[:3]:   # robustness exits for the primary hypotheses
        for exit_ in ("exit10m", "exit30m"):
            out.append(Strategy(f"{base.strategy_id}-{exit_[4:]}", f"{base.name} (exit {exit_[4:]})", base.instruments,
                                "robustness", base.hypothesis, base.logic, base.features, base.threshold_definition,
                                base.direction_rule, base.rule, exit=exit_))
    return out


def registry_frame(strategies: list[Strategy]) -> pd.DataFrame:
    rows = [{
        "strategy_id": s.strategy_id, "strategy_name": s.name, "instrument": "|".join(i[:2] for i in s.instruments),
        "entry_time": s.entry_time, "exit_time": s.exit_time, "features": s.features,
        "threshold_definition": s.threshold_definition, "direction_rule": s.direction_rule,
        "primary_or_secondary": s.role, "development_or_fixed": "development-estimated, frozen before holdout",
        "hypothesis": s.hypothesis, "economic_logic": s.logic,
    } for s in strategies]
    rows.append({"strategy_id": "S8", "strategy_name": "ZN liquidity-confirmed momentum (= P1, P2 on ZN)",
                 "instrument": "ZN", "entry_time": "+5:01", "exit_time": "+20:00", "features": "as P1, P2",
                 "threshold_definition": "ZN-specific development thresholds", "direction_rule": "follow",
                 "primary_or_secondary": "alias of P1/P2 ZN rows", "development_or_fixed": "development-estimated",
                 "hypothesis": "ZN price + liquidity beats ZN price only", "economic_logic": "as P2"})
    rows.append({"strategy_id": "S10", "strategy_name": "Second-level order-book predictability (research test)",
                 "instrument": "ES|NQ|ZN", "entry_time": "every second +1:00..+29:00", "exit_time": "+5s/+30s/+60s",
                 "features": "depth, bid/ask depth, imbalance, spread levels and 5/10/30/60s changes, past return",
                 "threshold_definition": "none (regression; dev-fitted coefficients, holdout out-of-sample R2)",
                 "direction_rule": "n/a", "primary_or_secondary": "secondary (research)",
                 "development_or_fixed": "development-fitted", "hypothesis": "Book changes predict next-second returns",
                 "economic_logic": "Order-book pressure leads price at very short horizons"})
    return pd.DataFrame(rows)


def evaluate(trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Attach executable returns to each trade leg."""
    if trades.empty:
        return trades.assign(gross_bp=[], executable_bp=[], net_bp=[], net_slip_bp=[], cost_bp=[])
    quotes = features.set_index(["event_id", "instrument"])
    rows = []
    for (entry, exit_), group in trades.groupby(["entry", "exit"]):
        q = quotes.loc[list(zip(group["event_id"], group["instrument"]))]
        r = trade_returns(group["direction"].to_numpy(), q[f"bid_{entry}"], q[f"ask_{entry}"], q[f"mid_{entry}"],
                          q[f"bid_{exit_}"], q[f"ask_{exit_}"], q[f"mid_{exit_}"], group["instrument"].to_numpy())
        rows.append(pd.concat([group.reset_index(drop=True), r.reset_index(drop=True)], axis=1))
    return pd.concat(rows, ignore_index=True)


def event_returns(legs: pd.DataFrame, column: str) -> pd.Series:
    """Weighted return per event (multi-leg strategies become one observation per event)."""
    w = legs["weight"] / legs.groupby("event_id")["weight"].transform("sum")
    return (legs[column] * w).groupby(legs["event_id"]).sum(min_count=1)


def summarize(legs: pd.DataFrame, n_events: int, dates: pd.Series) -> dict:
    """Event-level statistics. ``dates`` maps event_id -> date (for chronological drawdown)."""
    if legs.empty or legs["net_bp"].notna().sum() == 0:
        return {"N_events": n_events, "N_trades": 0}
    per = {c: event_returns(legs, c) for c in ("gross_bp", "executable_bp", "net_bp", "net_slip_bp")}
    net = per["net_bp"].dropna()
    order = net.index.map(dates).argsort()
    cumulative = net.iloc[order].cumsum()
    t, p = t_test(net)
    lo, hi = event_bootstrap_mean(net)
    std = net.std(ddof=1) if len(net) > 1 else np.nan
    return {
        "N_events": n_events, "N_trades": int(len(net)),
        "avg_gross_return": per["gross_bp"].mean(), "avg_executable_return": per["executable_bp"].mean(),
        "avg_net_return": net.mean(), "avg_net_slip_return": per["net_slip_bp"].mean(),
        "median_net_return": net.median(), "std_net_return": std, "hit_rate": float((net > 0).mean()),
        "t_stat": t, "p_value": p, "CI_low": lo, "CI_high": hi,
        "sharpe_like": net.mean() / std if std and std > 0 else np.nan,
        "cumulative_pnl": float(net.sum()), "worst_trade": float(net.min()),
        "max_drawdown": float((cumulative - cumulative.cummax()).min()),
    }
