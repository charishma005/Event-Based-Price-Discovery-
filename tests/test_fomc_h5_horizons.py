from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.analyze_fomc_h5_horizons import (
    ENDPOINT,
    _correlations,
    absolute_returns,
    response_fractions,
    surprise_terciles,
)


def _horizons(rows: list[tuple[str, str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "meeting": meeting,
                "instrument": instrument,
                "horizon_seconds": horizon,
                "log_return_bp": value,
                "subevent": "statement",
                "dataset_condition": "available",
                "full_horizon_covered": True,
            }
            for meeting, instrument, horizon, value in rows
        ]
    )


def test_absolute_returns_uses_magnitudes_and_needs_both_equities_for_average() -> None:
    data = _horizons(
        [
            ("m1", "ES.v.0", 5, -4.0),
            ("m1", "NQ.v.0", 5, 6.0),
            ("m2", "ES.v.0", 5, 3.0),
            ("m2", "ZN.v.0", 5, -2.0),
        ]
    )
    returns = absolute_returns(data)
    assert (returns["abs_return_bp"] >= 0).all()
    equity = returns.loc[returns["instrument"].eq("equity_average")]
    assert equity["meeting"].tolist() == ["m1"]
    assert equity["abs_return_bp"].iloc[0] == 5.0


def test_absolute_returns_drops_uncovered_horizons_and_press_rows() -> None:
    data = _horizons([("m1", "ES.v.0", ENDPOINT, 10.0), ("m2", "ES.v.0", ENDPOINT, 12.0)])
    data.loc[0, "full_horizon_covered"] = False
    data.loc[1, "subevent"] = "press_conference"
    assert absolute_returns(data).empty


def test_response_fractions_divide_by_30m_and_drop_bottom_quartile_endpoints() -> None:
    rows = []
    for i, end in enumerate([0.5, 8.0, 10.0, 20.0]):
        rows += [(f"m{i}", "ES.v.0", 5, end / 2), (f"m{i}", "ES.v.0", ENDPOINT, end)]
    fractions = response_fractions(absolute_returns(_horizons(rows)))
    es = fractions.loc[fractions["instrument"].eq("ES.v.0")]
    assert "m0" not in set(es["meeting"])
    early = es.loc[es["horizon_seconds"].eq(5), "fraction"]
    assert np.allclose(early, 0.5)


def test_surprise_terciles_split_meetings_into_equal_groups() -> None:
    surprises = pd.DataFrame({"meeting": [f"m{i}" for i in range(9)], "STMT": np.linspace(-0.4, 0.4, 9)})
    groups = surprise_terciles(surprises)
    assert groups.value_counts().to_dict() == {"small": 3, "medium": 3, "large": 3}
    assert groups["m4"] == "small" and groups["m0"] == "large"


def test_correlations_detect_constructed_positive_relation() -> None:
    meetings = [f"m{i}" for i in range(12)]
    surprises = pd.DataFrame({"meeting": meetings, "STMT": np.arange(12) / 10, "STMT_real_time": np.arange(12) / 10})
    returns = pd.DataFrame(
        {"meeting": meetings, "instrument": "ES.v.0", "horizon_seconds": 5, "abs_return_bp": np.arange(12) + 1.0}
    )
    table = _correlations(returns, "abs_return_bp", "greater", surprises)
    assert table["spearman_rho"].gt(0.99).all()
    assert table["one_sided_p_positive"].lt(0.001).all()
    assert {"holm_p", "bh_q"} <= set(table.columns)
