from __future__ import annotations

from pathlib import Path

import databento as db
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.events.registry import pilot_events
from src.utils.config import PROJECT_ROOT, load_yaml


BBO_PATH = PROJECT_ROOT / "data" / "raw" / "databento" / "EQUS.MINI-bbo-1s-ceba721457382abc.dbn.zst"
OHLCV_PATH = PROJECT_ROOT / "data" / "raw" / "databento" / "EQUS.MINI-ohlcv-1s-4638cbc68baf814c.dbn.zst"
EVENT_LABELS = ("statement", "press_conference")
HORIZONS_SECONDS = (1, 5, 30, 60, 300)


def _universe() -> pd.DataFrame:
    config = load_yaml(PROJECT_ROOT / "config" / "universe.yaml")
    return pd.DataFrame(config["securities"])


def _load_bbo() -> pd.DataFrame:
    data = db.DBNStore.from_file(BBO_PATH).to_df().reset_index()
    # For BBO-1s, the index is the one-second snapshot time. ts_event identifies
    # the underlying book event and can be stale in an inactive second.
    snapshot_column = data.columns[0]
    data = data.rename(
        columns={
            snapshot_column: "timestamp_utc",
            "bid_px_00": "bid",
            "ask_px_00": "ask",
            "bid_sz_00": "bid_size",
            "ask_sz_00": "ask_size",
        }
    )
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    valid = data["bid"].gt(0) & data["ask"].gt(data["bid"])
    data = data.loc[valid].copy()
    data["midpoint"] = (data["bid"] + data["ask"]) / 2
    data["spread"] = data["ask"] - data["bid"]
    data["relative_spread_bp"] = 1e4 * data["spread"] / data["midpoint"]
    data["touch_depth"] = data["bid_size"] + data["ask_size"]
    return data.sort_values(["symbol", "timestamp_utc"], kind="stable")


def _load_ohlcv() -> pd.DataFrame:
    data = db.DBNStore.from_file(OHLCV_PATH).to_df().reset_index()
    timestamp_column = data.columns[0]
    data = data.rename(columns={timestamp_column: "timestamp_utc"})
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    return data.sort_values(["symbol", "timestamp_utc"], kind="stable")


