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


def test_h6_clear_surprises_drop_smallest_quartile_and_flag_hawkish() -> None:
    from scripts.analyze_fomc_h6_horizons import clear_surprises

    surprises = pd.DataFrame({"meeting": [f"m{i}" for i in range(8)], "STMT": [-0.4, -0.3, -0.2, -0.01, 0.0, 0.02, 0.3, 0.5]})
    kept = clear_surprises(surprises, "STMT")
    assert {"m3", "m4"}.isdisjoint(kept["meeting"])
    assert kept.set_index("meeting")["hawkish"].to_dict()["m7"] == 1.0
    assert kept.set_index("meeting")["hawkish"].to_dict()["m0"] == 0.0


def test_h6_direction_counts_moves_that_match_the_news() -> None:
    from scripts.analyze_fomc_h6_horizons import direction_rows

    meetings = [f"m{i}" for i in range(10)]
    stmt = np.array([0.5, 0.4, 0.3, 0.2, 0.1, -0.1, -0.2, -0.3, -0.4, -0.5])
    surprises = pd.DataFrame({"meeting": meetings, "STMT": stmt, "STMT_real_time": stmt})
    # Hawkish -> price falls, dovish -> price rises: every move is in the expected direction.
    returns = pd.DataFrame(
        {"meeting": meetings, "instrument": "ES.v.0", "horizon_seconds": 5, "log_return_bp": -10 * stmt}
    )
    table = direction_rows(returns, surprises)
    assert table["expected_direction_share"].eq(1.0).all()


def test_h6_asymmetry_recovers_constructed_hawkish_effect() -> None:
    from scripts.analyze_fomc_h6_horizons import asymmetry_rows

    rng = np.random.default_rng(0)
    meetings = [f"m{i}" for i in range(40)]
    stmt = np.where(np.arange(40) % 2 == 0, 1, -1) * rng.uniform(0.2, 1.0, 40)
    surprises = pd.DataFrame({"meeting": meetings, "STMT": stmt, "STMT_real_time": stmt})
    outcome = np.abs(stmt) + np.where(stmt > 0, 1.0, 0.0) + rng.normal(0, 0.05, 40)
    frame = pd.DataFrame({"meeting": meetings, "instrument": "ES.v.0", "horizon_seconds": 5, "y": outcome})
    table = asymmetry_rows(frame, "y", surprises)
    assert table["hawkish_coef_given_magnitude"].between(0.9, 1.1).all()
    assert table["hawkish_coef_p_two_sided"].lt(1e-6).all()
