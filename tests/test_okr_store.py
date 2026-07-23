from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from okr.store import OkrStore

SGT = ZoneInfo("Asia/Singapore")


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=SGT)


def test_store_creates_all_tracking_tables(tmp_path: Path):
    store = OkrStore(tmp_path / "okr.sqlite")
    names = {
        row[0] for row in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "okr_events", "okr_job_status_history", "okr_gaps",
        "okr_followups", "okr_weekly_reviews",
    } <= names


def test_events_are_idempotent_and_aggregate_in_half_open_window():
    store = OkrStore()
    store.add_event("application", _at(20), quantity=2, event_id="event-1")
    store.add_event("application", _at(21), quantity=3)
    with pytest.raises(sqlite3.IntegrityError):
        store.add_event("application", _at(20), event_id="event-1")
    assert store.event_total("application", _at(20, 0), _at(21, 0)) == 2
    assert store.event_total("application", _at(20, 0), _at(22, 0)) == 5


def test_naive_timestamps_and_nonpositive_events_are_rejected():
    store = OkrStore()
    with pytest.raises(ValueError, match="timezone-aware"):
        store.add_event("coffee_chat", datetime(2026, 7, 20))
    with pytest.raises(ValueError, match="positive"):
        store.add_event("coffee_chat", _at(20), quantity=0)


def test_latest_status_per_job_is_derived_from_history():
    store = OkrStore()
    store.record_job_status("acme|ds", "applied", _at(20))
    store.record_job_status("acme|ds", "interview_scheduled", _at(21))
    store.record_job_status("beta|ml", "response", _at(21))
    assert store.latest_job_statuses() == {
        "acme|ds": "interview_scheduled", "beta|ml": "response",
    }


def test_followups_due_and_completion():
    store = OkrStore()
    due = store.add_followup("Jane", _at(21), _at(20), followup_id="f-due")
    store.add_followup("Sam", _at(23), _at(20), followup_id="f-later")
    assert [row["id"] for row in store.owed_followups(_at(22))] == [due]
    store.complete_followup(due, _at(22))
    assert store.owed_followups(_at(22)) == []


def test_weekly_review_round_trip_and_monday_validation(tmp_path: Path):
    path = tmp_path / "okr.sqlite"
    store = OkrStore(path)
    payload = {"actuals": {"applications": 8}, "next_chats_sourced": 5}
    store.save_weekly_review(date(2026, 7, 20), _at(26), payload)
    store.close()
    reopened = OkrStore(path)
    assert reopened.get_weekly_review(date(2026, 7, 20)) == payload
    with pytest.raises(ValueError, match="Monday"):
        reopened.save_weekly_review(date(2026, 7, 21), _at(26), {})
