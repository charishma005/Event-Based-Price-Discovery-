from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT


def test_hypothesis_status_distinguishes_unidentified_from_rejected() -> None:
    status = pd.read_csv(PROJECT_ROOT / "tables" / "hypothesis_status.csv").set_index(
        "hypothesis"
    )
    assert status.loc["H1", "status"] == "Rejected"
    assert status.loc["H2", "status"] == "Supported in sample"
    assert status.loc[["H3", "H5", "H6"], "status"].eq("Not identified").all()


def test_h2_and_speed_claims_match_reproducible_tables() -> None:
    h2 = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_h2_quote_fraction.csv")
    assert h2["count_below_40pct"].eq(h2["observations"]).all()
    assert h2["one_sided_wilcoxon_below_40pct_p"].lt(0.05).all()
    speed = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_speed_inference.csv")
    crossing = speed.loc[speed["metric"].eq("first_crossing_50_seconds")]
    stable = speed.loc[speed["metric"].eq("stable_within_10pct_seconds")]
    assert crossing["one_sided_wilcoxon_p_statement_faster"].lt(0.05).all()
    assert stable["one_sided_wilcoxon_p_statement_faster"].ge(0.05).all()
