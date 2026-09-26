from __future__ import annotations

import pandas as pd
import numpy as np

from scripts.analyze_subsecond_price_discovery import _first_move_rows, _grid_returns


def test_first_material_move_uses_absolute_basis_point_threshold() -> None:
    event = pd.Timestamp("2025-01-01T14:00:00Z")
    path = pd.DataFrame(
        {
            "ts_event": [event + pd.Timedelta(milliseconds=25), event + pd.Timedelta(milliseconds=80)],
            "midpoint": [100.004, 99.98],
            "delay_ms": [25.0, 80.0],
            "return_bp": [0.4, -2.0],
            "reference_midpoint": [100.0, 100.0],
        }
    )
    rows = pd.DataFrame(_first_move_rows({"ES.v.0": path}, "meeting", "statement"))
    assert rows.loc[rows["threshold_bp"].eq(0.5), "first_crossing_delay_ms"].iloc[0] == 80.0
    assert rows.loc[rows["threshold_bp"].eq(2.0), "crossed_within_30s"].iloc[0]


def test_grid_returns_preserves_event_jump_from_pre_event_reference() -> None:
    event = pd.Timestamp("2025-01-01T14:00:00Z")
    path = pd.DataFrame(
        {
            "ts_event": [event + pd.Timedelta(milliseconds=10)],
            "midpoint": [101.0],
            "return_bp": [10000.0 * np.log(1.01)],
            "reference_midpoint": [100.0],
        }
    )
    returns = _grid_returns(path, event)
    assert returns.iloc[0] > 0
