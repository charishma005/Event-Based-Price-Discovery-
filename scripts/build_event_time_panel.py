from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.panel import EVENT_TIME_COLUMNS, write_event_time_panel
from src.events.registry import pilot_events
from src.microstructure.mechanism import identify_initial_quote_revision, sign_trades
from src.utils.config import PROJECT_ROOT


EVENTS = pilot_events()


def _dataset(instrument: str) -> str:
    if instrument.endswith(".v.0"):
        return "GLBX.MDP3"
    if instrument in {"NVDA", "META", "GOOGL", "AMD"}:
        return "XNAS.ITCH"
    return "EQUS.MINI"


def _asset_class(instrument: str) -> str:
    if instrument == "ZN.v.0":
        return "treasury_future"
    if instrument.endswith(".v.0"):
        return "equity_index_future"
    if instrument == "SPY":
        return "etf"
    return "equity"


def _contamination_lookup() -> dict[tuple[str, str], object]:
    path = PROJECT_ROOT / "data" / "processed" / "event_news_contamination.parquet"
    if not path.exists():
        return {}
    flags = pd.read_parquet(path)
    return {
        (row.event_id, row.instrument): row.company_news_contamination
        for row in flags.itertuples(index=False)
    }


def _impact_lookup() -> dict[tuple[str, str], float]:
    path = PROJECT_ROOT / "data" / "processed" / "macro_panel" / "impact_coefficients_loo.parquet"
    lookup: dict[tuple[str, str], float] = {}
    if path.exists():
        impacts = pd.read_parquet(path)
        lookup.update({
        (row.focal_event, row.instrument): float(row.impact_coefficient)
        for row in impacts.itertuples(index=False)
        })
    news_path = PROJECT_ROOT / "data" / "processed" / "unscheduled_news" / "source_verified_mechanism.parquet"
    if news_path.exists():
        news = pd.read_parquet(news_path)
        for row in news.drop_duplicates(["event", "instrument"]).itertuples(index=False):
            lookup[(row.event, row.instrument)] = float(row.impact_coefficient)
    return lookup


