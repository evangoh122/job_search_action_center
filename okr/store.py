"""SQLite persistence for OKR activity and review state."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SINGAPORE = ZoneInfo("Asia/Singapore")


def _aware_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    # Normalization makes SQLite's lexical comparisons chronological even when
    # callers provide timestamps with different UTC offsets.
    return value.astimezone(timezone.utc).isoformat()


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class GapRecord:
    """A locally durable learning gap and its Drive-sync state."""

    id: str
    source: str
    description: str
    occurred_at: datetime
    priority: str
    context: dict[str, Any]
    sync_status: str
    sync_attempts: int
    last_error: str
    synced_at: datetime | None

    def is_overdue(self, as_of: datetime) -> bool:
        """Return whether same-day Drive logging has been missed."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return (
            self.sync_status != "synced"
            and as_of.astimezone(SINGAPORE).date()
            > self.occurred_at.astimezone(SINGAPORE).date()
        )


class OkrStore:
    """Own the independent SQLite tables used by the OKR workflow."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        self.conn.close()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS okr_events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                quantity REAL NOT NULL CHECK (quantity > 0),
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_okr_events_kind_time
                ON okr_events(kind, occurred_at);

            CREATE TABLE IF NOT EXISTS okr_job_status_history (
                id TEXT PRIMARY KEY,
                job_key TEXT NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_okr_job_history_job_time
                ON okr_job_status_history(job_key, changed_at);

            CREATE TABLE IF NOT EXISTS okr_gaps (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL CHECK (source IN ('interview', 'challenge')),
                description TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                context TEXT NOT NULL DEFAULT '{}',
                sync_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (sync_status IN ('pending', 'synced')),
                sync_attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                synced_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_okr_gaps_sync
                ON okr_gaps(sync_status, occurred_at);

            CREATE TABLE IF NOT EXISTS okr_followups (
                id TEXT PRIMARY KEY,
                contact TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'done', 'cancelled')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_okr_followups_due
                ON okr_followups(status, due_at);

            CREATE TABLE IF NOT EXISTS okr_weekly_reviews (
                week_start TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self.conn.commit()

    def add_event(
        self,
        kind: str,
        occurred_at: datetime,
        *,
        quantity: float = 1,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> str:
        if not kind.strip():
            raise ValueError("event kind is required")
        if quantity <= 0:
            raise ValueError("event quantity must be positive")
        event_id = event_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO okr_events VALUES (?, ?, ?, ?, ?)",
            (event_id, kind.strip(), _aware_iso(occurred_at), quantity, _json(metadata)),
        )
        self.conn.commit()
        return event_id

    def event_total(self, kind: str, start: datetime, end: datetime) -> float:
        """Sum events in the half-open interval ``[start, end)``."""
        row = self.conn.execute(
            """SELECT COALESCE(SUM(quantity), 0) AS total FROM okr_events
               WHERE kind = ? AND occurred_at >= ? AND occurred_at < ?""",
            (kind, _aware_iso(start), _aware_iso(end)),
        ).fetchone()
        return float(row["total"])

    def record_job_status(
        self,
        job_key: str,
        status: str,
        changed_at: datetime,
        *,
        metadata: dict[str, Any] | None = None,
        history_id: str | None = None,
    ) -> str:
        if not job_key.strip() or not status.strip():
            raise ValueError("job key and status are required")
        history_id = history_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO okr_job_status_history VALUES (?, ?, ?, ?, ?)",
            (history_id, job_key.strip(), status.strip(), _aware_iso(changed_at), _json(metadata)),
        )
        self.conn.commit()
        return history_id

    def latest_job_statuses(self) -> dict[str, str]:
        rows = self.conn.execute(
            """SELECT job_key, status FROM (
                   SELECT job_key, status,
                          ROW_NUMBER() OVER (
                              PARTITION BY job_key ORDER BY changed_at DESC, rowid DESC
                          ) AS rank
                   FROM okr_job_status_history
               ) WHERE rank = 1"""
        ).fetchall()
        return {row["job_key"]: row["status"] for row in rows}

    def create_gap(
        self,
        source: str,
        description: str,
        occurred_at: datetime,
        *,
        priority: str = "normal",
        context: dict[str, Any] | None = None,
        gap_id: str | None = None,
    ) -> GapRecord:
        if source not in {"interview", "challenge"}:
            raise ValueError("gap source must be interview or challenge")
        if not description.strip():
            raise ValueError("gap description is required")
        gap_id = gap_id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO okr_gaps
               (id, source, description, occurred_at, priority, context)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (gap_id, source, description.strip(), _aware_iso(occurred_at), priority, _json(context)),
        )
        self.conn.commit()
        return self.get_gap(gap_id)

    def get_gap(self, gap_id: str) -> GapRecord:
        row = self.conn.execute("SELECT * FROM okr_gaps WHERE id = ?", (gap_id,)).fetchone()
        if row is None:
            raise KeyError(gap_id)
        return self._gap(row)

    def pending_gaps(self) -> list[GapRecord]:
        rows = self.conn.execute(
            "SELECT * FROM okr_gaps WHERE sync_status = 'pending' ORDER BY occurred_at, id"
        ).fetchall()
        return [self._gap(row) for row in rows]

    def mark_gap_sync_failed(self, gap_id: str, error: str) -> None:
        self.conn.execute(
            """UPDATE okr_gaps SET sync_attempts = sync_attempts + 1, last_error = ?
               WHERE id = ?""",
            (error[:2000], gap_id),
        )
        self.conn.commit()

    def mark_gap_synced(self, gap_id: str, synced_at: datetime) -> None:
        self.conn.execute(
            """UPDATE okr_gaps SET sync_status = 'synced', sync_attempts = sync_attempts + 1,
               last_error = '', synced_at = ? WHERE id = ?""",
            (_aware_iso(synced_at), gap_id),
        )
        self.conn.commit()

    @staticmethod
    def _gap(row: sqlite3.Row) -> GapRecord:
        return GapRecord(
            id=row["id"], source=row["source"], description=row["description"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]), priority=row["priority"],
            context=json.loads(row["context"]), sync_status=row["sync_status"],
            sync_attempts=row["sync_attempts"], last_error=row["last_error"],
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        )

    def add_followup(
        self,
        contact: str,
        due_at: datetime,
        created_at: datetime,
        *,
        notes: str = "",
        followup_id: str | None = None,
    ) -> str:
        if not contact.strip():
            raise ValueError("follow-up contact is required")
        followup_id = followup_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO okr_followups VALUES (?, ?, ?, 'open', ?, ?, NULL)",
            (followup_id, contact.strip(), _aware_iso(due_at), notes, _aware_iso(created_at)),
        )
        self.conn.commit()
        return followup_id

    def complete_followup(self, followup_id: str, completed_at: datetime) -> None:
        cursor = self.conn.execute(
            """UPDATE okr_followups SET status = 'done', completed_at = ?
               WHERE id = ? AND status = 'open'""",
            (_aware_iso(completed_at), followup_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(followup_id)

    def owed_followups(self, as_of: datetime) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM okr_followups
               WHERE status = 'open' AND due_at <= ? ORDER BY due_at, id""",
            (_aware_iso(as_of),),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_weekly_review(
        self,
        week_start: date,
        created_at: datetime,
        payload: dict[str, Any],
    ) -> None:
        if week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        self.conn.execute(
            """INSERT INTO okr_weekly_reviews VALUES (?, ?, ?)
               ON CONFLICT(week_start) DO UPDATE SET
                   created_at = excluded.created_at, payload = excluded.payload""",
            (week_start.isoformat(), _aware_iso(created_at), _json(payload)),
        )
        self.conn.commit()

    def get_weekly_review(self, week_start: date) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM okr_weekly_reviews WHERE week_start = ?",
            (week_start.isoformat(),),
        ).fetchone()
        return json.loads(row["payload"]) if row else None
