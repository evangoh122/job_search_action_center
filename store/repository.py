from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from models import Contact, Job, LinkedInPostMatch
from matching import job_identity_key, merge_jobs


class Repository(ABC):
    """Represent repository."""
    @abstractmethod
    def upsert_job(self, job: Job) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def list_jobs(self) -> list[Job]: ...

    def get_job_by_dedupe_key(self, dedupe_key: str) -> Job | None:
        """Get job by dedupe key."""
        return next((j for j in self.list_jobs() if j.dedupe_key == dedupe_key), None)

    @abstractmethod
    def upsert_contact(self, c: Contact) -> None: ...

    @abstractmethod
    def incr_action(self, kind: str, day: str) -> int: ...

    @abstractmethod
    def count_actions(self, kind: str, day: str) -> int: ...


class SqliteRepository(Repository):
    """Represent sqlite repository."""
    def __init__(self, db_path: str = ":memory:"):
        """Initialize the instance."""
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate_cross_source_keys()

    def _create_tables(self) -> None:
        """Create tables."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                dedupe_key TEXT UNIQUE NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_counts (
                kind TEXT NOT NULL,
                day TEXT NOT NULL,
                n INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (kind, day)
            );
            CREATE TABLE IF NOT EXISTS linkedin_post_matches (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                data TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def upsert_job(self, job: Job) -> None:
        """Upsert job."""
        existing = self.get_job_by_dedupe_key(job.dedupe_key)
        if existing is not None and existing.id != job.id:
            job = merge_jobs(existing, job)
        self.conn.execute(
            """
            INSERT INTO jobs (id, dedupe_key, data)
            VALUES (?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                id = excluded.id,
                data = excluded.data
            """,
            (job.id, job.dedupe_key, json.dumps(job.model_dump(mode="json"))),
        )
        self.conn.commit()

    def get_job_by_dedupe_key(self, dedupe_key: str) -> Job | None:
        """Get job by dedupe key."""
        row = self.conn.execute(
            "SELECT data FROM jobs WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        return Job.model_validate(json.loads(row["data"])) if row else None

    def _migrate_cross_source_keys(self) -> None:
        """Consolidate legacy URL-based keys when an existing DB is opened."""
        rows = self.conn.execute("SELECT data FROM jobs").fetchall()
        if not rows:
            return
        grouped: dict[str, Job] = {}
        changed = False
        for row in rows:
            job = Job.model_validate(json.loads(row["data"]))
            key = job_identity_key(job.company_canonical, job.title, url=job.url)
            changed = changed or key != job.dedupe_key or key in grouped
            job.dedupe_key = key
            job.sources = job.sources or [job.source]
            job.source_urls = job.source_urls or {job.source: job.url}
            grouped[key] = merge_jobs(grouped[key], job) if key in grouped else job
        if not changed:
            return
        with self.conn:
            self.conn.execute("DELETE FROM jobs")
            self.conn.executemany(
                "INSERT INTO jobs (id, dedupe_key, data) VALUES (?, ?, ?)",
                [
                    (job.id, key, json.dumps(job.model_dump(mode="json")))
                    for key, job in grouped.items()
                ],
            )

    def get_job(self, job_id: str) -> Job | None:
        """Get job."""
        row = self.conn.execute(
            "SELECT data FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return Job.model_validate(json.loads(row["data"])) if row else None

    def list_jobs(self) -> list[Job]:
        """List jobs."""
        rows = self.conn.execute("SELECT data FROM jobs").fetchall()
        return [Job.model_validate(json.loads(r["data"])) for r in rows]

    def upsert_contact(self, c: Contact) -> None:
        """Upsert contact."""
        self.conn.execute(
            """
            INSERT INTO contacts (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (c.id, json.dumps(c.model_dump(mode="json"))),
        )
        self.conn.commit()

    def upsert_linkedin_post_match(self, match: LinkedInPostMatch) -> None:
        """Upsert linkedin post match."""
        self.conn.execute(
            """INSERT INTO linkedin_post_matches (id, job_id, data) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET job_id = excluded.job_id, data = excluded.data""",
            (match.id, match.job_id, json.dumps(match.model_dump(mode="json"))),
        )
        self.conn.commit()

    def list_linkedin_post_matches(self, job_id: str | None = None) -> list[LinkedInPostMatch]:
        """List linkedin post matches."""
        if job_id:
            rows = self.conn.execute(
                "SELECT data FROM linkedin_post_matches WHERE job_id = ?", (job_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM linkedin_post_matches").fetchall()
        return [LinkedInPostMatch.model_validate(json.loads(row["data"])) for row in rows]

    def incr_action(self, kind: str, day: str) -> int:
        """Incr action."""
        self.conn.execute(
            """
            INSERT INTO action_counts (kind, day, n)
            VALUES (?, ?, 1)
            ON CONFLICT(kind, day) DO UPDATE SET n = n + 1
            """,
            (kind, day),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT n FROM action_counts WHERE kind = ? AND day = ?", (kind, day)
        ).fetchone()
        return int(row["n"])

    def count_actions(self, kind: str, day: str) -> int:
        """Count actions."""
        row = self.conn.execute(
            "SELECT n FROM action_counts WHERE kind = ? AND day = ?", (kind, day)
        ).fetchone()
        return int(row["n"]) if row else 0
