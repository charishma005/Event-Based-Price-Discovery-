from __future__ import annotations

import pandas as pd

from src.utils.config import PROJECT_ROOT


def test_hypothesis_status_distinguishes_unidentified_from_rejected() -> None:
    status = pd.read_csv(PROJECT_ROOT / "tables" / "hypothesis_status.csv").set_index(
        "hypothesis"
    )
    assert status.loc["H1", "status"] == "Rejected"
    assert status.loc["H2", "status"] == "Supported in sample"
    assert status.loc["H3", "status"] == "Not identified"
    assert status.loc["H5", "status"] == "Not supported"
    assert status.loc["H6", "status"] == "Inconclusive"


def test_h5_claim_matches_surprise_speed_table() -> None:
    h5 = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_h5_surprise_speed.csv")
    row = h5.loc[
        h5["subevent"].eq("statement")
        & h5["metric"].eq("first_crossing_50_seconds")
        & h5["instrument"].eq("meeting_average")
        & h5["measure"].eq("STMT")
    ].iloc[0]
    assert row["spearman_rho_abs_surprise"] < 0
    assert row["two_sided_p"] < 0.01


def test_h2_and_speed_claims_match_reproducible_tables() -> None:
    h2 = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_h2_quote_fraction.csv")
    assert h2["count_below_40pct"].eq(h2["observations"]).all()
    assert h2["one_sided_wilcoxon_below_40pct_p"].lt(0.05).all()
    speed = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_speed_inference.csv")
    crossing = speed.loc[speed["metric"].eq("first_crossing_50_seconds")]
    stable = speed.loc[speed["metric"].eq("stable_within_10pct_seconds")]
    assert crossing["one_sided_wilcoxon_p_statement_faster"].lt(0.05).all()
    assert stable["one_sided_wilcoxon_p_statement_faster"].ge(0.05).all()
