"""Assemble one registry of every event and control clock used by the tick pipeline.

The registry only contains metadata that was fixed before any market outcome
was examined: official clocks, request windows, representation classes and the
development / out-of-sample split declared in
``config/q1_short_horizon_prereg.yaml``.

Sources
- config/macro_sample_2024.yaml, config/macro_sample.yaml   (8:30 a.m. bundles, 2024-01 to 2025-08)
- data/events/cpi_calendar_2015_2026.csv                    (official BLS CPI clocks)
- config/macro_extension_2015_2026.yaml                     (optional: other BLS releases)
- config/fomc_sample_2015_2026.yaml                         (statement and press-conference clocks)
- config/macro_placebos.yaml, config/fomc_placebos.yaml     (2024-2025 matched controls)
- config/fomc_placebos_2015_2026.yaml, config/macro_placebos_2015_2026.yaml (optional: added controls)
- config/unscheduled_events.yaml                            (optional: unscheduled arrivals and controls)
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

from src.utils.config import PROJECT_ROOT, load_yaml

INSTRUMENTS = ("ES.v.0", "NQ.v.0", "ZN.v.0")
DEVELOPMENT_START = pd.Timestamp("2024-01-01", tz="UTC")
DEVELOPMENT_END = pd.Timestamp("2025-10-01", tz="UTC")     # exclusive
CLOSED_SESSIONS = {"2017-04-14", "2020-04-10"}             # Good Friday releases, no futures session


def sample_label(event_time: pd.Timestamp) -> str:
    if event_time < DEVELOPMENT_START:
        return "oos_backward"
    if event_time < DEVELOPMENT_END:
        return "development"
    return "oos_forward"


def _optional(name: str) -> dict:
    path = PROJECT_ROOT / "config" / name
    return load_yaml(path) if path.exists() else {}


def _row(**values: object) -> dict[str, object]:
    base = {
        "event_id": None, "family": None, "subevent": "", "event_types": "",
        "representation_class": "", "scheduled": True, "is_control": False,
        "event_time_utc": None, "request_start_utc": None, "request_end_utc": None,
        "cluster": "", "matched_event": "", "sep_release": False, "policy_change_bps": 0,
        "concurrent_release": "", "dataset_condition": "", "quality_flag": "", "source": "",
    }
    base.update(values)
    return base


def macro_rows() -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for name in ("macro_sample_2024.yaml", "macro_sample.yaml", "macro_extension_2015_2026.yaml"):
        for event in _optional(name).get("events", []):
            grouped[(event["request_start_utc"], event["request_end_utc"])].append({**event, "_source": name})
    calendar_path = PROJECT_ROOT / "data" / "events" / "cpi_calendar_2015_2026.csv"
    if calendar_path.exists():
        calendar = pd.read_csv(calendar_path)
        calendar = calendar.loc[calendar["release_status"].eq("released")]
        for item in calendar.itertuples(index=False):
            key = (pd.Timestamp(item.request_start_utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   pd.Timestamp(item.request_end_utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            if any(member["event_type"] == "cpi" for member in grouped.get(key, [])):
                continue
            grouped[key].append({
                "event_id": item.event_id, "event_date": item.event_date,
                "event_time_utc": pd.Timestamp(item.scheduled_time_utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event_type": "cpi", "representation_class": "scalar_numeric",
                "concurrent_release": item.concurrent_release, "_source": "cpi_calendar_2015_2026.csv",
            })
    rows = []
    for (start, end), members in sorted(grouped.items()):
        clocks = {member["event_time_utc"] for member in members}
        if len(clocks) != 1:
            raise ValueError(f"Bundle {start} mixes event clocks: {sorted(clocks)}")
        event_time = pd.Timestamp(clocks.pop())
        local = event_time.tz_convert("America/New_York")
        classes = list(dict.fromkeys(member["representation_class"] for member in members))
        concurrent = [str(member["concurrent_release"]) for member in members
                      if member.get("concurrent_release") and str(member["concurrent_release"]) != "nan"]
        date = local.strftime("%Y-%m-%d")
        rows.append(_row(
            event_id=f"macro_{local:%Y%m%d_%H%M}", family="macro",
            event_types="|".join(dict.fromkeys(member["event_type"] for member in members)),
            representation_class=classes[0] if len(classes) == 1 else "mixed_numeric_bundle",
            event_time_utc=event_time, request_start_utc=pd.Timestamp(start), request_end_utc=pd.Timestamp(end),
            cluster=local.strftime("%Y-%m"), concurrent_release="|".join(dict.fromkeys(concurrent)),
            quality_flag="closed_session" if date in CLOSED_SESSIONS else "",
            source="|".join(dict.fromkeys(member["_source"] for member in members)),
        ))
    return rows


def fomc_rows(config_name: str) -> list[dict[str, object]]:
    rows = []
    for meeting in _optional(config_name).get("meetings", []):
        shared = dict(
            family="fomc", cluster=meeting["label"], matched_event=meeting["label"],
            request_start_utc=pd.Timestamp(meeting["request_start_utc"]),
            request_end_utc=pd.Timestamp(meeting["request_end_utc"]),
            sep_release=bool(meeting["sep_release"]), policy_change_bps=int(meeting["policy_change_bps"]),
            dataset_condition=meeting.get("dataset_condition", ""), source=config_name,
        )
        rows.append(_row(
            event_id=f"{meeting['label']}_statement", subevent="statement", event_types="fomc_statement",
            representation_class="narrative_text",
            event_time_utc=pd.Timestamp(meeting["statement_time_utc"]), **shared,
        ))
        if meeting.get("press_conference_time_utc"):
            rows.append(_row(
                event_id=f"{meeting['label']}_press_conference", subevent="press_conference",
                event_types="fomc_press_conference", representation_class="extemporaneous_speech",
                event_time_utc=pd.Timestamp(meeting["press_conference_time_utc"]), **shared,
            ))
    return rows


def control_rows() -> list[dict[str, object]]:
    rows = []
    for name, family, matched_key in (
        ("macro_placebos.yaml", "macro_control", "matched_month"),
        ("macro_placebos_2015_2026.yaml", "macro_control", "matched_month"),
        ("fomc_placebos.yaml", "fomc_control", "matched_meeting"),
        ("fomc_placebos_2015_2026.yaml", "fomc_control", "matched_meeting"),
    ):
        for placebo in _optional(name).get("placebos", []):
            rows.append(_row(
                event_id=placebo["placebo_id"], family=family, event_types="control",
                representation_class="control", scheduled=False, is_control=True,
                event_time_utc=pd.Timestamp(placebo["placebo_time_utc"]),
                request_start_utc=pd.Timestamp(placebo["request_start_utc"]),
                request_end_utc=pd.Timestamp(placebo["request_end_utc"]),
                cluster=str(placebo[matched_key]), matched_event=str(placebo[matched_key]),
                quality_flag=placebo.get("quality_flag", ""), source=name,
            ))
    return rows


def unscheduled_rows() -> list[dict[str, object]]:
    rows = []
    for event in _optional("unscheduled_events.yaml").get("events", []):
        rows.append(_row(
            event_id=event["event_id"], family=event["family"], event_types=event["event_type"],
            representation_class=event.get("representation_class", "unscheduled_news"),
            scheduled=False, is_control=bool(event.get("is_control", False)),
            event_time_utc=pd.Timestamp(event["event_time_utc"]),
            request_start_utc=pd.Timestamp(event["request_start_utc"]),
            request_end_utc=pd.Timestamp(event["request_end_utc"]),
            cluster=str(event.get("cluster", event["event_id"])),
            matched_event=str(event.get("matched_event", "")),
            quality_flag=event.get("quality_flag", ""), source="unscheduled_events.yaml",
        ))
    return rows


PSEUDO_OFFSET_SECONDS = -120


def pseudo_rows(events: list[dict[str, object]]) -> list[dict[str, object]]:
    """A no-news clock two minutes before each scheduled arrival, inside the same raw window.

    These rows give every event its own within-day placebo for the tick-level
    quote/trade split. They are not valid controls for pre-event liquidity,
    because the book is already being thinned at that point.
    """
    rows = []
    for event in events:
        rows.append({
            **event,
            "event_id": f"{event['event_id']}_pseudo120",
            "family": f"{event['family']}_pseudo",
            "representation_class": "within_window_pseudo",
            "scheduled": False, "is_control": True,
            "event_time_utc": pd.Timestamp(event["event_time_utc"]) + pd.Timedelta(seconds=PSEUDO_OFFSET_SECONDS),
            "matched_event": event["event_id"],
        })
    return rows


def build_registry(fomc_config: str = "fomc_sample_2015_2026.yaml") -> pd.DataFrame:
    scheduled = macro_rows() + fomc_rows(fomc_config)
    registry = pd.DataFrame(scheduled + pseudo_rows(scheduled) + control_rows() + unscheduled_rows())
    for column in ("event_time_utc", "request_start_utc", "request_end_utc"):
        registry[column] = pd.to_datetime(registry[column], utc=True)
    registry["sample"] = registry["event_time_utc"].map(sample_label)
    # Provider data-quality condition by UTC date (reports/glbx_dataset_conditions_2015_2026.json).
    conditions_path = PROJECT_ROOT / "reports" / "glbx_dataset_conditions_2015_2026.json"
    if conditions_path.exists():
        import json

        lookup = {row["date"]: row["condition"]
                  for row in json.loads(conditions_path.read_text(encoding="utf-8"))["conditions"]}
        provider = registry["event_time_utc"].dt.strftime("%Y-%m-%d").map(lookup).fillna("unverified")
        configured = registry["dataset_condition"].astype(str)
        registry["dataset_condition"] = configured.where(configured.ne("") & configured.ne("available"), provider)
    registry["event_date"] = registry["event_time_utc"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    duplicated = registry.loc[registry["event_id"].duplicated(), "event_id"].tolist()
    if duplicated:
        raise ValueError(f"Duplicate event ids: {duplicated[:5]}")
    return registry.sort_values(["event_time_utc", "event_id"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fomc-config", default="fomc_sample_2015_2026.yaml")
    parser.add_argument("--output", default="event_registry.csv", help="File under data/events/")
    args = parser.parse_args()
    registry = build_registry(args.fomc_config)
    output = PROJECT_ROOT / "data" / "events" / args.output
    registry.to_csv(output, index=False)
    summary = registry.groupby(["sample", "family", "subevent"]).size().unstack("sample", fill_value=0)
    print(summary.to_string())
    print(f"Wrote {len(registry)} event clocks in "
          f"{registry[['request_start_utc', 'request_end_utc']].drop_duplicates().shape[0]} request windows to {output}")


if __name__ == "__main__":
    main()
