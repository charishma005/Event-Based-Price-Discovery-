from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from scripts.analyze_fomc_surprises import _h5_rows, _h6_rows, _meetings
from src.events.surprises import (
    FUTNAMES,
    build_surprise_panel,
    compute_gss,
    compute_mps,
    compute_mps_real_time,
)


def _synthetic_futures(n: int = 200, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    target, path = rng.normal(size=(2, n))
    loadings = {"MP1": (1.0, 0.0), "MP2": (0.9, 0.3), "ED2": (0.7, 0.6), "ED3": (0.5, 0.8), "ED4": (0.4, 0.9)}
    dates = [dt.date(2000, 1, 1) + dt.timedelta(days=7 * i) for i in range(n)]
    futures = pd.DataFrame({"Date": dates})
    for name, (a, b) in loadings.items():
        futures[name] = 0.05 * (a * target + b * path) + 0.005 * rng.normal(size=n)
    y1 = pd.DataFrame({"Date": dates, "dy1": 0.03 * (0.6 * target + 0.8 * path) + 0.01 * rng.normal(size=n)})
    return futures, y1


def test_gss_factors_satisfy_normalizations() -> None:
    futures, _ = _synthetic_futures()
    factors = compute_gss(futures)
    design = np.column_stack([np.ones(len(factors)), factors["target"], factors["path"]])
    mp1 = np.linalg.lstsq(design, futures["MP1"], rcond=None)[0]
    ed4 = np.linalg.lstsq(design, futures["ED4"], rcond=None)[0]
    assert mp1[1] == pytest.approx(1.0)
    assert mp1[2] == pytest.approx(0.0, abs=1e-10)
    assert ed4[1] == pytest.approx(ed4[2])
    assert np.corrcoef(factors["target"], futures["MP1"])[0, 1] > 0


def test_mps_is_scaled_to_one_year_yield_and_hawkish_positive() -> None:
    futures, y1 = _synthetic_futures()
    mps = compute_mps(futures, y1)
    slope = np.polyfit(mps.to_numpy(), y1["dy1"].to_numpy(), 1)[0]
    assert slope == pytest.approx(1.0)
    assert np.corrcoef(mps, futures[list(FUTNAMES)].mean(axis=1))[0, 1] > 0


def test_real_time_mps_uses_no_future_events() -> None:
    futures, y1 = _synthetic_futures()
    date = futures["Date"].iloc[120]
    real_time = compute_mps_real_time(futures, y1, [date])
    truncated = compute_mps(futures.iloc[:121], y1)
    assert real_time.loc[date] == pytest.approx(truncated.loc[date])
    assert real_time.loc[date] != pytest.approx(compute_mps(futures, y1).loc[date])


def test_panel_attaches_published_surprises_to_sample_meetings(tmp_path) -> None:
    panel = build_surprise_panel(_meetings(), usmpd_path=tmp_path / "missing.xlsx").set_index("meeting")
    assert panel.loc["fomc_20241218", "STMT"] == pytest.approx(0.054929543948452716)
    assert panel.loc["fomc_20250730", "PC"] == pytest.approx(0.059754369148656734)
    available = panel.loc[panel["dataset_condition"].eq("available")]
    assert available[["STMT", "PC"]].notna().all().all()


def test_h5_and_h6_rows_detect_constructed_relationships() -> None:
    surprise = np.array([-0.08, -0.05, -0.03, -0.01, 0.01, 0.02, 0.04, 0.06, 0.09, 0.12])
    seconds = 5 + 200 * np.abs(surprise) + np.where(surprise > 0, 3.0, 0.0)
    data = pd.DataFrame(
        {
            "meeting": [f"m{i}" for i in range(10)],
            "subevent": "press_conference",
            "metric": "first_crossing_50_seconds",
            "instrument": "ES.v.0",
            "seconds": seconds,
            "log_seconds": np.log1p(seconds),
            "PC": surprise,
        }
    )
    h5 = pd.DataFrame(_h5_rows(data))
    h6 = pd.DataFrame(_h6_rows(data))
    assert h5["spearman_rho_abs_surprise"].iloc[0] > 0.8
    assert h5["one_sided_p_positive"].iloc[0] < 0.01
    assert h6["hawkish_log_coef_given_magnitude"].iloc[0] > 0
    assert h6["hawkish_count"].iloc[0] == 6