def _last_at_or_before(frame: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series | None:
    sample = frame.loc[frame["timestamp_utc"].le(timestamp)]
    return None if sample.empty else sample.iloc[-1]


def _contamination() -> pd.DataFrame:
    path = PROJECT_ROOT / "data" / "processed" / "event_news_contamination.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["event_id", "instrument", "company_news_contamination"])
    data = pd.read_parquet(path)
    return data[["event_id", "instrument", "company_news_contamination"]].rename(
        columns={"instrument": "ticker"}
    )


def main() -> None:
    events = pilot_events()
    universe = _universe()
    bbo = _load_bbo()
    bars = _load_ohlcv()
    rows: list[dict[str, object]] = []
    for event_label in EVENT_LABELS:
        event = events[event_label]
        event_time = event["time"]
        for security in universe.itertuples(index=False):
            quotes = bbo.loc[bbo["symbol"].eq(security.ticker)]
            stock_bars = bars.loc[bars["symbol"].eq(security.ticker)].copy()
            pre_bar = stock_bars.loc[stock_bars["timestamp_utc"].lt(event_time)].tail(1)
            if pre_bar.empty:
                continue
            reference_price = float(pre_bar.iloc[0]["close"])
            pre_window = quotes.loc[
                quotes["timestamp_utc"].ge(event_time - pd.Timedelta(minutes=5))
                & quotes["timestamp_utc"].lt(event_time)
            ]
            for horizon in HORIZONS_SECONDS:
                cutoff = event_time + pd.Timedelta(seconds=horizon)
                quote = _last_at_or_before(quotes, cutoff)
                price_bar = _last_at_or_before(stock_bars, cutoff)
                volume_sample = stock_bars.loc[
                    stock_bars["timestamp_utc"].ge(event_time)
                    & stock_bars["timestamp_utc"].lt(cutoff)
                ]
                prices = volume_sample["close"].astype(float)
                realized_variance = float(np.log(prices).diff().pow(2).sum()) if len(prices) > 1 else np.nan
                response_price = None if price_bar is None else float(price_bar["close"])
                flags = ["one_second_data_not_message_sequence"]
                if quote is None:
                    flags.append("missing_bbo_snapshot")
                elif float(quote["relative_spread_bp"]) > 50:
                    flags.append("wide_or_stale_eq_us_mini_bbo")
                rows.append(
                    {
                        "event_id": event["event_id"],
                        "event": event_label,
                        "event_time_utc": event_time,
                        "ticker": security.ticker,
                        "sector": security.sector,
                        "theme": security.theme,
                        "horizon_seconds": horizon,
                        "reference_price": reference_price,
                        "response_price": response_price,
                        "quote_midpoint": None if quote is None else float(quote["midpoint"]),
                        "log_return_bp": None
                        if response_price is None
                        else float(1e4 * np.log(response_price / reference_price)),
                        "absolute_return_bp": None
                        if response_price is None
                        else float(abs(1e4 * np.log(response_price / reference_price))),
                        "relative_spread_bp": None if quote is None else float(quote["relative_spread_bp"]),
                        "touch_depth": None if quote is None else float(quote["touch_depth"]),
                        "pre5m_relative_spread_bp": float(pre_window["relative_spread_bp"].mean()),
                        "pre5m_touch_depth": float(pre_window["touch_depth"].mean()),
                        "trade_volume": int(volume_sample["volume"].sum()),
                        "realized_volatility_bp": None
                        if not np.isfinite(realized_variance)
                        else float(1e4 * np.sqrt(realized_variance)),
                        "data_tier": "A_1s",
                        "return_source": "EQUS.MINI_ohlcv_1s_trade_close",
                        "q1_usable": False,
                        "quality_flags": "|".join(flags),
                    }
                )
    panel = pd.DataFrame(rows).merge(
        _contamination(), on=["event_id", "ticker"], how="left"
    )
    output_dir = PROJECT_ROOT / "data" / "processed" / "stock_cross_section"
    figure_dir = PROJECT_ROOT / "figures" / "stock_cross_section"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(output_dir / "fomc_1s_cross_section.parquet", index=False)
    panel.to_csv(output_dir / "fomc_1s_cross_section.csv", index=False)

    theme_summary = (
        panel.groupby(["event", "theme", "horizon_seconds"], as_index=False)
        .agg(
            mean_return_bp=("log_return_bp", "mean"),
            median_return_bp=("log_return_bp", "median"),
            mean_absolute_return_bp=("absolute_return_bp", "mean"),
            stock_count=("ticker", "nunique"),
        )
    )
    theme_summary.to_csv(output_dir / "theme_summary.csv", index=False)

    display = panel.loc[panel["horizon_seconds"].isin([5, 60, 300])].copy()
    display["column"] = display["event"].str.replace("_", " ") + " " + display["horizon_seconds"].astype(str) + "s"
    table = display.pivot(index="ticker", columns="column", values="log_return_bp")
    ticker_order = universe["ticker"].tolist()
    column_order = [
        f"{event.replace('_', ' ')} {horizon}s"
        for event in EVENT_LABELS
        for horizon in (5, 60, 300)
    ]
    table = table.reindex(index=ticker_order, columns=column_order)
    values = table.to_numpy(float)
    limit = float(np.nanmax(np.abs(values)))
    fig, ax = plt.subplots(figsize=(11, 9))
    image = ax.imshow(values, aspect="auto", cmap="RdBu_r", vmin=-limit, vmax=limit)
    ax.set_xticks(range(len(table.columns)), table.columns, rotation=35, ha="right")
    ax.set_yticks(range(len(table.index)), table.index)
    ax.set_title("FOMC statement and press-conference stock responses")
    bar = fig.colorbar(image, ax=ax, shrink=0.75)
    bar.set_label("log one-second trade-close return (bp)")
    fig.tight_layout()
    fig.savefig(figure_dir / "fomc_stock_return_heatmap.png", dpi=180)
    plt.close(fig)
    print(f"Wrote {len(panel)} stock-event-horizon rows for {panel['ticker'].nunique()} stocks.")


if __name__ == "__main__":
    main()
