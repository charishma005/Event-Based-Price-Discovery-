from pathlib import Path

from src.events.calendar import load_event_calendar


def test_pilot_calendar_is_valid():
    path = Path(__file__).parents[1] / "data" / "events" / "event_calendar.csv"
    frame = load_event_calendar(path)
    assert frame["event_id"].is_unique
    assert {"fomc_statement_20250917", "fomc_sep_20250917"}.issubset(
        set(frame["event_id"])
    )

