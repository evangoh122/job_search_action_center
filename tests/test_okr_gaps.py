from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from okr.gaps import DriveMarkdownGapSink, GapService
from okr.store import OkrStore

SGT = ZoneInfo("Asia/Singapore")


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=SGT)


def test_gap_is_local_first_then_immediately_appended_to_drive_path(tmp_path: Path):
    store = OkrStore(tmp_path / "okr.sqlite")
    note = tmp_path / "Drive" / "job-search-gaps.md"
    service = GapService(store, DriveMarkdownGapSink(note), now=lambda: _at(20, 18))
    gap = service.log(
        "interview", "Explain uplift modeling more clearly", gap_id="gap-1",
        context={"company": "Acme"}, priority="high",
    )
    assert gap.sync_status == "synced"
    assert gap.sync_attempts == 1
    text = note.read_text(encoding="utf-8")
    assert "job-search-gap:gap-1" in text
    assert "Explain uplift modeling more clearly" in text
    assert "company=Acme" in text


class _FailingSink:
    def append(self, gap):
        raise OSError("Drive directory unavailable")


def test_sink_failure_leaves_durable_pending_gap_with_error(tmp_path: Path):
    path = tmp_path / "okr.sqlite"
    store = OkrStore(path)
    gap = GapService(store, _FailingSink(), now=lambda: _at(20)).log(
        "challenge", "Review dynamic programming", gap_id="gap-pending",
    )
    assert gap.sync_status == "pending"
    assert gap.sync_attempts == 1
    assert "Drive directory unavailable" in gap.last_error
    store.close()
    assert OkrStore(path).get_gap("gap-pending").description == "Review dynamic programming"


def test_retry_is_idempotent_and_clears_pending_state(tmp_path: Path):
    store = OkrStore()
    service = GapService(store, None, now=lambda: _at(20))
    service.log("challenge", "Practice joins", gap_id="gap-retry")
    note = tmp_path / "gaps.md"
    service.sink = DriveMarkdownGapSink(note)
    assert service.retry_pending() == []
    # Simulate the append succeeding before a process died prior to its DB update.
    store.conn.execute(
        "UPDATE okr_gaps SET sync_status='pending', synced_at=NULL WHERE id='gap-retry'"
    )
    store.conn.commit()
    assert service.retry_pending() == []
    assert note.read_text(encoding="utf-8").count("job-search-gap:gap-retry") == 1


def test_pending_gap_becomes_overdue_next_singapore_day():
    store = OkrStore()
    service = GapService(store, None, now=lambda: _at(20, 23))
    service.log("interview", "Refresh confidence intervals", gap_id="gap-overdue")
    assert service.overdue(_at(20, 23)) == []
    assert [gap.id for gap in service.overdue(_at(21, 0))] == ["gap-overdue"]


def test_invalid_gap_source_is_rejected():
    store = OkrStore()
    service = GapService(store, None, now=lambda: _at(20))
    try:
        service.log("commute", "new issue")
    except ValueError as exc:
        assert "interview or challenge" in str(exc)
    else:
        raise AssertionError("invalid gap source was accepted")