def _one_panel(
    messages: pd.DataFrame,
    *,
    instrument: str,
    event_label: str,
    contamination: dict[tuple[str, str], object],
    impacts: dict[tuple[str, str], float],
) -> pd.DataFrame:
    metadata = EVENTS[event_label]
    event_time = metadata["time"]
    data = messages.copy().sort_values(["ts_event", "sequence"], kind="stable")
    asset = _asset_class(instrument)
    group = "futures" if instrument.endswith(".v.0") else "equities"
    condition = metadata["dataset_condition"][group]
    data["event_id"] = metadata["event_id"]
    data["instrument"] = instrument
    data["asset_class"] = asset
    data["event_type"] = metadata["event_type"]
    data["representation_class"] = metadata["representation_class"]
    data["source_dataset"] = _dataset(instrument)
    data["dataset_condition"] = condition
    data["timestamp_utc"] = pd.to_datetime(data["ts_event"], utc=True)
    data["timestamp_et"] = data["timestamp_utc"].dt.tz_convert("America/New_York")
    data["timestamp_recv_utc"] = pd.to_datetime(
        data.get("ts_recv"), utc=True, errors="coerce"
    )
    data["capture_latency_us"] = (
        data["timestamp_recv_utc"] - data["timestamp_utc"]
    ).dt.total_seconds() * 1e6
    data["event_time_ms"] = (
        data["timestamp_utc"] - event_time
    ).dt.total_seconds() * 1000
    valid = data["bid"].gt(0) & data["ask"].gt(data["bid"])
    data["midpoint"] = np.where(valid, (data["bid"] + data["ask"]) / 2, np.nan)
    data["spread"] = np.where(valid, data["ask"] - data["bid"], np.nan)
    data["relative_spread"] = data["spread"] / data["midpoint"]
    data["depth_total_touch"] = data["bid_size"] + data["ask_size"]
    data["depth_imbalance"] = np.where(
        data["depth_total_touch"].gt(0),
        (data["bid_size"] - data["ask_size"]) / data["depth_total_touch"],
        np.nan,
    )
    data["depth_bid_10"] = np.nan
    data["depth_ask_10"] = np.nan
    seconds = data["timestamp_utc"].dt.floor("1s")
    data["message_intensity"] = seconds.map(seconds.value_counts())
    is_trade = data["record_type"].eq("trade")
    data["trade_price"] = data["price"].where(is_trade)
    data["trade_size"] = data["size"].where(is_trade)
    data["aggressor_side"] = data["side"].where(is_trade)
    signed = sign_trades(data.loc[is_trade, ["side", "size", "price"]])
    data["signed_volume"] = np.nan
    data["signed_notional"] = np.nan
    data.loc[is_trade, "signed_volume"] = signed["signed_volume"].to_numpy()
    data.loc[is_trade, "signed_notional"] = signed["signed_notional"].to_numpy()
    state_midpoint = data["midpoint"].ffill()
    data["return"] = np.log(state_midpoint).diff()
    pre = data.loc[data["timestamp_utc"].lt(event_time) & data["midpoint"].notna(), "midpoint"]
    reference = pre.iloc[-1] if not pre.empty else np.nan
    data["cumulative_return"] = np.log(state_midpoint / reference)
    primary = identify_initial_quote_revision(data, event_time)
    quote_component = (
        np.nan
        if not primary.pre_midpoint or primary.post_midpoint is None
        else float(np.log(primary.post_midpoint / primary.pre_midpoint))
    )
    post_event = data["timestamp_utc"].ge(event_time)
    data["quote_revision_component"] = np.where(post_event, quote_component, np.nan)
    impact = impacts.get((event_label, instrument))
    if impact is None:
        data["order_flow_component"] = np.nan
        data["residual_component"] = np.nan
        data["mechanism_share"] = np.nan
    else:
        cumulative_flow = data["signed_volume"].fillna(0.0).where(post_event, 0.0).cumsum()
        data["order_flow_component"] = np.where(post_event, impact * cumulative_flow, np.nan)
        denominator = data["quote_revision_component"] + data["order_flow_component"]
        data["residual_component"] = np.where(
            post_event,
            data["cumulative_return"] - denominator,
            np.nan,
        )
        data["mechanism_share"] = np.where(
            post_event & denominator.abs().gt(1e-12),
            data["quote_revision_component"] / denominator,
            np.nan,
        )
    flag = contamination.get((metadata["event_id"], instrument), pd.NA)
    data["contamination_flag"] = flag
    data["contamination_notes"] = (
        "Alpha Vantage automated candidate; manual confirmation required"
        if pd.notna(flag) and bool(flag)
        else ""
    )
    quality = []
    if condition != "available":
        quality.append(f"dataset_{condition}")
    if not primary.valid_for_primary_q1:
        quality.append("primary_quote_sequence_invalid")
    if _dataset(instrument) == "EQUS.MINI":
        quality.append("sequence_zero_aggregated_bbo")
    if instrument.endswith(".v.0") and impact is None:
        quality.append("loo_flow_impact_unavailable")
    quality.extend(primary.quality_flags)
    data["quality_flags"] = "|".join(dict.fromkeys(quality))
    return data.reindex(columns=EVENT_TIME_COLUMNS)


def main() -> None:
    contamination = _contamination_lookup()
    impacts = _impact_lookup()
    frames: list[pd.DataFrame] = []
    root = PROJECT_ROOT / "data" / "processed" / "fomc_pilot"
    for event_label in EVENTS:
        for path in sorted((root / event_label).glob("*_messages.parquet")):
            instrument = path.name.removesuffix("_messages.parquet")
            frames.append(
                _one_panel(
                    pd.read_parquet(path),
                    instrument=instrument,
                    event_label=event_label,
                    contamination=contamination,
                    impacts=impacts,
                )
            )
    panel = pd.concat(frames, ignore_index=True)
    target = PROJECT_ROOT / "data" / "processed" / "event_time_panel.parquet"
    write_event_time_panel(panel, target, overwrite=True)
    print(
        f"Wrote {len(panel):,} event-message rows across "
        f"{panel[['event_id', 'instrument']].drop_duplicates().shape[0]} event-instrument pairs "
        f"to {target}"
    )


if __name__ == "__main__":
    main()
