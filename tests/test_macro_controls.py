import numpy as np
import pandas as pd

from scripts.analyze_macro_extension import paired_table
from scripts.screen_macro_controls_by_volume import RELEASE_MINUTE, flagged, volume_ratios

DAY = 20200102


def _bars(volumes: dict[int, int], instrument: str = "ES.v.0", day: int = DAY) -> pd.DataFrame:
    return pd.DataFrame({"instrument": instrument, "day": day, "minute_of_day": list(volumes),
                         "volume": list(volumes.values())})


def test_volume_ratio_is_the_release_bar_over_the_mean_of_the_ten_minutes_before():
    before = {RELEASE_MINUTE - k: 100 for k in range(1, 11)}
    bars = pd.concat([_bars({**before, RELEASE_MINUTE: 450}), _bars({**before, RELEASE_MINUTE: 50}, "ZN.v.0")])
    ratios = volume_ratios(bars, [DAY])
    assert ratios.loc[DAY, "ES.v.0"] == 4.5
    assert ratios.loc[DAY, "ZN.v.0"] == 0.5


def test_a_minute_without_a_bar_counts_as_zero_volume():
    # Five of the ten baseline minutes traded 100 contracts: the mean is 50, not 100.
    before = {RELEASE_MINUTE - k: 100 for k in range(1, 6)}
    ratios = volume_ratios(_bars({**before, RELEASE_MINUTE: 100}), [DAY])
    assert ratios.loc[DAY, "ES.v.0"] == 2.0


def test_other_minutes_and_other_days_are_ignored():
    before = {RELEASE_MINUTE - k: 100 for k in range(1, 11)}
    wanted = _bars({**before, RELEASE_MINUTE: 300, RELEASE_MINUTE - 11: 10_000, RELEASE_MINUTE + 1: 10_000})
    other = _bars({**before, RELEASE_MINUTE: 900}, day=DAY + 1)
    ratios = volume_ratios(pd.concat([wanted, other]), [DAY])
    assert list(ratios.index) == [DAY]
    assert ratios.loc[DAY, "ES.v.0"] == 3.0


def test_a_control_morning_is_flagged_on_es_or_zn_only():
    screen = pd.DataFrame({"es_volume_ratio_0830": [1.0, 3.0, 1.0], "nq_volume_ratio_0830": [9.0, 1.0, 1.0],
                           "zn_volume_ratio_0830": [1.0, 1.0, 3.5]})
    assert flagged(screen).tolist() == [False, True, True]


def test_paired_table_pairs_releases_with_the_control_mornings_of_the_same_month():
    rng = np.random.default_rng(0)
    rows = []
    for month in range(1, 13):
        for instrument in ("ES.v.0", "NQ.v.0", "ZN.v.0"):
            for _ in range(2):          # two releases in the month, one control morning
                rows.append({"cluster": f"2020-{month:02d}", "instrument": instrument, "role": "event",
                             "ratio": 0.6 + 0.01 * rng.standard_normal()})
            rows.append({"cluster": f"2020-{month:02d}", "instrument": instrument, "role": "control",
                         "ratio": 1.0 + 0.01 * rng.standard_normal()})
    rows.append({"cluster": "2021-01", "instrument": "ES.v.0", "role": "event", "ratio": 5.0})   # no control: left out
    frame = pd.DataFrame(rows)
    table = paired_table(frame.loc[frame["role"].eq("event")], frame.loc[frame["role"].eq("control")],
                         "cluster", {"depth_ratio": "ratio"}).set_index("instrument")
    assert set(table.index) == {"ES.v.0", "NQ.v.0", "ZN.v.0", "cluster_average"}
    es = table.loc["ES.v.0"]
    assert es["clusters"] == 12 and es["clusters_event_lower"] == 12
    assert abs(es["mean_difference"] + 0.4) < 0.02
    assert es["ci_low"] < es["mean_difference"] < es["ci_high"] < 0
    assert es["wilcoxon_p_two_sided"] < 0.01
    assert es["holm_p"] >= es["wilcoxon_p_two_sided"]
    assert np.isnan(table.loc["cluster_average", "holm_p"])
