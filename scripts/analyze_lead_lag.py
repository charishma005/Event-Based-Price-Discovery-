from __future__ import annotations

import databento as db
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.events.registry import pilot_events
from src.utils.config import PROJECT_ROOT


BAR_PATH = PROJECT_ROOT / "data" / "raw" / "databento" / "GLBX.MDP3-ohlcv-1s-6ed5fca61b6588eb.dbn.zst"
INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
EVENTS = ("statement", "press_conference")


def main() -> None:
    metadata = pilot_events()
    bars = db.DBNStore.from_file(BAR_PATH).to_df().reset_index()
    timestamp_column = bars.columns[0]
    bars = bars.rename(columns={timestamp_column: "timestamp_utc"})
    bars["timestamp_utc"] = pd.to_datetime(bars["timestamp_utc"], utc=True)
    prices = bars.pivot(index="timestamp_utc", columns="symbol", values="close").reindex(columns=INSTRUMENTS)
    returns = np.log(prices).diff()
    rows: list[dict[str, object]] = []
    for event in EVENTS:
        event_time = metadata[event]["time"]
        sample = returns.loc[
            (returns.index >= event_time - pd.Timedelta(seconds=60))
            & (returns.index <= event_time + pd.Timedelta(seconds=300))
        ]
        for leader in INSTRUMENTS:
            for follower in INSTRUMENTS:
                if leader == follower:
                    continue
                correlations: list[tuple[int, float]] = []
                for lag_seconds in range(-5, 6):
                    # Positive lag compares leader(t) with follower(t + lag).
                    value = sample[leader].corr(sample[follower].shift(-lag_seconds))
                    correlations.append((lag_seconds, float(value)))
                    rows.append(
                        {
                            "event": event,
                            "leader_candidate": leader,
                            "follower_candidate": follower,
                            "lag_seconds": lag_seconds,
                            "correlation": value,
                            "positive_lag_means": "leader_candidate_precedes_follower_candidate",
                            "dataset_condition": metadata[event]["dataset_condition"]["futures"],
                            "method": "descriptive_1s_return_cross_correlation",
                        }
                    )
    panel = pd.DataFrame(rows)
    output_dir = PROJECT_ROOT / "data" / "processed" / "macro_panel"
    figure_dir = PROJECT_ROOT / "figures" / "macro_panel"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_dir / "fomc_lead_lag_1s.csv", index=False)
    panel.to_parquet(output_dir / "fomc_lead_lag_1s.parquet", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, event in zip(axes, EVENTS):
        event_sample = panel.loc[panel["event"].eq(event)]
        for pair in (("ES.v.0", "ZN.v.0"), ("NQ.v.0", "ZN.v.0"), ("ES.v.0", "NQ.v.0")):
            sample = event_sample.loc[
                event_sample["leader_candidate"].eq(pair[0])
                & event_sample["follower_candidate"].eq(pair[1])
            ]
            ax.plot(sample["lag_seconds"], sample["correlation"], marker="o", label=f"{pair[0]} → {pair[1]}")
        ax.axvline(0, color="black", lw=0.8, ls="--")
        ax.axhline(0, color="black", lw=0.5)
        ax.set_title(event.replace("_", " "))
        ax.set_xlabel("Lag (seconds; positive means first instrument leads)")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Return correlation")
    axes[-1].legend(fontsize=8)
    fig.suptitle("Coarse one-second futures lead–lag diagnostic")
    fig.tight_layout()
    fig.savefig(figure_dir / "fomc_lead_lag_1s.png", dpi=180)
    plt.close(fig)

    best = (
        panel.assign(abs_correlation=panel["correlation"].abs())
        .sort_values("abs_correlation", ascending=False)
        .groupby(["event", "leader_candidate", "follower_candidate"], as_index=False)
        .first()
    )
    best.to_csv(output_dir / "fomc_lead_lag_best.csv", index=False)
    print(f"Wrote {len(panel)} lag correlations and {len(best)} pairwise maxima.")


if __name__ == "__main__":
    main()
